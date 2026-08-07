"""Minimal, runnable VaLPAS autoencoder analysis.

Run from an installed checkout with:
    python examples/basic_autoencoder_analysis.py

The direct autoencoder API expects a DataFrame with features as rows and
samples/conditions as columns. Replace ``make_example_data`` with a CSV import
in a real analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from valpas._core.autoencoder import train_proteomics_autoencoder


def make_example_data(
    n_features: int = 24,
    n_samples: int = 10,
    seed: int = 42,
) -> pd.DataFrame:
    """Create a small feature-by-sample matrix with shared latent structure."""
    rng = np.random.default_rng(seed)
    feature_effects = rng.normal(size=(n_features, 2))
    sample_effects = rng.normal(size=(2, n_samples))
    measurements = feature_effects @ sample_effects + rng.normal(
        scale=0.1, size=(n_features, n_samples)
    )
    return pd.DataFrame(
        measurements,
        index=[f"protein_{index:02d}" for index in range(n_features)],
        columns=[f"sample_{index:02d}" for index in range(n_samples)],
    )


def run_analysis(data: pd.DataFrame | None = None):
    """Train a small CPU-safe model and return its result object."""
    if data is None:
        data = make_example_data()

    torch.manual_seed(42)
    return train_proteomics_autoencoder(
        data,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
        epochs=3,
        learning_rate=1e-3,
        mask_probability=0.15,
        validation_split=0.2,
        early_stopping_patience=0,
        device=torch.device("cpu"),
    )


def main() -> None:
    """Run the example and print the primary analysis outputs."""
    results = run_analysis()
    print("Embedding shape:", results.embeddings.shape)
    print("Similarity matrix shape:", results.similarity_matrix.shape)
    print("Final validation loss:", results.training_history["final_val_loss"])
    print("\nTop similar feature pairs:")
    print(results.get_top_similar_proteins(n=5).to_string(index=False))


if __name__ == "__main__":
    main()
