"""Tests for CosineEmbeddingAuxLoss and its integration into training."""

import pytest
import torch
import torch.nn.functional as F
import numpy as np
import pandas as pd

from valpas._core.autoencoder import (
    CosineEmbeddingAuxLoss,
    ProteomicsAutoencoderTrainer,
    ProteomicsDataset,
    BiDirectionalAutoencoder,
    ModalityAwareAutoencoder,
    train_proteomics_autoencoder,
)


# ---------- Unit tests for CosineEmbeddingAuxLoss ----------

class TestCosineEmbeddingAuxLoss:
    """Unit tests for the CosineEmbeddingAuxLoss module."""

    def test_basic_forward(self):
        """Loss computes a scalar value without error."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=8)
        B, n_proteins, emb_dim, n_samples = 2, 20, 16, 10
        embeddings = torch.randn(B, n_proteins, emb_dim)
        data = torch.randn(B, n_proteins, n_samples)
        loss = loss_fn(embeddings, data)
        assert loss.shape == ()
        assert loss.item() >= 0  # MSE is non-negative

    def test_identical_geometry_gives_low_loss(self):
        """When embeddings preserve data-space similarity, loss should be low."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=10, temperature=1.0)
        B, n_proteins, n_samples = 1, 10, 8

        # Create data where each protein row is distinct
        data = torch.randn(B, n_proteins, n_samples)

        # Build embeddings that have the SAME cosine similarity structure
        # by using the data rows themselves as embeddings
        embeddings = data.clone()  # [B, n_proteins, n_samples] — same dim works

        loss = loss_fn(embeddings, data)
        # Should be very close to 0 since sim matrices are identical
        assert loss.item() < 1e-5

    def test_random_embeddings_higher_loss(self):
        """Random embeddings should give higher loss than aligned ones."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=10)
        B, n_proteins, n_samples = 1, 10, 8

        data = torch.randn(B, n_proteins, n_samples)
        # Aligned embeddings (same structure)
        aligned_emb = data.clone()
        # Random embeddings (different structure)
        random_emb = torch.randn(B, n_proteins, 16)

        loss_aligned = loss_fn(aligned_emb, data)
        loss_random = loss_fn(random_emb, data)

        # Random should generally give higher loss
        # (not guaranteed for every seed, but very likely)
        assert loss_aligned.item() < loss_random.item()

    def test_temperature_sharpening(self):
        """Lower temperature should sharpen the target similarities."""
        B, n_proteins, n_samples = 1, 10, 8
        data = torch.randn(B, n_proteins, n_samples)
        embeddings = torch.randn(B, n_proteins, 16)

        loss_t1 = CosineEmbeddingAuxLoss(n_pairs=10, temperature=1.0)
        loss_t05 = CosineEmbeddingAuxLoss(n_pairs=10, temperature=0.5)

        val_t1 = loss_t1(embeddings, data)
        val_t05 = loss_t05(embeddings, data)

        # Different temperatures should produce different loss values
        assert val_t1.item() != val_t05.item()

    def test_n_pairs_capped_at_n_proteins(self):
        """n_pairs should be capped at n_proteins without error."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=100)  # More than n_proteins
        B, n_proteins, emb_dim, n_samples = 2, 10, 8, 6
        embeddings = torch.randn(B, n_proteins, emb_dim)
        data = torch.randn(B, n_proteins, n_samples)
        loss = loss_fn(embeddings, data)
        assert loss.shape == ()

    def test_detach_targets(self):
        """When detach_targets=True, data-space sims don't receive gradient."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=5, detach_targets=True)
        B, n_proteins, emb_dim, n_samples = 1, 8, 4, 6
        embeddings = torch.randn(B, n_proteins, emb_dim, requires_grad=True)
        data = torch.randn(B, n_proteins, n_samples, requires_grad=True)

        loss = loss_fn(embeddings, data)
        loss.backward()

        # Embeddings should have gradients
        assert embeddings.grad is not None
        # Data should NOT have gradients (targets detached)
        assert data.grad is None

    def test_detach_targets_false(self):
        """When detach_targets=False, data tensor gets gradients too."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=5, detach_targets=False)
        B, n_proteins, emb_dim, n_samples = 1, 8, 4, 6
        embeddings = torch.randn(B, n_proteins, emb_dim, requires_grad=True)
        data = torch.randn(B, n_proteins, n_samples, requires_grad=True)

        loss = loss_fn(embeddings, data)
        loss.backward()

        assert embeddings.grad is not None
        assert data.grad is not None

    def test_batch_dimension(self):
        """Loss works correctly with multiple batch elements."""
        loss_fn = CosineEmbeddingAuxLoss(n_pairs=5)
        B, n_proteins, emb_dim, n_samples = 4, 12, 8, 6
        embeddings = torch.randn(B, n_proteins, emb_dim)
        data = torch.randn(B, n_proteins, n_samples)
        loss = loss_fn(embeddings, data)
        assert loss.shape == ()
        assert torch.isfinite(loss)


# ---------- Integration with Trainer ----------

class TestCosineAuxInTrainer:
    """Test cosine aux loss integration in ProteomicsAutoencoderTrainer."""

    @pytest.fixture
    def small_dataset(self):
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(20, 8),
            index=[f"protein_{i}" for i in range(20)],
            columns=[f"sample_{j}" for j in range(8)]
        )
        return ProteomicsDataset(data, mask_probability=0.15)

    @pytest.fixture
    def small_model(self, small_dataset):
        return BiDirectionalAutoencoder(
            n_proteins=small_dataset.n_proteins,
            n_samples=small_dataset.n_samples,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16]
        )

    def test_trainer_with_cosine_aux(self, small_model, small_dataset):
        """Trainer initializes and trains with cosine_aux_weight > 0."""
        trainer = ProteomicsAutoencoderTrainer(
            small_model,
            learning_rate=1e-3,
            cosine_aux_weight=0.05,
            cosine_aux_args={'n_pairs': 10, 'temperature': 1.0}
        )
        assert trainer.cosine_aux_loss is not None
        assert trainer.cosine_aux_weight == 0.05

        device = torch.device('cpu')
        loss = trainer.train_epoch(small_dataset, device, n_batches=5, mini_batch_size=2)
        assert loss > 0
        assert np.isfinite(loss)

    def test_trainer_without_cosine_aux(self, small_model, small_dataset):
        """Trainer works normally when cosine_aux_weight=0."""
        trainer = ProteomicsAutoencoderTrainer(
            small_model,
            learning_rate=1e-3,
            cosine_aux_weight=0.0,
        )
        assert trainer.cosine_aux_loss is None

        device = torch.device('cpu')
        loss = trainer.train_epoch(small_dataset, device, n_batches=5, mini_batch_size=2)
        assert loss > 0

    def test_cosine_aux_adds_to_loss(self, small_model, small_dataset):
        """Cosine aux loss should increase total loss compared to no aux."""
        device = torch.device('cpu')

        # Train one epoch without cosine aux
        torch.manual_seed(123)
        trainer_no_aux = ProteomicsAutoencoderTrainer(
            small_model, learning_rate=0.0, cosine_aux_weight=0.0
        )
        loss_no_aux = trainer_no_aux.train_epoch(small_dataset, device, n_batches=3, mini_batch_size=1)

        # Train one epoch with cosine aux (same model state, lr=0 so no update)
        torch.manual_seed(123)
        trainer_aux = ProteomicsAutoencoderTrainer(
            small_model, learning_rate=0.0, cosine_aux_weight=1.0,
            cosine_aux_args={'n_pairs': 10}
        )
        loss_aux = trainer_aux.train_epoch(small_dataset, device, n_batches=3, mini_batch_size=1)

        # With aux loss, total should be higher (or equal if aux is 0)
        assert loss_aux >= loss_no_aux

    def test_cosine_aux_with_modality_aware(self, small_dataset):
        """Cosine aux works with ModalityAwareAutoencoder."""
        model = ModalityAwareAutoencoder(
            n_proteins=small_dataset.n_proteins,
            n_samples=small_dataset.n_samples,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            modality_split=10,
        )
        trainer = ProteomicsAutoencoderTrainer(
            model,
            learning_rate=1e-3,
            cosine_aux_weight=0.05,
            cosine_aux_args={'n_pairs': 8}
        )
        device = torch.device('cpu')
        loss = trainer.train_epoch(small_dataset, device, n_batches=3, mini_batch_size=2)
        assert np.isfinite(loss)

    def test_cosine_aux_default_args(self, small_model, small_dataset):
        """Default args (None) should use sensible defaults."""
        trainer = ProteomicsAutoencoderTrainer(
            small_model,
            learning_rate=1e-3,
            cosine_aux_weight=0.1,
            cosine_aux_args=None  # Should use defaults
        )
        assert trainer.cosine_aux_loss is not None
        assert trainer.cosine_aux_loss.n_pairs == 64
        assert trainer.cosine_aux_loss.temperature == 1.0
        assert trainer.cosine_aux_loss.detach_targets is True


# ---------- Integration with train_proteomics_autoencoder ----------

class TestCosineAuxEndToEnd:
    """End-to-end tests through the train_proteomics_autoencoder API."""

    @pytest.fixture
    def sample_data(self):
        np.random.seed(42)
        return pd.DataFrame(
            np.random.randn(20, 8),
            index=[f"protein_{i}" for i in range(20)],
            columns=[f"sample_{j}" for j in range(8)]
        )

    def test_train_with_cosine_aux(self, sample_data):
        """Full training pipeline with cosine aux loss enabled."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            learning_rate=1e-3,
            cosine_aux_weight=0.05,
            cosine_aux_args={'n_pairs': 10},
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 5

    def test_train_cosine_aux_with_vae(self, sample_data):
        """Cosine aux + VAE work together."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            learning_rate=1e-3,
            modality_split=10,
            use_vae=True,
            kl_weight=1e-3,
            cosine_aux_weight=0.05,
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_train_cosine_aux_disabled_by_default(self, sample_data):
        """Default cosine_aux_weight=0 means no cosine loss."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            early_stopping_patience=0,
        )
        assert len(results.training_history["train_losses"]) == 3
