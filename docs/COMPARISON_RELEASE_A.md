# Release A: offline saved-output comparison

Compare **two or more saved association outputs**, not measurement matrices alone. Two methods, configurations, or distinct runs of one configuration are supported. Protein-only, gene-expression-only, and cross-modality comparisons use the same exact-ID rules. No training, scoring, models, network access, or target query is required. Agreement is not correctness, and seeds are not biological replicates.

## CLI-first quick start

From a source checkout with Python 3.12+, run the [CLI](../src/valpas/cli.py:304) against the [no-profile manifest](../tests/comparison/fixtures/demo-01/manifest.json):

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir demo-comparison --pool common --depths 1 2 5
```

Open the generated report directly from disk in a modern browser. The single HTML file contains its script, styles, data and inline SVG. It needs no server, CDN, connection, local-file fetch or filesystem permission. The remaining bundle files are for complete scientific export and regeneration, not browser dependencies. Copying only the HTML is sufficient to browse it.

For synthetic measurement profiles, use the [profile manifest](../tests/comparison/fixtures/demo-01/manifest-with-profiles.json) and [explicit profile layers](../tests/comparison/fixtures/demo-01/profiles.json):

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-profiles.json --outdir demo-profiles --pool common
```

These are synthetic illustration values, **not measurements used to derive the fixture scores**. Their relationship to every algorithm layer is explicitly “different.” The no-profile report remains fully usable for rankings and agreement.

The [API example](../examples/compare_saved_results.py) prints summaries, writes HTML and complete tables, then reloads and checks scientific parity:

```sh
PYTHONPATH=src python3 examples/compare_saved_results.py retained-example
```

## Overview → queries → candidates → profiles

1. Start with dataset identity, observation cohort, configuration differences, output inventory and compatibility warnings. Each output retains method/configuration/run/seed identity; runs are not implicitly collapsed into methods.
2. Agreement heatmap tiles show one output pair's median controlled overlap and **evaluable / declared query denominator**. Gray is unavailable, not zero. Select a tile to inspect per-query overlap, status and reason. The depth chart shows saved cohort medians; points expose denominators and drill down.
3. Run recurrence is a separate panel. Expected runs remain the denominator, even when a run is unavailable; one run is not assessed. Select a group/query for candidate nominations.
4. Search/sort the query table. Canonical IDs remain visible beside optional labels and modality. Duplicate labels are disambiguated by ID. Search includes available embedded annotations, not an external annotation service.
5. Select a query, then inspect the **union of each output's top list at the selected depth plus pinned IDs**. Candidate default order is canonical ID, not a consensus ranking. Searching can reveal candidates embedded for other depths; pin them for the current view. Select a candidate for signed native scores, native/active/saved ranks, statuses, reasons and run recurrence. Unknown sparse pairs are disclosed separately, not fabricated as ranked rows.
6. Optional profiles show original-mask coverage, jointly observed finite scatter, and sample profiles. Hover marks for observation IDs and exact values. Filled marks are observed; hollow orange marks are finite originally unobserved/imputed values. Imputed values never enter observed-only scatter/counts. Constant and near-empty flags are displayed. Units, transform, provenance, layer name and relationship to each algorithm layer are explicit.

Display filters, hidden outputs and chart selections **never redefine scientific pools or denominators**. Hidden outputs still contribute to the already computed candidate union. There are no model-attribution claims, biological-replicate interpretations or “best method” scores.

## Scope and payload budget

[ReportSettings](../src/valpas/comparison/browser.py:12) is independent of [ComparisonSettings](../src/valpas/comparison/models.py). Report controls do not change comparison identity or complete scientific tables:

| Report field / CLI option | Default and meaning |
|---|---|
| query_ids / --report-query | All declared queries; repeat the CLI option to embed an explicit detail subset. Whole-cohort overview remains available. |
| max_interactive_depth / --max-interactive-depth | 50; positive integer. Auxiliary report depths are generated with the existing Python engine, not JavaScript metrics. |
| pinned_candidate_ids / --pin-candidate | Empty; repeatable exact canonical IDs, embedded for each selected query beyond top unions. |
| max_payload_bytes / --max-payload-bytes | 52,428,800 bytes (50 MiB) of UTF-8 escaped JSON **before HTML wrapping**. |
| omit_metadata / --omit-metadata | False; explicit HTML-only metadata/profile omission. |

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-profiles.json --outdir small-report --report-query M01 --max-interactive-depth 2 --pin-candidate P03 --max-payload-bytes 1048576
```

The UI distinguishes outside-detail-scope queries and searches only embedded labels/annotations/candidates. No match is not evidence of absence. Re-export with the exact query/candidate IDs needed; candidate IDs must exist on a declared axis. Browser pins are transient display state, not B2 sessions or decisions.

Over-budget reports fail before publication with the measured payload size and explicit remedies: reduce detail queries/depth/pins, omit metadata, raise the explicit budget, or use tables-only. There is **no silent sampling or omission**. Whole-cohort agreement data still scales with query × output-pair × report-depth counts; subset export is not a guarantee of small payload or low peak memory. The exporter currently constructs the payload before checking its serialized size. B3 target-scale performance is unverified.

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir complete-tables --tables-only
```

## Profile contract

The manifest can optionally contain a profiles object, either an inline version-one layer document or a local JSON path descriptor. See the [complete working example](../tests/comparison/fixtures/demo-01/profiles.json) and [validator](../src/valpas/comparison/profiles.py:15). Only JSON profile transport is supported; no guessing of CSV orientation or identifier coercion.

Each layer declares:

- Unique layer ID; complete dataset identity matching the comparison; orientation explicitly feature rows × observation columns.
- Unique exact observation IDs; units, transform and provenance; explicit raw/unimputed and extra-observation-subsetting booleans.
- A relationship of same/different/unknown for **every output ID** in algorithm_layers.
- Features keyed by exact namespace ID, modality and feature ID, with one finite numeric value or null per observation. Optional label/annotations are text.
- Mask source: explicit_original requires a same-shaped original boolean mask independent from imputed values. raw_finite requires explicitly raw/unimputed data and a null supplied mask; only this mode derives observation from finite values. unavailable requires a null mask and retains unknown coverage rather than guessing from values.

Observation order may differ; alignment is by exact ID. Extra observations require explicit permission to subset and their IDs are exported as exclusions. Missing required observations or features disable the relevant plots with a reason, never silently compare a smaller cohort. Original observed counts may include a transformed null value; plotted points additionally require finite values. Near-empty means fewer than three observed finite values; constant means at least two such values all exactly equal. Unknown masks disable observed-only plots and keep counts null.

Profiles are normalized once per layer/feature, not duplicated as sample arrays per query-candidate pair. Full profile-value and coverage tables are independent of report scope. Normalized layers persist in the bundle, so source deletion does not remove measurement evidence.

## Saved bundle, API and regeneration

[write_comparison()](../src/valpas/comparison/report.py:282) defaults to HTML plus complete tables; explicit tables-only remains supported. [load_comparison_bundle()](../src/valpas/comparison/report.py:225) accepts existing A2 version-one bundles and new version-two result bundles. Input descriptors/manifests, scientific table columns and comparison identity policy remain version one. Version two adds report settings, normalized optional profiles, optional profile tables, a reloadable report-view payload, HTML and inventory checks. The report-view and profile documents each have their own version-one schemas.

The loader checks normalized contracts, identity, warnings, checksums, exact table parity and report parity. It uses saved normalized values, not original source paths or models. Current reload requires the same software/policy versions; there is no cross-version migration. Report settings and profiles do not change the scientific comparison ID; their bytes are protected by the completion inventory.

```sh
PYTHONPATH=src python3 -m valpas.cli compare --bundle demo-profiles --outdir regenerated --report-query M02 --max-interactive-depth 3 --pin-candidate P01
```

Bundle regeneration preserves scientific settings; pool/depth analysis overrides are rejected with bundle input. Use a new directory. Default publication refuses existing paths, including empty directories. Explicit overwrite accepts only an intact owned comparison bundle with no foreign files or consumed inputs. Staging, validation, sibling rename and rollback protect the prior bundle. A loaded bundle cannot overwrite itself.

Public [API exports](../src/valpas/comparison/__init__.py):

```python
from valpas.comparison import (
    load_manifest, compare_results, write_comparison,
    load_comparison_bundle, ReportSettings, ProfileData, load_profile_data,
)
result = compare_results(load_manifest("tests/comparison/fixtures/demo-01/manifest-with-profiles.json"))
write_comparison(result, "api-report", report_settings=ReportSettings(
    query_ids=("M01",), max_interactive_depth=5, pinned_candidate_ids=("P03",),
))
restored = load_comparison_bundle("api-report")
write_comparison(restored, "api-regenerated")
```

For in-memory inputs, pass validated optional profiles to [compare_results()](../src/valpas/comparison/engine.py:247). The [input schema guide](COMPARISON_SCHEMA_V1.md) documents score/rank completeness, legacy count strings, self exclusion, pool policies and denominators. All ten A2 tables remain complete; optional profiles add two tables. Every canonical CSV data cell is JSON-encoded, retaining exact IDs and precision. No separate spreadsheet-safe copy is supplied; treat canonical files as machine-readable data, not formulas for spreadsheet execution.

## Safety and limitations

Local does not mean anonymized. Canonical IDs, signed scores, configurations, observation IDs and profile values can be sensitive. Metadata omission removes output labels/provenance/configuration values, dataset descriptive context/evidence/observation IDs, profile values/labels/annotations and attestation statements **from HTML only**. IDs, scientific values, statuses/reasons and warnings remain. The full bundle is deliberately **not redacted** so it can regenerate. Inspect before sharing; share only the HTML when using omission. This is not an anonymization guarantee.

Embedded JSON escapes script closers and special Unicode separators. Imported text uses text-only DOM updates; no imported hyperlinks or dynamic markup are rendered. Content Security Policy prohibits connections and external resources. No browser storage, downloads, server or filesystem API is required. UI pins reset on reopen. B1 group/metadata overlays and covariance diagnostics, B2 references/notes/sessions/publication figures, and B3 production export hooks and target-scale validation remain unfinished.

## Validation and manual smoke checklist

Automated [A3 contract tests](../tests/comparison/test_a3_report.py) cover profiles, masks/alignment, parity, source-free reload/re-export, size rejection without partial publication, metadata omission, corruption, API/CLI and resource lookup outside the workspace. The [real-browser test](../tests/comparison/test_a3_browser.py) uses an already installed Chrome/Chromium and direct-file loading with external hostname resolution disabled. It installs nothing; environments without that browser explicitly skip it.

For manual visual validation: open a report with networking disabled; select a heat tile and depth point; search/sort queries; select a candidate; change depth and output visibility; pin/search an ID; inspect scatter/sample marks and hover values; verify unknown/missing profiles show reasons; open no-profile and metadata-omitted reports; move the HTML alone and reopen. Inspect layout, keyboard focus, small-screen scrolling and long/duplicate Unicode labels. Automated interaction is not a pixel-level accessibility or cross-browser certification.
