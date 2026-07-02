"""
Tests for autoencoder performance optimizations.

Verifies that:
1. Batched encode_proteins produces identical output to the original loop version
2. Batched encode_samples produces identical output to the original loop version  
3. Early stopping halts training when loss plateaus
4. get_optimal_device() returns a valid torch.device
5. Pre-allocated mask buffer produces correct mask statistics
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import pytest

from valpas._core.autoencoder import (
    BiDirectionalAutoencoder,
    ProteomicsDataset,
    ProteomicsAutoencoderTrainer,
    get_optimal_device,
    train_proteomics_autoencoder,
)


@pytest.fixture
def small_model():
    """Create a small model for testing."""
    torch.manual_seed(42)
    model = BiDirectionalAutoencoder(
        n_proteins=50,
        n_samples=20,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
    )
    return model


@pytest.fixture
def small_dataset():
    """Create a small dataset for testing."""
    np.random.seed(42)
    data = pd.DataFrame(
        np.random.randn(50, 20),
        index=[f"protein_{i}" for i in range(50)],
        columns=[f"sample_{j}" for j in range(20)],
    )
    return ProteomicsDataset(data, mask_probability=0.15, scaling_method='standard')


def _encode_proteins_loop(model, x):
    """Original loop-based encode_proteins for reference comparison."""
    batch_size = x.shape[0]
    protein_embeddings = []
    for i in range(model.n_proteins):
        protein_data = x[:, i, :]
        embedding = model.protein_encoder(protein_data)
        protein_embeddings.append(embedding)
    return torch.stack(protein_embeddings, dim=1)


def _encode_samples_loop(model, x):
    """Original loop-based encode_samples for reference comparison."""
    batch_size = x.shape[0]
    sample_embeddings = []
    for j in range(model.n_samples):
        sample_data = x[:, :, j]
        embedding = model.sample_encoder(sample_data)
        sample_embeddings.append(embedding)
    return torch.stack(sample_embeddings, dim=1)


class TestBatchedEncoding:
    """Verify batched encoding produces identical results to loop version."""

    def test_encode_proteins_equivalence(self, small_model):
        """Batched encode_proteins must match loop version exactly."""
        torch.manual_seed(0)
        x = torch.randn(1, small_model.n_proteins, small_model.n_samples)

        small_model.eval()
        with torch.no_grad():
            batched_result = small_model.encode_proteins(x)
            loop_result = _encode_proteins_loop(small_model, x)

        assert torch.allclose(batched_result, loop_result, atol=1e-6), (
            f"Max diff: {(batched_result - loop_result).abs().max().item()}"
        )

    def test_encode_samples_equivalence(self, small_model):
        """Batched encode_samples must match loop version exactly."""
        torch.manual_seed(0)
        x = torch.randn(1, small_model.n_proteins, small_model.n_samples)

        small_model.eval()
        with torch.no_grad():
            batched_result = small_model.encode_samples(x)
            loop_result = _encode_samples_loop(small_model, x)

        assert torch.allclose(batched_result, loop_result, atol=1e-6), (
            f"Max diff: {(batched_result - loop_result).abs().max().item()}"
        )

    def test_encode_proteins_multi_batch(self, small_model):
        """Batched encoding works with batch_size > 1."""
        torch.manual_seed(0)
        x = torch.randn(4, small_model.n_proteins, small_model.n_samples)

        small_model.eval()
        with torch.no_grad():
            result = small_model.encode_proteins(x)

        assert result.shape == (4, small_model.n_proteins, small_model.protein_embedding_dim)

    def test_encode_samples_multi_batch(self, small_model):
        """Batched encoding works with batch_size > 1."""
        torch.manual_seed(0)
        x = torch.randn(4, small_model.n_proteins, small_model.n_samples)

        small_model.eval()
        with torch.no_grad():
            result = small_model.encode_samples(x)

        assert result.shape == (4, small_model.n_samples, small_model.sample_embedding_dim)

    def test_forward_pass_shape(self, small_model):
        """Full forward pass produces correct output shape."""
        x = torch.randn(1, small_model.n_proteins, small_model.n_samples)
        small_model.eval()
        with torch.no_grad():
            output = small_model(x)
        assert output.shape == (1, small_model.n_proteins, small_model.n_samples)


class TestDeviceSelection:
    """Test get_optimal_device() utility."""

    def test_returns_valid_device(self):
        """get_optimal_device must return a valid torch.device."""
        device = get_optimal_device()
        assert isinstance(device, torch.device)
        assert device.type in ('cpu', 'cuda', 'mps')

    def test_cpu_fallback(self):
        """On systems without GPU, should return CPU."""
        device = get_optimal_device()
        # We can't guarantee GPU is absent, but device should always be valid
        assert device.type in ('cpu', 'cuda', 'mps')


class TestMaskBuffer:
    """Test pre-allocated mask buffer in ProteomicsDataset."""

    def test_buffer_exists(self, small_dataset):
        """Dataset should have pre-allocated buffers."""
        assert hasattr(small_dataset, '_mask_buffer')
        assert hasattr(small_dataset, '_masked_data_buffer')
        assert small_dataset._mask_buffer.shape == (50, 20)
        assert small_dataset._masked_data_buffer.shape == (50, 20)

    def test_mask_probability(self, small_dataset):
        """Mask should respect approximate mask_probability over many calls."""
        total_masked = 0
        total_elements = 0
        n_trials = 100

        for _ in range(n_trials):
            _, mask, _ = small_dataset.create_masked_batch()
            total_masked += mask.sum().item()
            total_elements += mask.numel()

        empirical_rate = total_masked / total_elements
        # Should be approximately 0.15 (within 3% tolerance)
        assert abs(empirical_rate - 0.15) < 0.03, f"Empirical mask rate: {empirical_rate:.4f}"

    def test_masked_values_are_zero(self, small_dataset):
        """Masked positions in data should be set to zero."""
        masked_data, mask, target = small_dataset.create_masked_batch()
        # Where mask is True, masked_data should be 0
        assert (masked_data[mask] == 0).all()


class TestEarlyStopping:
    """Test early stopping behavior."""

    def test_early_stopping_triggers(self):
        """Training should stop early when loss plateaus."""
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(30, 15),
            index=[f"p_{i}" for i in range(30)],
            columns=[f"s_{j}" for j in range(15)],
        )

        # Use very aggressive early stopping (patience=2) to ensure it triggers
        # Force CPU to avoid MPS torch.compile issues
        result = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=8,
            sample_embedding_dim=4,
            hidden_dims=[16, 8],
            epochs=500,
            learning_rate=1e-3,
            early_stopping_patience=2,
            min_delta=0.0,  # any non-improvement triggers counter
            scaling_method='standard',
            device=torch.device('cpu'),
        )

        # Should have stopped before 500 epochs
        history = result.training_history
        assert history['epochs_trained'] < 500, (
            f"Expected early stop but trained all {history['epochs_trained']} epochs"
        )
        assert history['early_stopped'] is True

    def test_early_stopping_disabled(self):
        """With patience=0, should train for all epochs."""
        np.random.seed(42)
        data = pd.DataFrame(
            np.random.randn(20, 10),
            index=[f"p_{i}" for i in range(20)],
            columns=[f"s_{j}" for j in range(10)],
        )

        # Force CPU to avoid MPS torch.compile issues
        result = train_proteomics_autoencoder(
            data,
            protein_embedding_dim=8,
            sample_embedding_dim=4,
            hidden_dims=[16, 8],
            epochs=20,
            learning_rate=1e-3,
            early_stopping_patience=0,
            scaling_method='standard',
            device=torch.device('cpu'),
        )

        history = result.training_history
        assert history['epochs_trained'] == 20
        assert history['early_stopped'] is False


class TestMixedPrecision:
    """Test that AMP setup doesn't crash on CPU."""

    def test_trainer_no_amp_on_cpu(self, small_model):
        """Trainer should not use AMP when device is CPU."""
        device = torch.device('cpu')
        trainer = ProteomicsAutoencoderTrainer(
            small_model, learning_rate=1e-3, device=device
        )
        assert trainer.use_amp is False

    def test_training_runs_on_cpu(self, small_model, small_dataset):
        """Training should complete without errors on CPU."""
        device = torch.device('cpu')
        trainer = ProteomicsAutoencoderTrainer(
            small_model, learning_rate=1e-3, device=device
        )
        loss = trainer.train_epoch(small_dataset, device, n_batches=5, mini_batch_size=2)
        assert loss > 0
        assert np.isfinite(loss)
