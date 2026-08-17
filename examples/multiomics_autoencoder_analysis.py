"""Runnable VaLPAS multi-omics autoencoder analysis.

Run from an installed checkout with:
    python examples/multiomics_autoencoder_analysis.py

The two input modalities must share the same sample columns in the same order.
Rows are concatenated vertically, and ``modality_split`` marks where the first
modality ends.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from valpas._core.autoencoder import train_proteomics_autoencoder


def make_example_modalities(
    n_proteins: int = 12,
    n_metabolites: int = 8,
    n_samples: int = 8,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create aligned synthetic modalities with a shared signal."""
    rng = np.random.default_rng(seed)
    shared_sample_signal = rng.normal(size=(2, n_samples))
    protein_data = rng.normal(size=(n_proteins, 2)) @ shared_sample_signal
    metabolite_data = rng.normal(size=(n_metabolites, 2)) @ shared_sample_signal
    columns = [f"sample_{index:02d}" for index in range(n_samples)]

    proteins = pd.DataFrame(
        protein_data + rng.normal(scale=0.1, size=protein_data.shape),
        index=[f"protein_{index:02d}" for index in range(n_proteins)],
        columns=columns,
    )
    metabolites = pd.DataFrame(
        metabolite_data + rng.normal(scale=0.1, size=metabolite_data.shape),
        index=[f"metabolite_{index:02d}" for index in range(n_metabolites)],
        columns=columns,
    )
    return proteins, metabolites


def run_analysis(
    proteins: pd.DataFrame | None = None,
    metabolites: pd.DataFrame | None = None,
):
    """Train a modality-aware model with masking and cross-attention."""
    if proteins is None or metabolites is None:
        proteins, metabolites = make_example_modalities()
    if not proteins.columns.equals(metabolites.columns):
        raise ValueError("Modalities must have identical sample columns in the same order.")

    multiomics_data = pd.concat([proteins, metabolites], axis=0)
    torch.manual_seed(42)
    return train_proteomics_autoencoder(
        multiomics_data,
        protein_embedding_dim=16,
        sample_embedding_dim=8,
        hidden_dims=[32, 16],
        epochs=3,
        learning_rate=1e-3,
        modality_split=len(proteins),
        cross_modal_mask_ratio=0.3,
        cross_attention_args={"n_heads": 4, "n_layers": 1, "dropout": 0.1},
        early_stopping_patience=0,
        device=torch.device("cpu"),
    )


def main() -> None:
    """Run the multi-omics example and print primary outputs."""
    results = run_analysis()
    print("Embedding shape:", results.embeddings.shape)
    print("Similarity matrix shape:", results.similarity_matrix.shape)
    print("\nTop similar feature pairs:")
    print(results.get_top_similar_proteins(n=5).to_string(index=False))


if __name__ == "__main__":
    main()
