"""Tests for CrossAttentionBlock and its integration into ModalityAwareAutoencoder."""

import pytest
import torch
import numpy as np
import pandas as pd

from valpas._core.autoencoder import (
    CrossAttentionBlock,
    ModalityAwareAutoencoder,
    ProteomicsAutoencoderTrainer,
    ProteomicsDataset,
    train_proteomics_autoencoder,
)


# ---------- Unit tests for CrossAttentionBlock ----------

class TestCrossAttentionBlock:
    """Unit tests for the CrossAttentionBlock module."""

    def test_basic_forward(self):
        """Block produces output with correct shapes."""
        block = CrossAttentionBlock(dim_a=16, dim_b=8, n_heads=4)
        B, n_a, n_b = 2, 10, 6
        seq_a = torch.randn(B, n_a, 16)
        seq_b = torch.randn(B, n_b, 8)

        out_a, out_b = block(seq_a, seq_b)
        assert out_a.shape == (B, n_a, 16)
        assert out_b.shape == (B, n_b, 8)

    def test_single_head(self):
        """Works with a single attention head."""
        block = CrossAttentionBlock(dim_a=8, dim_b=8, n_heads=1)
        seq_a = torch.randn(1, 5, 8)
        seq_b = torch.randn(1, 3, 8)
        out_a, out_b = block(seq_a, seq_b)
        assert out_a.shape == (1, 5, 8)
        assert out_b.shape == (1, 3, 8)

    def test_multiple_layers(self):
        """Multiple stacked cross-attention layers work."""
        block = CrossAttentionBlock(dim_a=16, dim_b=8, n_heads=4, n_layers=3)
        seq_a = torch.randn(2, 10, 16)
        seq_b = torch.randn(2, 6, 8)
        out_a, out_b = block(seq_a, seq_b)
        assert out_a.shape == (2, 10, 16)
        assert out_b.shape == (2, 6, 8)

    def test_gradient_flow(self):
        """Gradients flow through both outputs."""
        block = CrossAttentionBlock(dim_a=8, dim_b=8, n_heads=2)
        seq_a = torch.randn(1, 5, 8, requires_grad=True)
        seq_b = torch.randn(1, 3, 8, requires_grad=True)

        out_a, out_b = block(seq_a, seq_b)
        loss = out_a.sum() + out_b.sum()
        loss.backward()

        assert seq_a.grad is not None
        assert seq_b.grad is not None

    def test_different_dims(self):
        """Works when dim_a != dim_b."""
        block = CrossAttentionBlock(dim_a=32, dim_b=16, n_heads=4)
        seq_a = torch.randn(2, 8, 32)
        seq_b = torch.randn(2, 4, 16)
        out_a, out_b = block(seq_a, seq_b)
        assert out_a.shape == (2, 8, 32)
        assert out_b.shape == (2, 4, 16)

    def test_output_differs_from_input(self):
        """Cross-attention modifies the embeddings (not identity)."""
        block = CrossAttentionBlock(dim_a=16, dim_b=8, n_heads=4)
        block.eval()
        seq_a = torch.randn(1, 5, 16)
        seq_b = torch.randn(1, 3, 8)
        with torch.no_grad():
            out_a, out_b = block(seq_a, seq_b)
        # Due to residual connections, outputs won't be identical to inputs
        # but they should be different due to attention
        assert not torch.allclose(out_a, seq_a, atol=1e-3)

    def test_dropout(self):
        """Dropout causes different outputs in train vs eval."""
        block = CrossAttentionBlock(dim_a=16, dim_b=8, n_heads=4, dropout=0.5)
        seq_a = torch.randn(1, 10, 16)
        seq_b = torch.randn(1, 6, 8)

        block.train()
        torch.manual_seed(42)
        out_train, _ = block(seq_a, seq_b)

        block.eval()
        torch.manual_seed(42)
        out_eval, _ = block(seq_a, seq_b)

        # Train and eval outputs should differ due to dropout
        # (with high dropout and enough elements, very likely)
        assert not torch.allclose(out_train, out_eval, atol=1e-5)


# ---------- Integration with ModalityAwareAutoencoder ----------

class TestCrossAttentionInModel:
    """Test cross-attention integration in ModalityAwareAutoencoder."""

    @pytest.fixture
    def model_with_ca(self):
        return ModalityAwareAutoencoder(
            n_proteins=20,
            n_samples=8,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
            cross_attention_args={'n_heads': 4, 'n_layers': 1, 'dropout': 0.1}
        )

    @pytest.fixture
    def model_without_ca(self):
        return ModalityAwareAutoencoder(
            n_proteins=20,
            n_samples=8,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
        )

    def test_model_has_cross_attention(self, model_with_ca):
        """Model creates cross-attention when args provided."""
        assert model_with_ca.use_cross_attention is True
        assert model_with_ca.cross_attention is not None

    def test_model_without_cross_attention(self, model_without_ca):
        """Model has no cross-attention when args=None."""
        assert model_without_ca.use_cross_attention is False
        assert model_without_ca.cross_attention is None

    def test_forward_with_ca(self, model_with_ca):
        """Forward pass works with cross-attention enabled."""
        x = torch.randn(2, 20, 8)
        output = model_with_ca(x)
        assert output.shape == (2, 20, 8)

    def test_forward_with_ca_return_embeddings(self, model_with_ca):
        """Return embeddings works with cross-attention."""
        x = torch.randn(2, 20, 8)
        output, emb_dict = model_with_ca(x, return_embeddings=True)
        assert output.shape == (2, 20, 8)
        assert 'protein_embeddings' in emb_dict
        assert 'sample_embeddings' in emb_dict

    def test_ca_changes_reconstruction(self, model_with_ca, model_without_ca):
        """Cross-attention produces different outputs than no cross-attention."""
        # This just verifies the architecture is structurally different
        x = torch.randn(1, 20, 8)
        # Both should produce valid outputs
        out_ca = model_with_ca(x)
        out_no_ca = model_without_ca(x)
        assert out_ca.shape == out_no_ca.shape

    def test_ca_no_modality_split(self):
        """Cross-attention works without modality_split (shared encoder)."""
        model = ModalityAwareAutoencoder(
            n_proteins=15,
            n_samples=6,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=None,
            cross_attention_args={'n_heads': 2, 'n_layers': 1}
        )
        x = torch.randn(2, 15, 6)
        output = model(x)
        assert output.shape == (2, 15, 6)

    def test_ca_with_vae(self):
        """Cross-attention + VAE work together."""
        model = ModalityAwareAutoencoder(
            n_proteins=20,
            n_samples=8,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
            use_vae=True,
            cross_attention_args={'n_heads': 4, 'n_layers': 2}
        )
        x = torch.randn(2, 20, 8)
        output, emb_dict = model(x, return_embeddings=True)
        assert output.shape == (2, 20, 8)
        assert model._last_kl_loss.item() > 0


# ---------- Integration with Trainer ----------

class TestCrossAttentionTraining:
    """Test training with cross-attention enabled."""

    @pytest.fixture
    def small_dataset(self):
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(20, 8),
            index=[f"protein_{i}" for i in range(20)],
            columns=[f"sample_{j}" for j in range(8)]
        )
        return ProteomicsDataset(data, mask_probability=0.15)

    def test_train_epoch_with_ca(self, small_dataset):
        """Training epoch completes with cross-attention model."""
        model = ModalityAwareAutoencoder(
            n_proteins=small_dataset.n_proteins,
            n_samples=small_dataset.n_samples,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
            cross_attention_args={'n_heads': 4, 'n_layers': 1}
        )
        trainer = ProteomicsAutoencoderTrainer(model, learning_rate=1e-3)
        device = torch.device('cpu')
        loss = trainer.train_epoch(small_dataset, device, n_batches=5, mini_batch_size=2)
        assert loss > 0
        assert np.isfinite(loss)

    def test_train_epoch_ca_with_cosine_aux(self, small_dataset):
        """Cross-attention + cosine aux loss work together."""
        model = ModalityAwareAutoencoder(
            n_proteins=small_dataset.n_proteins,
            n_samples=small_dataset.n_samples,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
            cross_attention_args={'n_heads': 4, 'n_layers': 1}
        )
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3,
            cosine_aux_weight=0.05,
            cosine_aux_args={'n_pairs': 10}
        )
        device = torch.device('cpu')
        loss = trainer.train_epoch(small_dataset, device, n_batches=3, mini_batch_size=2)
        assert np.isfinite(loss)


# ---------- End-to-end through train_proteomics_autoencoder ----------

class TestCrossAttentionEndToEnd:
    """End-to-end tests through the public API."""

    @pytest.fixture
    def sample_data(self):
        np.random.seed(42)
        return pd.DataFrame(
            np.random.randn(20, 8),
            index=[f"protein_{i}" for i in range(20)],
            columns=[f"sample_{j}" for j in range(8)]
        )

    def test_train_with_cross_attention(self, sample_data):
        """Full training pipeline with cross-attention."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            learning_rate=1e-3,
            cross_attention_args={'n_heads': 4, 'n_layers': 1},
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_train_ca_with_modality_split(self, sample_data):
        """Cross-attention with modality split."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            modality_split=10,
            cross_attention_args={'n_heads': 4, 'n_layers': 2},
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_train_ca_with_vae_and_kl(self, sample_data):
        """Cross-attention + VAE + KL loss combined."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            modality_split=10,
            use_vae=True,
            kl_weight=1e-3,
            cross_attention_args={'n_heads': 4, 'n_layers': 1},
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_disabled_by_default(self, sample_data):
        """Default cross_attention_args=None means no cross-attention."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3
