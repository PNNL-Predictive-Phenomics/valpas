"""Tests for curriculum masking and row/feature-level masking."""

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
def model(dataset):
    return BiDirectionalAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
    )


class TestCurriculumMasking:
    """Test curriculum masking schedule."""

    def test_no_curriculum_uses_base_prob(self, model):
        """Without curriculum, _get_mask_probability returns base_prob."""
        trainer = ProteomicsAutoencoderTrainer(model)
        assert trainer.use_curriculum is False
        assert trainer._get_mask_probability(0, 0.15) == 0.15
        assert trainer._get_mask_probability(100, 0.15) == 0.15

    def test_curriculum_start_prob(self, model):
        """At epoch 0, curriculum returns start_prob."""
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.30, 'warmup_epochs': 50}
        )
        assert trainer.use_curriculum is True
        prob = trainer._get_mask_probability(0, 0.15)
        assert abs(prob - 0.05) < 1e-6

    def test_curriculum_end_prob(self, model):
        """At/after warmup_epochs, curriculum returns end_prob."""
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.30, 'warmup_epochs': 50}
        )
        prob = trainer._get_mask_probability(50, 0.15)
        assert abs(prob - 0.30) < 1e-6

        # Beyond warmup should still be end_prob
        prob = trainer._get_mask_probability(100, 0.15)
        assert abs(prob - 0.30) < 1e-6

    def test_curriculum_midpoint(self, model):
        """At half warmup, probability is midpoint between start and end."""
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.0, 'end_prob': 1.0, 'warmup_epochs': 100}
        )
        prob = trainer._get_mask_probability(50, 0.15)
        assert abs(prob - 0.5) < 1e-6

    def test_curriculum_training_epoch(self, model, dataset):
        """Training with curriculum masking completes successfully."""
        device = torch.device("cpu")
        model.to(device)
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.25, 'warmup_epochs': 10}
        )
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2, epoch=5)
        assert isinstance(loss, float)
        assert loss > 0

    def test_curriculum_ignores_base_prob(self, model, dataset):
        """When curriculum is active, base mask_probability is overridden."""
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.30, 'warmup_epochs': 50}
        )
        # base_prob argument is ignored when curriculum is active
        prob = trainer._get_mask_probability(25, base_prob=0.99)
        expected = 0.05 + (0.30 - 0.05) * (25 / 50)  # 0.175
        assert abs(prob - expected) < 1e-6


class TestRowMasking:
    """Test row/feature-level masking."""

    def test_row_mask_ratio_zero_no_change(self, model):
        """row_mask_ratio=0 returns masks unchanged."""
        trainer = ProteomicsAutoencoderTrainer(model, row_mask_ratio=0.0)
        torch.manual_seed(0)
        masks = torch.rand(5, 20, 8) < 0.15
        original = masks.clone()
        result = trainer._apply_row_masking(masks, 0.15)
        assert torch.equal(result, original)

    def test_row_mask_ratio_one_all_row_masked(self, model):
        """row_mask_ratio=1.0 applies row masking to all batch elements."""
        trainer = ProteomicsAutoencoderTrainer(model, row_mask_ratio=1.0)
        torch.manual_seed(0)
        masks = torch.zeros(10, 20, 8, dtype=torch.bool)
        result = trainer._apply_row_masking(masks, 0.15)

        # Each batch element should have some fully masked rows
        for i in range(10):
            # Check that at least one row is fully True
            fully_masked_rows = result[i].all(dim=1)  # [n_proteins]
            assert fully_masked_rows.any(), f"Batch {i} has no fully masked rows"

    def test_row_masking_creates_full_rows(self, model):
        """Row masking makes entire rows True (all columns)."""
        trainer = ProteomicsAutoencoderTrainer(model, row_mask_ratio=1.0)
        torch.manual_seed(42)
        masks = torch.zeros(5, 20, 8, dtype=torch.bool)
        result = trainer._apply_row_masking(masks, 0.3)

        # Find rows that got masked and verify they're fully masked
        for i in range(5):
            for row in range(20):
                if result[i, row, :].any():
                    # If any element in this row is True, all should be True
                    assert result[i, row, :].all()

    def test_row_mask_partial_batch(self, model):
        """row_mask_ratio < 1.0 only affects some batch elements."""
        trainer = ProteomicsAutoencoderTrainer(model, row_mask_ratio=0.5)
        torch.manual_seed(0)
        # Start with all-zero masks
        masks = torch.zeros(100, 20, 8, dtype=torch.bool)
        result = trainer._apply_row_masking(masks, 0.15)

        # Some batch elements should have row masks, some shouldn't
        has_masks = result.any(dim=(1, 2))  # [100]
        frac_masked = has_masks.float().mean().item()
        # Should be roughly 0.5 ± tolerance
        assert 0.3 < frac_masked < 0.7

    def test_row_masking_training_epoch(self, model, dataset):
        """Training with row masking completes successfully."""
        device = torch.device("cpu")
        model.to(device)
        trainer = ProteomicsAutoencoderTrainer(model, row_mask_ratio=0.3)
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2)
        assert isinstance(loss, float)
        assert loss > 0


class TestCombinedCurriculumAndRowMasking:
    """Test curriculum + row masking together."""

    def test_both_active(self, model, dataset):
        """Both curriculum and row masking can be active simultaneously."""
        device = torch.device("cpu")
        model.to(device)
        trainer = ProteomicsAutoencoderTrainer(
            model,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.25, 'warmup_epochs': 10},
            row_mask_ratio=0.2,
        )
        loss = trainer.train_epoch(dataset, device, n_batches=5, mini_batch_size=2, epoch=5)
        assert isinstance(loss, float)
        assert loss > 0


class TestAPIIntegration:
    """Test through train_proteomics_autoencoder."""

    def test_curriculum_masking_api(self, sample_data):
        """API accepts curriculum_masking parameter."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.20, 'warmup_epochs': 3},
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 5

    def test_row_mask_ratio_api(self, sample_data):
        """API accepts row_mask_ratio parameter."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            row_mask_ratio=0.2,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3

    def test_both_params_api(self, sample_data):
        """API accepts both curriculum and row masking together."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=5,
            curriculum_masking={'start_prob': 0.05, 'end_prob': 0.25, 'warmup_epochs': 3},
            row_mask_ratio=0.2,
            modality_split=10,
            cross_modal_mask_ratio=0.3,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 5

    def test_backward_compatible(self, sample_data):
        """Default params (no curriculum, no row masking) still work."""
        results = train_proteomics_autoencoder(
            sample_data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=3,
            device=torch.device("cpu"),
        )
        assert len(results.training_history["train_losses"]) == 3
