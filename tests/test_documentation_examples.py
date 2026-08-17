"""Smoke tests that keep the executable documentation examples current."""

from examples.basic_autoencoder_analysis import make_example_data, run_analysis as run_basic_analysis
from examples.multiomics_autoencoder_analysis import (
    make_example_modalities,
    run_analysis as run_multiomics_analysis,
)


def test_basic_autoencoder_example_runs():
    """The basic executable example trains and exposes documented outputs."""
    data = make_example_data(n_features=12, n_samples=6)
    results = run_basic_analysis(data)

    assert results.protein_embeddings.shape == (12, 16)
    assert results.sample_embeddings.shape == (6, 8)
    assert results.similarity_matrix.shape == (12, 12)
    assert len(results.training_history["train_losses"]) == 3


def test_multiomics_autoencoder_example_runs():
    """The multi-omics example trains with the documented modality workflow."""
    proteins, metabolites = make_example_modalities(
        n_proteins=8,
        n_metabolites=6,
        n_samples=6,
    )
    results = run_multiomics_analysis(proteins, metabolites)

    assert results.protein_embeddings.shape == (14, 16)
    assert results.sample_embeddings.shape == (6, 8)
    assert results.similarity_matrix.shape == (14, 14)
    assert len(results.training_history["train_losses"]) == 3
