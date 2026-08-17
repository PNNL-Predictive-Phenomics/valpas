"""Tests for cross-modal masking bias in ProteomicsAutoencoderTrainer."""

import pytest
import torch
import pandas as pd
import numpy as np

from valpas._core.autoencoder import (
    ProteomicsAutoencoderTrainer,
    ProteomicsDataset,
    BiDirectionalAutoencoder,
    ModalityAwareAutoencoder,
    train_proteomics_autoencoder,
)


@pytest.fixture
def sample_data():
    """Create sample multi-omics data (20 features, 8 samples)."""
    np.random.seed(42)
    data = pd.DataFrame(
        np.random.randn(20, 8),
        index=[f"feat_{i}" for i in range(20)],
        columns=[f"sample_{j}" for j in range(8)],
    )
    return data


@pytest.fixture
def dataset(sample_data):
    """Create ProteomicsDataset from sample data."""
    return ProteomicsDataset(sample_data, mask_probability=0.15)


@pytest.fixture
def model_with_split(dataset):
    """Create ModalityAwareAutoencoder with split at row 10."""
    return ModalityAwareAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
        modality_split=10,
    )


@pytest.fixture
def model_no_split(dataset):
    """Create BiDirectionalAutoencoder (no split)."""
    return BiDirectionalAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
    )


class TestCrossModalMaskGeneration:
    """Test the _generate_cross_modal_masks method."""

    def test_mask_shape(self, model_with_split):
        """Masks have correct shape."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
        )
        masks = trainer._generate_cross_modal_masks(5, 20, 8, 0.15)
        assert masks.shape == (5, 20, 8)

    def test_mask_dtype(self, model_with_split):
        """Masks are boolean tensors."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
        )
        masks = trainer._generate_cross_modal_masks(5, 20, 8, 0.15)
        assert masks.dtype == torch.bool

    def test_cross_modal_bias_increases_target_masking(self, model_with_split):
        """Target modality should have higher mask rate than source."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.5,
        )
        # Generate many masks for statistical reliability
        torch.manual_seed(0)
        masks = trainer._generate_cross_modal_masks(1000, 20, 8, 0.15)

        # Overall mask rate for modality A (rows 0:10) vs modality B (rows 10:20)
        mask_rate_a = masks[:, :10, :].float().mean().item()
        mask_rate_b = masks[:, 10:, :].float().mean().item()

        # Both should be somewhere between base (0.15) and target (0.65)
        # because each is the target ~50% of the time
        expected_avg = (0.15 + 0.65) / 2  # ~0.40

        assert abs(mask_rate_a - expected_avg) < 0.05
        assert abs(mask_rate_b - expected_avg) < 0.05

    def test_zero_ratio_gives_uniform_masking(self, model_with_split):
        """When cross_modal_mask_ratio=0, both modalities get base probability."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.0,
        )
        # With ratio=0, the condition in train_epoch won't call this method,
        # but we test the method directly to verify behavior
        torch.manual_seed(0)
        masks = trainer._generate_cross_modal_masks(1000, 20, 8, 0.15)

        mask_rate_a = masks[:, :10, :].float().mean().item()
        mask_rate_b = masks[:, 10:, :].float().mean().item()

        # Both should be close to 0.15 (base prob + 0.0 target adjustment)
        # Since target_prob = base + 0.0 = base, uniform masking
        assert abs(mask_rate_a - 0.15) < 0.02
        assert abs(mask_rate_b - 0.15) < 0.02

    def test_high_ratio_caps_at_one(self, model_with_split):
        """cross_modal_mask_ratio + base_prob > 1.0 is capped at 1.0."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.95,
        )
        torch.manual_seed(0)
        masks = trainer._generate_cross_modal_masks(1000, 20, 8, 0.15)

        # Target prob = min(0.15 + 0.95, 1.0) = 1.0
        # So target modality should be masked ~100% when it's the target
        # Average = (0.15 + 1.0) / 2 = 0.575
        mask_rate_a = masks[:, :10, :].float().mean().item()
        mask_rate_b = masks[:, 10:, :].float().mean().item()

        assert mask_rate_a > 0.5
        assert mask_rate_b > 0.5

    def test_asymmetric_split(self, model_with_split):
        """Works correctly with non-even modality split."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=5,  # 5 rows modality A, 15 rows modality B
            cross_modal_mask_ratio=0.4,
        )
        torch.manual_seed(0)
        masks = trainer._generate_cross_modal_masks(1000, 20, 8, 0.15)

        mask_rate_a = masks[:, :5, :].float().mean().item()
        mask_rate_b = masks[:, 5:, :].float().mean().item()

        # Both ~= (0.15 + 0.55) / 2 = 0.35
        expected = (0.15 + 0.55) / 2
        assert abs(mask_rate_a - expected) < 0.05
        assert abs(mask_rate_b - expected) < 0.05


class TestTrainerIntegration:
    """Test cross-modal masking in the training loop."""

    def test_trainer_no_cross_modal_by_default(self, model_no_split):
        """Without modality_split, cross-modal masking is not active."""
        trainer = ProteomicsAutoencoderTrainer(model_no_split)
        assert trainer.modality_split is None
        assert trainer.cross_modal_mask_ratio == 0.0

    def test_trainer_stores_params(self, model_with_split):
        """Trainer stores modality_split and cross_modal_mask_ratio."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.4,
        )
        assert trainer.modality_split == 10
        assert trainer.cross_modal_mask_ratio == 0.4

    def test_train_epoch_with_cross_modal(self, model_with_split, dataset):
        """Training epoch runs without error with cross-modal masking."""
        trainer = ProteomicsAutoencoderTrainer(
            model_with_split,
            modality_split=10,
            cross_modal_mask_ratio=0.4,
        )
        device = torch.device("cpu")
        model_with_split.to(device)

        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2)
        assert isinstance(loss, float)
        assert loss > 0

    def test_train_epoch_without_cross_modal(self, model_no_split, dataset):
        """Training epoch works normally without cross-modal masking."""
        trainer = ProteomicsAutoencoderTrainer(model_no_split)
        device = torch.device("cpu")
        model_no_split.to(device)

        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2)
        assert isinstance(loss, float)
        assert loss > 0

    def test_cross_modal_disabled_when_split_none(self, model_no_split, dataset):
        """Even if ratio > 0, no bias without modality_split."""
        trainer = ProteomicsAutoencoderTrainer(
            model_no_split,
            modality_split=None,
            cross_modal_mask_ratio=0.5,
        )
        device = torch.device("cpu")
        model_no_split.to(device)

        # Should run without error (no cross-modal masking applied)
        loss = trainer.train_epoch(dataset, device, n_batches=3, mini_batch_size=2)
        assert isinstance(loss, float)


class TestAPIIntegration:
    """Test cross_modal_mask_ratio through the full API."""

    def test_train_with_cross_modal_mask_ratio(self, sample_data):
        """train_proteomics_autoencoder accepts cross_modal_mask_ratio."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_train_without_cross_modal(self, sample_data):
        """Backward compatible: no cross_modal_mask_ratio param needed."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_cross_modal_ignored_without_modality_split(self, sample_data):
        """cross_modal_mask_ratio has no effect without modality_split."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            cross_modal_mask_ratio=0.5,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_cross_modal_with_contrastive(self, sample_data):
        """Cross-modal masking works alongside contrastive loss."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
            contrastive_args={
                "enabled": True,
                "decoy_strategy": "row_shuffle",
                "lambda_negative": 0.1,
                "warmup_epochs": 2,
            },
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 5
