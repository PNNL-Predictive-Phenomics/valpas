"""Tests for VAE KL loss and embedding norm regularization in trainer."""

import pytest
import torch
import pandas as pd
import numpy as np

from valpas._core.autoencoder import (
    ProteomicsAutoencoderTrainer,
    ProteomicsDataset,
    ModalityAwareAutoencoder,
    BiDirectionalAutoencoder,
    train_proteomics_autoencoder,
)


@pytest.fixture
def sample_data():
    """Create sample multi-omics data (20 features, 8 samples)."""
    np.random.seed(42)
    return pd.DataFrame(
        np.random.randn(20, 8),
        index=[f"feat_{i}" for i in range(20)],
        columns=[f"sample_{j}" for j in range(8)],
    )


@pytest.fixture
def dataset(sample_data):
    return ProteomicsDataset(sample_data, mask_probability=0.15)


@pytest.fixture
def vae_model(dataset):
    """ModalityAwareAutoencoder with VAE enabled."""
    return ModalityAwareAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
        modality_split=10,
        use_vae=True,
    )


@pytest.fixture
def non_vae_model(dataset):
    """ModalityAwareAutoencoder without VAE."""
    return ModalityAwareAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
        modality_split=10,
        use_vae=False,
    )


@pytest.fixture
def basic_model(dataset):
    """BiDirectionalAutoencoder (no VAE support)."""
    return BiDirectionalAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
    )


class TestVAEKLLoss:
    """Test VAE KL divergence loss integration in trainer."""

    def test_vae_model_produces_kl_loss(self, vae_model, dataset):
        """VAE model computes _last_kl_loss during forward pass."""
        device = torch.device("cpu")
        vae_model.to(device)
        vae_model.train()

        x = dataset.data_tensor.unsqueeze(0).to(device)
        _ = vae_model(x)

        assert hasattr(vae_model, '_last_kl_loss')
        assert vae_model._last_kl_loss.item() > 0

    def test_non_vae_model_kl_is_zero(self, non_vae_model, dataset):
        """Non-VAE model has zero KL loss."""
        device = torch.device("cpu")
        non_vae_model.to(device)
        non_vae_model.train()

        x = dataset.data_tensor.unsqueeze(0).to(device)
        _ = non_vae_model(x)

        assert non_vae_model._last_kl_loss.item() == 0.0

    def test_trainer_kl_weight_stored(self, vae_model):
        """Trainer stores kl_weight parameter."""
        trainer = ProteomicsAutoencoderTrainer(
            vae_model, kl_weight=0.01
        )
        assert trainer.kl_weight == 0.01

    def test_trainer_kl_increases_loss(self, vae_model, dataset):
        """KL loss increases total training loss compared to kl_weight=0."""
        device = torch.device("cpu")
        vae_model.to(device)

        # Train with KL
        torch.manual_seed(0)
        trainer_with_kl = ProteomicsAutoencoderTrainer(
            vae_model, kl_weight=1.0, learning_rate=0.0  # lr=0 so no param updates
        )
        loss_with_kl = trainer_with_kl.train_epoch(dataset, device, n_batches=3, mini_batch_size=3)

        # Train without KL (reset model)
        torch.manual_seed(0)
        trainer_no_kl = ProteomicsAutoencoderTrainer(
            vae_model, kl_weight=0.0, learning_rate=0.0
        )
        loss_no_kl = trainer_no_kl.train_epoch(dataset, device, n_batches=3, mini_batch_size=3)

        assert loss_with_kl > loss_no_kl

    def test_train_epoch_with_vae(self, vae_model, dataset):
        """Training epoch completes successfully with VAE KL loss."""
        device = torch.device("cpu")
        vae_model.to(device)

        trainer = ProteomicsAutoencoderTrainer(
            vae_model, kl_weight=1e-3
        )
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2)
        assert isinstance(loss, float)
        assert loss > 0


class TestEmbeddingNormRegularization:
    """Test embedding norm regularization in trainer."""

    def test_norm_reg_weight_stored(self, vae_model):
        """Trainer stores norm_reg_weight."""
        trainer = ProteomicsAutoencoderTrainer(
            vae_model, norm_reg_weight=0.1
        )
        assert trainer.norm_reg_weight == 0.1

    def test_norm_reg_disabled_by_default(self, basic_model):
        """Norm reg weight is 0 by default."""
        trainer = ProteomicsAutoencoderTrainer(basic_model)
        assert trainer.norm_reg_weight == 0.0

    def test_get_embedding_norm_loss(self, vae_model, dataset):
        """Model computes embedding norm loss correctly."""
        device = torch.device("cpu")
        vae_model.to(device)

        x = dataset.data_tensor.unsqueeze(0).to(device)
        _, emb_dict = vae_model(x, return_embeddings=True)

        norm_loss = vae_model.get_embedding_norm_loss(emb_dict['protein_embeddings'])
        assert norm_loss.item() >= 0
        assert norm_loss.requires_grad

    def test_norm_reg_increases_loss(self, non_vae_model, dataset):
        """Norm reg adds to total loss when weight > 0."""
        device = torch.device("cpu")
        non_vae_model.to(device)

        # With norm reg
        torch.manual_seed(0)
        trainer_with = ProteomicsAutoencoderTrainer(
            non_vae_model, norm_reg_weight=10.0, learning_rate=0.0
        )
        loss_with = trainer_with.train_epoch(dataset, device, n_batches=3, mini_batch_size=3)

        # Without norm reg
        torch.manual_seed(0)
        trainer_without = ProteomicsAutoencoderTrainer(
            non_vae_model, norm_reg_weight=0.0, learning_rate=0.0
        )
        loss_without = trainer_without.train_epoch(dataset, device, n_batches=3, mini_batch_size=3)

        assert loss_with > loss_without

    def test_train_epoch_with_norm_reg(self, non_vae_model, dataset):
        """Training epoch completes with norm regularization."""
        device = torch.device("cpu")
        non_vae_model.to(device)

        trainer = ProteomicsAutoencoderTrainer(
            non_vae_model, norm_reg_weight=0.01
        )
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2)
        assert isinstance(loss, float)
        assert loss > 0

    def test_norm_reg_with_basic_model(self, basic_model, dataset):
        """Norm reg is silently skipped for models without get_embedding_norm_loss."""
        device = torch.device("cpu")
        basic_model.to(device)

        trainer = ProteomicsAutoencoderTrainer(
            basic_model, norm_reg_weight=0.1
        )
        # Should not raise - the model doesn't have get_embedding_norm_loss
        # but it also doesn't support return_embeddings the same way
        # Actually BiDirectionalAutoencoder does support return_embeddings
        loss = trainer.train_epoch(dataset, device, n_batches=3, mini_batch_size=2)
        assert isinstance(loss, float)


class TestCombinedLosses:
    """Test combining VAE KL + norm reg + contrastive."""

    def test_all_losses_combined(self, vae_model, dataset):
        """Training works with all loss components active."""
        device = torch.device("cpu")
        vae_model.to(device)

        trainer = ProteomicsAutoencoderTrainer(
            vae_model,
            kl_weight=1e-3,
            norm_reg_weight=0.01,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
            contrastive_args={
                "enabled": True,
                "decoy_strategy": "row_shuffle",
                "lambda_negative": 0.1,
                "warmup_epochs": 0,
            },
        )
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2, epoch=5)
        assert isinstance(loss, float)
        assert loss > 0

    def test_api_vae_with_kl_and_norm(self, sample_data):
        """Full API with VAE + KL + norm reg."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            modality_split=10,
            use_vae=True,
            kl_weight=1e-3,
            norm_reg_weight=0.01,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_api_norm_reg_without_vae(self, sample_data):
        """Norm reg works without VAE."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            modality_split=10,
            norm_reg_weight=0.05,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_api_backward_compatible(self, sample_data):
        """Default params (no VAE, no norm reg) still work."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3
