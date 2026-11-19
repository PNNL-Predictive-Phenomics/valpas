# VaLPAS

VaLPAS (Variation-Leveraged Phenomic Association Study) identifies associations among molecular features measured across shared experimental conditions. It supports conventional association metrics, supervised learned correlation, and denoising autoencoder-based representation learning for proteomics and multi-omics data.

- [User guide](docs/USER_GUIDE.md): method selection, parameters, autoencoder options, and workflows.
- [API reference](https://pnnl-predictive-phenomics.github.io/valpas/): complete package API.
- [Demonstration notebook](notebooks/valpas_demonstration.ipynb): interactive analysis walkthrough.
- [Basic runnable example](examples/basic_autoencoder_analysis.py) and [multi-omics runnable example](examples/multiomics_autoencoder_analysis.py).

## Installation

VaLPAS requires Python 3.12 or later.

```bash
git clone https://github.com/PNNL-Predictive-Phenomics/valpas.git
cd valpas
python -m venv valpas-env
source valpas-env/bin/activate  # macOS/Linux
# Windows PowerShell: valpas-env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install .
```

For the demonstration notebook, install its additional dependencies:

```bash
pip install -r requirements.txt
```

To build documentation locally:

```bash
pip install -r docs/requirements.txt
make -C docs html
```

Conda environments are also supported. Activate the selected environment before installing or running VaLPAS.

## Quick start

### Command line: file-based association analysis

The installed `valpas` command is the recommended entry point for file-based association workflows. Inspect its commands with:

```bash
valpas --help
```

Calculate Spearman associations from a CSV file and write a sorted association list:

```bash
valpas associate from_file \
  --csv \
  --infile measurements.csv \
  --association_type spearman \
  --output_type sorted_list \
  --outfile spearman_associations.csv \
  --overwrite_output
```

Validate inputs beforehand with `valpas prepare from_file --csv --infile measurements.csv`, and generate a heatmap with `valpas visualize --infile association_matrix.csv --outfile association_heatmap.png`. See the [CLI section of the user guide](docs/USER_GUIDE.md#command-line-interface) for all commands and options.

### Python: file-based association analysis

Use [`associate`](src/valpas/valpas_core.py:21) for scripted or in-memory file-based workflows:

```python
from valpas.valpas_core import associate

results = associate(
    association_type="spearman",
    infile="measurements.csv",
    file_type="csv",
    output_type="sorted_list",
    normalization="pre",
)
```

### Python: autoencoder analysis

For nonlinear denoising and learned embeddings, use the direct autoencoder API with a feature-by-sample table (features as rows; samples or conditions as columns):

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
)

similarities = results.similarity_matrix
protein_embeddings = results.protein_embeddings
```

Read the [user guide](docs/USER_GUIDE.md) before enabling advanced options such as modality-specific encoders, cross-modal masking, variational bottlenecks, cosine auxiliary loss, contrastive decoys, or cross-attention.

## Data conventions

- In file-based workflows, experimental conditions are observations and molecular features are variables.
- The direct autoencoder API requires **features as rows** and **samples/conditions as columns**.
- For multi-omics autoencoder analysis, vertically concatenate modalities in a known row order, ensure they have identical sample columns, and set `modality_split` to the first modality's row count.

## Running examples and tests

Run the examples from an installed checkout:

```bash
python examples/basic_autoencoder_analysis.py
python examples/multiomics_autoencoder_analysis.py
```

Run the test suite with:

```bash
pytest
```

## Saved-output comparison (Release A workflow + B1 diagnostics)

Compare two or more saved outputs—including two runs of one configuration—without training, scoring, checkpoints or network access. The lightweight [comparison API and schema](docs/COMPARISON_SCHEMA_V1.md) now provide full available ranks, coverage/exclusions, output-pair agreement, separate run recurrence, and dataset/query summaries. **No target metabolite or protein is required up front:** compare all declared queries under an explicit pool policy, inspect the overview, then select queries for detail.

Run the [saved-comparison example](examples/compare_saved_results.py), or use the [manifest-driven CLI](src/valpas/cli.py:304) with the [validated synthetic manifest](tests/comparison/fixtures/demo-01/manifest.json):

```sh
PYTHONPATH=src python3 examples/compare_saved_results.py
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir demo-comparison --pool common --depths 1 2 5
```

The result bundle retains normalized saved values, stable content/settings identity, source fingerprints and complete machine-readable tables. It reloads without original sources/models. CSV data cells are JSON encoded; large detail tables are compressed. Existing destinations are refused by default; explicit overwrite is restricted to intact owned result bundles containing no consumed inputs or foreign files. The [A1 input inspection/export example](examples/inspect_comparison_inputs.py) remains available separately.

Open the generated single-file HTML directly from disk: no server, network or browser filesystem permission is needed. The [Release A quick start](docs/COMPARISON_RELEASE_A.md) covers overview heatmaps/depth charts, separate recurrence, searchable query/candidate drilldown, optional original-mask profiles, 50 MiB report limits, metadata omission and source-free regeneration. HTML is now the default; explicit tables-only remains available. Use the [profile-enabled manifest](tests/comparison/fixtures/demo-01/manifest-with-profiles.json) for synthetic profile examples.

B1 adds optional exact-ID sample metadata (categorical/continuous coloring and explicit display ordering), marginal observed-value group summaries, joint-centered covariance products and an explicit recentered omission preview. Use the separate [B1 manifest](tests/comparison/fixtures/demo-01/manifest-with-b1.json) and [hand-calculated fixture guide](tests/comparison/fixtures/demo-01/README.md); the runnable example now defaults to this fixture. Its single requested diagnostic pair does not restrict the all-query overview. Browser diagnostics are on demand for embedded pairs; exported diagnostics cover only explicit requests. Colors, ordering and diagnostics never change scientific identity, saved scores or ranks and do not imply causality, model attribution, retraining or new association scoring.

New result bundles use schema v3; A2 v1/A3 v2 reload remains supported only with the same software/policy versions. The [schema reference](docs/COMPARISON_SCHEMA_V1.md) documents exact metadata/request APIs, nested JSON table cells, null/status meanings and legacy HTML checks. Metadata is included in the report payload budget. Metadata omission is **HTML-only**; full bundles retain sensitive IDs, profiles, metadata and diagnostic tables.

Agreement is not correctness; seed recurrence is not biological replication. B1 is implemented; B2/B3 references, sessions, publication figures, production hooks and target-scale validation remain unfinished. Neither release is declared finally complete for the modified B1 tree. Existing association and training workflows are unchanged.

For repeatable wheel/sdist builds, fresh full-dependency installs, source-free CLI regeneration and direct-file browser checks, run the [distribution validator](docs/DISTRIBUTION_VALIDATION.md). Browser assets ship in wheels; comparison guides, examples and demo inputs ship in source distributions, not as installed wheel data.

## Troubleshooting

### Python or permission errors

Ensure Python 3.12+ is active. In restricted environments, install to the active user environment:

```bash
pip install --user .
pip install --user -r requirements.txt
```

### PyTorch GPU support

For CUDA-enabled PyTorch, install the platform-appropriate build from [pytorch.org](https://pytorch.org/get-started/locally/) before installing VaLPAS dependencies.

### Notebook use

After activating the environment, start Jupyter with `jupyter notebook` or `jupyter lab`. In VS Code, install the [Jupyter extension](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter) and select the same Python environment as the notebook kernel.

## License

VaLPAS is distributed under the [BSD 2-Clause License](LICENSE).
