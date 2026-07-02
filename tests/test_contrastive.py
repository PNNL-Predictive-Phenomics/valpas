"""
Tests for negative contrastive loss with decoys.
"""
import pytest
import torch
import numpy as np
import pandas as pd

from valpas._core.autoencoder import (
    DecoyGenerator,
    NegativeContrastiveLoss,
    ProteomicsAutoencoderTrainer,
    ProteomicsDataset,
    BiDirectionalAutoencoder,
    train_proteomics_autoencoder,
)


# ============================================================
# DecoyGenerator Tests
# ============================================================

class TestDecoyGenerator:
    """Tests for DecoyGenerator class."""

    @pytest.fixture
    def sample_data(self):
        """Create sample tensor for testing."""
        torch.manual_seed(42)
        return torch.randn(1, 10, 5)  # batch=1, 10 proteins, 5 samples

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="strategy must be one of"):
            DecoyGenerator(strategy='invalid')

    @pytest.mark.parametrize("strategy", DecoyGenerator.STRATEGIES)
    def test_all_strategies_produce_correct_shape(self, strategy, sample_data):
        n_decoys = 3
        gen = DecoyGenerator(strategy=strategy, n_decoys=n_decoys)
        decoys = gen.generate(sample_data)
        assert decoys.shape == (n_decoys, 10, 5)

    def test_row_shuffle_preserves_row_statistics(self, sample_data):
        """row_shuffle permutes each row independently — same values per row."""
        gen = DecoyGenerator(strategy='row_shuffle', n_decoys=1)
        decoys = gen.generate(sample_data)
        original = sample_data.squeeze(0)
        decoy = decoys[0]
        # Each row should have the same sorted values
        for i in range(original.shape[0]):
            assert torch.allclose(original[i].sort()[0], decoy[i].sort()[0])

    def test_col_shuffle_preserves_col_statistics(self, sample_data):
        """col_shuffle permutes each column independently — same values per col."""
        gen = DecoyGenerator(strategy='col_shuffle', n_decoys=1)
        decoys = gen.generate(sample_data)
        original = sample_data.squeeze(0)
        decoy = decoys[0]
        # Each column should have the same sorted values
        for j in range(original.shape[1]):
            assert torch.allclose(original[:, j].sort()[0], decoy[:, j].sort()[0])

    def test_full_shuffle_preserves_all_values(self, sample_data):
        gen = DecoyGenerator(strategy='full_shuffle', n_decoys=1)
        decoys = gen.generate(sample_data)
        original = sample_data.squeeze(0)
        decoy = decoys[0]
        # Same set of values when flattened and sorted
        assert torch.allclose(original.flatten().sort()[0], decoy.flatten().sort()[0])

    def test_gaussian_matches_statistics(self, sample_data):
        gen = DecoyGenerator(strategy='gaussian', n_decoys=1)
        torch.manual_seed(0)
        decoys = gen.generate(sample_data)
        original = sample_data.squeeze(0)
        # Mean and std should be roughly similar (within tolerance for single sample)
        assert abs(decoys[0].mean().item() - original.mean().item()) < 1.0
        assert abs(decoys[0].std().item() - original.std().item()) < 1.0

    def test_block_shuffle_preserves_shape(self, sample_data):
        gen = DecoyGenerator(strategy='block_shuffle', n_decoys=2)
        decoys = gen.generate(sample_data)
        assert decoys.shape == (2, 10, 5)

    def test_multiple_decoys_are_different(self, sample_data):
        gen = DecoyGenerator(strategy='row_shuffle', n_decoys=5)
        torch.manual_seed(123)
        decoys = gen.generate(sample_data)
        # At least some decoys should differ from each other
        all_same = all(torch.allclose(decoys[0], decoys[i]) for i in range(1, 5))
        assert not all_same, "Multiple decoys should produce different permutations"


# ============================================================
# NegativeContrastiveLoss Tests
# ============================================================

class TestNegativeContrastiveLoss:
    """Tests for NegativeContrastiveLoss class."""

    def test_invalid_loss_type_raises(self):
        with pytest.raises(ValueError, match="loss_type must be one of"):
            NegativeContrastiveLoss(loss_type='invalid')

    def test_margin_loss_basic(self):
        loss_fn = NegativeContrastiveLoss(loss_type='margin', margin=1.0)
        decoy_input = torch.randn(1, 10, 5)
        decoy_recon = decoy_input + 0.1  # Small reconstruction error
        real_loss = torch.tensor(0.5)
        result = loss_fn(decoy_input, decoy_recon, real_loss)
        assert result.ndim == 0  # scalar

    def test_negative_mse_loss(self):
        loss_fn = NegativeContrastiveLoss(loss_type='negative_mse')
        decoy_input = torch.randn(1, 10, 5)
        decoy_recon = decoy_input.clone()  # Perfect reconstruction
        result = loss_fn(decoy_input, decoy_recon)
        assert result.ndim == 0

    def test_log_ratio_loss(self):
        loss_fn = NegativeContrastiveLoss(loss_type='log_ratio')
        decoy_input = torch.randn(1, 10, 5)
        decoy_recon = decoy_input + torch.randn_like(decoy_input) * 2  # Large error
        real_loss = torch.tensor(0.1)
        result = loss_fn(decoy_input, decoy_recon, real_loss)
        assert result.ndim == 0

    def test_margin_loss_rewards_high_decoy_error(self):
        """Model should be rewarded when decoy reconstruction error is large."""
        loss_fn = NegativeContrastiveLoss(loss_type='margin', margin=1.0)
        decoy_input = torch.randn(1, 10, 5)
        # Good case: decoy poorly reconstructed (large error)
        decoy_recon_bad = decoy_input + torch.randn_like(decoy_input) * 5
        real_loss_good = torch.tensor(0.1)
        loss_good = loss_fn(decoy_input, decoy_recon_bad, real_loss_good)

        # Bad case: decoy well reconstructed (small error)
        decoy_recon_good = decoy_input + torch.randn_like(decoy_input) * 0.01
        real_loss_bad = torch.tensor(0.5)
        loss_bad = loss_fn(decoy_input, decoy_recon_good, real_loss_bad)

        # Loss should be lower (better) when decoy is poorly reconstructed
        assert loss_good.item() <= loss_bad.item()

    def test_clip_value_prevents_explosion(self):
        loss_fn = NegativeContrastiveLoss(loss_type='margin', margin=1.0, clip_value=5.0)
        decoy_input = torch.randn(1, 10, 5)
        decoy_recon = decoy_input.clone()  # Perfect decoy reconstruction (bad)
        real_loss = torch.tensor(100.0)  # Huge real loss
        result = loss_fn(decoy_input, decoy_recon, real_loss)
        assert result.item() <= 5.0


# ============================================================
# Trainer Integration Tests
# ============================================================

class TestTrainerContrastive:
    """Tests for contrastive loss integrated into ProteomicsAutoencoderTrainer."""

    @pytest.fixture
    def setup(self):
        """Create model, dataset, trainer with contrastive enabled."""
        torch.manual_seed(42)
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(20, 8),
            index=[f'protein_{i}' for i in range(20)],
            columns=[f'sample_{i}' for i in range(8)]
        )
        dataset = ProteomicsDataset(data, mask_probability=0.15, scaling_method='robust')
        model = BiDirectionalAutoencoder(
            n_proteins=20, n_samples=8,
            protein_embedding_dim=16, sample_embedding_dim=8,
            hidden_dims=[32, 16]
        )
        device = torch.device('cpu')
        return model, dataset, device

    def test_trainer_without_contrastive(self, setup):
        model, dataset, device = setup
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3, device=device, contrastive_args=None
        )
        assert not trainer.use_contrastive
        loss = trainer.train_epoch(dataset, device, epoch=0)
        assert loss > 0

    def test_trainer_with_contrastive(self, setup):
        model, dataset, device = setup
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': 'row_shuffle',
            'n_decoys': 2,
            'loss_type': 'margin',
            'margin': 1.0,
            'lambda_negative': 0.1,
            'max_lambda': 0.5,
            'warmup_epochs': 0,
        }
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3, device=device,
            contrastive_args=contrastive_args
        )
        assert trainer.use_contrastive
        loss = trainer.train_epoch(dataset, device, epoch=5)
        assert loss > 0
        assert len(trainer.negative_losses) == 1

    def test_lambda_warmup(self, setup):
        model, dataset, device = setup
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': 'col_shuffle',
            'n_decoys': 1,
            'loss_type': 'margin',
            'lambda_negative': 0.1,
            'max_lambda': 0.5,
            'warmup_epochs': 10,
        }
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3, device=device,
            contrastive_args=contrastive_args
        )
        # During warmup, lambda should be 0
        assert trainer._get_current_lambda(0) == 0.0
        assert trainer._get_current_lambda(9) == 0.0
        # After warmup, should ramp up (ramp_epochs == warmup_epochs = 10)
        assert trainer._get_current_lambda(10) == pytest.approx(0.1, abs=0.01)
        # After warmup + ramp, should reach max_lambda
        assert trainer._get_current_lambda(20) == pytest.approx(0.5)
        assert trainer._get_current_lambda(100) == pytest.approx(0.5)

    @pytest.mark.parametrize("strategy", ['row_shuffle', 'col_shuffle', 'full_shuffle', 'gaussian', 'block_shuffle'])
    def test_all_strategies_train(self, setup, strategy):
        model, dataset, device = setup
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': strategy,
            'n_decoys': 1,
            'loss_type': 'margin',
            'lambda_negative': 0.1,
            'max_lambda': 0.1,
            'warmup_epochs': 0,
        }
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3, device=device,
            contrastive_args=contrastive_args
        )
        loss = trainer.train_epoch(dataset, device, epoch=1)
        assert np.isfinite(loss)

    @pytest.mark.parametrize("loss_type", ['margin', 'negative_mse', 'log_ratio'])
    def test_all_loss_types_train(self, setup, loss_type):
        model, dataset, device = setup
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': 'row_shuffle',
            'n_decoys': 1,
            'loss_type': loss_type,
            'lambda_negative': 0.1,
            'max_lambda': 0.1,
            'warmup_epochs': 0,
        }
        trainer = ProteomicsAutoencoderTrainer(
            model, learning_rate=1e-3, device=device,
            contrastive_args=contrastive_args
        )
        loss = trainer.train_epoch(dataset, device, epoch=1)
        assert np.isfinite(loss)


# ============================================================
# End-to-end Integration Test
# ============================================================

class TestEndToEnd:
    """End-to-end test of train_proteomics_autoencoder with contrastive loss."""

    def test_train_with_contrastive_args(self):
        torch.manual_seed(42)
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(15, 6),
            index=[f'prot_{i}' for i in range(15)],
            columns=[f'samp_{i}' for i in range(6)]
        )
        contrastive_args = {
            'enabled': True,
            'decoy_strategy': 'row_shuffle',
            'n_decoys': 1,
            'loss_type': 'margin',
            'lambda_negative': 0.1,
            'max_lambda': 0.5,
            'warmup_epochs': 5,
        }
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=20,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
            contrastive_args=contrastive_args,
        )
        # Results should contain negative losses in training_history
        assert 'negative_losses' in results.training_history
        assert len(results.training_history['negative_losses']) == 20

    def test_train_without_contrastive_args(self):
        """Verify backward compatibility: no contrastive_args means no change."""
        torch.manual_seed(42)
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(15, 6),
            index=[f'prot_{i}' for i in range(15)],
            columns=[f'samp_{i}' for i in range(6)]
        )
        results = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=16,
            sample_embedding_dim=8,
            hidden_dims=[32, 16],
            epochs=10,
            learning_rate=1e-3,
            device=torch.device('cpu'),
            early_stopping_patience=0,
        )
        assert 'negative_losses' not in results.training_history
