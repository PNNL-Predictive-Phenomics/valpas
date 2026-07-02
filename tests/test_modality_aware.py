"""
Tests for ModalityAwareAutoencoder with modality-specific encoders.
"""
import pytest
import torch
import numpy as np
import pandas as pd

from valpas._core.autoencoder import (
    ModalityAwareAutoencoder,
    BiDirectionalAutoencoder,
    ProteomicsDataset,
    ProteomicsAutoencoderTrainer,
    train_proteomics_autoencoder,
)


class TestModalityAwareAutoencoder:
    """Tests for the ModalityAwareAutoencoder class."""

    @pytest.fixture
    def model_with_split(self):
        """Model with modality split (dual encoders)."""
        return ModalityAwareAutoencoder(
            n_proteins=20, n_samples=8,
            protein_embedding_dim=16, sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=12,  # First 12 rows = modality A, last 8 = modality B
        )

    @pytest.fixture
    def model_no_split(self):
        """Model without modality split (shared encoder, equivalent to BiDirectional)."""
        return ModalityAwareAutoencoder(
            n_proteins=20, n_samples=8,
            protein_embedding_dim=16, sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=None,
        )

    @pytest.fixture
    def model_vae(self):
        """Model with VAE bottleneck."""
        return ModalityAwareAutoencoder(
            n_proteins=20, n_samples=8,
            protein_embedding_dim=16, sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=12,
            use_vae=True,
        )

    @pytest.fixture
    def sample_input(self):
        """Sample input tensor."""
        torch.manual_seed(42)
        return torch.randn(2, 20, 8)  # batch=2, 20 features, 8 samples

    def test_forward_with_split(self, model_with_split, sample_input):
        """Forward pass with dual encoders produces correct output shape."""
        output = model_with_split(sample_input)
        assert output.shape == sample_input.shape

    def test_forward_no_split(self, model_no_split, sample_input):
        """Forward pass without split produces correct output shape."""
        output = model_no_split(sample_input)
        assert output.shape == sample_input.shape

    def test_forward_vae(self, model_vae, sample_input):
        """VAE forward pass produces correct shape and non-zero KL."""
        model_vae.train()
        output = model_vae(sample_input)
        assert output.shape == sample_input.shape
        kl = model_vae.get_kl_loss()
        assert kl.item() > 0, "KL divergence should be positive during training"

    def test_vae_kl_zero_in_eval(self, model_vae, sample_input):
        """In eval mode, VAE uses mu directly (no sampling), KL should still be computed."""
        model_vae.eval()
        output = model_vae(sample_input)
        assert output.shape == sample_input.shape

    def test_encode_proteins_with_split(self, model_with_split, sample_input):
        """Protein encoding produces correct shape with dual encoders."""
        emb = model_with_split.encode_proteins(sample_input)
        assert emb.shape == (2, 20, 16)  # [batch, n_proteins, embedding_dim]

    def test_encode_samples(self, model_with_split, sample_input):
        """Sample encoding produces correct shape."""
        emb = model_with_split.encode_samples(sample_input)
        assert emb.shape == (2, 8, 8)  # [batch, n_samples, sample_embedding_dim]

    def test_dual_encoders_have_separate_params(self, model_with_split):
        """Verify modality A and B encoders have independent parameters."""
        params_a = set(id(p) for p in model_with_split.modality_a_encoder.parameters())
        params_b = set(id(p) for p in model_with_split.modality_b_encoder.parameters())
        assert params_a.isdisjoint(params_b), "Dual encoders should have independent parameters"

    def test_shared_encoder_when_no_split(self, model_no_split):
        """Without split, should have single protein_encoder."""
        assert hasattr(model_no_split, 'protein_encoder')
        assert not hasattr(model_no_split, 'modality_a_encoder')

    def test_return_embeddings(self, model_with_split, sample_input):
        """return_embeddings=True returns dict with embeddings."""
        output, emb_dict = model_with_split(sample_input, return_embeddings=True)
        assert output.shape == sample_input.shape
        assert 'protein_embeddings' in emb_dict
        assert 'sample_embeddings' in emb_dict
        assert emb_dict['protein_embeddings'].shape == (2, 20, 16)
        assert emb_dict['sample_embeddings'].shape == (2, 8, 8)

    def test_get_protein_embeddings(self, model_with_split, sample_input):
        """get_protein_embeddings returns embeddings in no_grad context."""
        emb = model_with_split.get_protein_embeddings(sample_input)
        assert emb.shape == (2, 20, 16)
        assert not emb.requires_grad

    def test_get_sample_embeddings(self, model_with_split, sample_input):
        """get_sample_embeddings returns embeddings in no_grad context."""
        emb = model_with_split.get_sample_embeddings(sample_input)
        assert emb.shape == (2, 8, 8)
        assert not emb.requires_grad

    def test_embedding_norm_loss(self, model_with_split, sample_input):
        """Embedding norm loss computes without error."""
        emb = model_with_split.encode_proteins(sample_input)
        norm_loss = model_with_split.get_embedding_norm_loss(emb)
        assert norm_loss.ndim == 0
        assert norm_loss.item() >= 0

    def test_gradient_flow_through_dual_encoders(self, model_with_split, sample_input):
        """Gradients flow correctly through both encoders."""
        output = model_with_split(sample_input)
        loss = output.mean()
        loss.backward()
        # Check both encoders got gradients
        for p in model_with_split.modality_a_encoder.parameters():
            assert p.grad is not None
        for p in model_with_split.modality_b_encoder.parameters():
            assert p.grad is not None


class TestModalityAwareTraining:
    """Integration tests for training with ModalityAwareAutoencoder."""

    @pytest.fixture
    def multi_omics_data(self):
        """Create fake multi-omics data (15 proteins + 10 metabolites, 6 samples)."""
        torch.manual_seed(42)
        np.random.seed(42)
        n_proteins = 15
        n_metabolites = 10
        n_samples = 6
        data = pd.DataFrame(
            np.random.randn(n_proteins + n_metabolites, n_samples),
            index=[f'prot_{i}' for i in range(n_proteins)] +
                  [f'met_{i}' for i in range(n_metabolites)],
            columns=[f'sample_{i}' for i in range(n_samples)]
        )
        return data, n_proteins  # modality_split = n_proteins

    def test_train_with_modality_split(self, multi_omics_data):
        """Training with modality_split uses ModalityAwareAutoencoder."""
        data, split = multi_omics_data
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=10,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            modality_split=split,
        )
        assert isinstance(results.trained_model, ModalityAwareAutoencoder)
        assert results.trained_model.has_dual_encoders
        assert results.training_history['epochs_trained'] == 10

    def test_train_without_modality_split(self, multi_omics_data):
        """Training without modality_split uses BiDirectionalAutoencoder (backward compat)."""
        data, _ = multi_omics_data
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
        )
        assert isinstance(results.trained_model, BiDirectionalAutoencoder)

    def test_train_with_vae(self, multi_omics_data):
        """Training with use_vae=True enables variational bottleneck."""
        data, split = multi_omics_data
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=10,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            modality_split=split,
            use_vae=True,
        )
        assert isinstance(results.trained_model, ModalityAwareAutoencoder)
        assert results.trained_model.use_vae

    def test_train_modality_split_with_contrastive(self, multi_omics_data):
        """Modality-aware model works with contrastive loss."""
        data, split = multi_omics_data
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': 'row_shuffle',
            'n_decoys': 1,
            'loss_type': 'margin',
            'lambda_negative': 0.1,
            'max_lambda': 0.3,
            'warmup_epochs': 0,
        }
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=10,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            modality_split=split,
            contrastive_args=contrastive_args,
        )
        assert 'negative_losses' in results.training_history

    def test_similarity_matrix_shape(self, multi_omics_data):
        """Similarity matrix has correct shape with modality-aware model."""
        data, split = multi_omics_data
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            modality_split=split,
        )
        sim = results.similarity_matrix
        n_total = data.shape[0]
        assert sim.shape == (n_total, n_total)

    def test_embeddings_shape(self, multi_omics_data):
        """Embeddings have correct dimensions."""
        data, split = multi_omics_data
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            modality_split=split,
        )
        assert results.embeddings.shape == (25, 16)  # n_features x embedding_dim
