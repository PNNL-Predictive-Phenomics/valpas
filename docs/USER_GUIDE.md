# VaLPAS User Guide

VaLPAS (Variation-Leveraged Phenomic Association Study) identifies associations among features measured across shared experimental conditions. Typical uses include protein–protein association inference, cross-omics association analysis, and representation learning from proteomics or other feature-by-sample matrices.

This guide is the central user-facing reference for selecting a method, preparing inputs, configuring the autoencoder, and interpreting outputs. For API signatures, see the [online API reference](https://pnnl-predictive-phenomics.github.io/valpas/). For an interactive walkthrough, see the [demonstration notebook](../notebooks/valpas_demonstration.ipynb).

## Contents

- [Installation](#installation)
- [Data conventions](#data-conventions)
- [Choose an analysis method](#choose-an-analysis-method)
- [Quick start: correlation analysis](#quick-start-correlation-analysis)
- [Quick start: autoencoder analysis](#quick-start-autoencoder-analysis)
- [Autoencoder configuration](#autoencoder-configuration)
- [Multi-omics workflows](#multi-omics-workflows)
- [Results and export](#results-and-export)
- [Reproducibility and troubleshooting](#reproducibility-and-troubleshooting)

## Installation

VaLPAS requires Python 3.12 or later. From a local clone:

```bash
python -m venv valpas-env
source valpas-env/bin/activate  # macOS/Linux
# On Windows: valpas-env\Scripts\activate
pip install .
```

Install notebook and documentation dependencies when needed:

```bash
pip install -r requirements.txt
pip install -r docs/requirements.txt
```

See the root [README](../README.md) for platform-specific installation and GPU notes.

## Data conventions

### Association input

The high-level `associate()` workflow imports delimited or Excel files. In an input measurement table, experimental conditions are observations and molecular features are variables. VaLPAS internally transposes data before autoencoder training, so the direct autoencoder API instead expects **features as rows and samples/conditions as columns**.

Use consistent condition labels when comparing two omics datasets. Remove or impute missing values according to the needs of the selected analysis before interpreting associations.

### Direct autoencoder input

```python
import pandas as pd

# Rows: proteins, metabolites, genes, or other features.
# Columns: samples / environmental conditions / perturbations.
data = pd.read_csv("feature_by_sample.csv", index_col=0)
```

For a multi-omics matrix, vertically concatenate the modalities in a known order. The `modality_split` value is the number of rows in the first modality.

## Choose an analysis method

| Method | Use it when | Set `association_type` to | Result |
| --- | --- | --- | --- |
| Pearson correlation | Linear co-variation is expected | `"pearson"` | Signed linear association |
| Spearman correlation | Relationships are monotonic or ranks are more robust | `"spearman"` | Signed rank correlation |
| Cosine similarity | Profile direction matters more than absolute magnitude | `"cosine_similarity"` | Profile similarity |
| Mutual information | Nonlinear dependence may be important | `"mutual_information"` | Dependence score |
| Jaccard metrics | Data are binary or thresholded | `"jaccard_similarity"`, `"jaccard_distance"`, or `"jaccard_index"` | Set-overlap score/distance |
| Learned correlation | A set of known interactions is available for supervision | `"learn_correlation"` | Learned weighted association |
| Autoencoder | Denoising, nonlinear structure, or learned embeddings are desired | `"autoencoder"` | Embedding-derived similarity matrix and training diagnostics |

Correlation-like scores are associations, not causal claims. Inspect experimental design, replicate quality, missingness, and multiple-testing considerations before assigning biological meaning.

## Quick start: correlation analysis

Use the public high-level interface for file-based association analysis:

```python
from valpas.valpas_core import associate

results = associate(
    association_type="spearman",
    infile="measurements.csv",
    file_type="csv",
    output_type="sorted_list",
    normalization="pre",
    filter_cutoff=0.9,
)
```

Important options:

| Option | Default | Purpose |
| --- | --- | --- |
| `association_type` | `"pearson"` | Selects the metric listed above. |
| `infile` / `infile2` | `None` | Primary and optional second omics input. |
| `file_type` | `"csv"` | Input type: `"csv"` or `"xlsx"`. |
| `normalization` | `"none"` | Preprocessing mode: `"pre"`, `"post"`, or `"none"`. |
| `filter_cutoff` | `0.9` | Low-confidence/missingness filtering threshold. |
| `min_counts` | `3` | Minimum number of contributing observations per edge. |
| `calculate_confidence` | `False` | Calculate confidence when reference interactions are supplied. |

## Quick start: autoencoder analysis

Use the direct API when working from an in-memory feature-by-sample `pandas.DataFrame`:

```python
import pandas as pd
from valpas._core.autoencoder import train_proteomics_autoencoder

data = pd.read_csv("feature_by_sample.csv", index_col=0)
results = train_proteomics_autoencoder(
    data,
    protein_embedding_dim=64,
    sample_embedding_dim=32,
    hidden_dims=[128, 64],
    epochs=100,
    learning_rate=1e-3,
    mask_probability=0.15,
)

similarities = results.similarity_matrix
protein_embeddings = results.protein_embeddings
history = results.training_history
```

The autoencoder learns feature and sample embeddings while reconstructing masked values. Pairwise cosine similarity of learned feature embeddings becomes the association matrix.

### Baseline parameters

| Parameter | Default | Guidance |
| --- | --- | --- |
| `protein_embedding_dim` | `128` | Feature latent dimension. Try 32–128 for small/medium datasets. |
| `sample_embedding_dim` | `64` | Sample latent dimension. Try 16–64 for modest sample counts. |
| `hidden_dims` | `[256, 128]` | At least two dimensions are required by the current architecture. Start with `[128, 64]` for small data. |
| `epochs` | `200` | Maximum training epochs. Use validation loss and early stopping to choose a practical value. |
| `learning_rate` | `1e-3` | Reduce to `3e-4` if loss is unstable. |
| `mask_probability` | `0.15` | Fraction of values masked in baseline denoising training. |
| `scaling_method` | `"robust"` | Input scaling method. Use robust scaling when outliers are expected. |
| `validation_split` | `0.2` | Held-out fraction used for validation. |
| `early_stopping_patience` | `20` | Validation checks without improvement before stopping; set `0` to disable. |
| `min_delta` | `1e-5` | Minimum validation-loss improvement that resets patience. |

## Autoencoder configuration

Enable advanced options incrementally. Establish a stable baseline before combining multiple objectives, then compare validation loss, embedding stability, and biological recovery against the baseline.

### Modality-specific encoders

Use separate feature encoders for two vertically stacked modalities:

```python
results = train_proteomics_autoencoder(
    multiomics_data,
    modality_split=100,  # first 100 rows are modality A
    hidden_dims=[128, 64],
)
```

`modality_split` must lie strictly between zero and the number of input rows. Rows before the split belong to modality A; remaining rows belong to modality B.

### Cross-modal masking bias

Mask one randomly chosen target modality more heavily for each training pattern. This forces reconstruction using context from the opposite modality.

```python
cross_modal_config = {
    "modality_split": 100,
    "cross_modal_mask_ratio": 0.3,
}
```

`cross_modal_mask_ratio` is added to the base mask probability for the target modality and is capped at 1.0. Start in the 0.3–0.5 range. This option is only meaningful with `modality_split`.

### VAE bottleneck and KL regularization

A variational bottleneck encourages smoother, regularized embedding distributions:

```python
vae_config = {
    "use_vae": True,
    "kl_weight": 1e-3,
}
```

Lower `kl_weight` if reconstruction quality degrades; start at `1e-3`. The variational architecture is selected automatically when `use_vae=True`.

### Embedding norm regularization

Penalize deviation of feature-embedding L2 norms from the target norm (1.0):

```python
norm_config = {"norm_reg_weight": 0.01}
```

Start at 0.01. Larger values may stabilize norms but can over-constrain the learned representation.

### Curriculum masking

Increase the reconstruction task difficulty over training:

```python
curriculum_config = {
    "curriculum_masking": {
        "start_prob": 0.05,
        "end_prob": 0.30,
        "warmup_epochs": 50,
    }
}
```

While active, the schedule replaces fixed `mask_probability` in training. Use it when a high fixed masking rate gives unstable early training.

### Row / feature-level masking

Mask complete feature rows for a fraction of batch elements:

```python
row_mask_config = {"row_mask_ratio": 0.2}
```

Start in the 0.1–0.3 range. This is more difficult than element-wise masking and encourages feature reconstruction from inter-feature context.

### Cosine embedding auxiliary loss

Match pairwise data-space cosine structure to learned feature-embedding cosine structure:

```python
cosine_config = {
    "cosine_aux_weight": 0.05,
    "cosine_aux_args": {
        "n_pairs": 64,
        "temperature": 1.0,
        "detach_targets": True,
    },
}
```

`n_pairs` limits sampled features per mini-batch and avoids full quadratic cost. Start with `cosine_aux_weight` between 0.01 and 0.1. Keep `detach_targets=True` unless intentionally optimizing through the similarity targets.

### Bidirectional cross-attention

Cross-attention lets feature embeddings attend to sample embeddings and lets sample embeddings attend to feature embeddings before decoding:

```python
attention_config = {
    "cross_attention_args": {
        "n_heads": 4,
        "n_layers": 1,
        "dropout": 0.1,
    }
}
```

Providing `cross_attention_args` selects the modality-aware architecture even if `modality_split` is absent. Use one layer initially; add layers only if validation and downstream biological metrics support the added complexity.

### Negative contrastive loss with decoys

Create shuffled or synthetic decoys and train the model to reconstruct decoys poorly, reducing trivial identity behavior:

```python
contrastive_config = {
    "contrastive_args": {
        "enabled": True,
        "decoy_strategy": "row_shuffle",
        "n_decoys": 1,
        "loss_type": "margin",
        "margin": 1.0,
        "lambda_negative": 0.1,
        "max_lambda": 0.5,
        "warmup_epochs": 10,
        "clip_negative_loss": 10.0,
    }
}
```

Supported strategies are `row_shuffle`, `col_shuffle`, `full_shuffle`, `gaussian`, and `block_shuffle`. Supported losses are `margin`, `negative_mse`, and `log_ratio`. Enable this only after confirming ordinary reconstruction training is stable.

### Advanced-option dependency reference

| Option | Default | Prerequisite / interaction |
| --- | --- | --- |
| `modality_split` | `None` | Requires vertically stacked modalities in known row order. |
| `cross_modal_mask_ratio` | `0.0` | Requires `modality_split`. |
| `use_vae` | `False` | Enables KL term when `kl_weight > 0`. |
| `kl_weight` | `1e-3` | Used only with `use_vae=True`. |
| `norm_reg_weight` | `0.0` | Positive value enables norm loss. |
| `curriculum_masking` | `None` | Replaces fixed mask probability during training. |
| `row_mask_ratio` | `0.0` | Positive value enables full-row masking. |
| `cosine_aux_weight` | `0.0` | Positive value enables cosine auxiliary loss. |
| `cross_attention_args` | `None` | Non-`None` enables bidirectional cross-attention. |
| `contrastive_args` | `None` | Set `enabled=True` to activate decoy loss. |

## Multi-omics workflows

For two modalities, first create a single matrix in a fixed row order:

```python
import pandas as pd
from valpas._core.autoencoder import train_proteomics_autoencoder

proteins = pd.read_csv("proteins_feature_by_sample.csv", index_col=0)
metabolites = pd.read_csv("metabolites_feature_by_sample.csv", index_col=0)

if not proteins.columns.equals(metabolites.columns):
    raise ValueError("Both modalities must use the same samples in the same order.")

multiomics = pd.concat([proteins, metabolites], axis=0)
results = train_proteomics_autoencoder(
    multiomics,
    hidden_dims=[128, 64],
    modality_split=len(proteins),
    cross_modal_mask_ratio=0.3,
    cross_attention_args={"n_heads": 4, "n_layers": 1, "dropout": 0.1},
)
```

Recommended progression:

1. Train a baseline with `modality_split` only.
2. Add `cross_modal_mask_ratio` to emphasize cross-modal reconstruction.
3. Add cross-attention if validation and biological benchmarks justify its additional capacity.
4. Add VAE, cosine, contrastive, or other regularizers one at a time.

## Results and export

The direct autoencoder function returns `ProteomicsAutoencoderResults`. Common attributes include:

```python
similarities = results.similarity_matrix
protein_embeddings = results.protein_embeddings
sample_embeddings = results.sample_embeddings
history = results.training_history
```

Use built-in helpers for downstream inspection:

```python
results.get_top_similar_proteins(n=10)
results.export_embeddings("protein_embeddings.csv", format="csv")
plots = results.create_plots()
```

For association results, use the result-object list/export functions described in the API reference. Preserve the input identifiers, analysis configuration, and result table with every downstream interpretation.

## Reproducibility and troubleshooting

### Reproducibility checklist

- Record the VaLPAS version, Python version, PyTorch version, and hardware/device.
- Save the full `autoencoder_args` configuration alongside every result.
- Fix random seeds in your analysis script when comparing model configurations.
- Preserve feature and sample ordering, especially when using `modality_split`.
- Report validation loss and an independent biological or benchmark-based evaluation; low reconstruction loss alone is not sufficient evidence of useful associations.

### Common issues

| Symptom | Likely cause and action |
| --- | --- |
| Shape or encoder error | Confirm data are feature-by-sample and `hidden_dims` has at least two entries. |
| Weak multi-omics results | Verify matching sample labels/order and correct `modality_split`. |
| Unstable or increasing loss | Reduce learning rate, reduce masking or auxiliary-loss weights, and begin from a baseline configuration. |
| Poor reconstruction at startup | Use curriculum masking or lower `mask_probability`. |
| Excessive CPU runtime | Reduce dimensions/epochs for prototyping; use CUDA-enabled PyTorch where available. |
| GPU installation problems | Install the platform-appropriate PyTorch build from [pytorch.org](https://pytorch.org/get-started/locally/). |

## Further resources

- [Root README](../README.md): installation and repository entry point.
- [Demonstration notebook](../notebooks/valpas_demonstration.ipynb): interactive workflow.
- [API documentation](https://pnnl-predictive-phenomics.github.io/valpas/): complete API reference.
- [Basic executable example](../examples/basic_autoencoder_analysis.py).
- [Multi-omics executable example](../examples/multiomics_autoencoder_analysis.py).
