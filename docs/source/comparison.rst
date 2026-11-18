Offline saved-output comparison (Release A)
==========================================

Compare saved methods/configurations/runs without training, scoring, a server,
network access, or a target feature. HTML plus complete scientific tables is the
default; explicit tables-only export remains supported.

.. code-block:: sh

   PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir demo-comparison --pool common --depths 1 2 5

Open the generated HTML directly from disk. Start with the dataset overview,
output-pair heatmap and depth chart, inspect separate run recurrence, then search
queries and drill down into candidate ranks and optional original-mask profiles.
Filters never change scientific pools. Agreement is not correctness.

The full `Release A guide <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_RELEASE_A.md>`_
covers usable manifests, optional profile contracts, payload limits, metadata
omission, regeneration, API usage, schema versions and validation limitations.
The `input/scientific schema reference <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_SCHEMA_V1.md>`_
documents completeness, missingness, legacy formats and denominators.

Reports embed at most the explicit query/top-union/pinned scope, with a default
50 MiB JSON payload limit before HTML wrapping. Full scientific tables remain
independent. Sensitive metadata is retained unless explicitly omitted from HTML;
the normalized bundle is never redacted. New result bundles use schema version
two, with A2 version-one reload support. B1–B3 remain unfinished.
