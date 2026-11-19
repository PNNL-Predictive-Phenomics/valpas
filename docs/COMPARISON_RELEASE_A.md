# Offline saved-output comparison: saved-data workflow

B3 adds [opt-in production sidecars and metadata capture](COMPARISON_PRODUCTION.md), an executable production example, final distribution checks and measured scale limits. This guide retains the overview-first B2 workflow below; the historical filename does not limit its scope.

The historical filename is retained for existing links. B2 supplies the saved-data workflow; B3 adds production integration and explicit scale measurements, with dense target-scale completion still unverified.

Compare **two or more saved association outputs**, not measurement matrices alone. Two methods, configurations, or distinct runs of one configuration are supported. Protein-only, gene-expression-only, and cross-modality comparisons use the same exact-ID rules. No training, scoring, models, network access, or target query is required. Agreement is not correctness, and seeds are not biological replicates.

## CLI-first quick start

From a source checkout with Python 3.12+ and project dependencies installed, run the [CLI](../src/valpas/cli.py:304) against the [combined B2 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b2.json). Choose new destinations; write figures outside the bundle:

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-b2.json --outdir demo-b2 --pool common --depths 1 2 5
PYTHONPATH=src python3 -m valpas.cli export-query --bundle demo-b2 --query M01 --candidate P01 --layer b1-observed --output query-figure.svg
PYTHONPATH=src python3 -m valpas.cli export-query --bundle demo-b2 --query M01 --candidate P01 --layer b1-observed --color condition --group condition --order metadata --h 1 --omission --output query-figure.pdf
```

Open the generated report in the bundle (the HTML filename is defined by the [writer](../src/valpas/comparison/report.py:357)). The combined demo supplies B1 profiles/metadata/diagnostics plus three independent reference endpoints and explicit group weighting. The common pool and depths 1, 2, 5 above are deliberate overrides: defaults remain strict and 5, 10, 20. No query is required to create the all-query comparison. The later figure commands select one inspected pair, not the comparison cohort. For rankings without measurement data, the [no-profile manifest](../tests/comparison/fixtures/demo-01/manifest.json) remains available.

Open the generated report directly from disk in a modern browser. The single HTML file contains its script, styles, data and inline SVG. It needs no server, CDN, connection, local-file fetch or filesystem permission. The remaining bundle files are for complete scientific export and regeneration, not browser dependencies. Copying only the HTML is sufficient to browse it.

For synthetic measurement profiles, use the [profile manifest](../tests/comparison/fixtures/demo-01/manifest-with-profiles.json) and [explicit profile layers](../tests/comparison/fixtures/demo-01/profiles.json):

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-profiles.json --outdir demo-profiles --pool common
```

These are synthetic illustration values, **not measurements used to derive the fixture scores**. Their relationship to every algorithm layer is explicitly “different.” The no-profile report remains fully usable for rankings and agreement.

For B1 overlays and diagnostics, use the separate [B1 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b1.json), [metadata](../tests/comparison/fixtures/demo-01/sample-metadata.json) and [hand-calculable profiles](../tests/comparison/fixtures/demo-01/b1-profiles.json). It references the same saved scores without changing the original A3 fixture:

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-b1.json --outdir demo-b1 --pool common
```

The [API example](../examples/compare_saved_results.py) remains a B1-focused illustration. It prints the all-query overview first, checks the influential-point and marginal-group hand calculations, writes HTML and complete tables, then reloads and checks all-table parity. Its historical printed B2-incomplete message is superseded by the integrated completion record; the example's executable logic is unchanged in this documentation-only update. One requested diagnostic pair is optional export scope, **not a required target or a restriction on the comparison overview**:

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

## B1: metadata overlays, grouping and descriptive omission

After selecting an embedded query/candidate and layer:

1. Choose **Color by**: condition, batch, genotype or any supplied categorical field, or a continuous field such as time. Missing records/fields/nulls are shown as missing (gray/dashed), not converted to zero or a new biological group. Hover includes exact ID, value and metadata status. Hollow orange still means finite originally unobserved/imputed, regardless of overlay.
2. Choose **Sample display order** explicitly: dataset order, exact observation-ID order, or selected metadata order. Missing metadata sorts last for metadata order; equal values use exact Unicode IDs. Coloring/order are display state only, not scientific identity, cohort filtering or ranking settings.
3. Choose a categorical **Marginal grouping (separate from color)** field and optionally **Include between-group / total SS fraction**. Each feature gets its own observed-finite, known-group marginal cohort, with required/known/observed/included counts and exact exclusions. Missing group takes precedence over not-observed-finite, so exclusion counts never overlap. Continuous fields color points but are not automatically binned into groups.
4. Inspect signed joint-centered products, absolute shares, and **Largest absolute products h** (default 5). Ties use exact observation-ID Unicode order. Enable **Preview omission and recenter remaining pairs** explicitly; changing h resets the preview. Selected observations are removed only from this descriptive preview, both retained profiles are recentered, and original/remaining sample covariance and correlation have separate availability reasons. At least three joint/remaining points are required; correlation additionally needs nonzero variance.

In the [B1 demo](../tests/comparison/fixtures/demo-01/README.md), choose M01/P01, h = 1 and omission: S06 contributes 10/13 of absolute products, covariance changes from 26 to 2.5 after recentering, and correlation remains 1. Condition groups include four samples, with total SS 5, between-group SS 4 and fraction 0.8. The absent S06 metadata record does not remove it from covariance. M02 is constant; P02 illustrates imputed/null mask exclusions. Zero total group variation makes the fraction unavailable, not zero. Zero absolute-product sum, too few observations, unknown masks/missing required profiles, and nonfinite arithmetic have explicit unavailable reasons; numeric_range identifies arithmetic limits.

These are **observed-data descriptions**, not causal effects, adjusted variance components, automatic confounding corrections, model attribution or leave-one-out model evaluation. They do not retrain, calculate new association scores, alter saved scores or change ranks. No universal biological-quality threshold is inferred.

Metadata is optional and exact-ID keyed with unique nonempty IDs, declared categorical/continuous types, no coercion, and a complete matching dataset binding. Missing records/fields are allowed. Extra IDs require explicit subsetting permission and remain disclosed outside the diagnostic cohort. Profiles still obey original-mask rules; finite imputed values never enter observed-only summaries.

Browser calculations are **on demand for embedded pairs**, independent of the manifest's optional [diagnostic_requests](../src/valpas/comparison/adapters.py:386). Export requests name exact pair/layer, h, omission and optional categorical grouping/fraction; they do not compute the whole pair universe or save subsequent UI choices. Metadata can be supplied without profiles or requests. See the [exact API, request, nested-table and status reference](COMPARISON_SCHEMA_V1.md#b1-sample-metadata-and-requested-diagnostics).

## B2: interpret reference endpoints before filtering

References are optional, local and explicitly bound to the dataset. Use the overview's reference summaries before selecting a query. Each **source/version/evidence type/support class** is its own endpoint: reaction-direct, reaction-inferred and pathway co-membership are never unioned into a biological truth set. Multiple evidence records for one query/candidate remain inspectable but count as **one supported pair**.

- **Reference-supported fraction** = supported nominations / actual nomination-list size, not requested depth and not biological precision.
- **Recovery** = supported nominations / known reachable support. A zero or unknown denominator gives unavailable/null, not zero recovery.
- **Reachability** = reachable support / total known support. A zero or unknown total likewise gives unavailable/null.
- Distinguish assessed-zero, unassessed, unreachable, unavailable and limited-depth. All-assessed summaries include zero-opportunity queries; the reachable cohort requires known positive reachable support. Opportunity strata are **0, 1, 2–5, 6+**; unknown reachability is not stratum zero.
- Default weighting gives each evaluable feature equal weight. Explicit group weighting first averages evaluable features **within each group**, then equally averages nonempty groups; it does not select the best peak. Each metric exposes its own denominator/exclusions. Output/run summaries remain independent.

In the [combined fixture](../tests/comparison/fixtures/demo-01/README.md), both queries belong to G1 and weighting is explicitly group-based. Select M01, use sufficient depth (for example 5), and inspect reference endpoint/filter controls: all candidates are P01/P02/P03; direct-supported shows P01, inferred-supported P02, pathway-supported P03, and direct-unsupported P02/P03. M01/P01 has two direct evidence records but only one support pair. For M02, inferred is unassessed, pathway is assessed-zero, and direct support lies outside the reachable pool. Outside-universe and unassessed candidates are not simply unsupported by the selected source.

Evidence filters change **candidate display only**—never nominations, ranks, pools, scientific identity or denominators. Missing reference evidence is not a biological negative. Full-cohort reference summaries survive reduced HTML detail scope. See the [reference mathematics and schema](COMPARISON_SCHEMA_V1.md#b2-reference-evidence) and independent [known-math fixture](../tests/comparison/fixtures/b2-reference/README.md).

## B2: decisions, downloads and strict restoration

1. Select a query/candidate and inspect output identities, native scores/ranks, endpoint evidence and optional profiles/B1 diagnostics. Choose **investigate** for a candidate to pursue or **retain alternative** for a candidate to keep in consideration. Enter a **nonblank rationale** for every decision; optional notes are separate.
2. To defer the query rather than nominate a candidate, choose **abstain**. Both its decision and saved snapshot have a null candidate. These are user judgments, not automatic model labels. Every action retains a unique action ID, UTC timestamp, scientific comparison ID, pool/depth, inspected outputs and the full view snapshot.
3. Explicitly download **session JSON** or **shortlist JSON** to retain the current view, notes and decisions (including abstentions). Keep the matching HTML or complete bundle: these documents store inspection state, not duplicate scores/profiles. There is no browser storage or automatic write; unsaved edits are lost on reopening.
4. Download **shortlist CSV** only for spreadsheet display. Every data cell is apostrophe-prefixed to prevent formula execution. CSV is **not importable** and is not a substitute for canonical JSON. Scientific-table CSV has a different machine-readable JSON-cell contract.
5. Use the separate session/shortlist file inputs to import the corresponding JSON (maximum 50 MiB). Import **atomically replaces** view, notes and decisions; it does not merge. Reimporting the same document is idempotent. Invalid/tampered content is rejected without changing the existing state.

Restoration requires exact scientific comparison identity, separate descriptive **content identity**, and **report scope**. Content binds the complete dataset/descriptive output metadata, profiles, sample metadata and reference provenance. Scope separately binds embedded queries/candidates, depth, pins, omission, output/layer inventory, metadata fields and endpoints. Even an expanded scope requires explicit rebinding; a matching comparison ID alone is insufficient. Unknown fields, altered checksums and incompatible settings are rejected, not migrated or clamped.

Use [`load_session(..., result=result, settings=settings)`](../src/valpas/comparison/session.py:347) or the corresponding shortlist loader for authoritative validation; without a result, loading checks structure/integrity only. [`Session.rebind_scope(result, settings)`](../src/valpas/comparison/session.py:277) is **Python-only and explicit**, permitted only when all current settings and every decision snapshot survive unchanged. No decisions are dropped. The [session API example and schema](COMPARISON_SCHEMA_V1.md#b2-portable-sessions-user-decisions-and-shortlists) show exact operations.

An initial session can be attached with [`write_comparison(..., initial_session=session)`](../src/valpas/comparison/report.py:357); it is an inventoried document, not an extra scientific table. By default the writer retains an attached session. To detach, explicitly replace the result's initial-session field with null through the Python result API; passing the default writer argument does not detach it. Exporting metadata-omitted HTML with an attached initial session is rejected. Notes entered afterward in an omitted report still appear in downloads. Hashes detect corruption, **not authentication or authorship**.

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

The UI distinguishes outside-detail-scope queries and searches only embedded labels/annotations/candidates. No match is not evidence of absence. Re-export with the exact query/candidate IDs needed; candidate IDs must exist on a declared axis. Browser pins and B1 settings can now be persisted through explicit B2 session/shortlist downloads; see the [session schema and API example](COMPARISON_SCHEMA_V1.md#b2-portable-sessions-user-decisions-and-shortlists).

Over-budget reports fail before publication with the measured payload size and explicit remedies: reduce detail queries/depth/pins, omit metadata, raise the explicit budget, or use tables-only. There is **no silent sampling or omission**. The budget includes embedded **sample metadata**, profiles and all other escaped JSON; reducing detail queries does not automatically subset metadata records. Whole-cohort agreement data still scales with query × output-pair × report-depth counts; subset export is not a guarantee of small payload or low peak memory. The exporter currently constructs the payload before checking its serialized size. B3 target-scale performance is unverified.

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

[`write_comparison()`](../src/valpas/comparison/report.py:357) defaults to HTML plus complete tables; explicit tables-only remains supported. It writes **result schema v3**, including when optional data is absent. [`load_comparison_bundle()`](../src/valpas/comparison/report.py:266) accepts A2 v1, A3 v2 and B1/B2 v3 bundles. Input/scientific schemas and comparison identity policy remain version one. Version two added report settings, normalized optional profiles, profile tables, report-view payload and HTML. Version three adds sample metadata/requests and optional B1 tables, plus strict optional schema-v1 reference and session extensions. The combined demo has **20 tables**; an attached session adds a document, not a table. See the [exact schema and inventory contract](COMPARISON_SCHEMA_V1.md).

The loader checks normalized contracts, identity, warnings, checksums, exact table parity and applicable report parity. It uses saved normalized values, not original source paths or models. Reload requires the **same software/policy versions** and expected schemas; older schema support is not cross-software-version migration. Old HTML/assets are verified against their stored inventory checksums, not today's asset bytes; stored/embedded payload is checked against normalized saved values/settings, with payload hash/size/budget checks. Known old-shape projection is allowed only where documented in the schema guide. Session-bearing bundles retain exact complete session/payload checks, even when their assets predate figure downloads. Regeneration writes current assets and v3, subject to the current budget. Report settings, profiles, metadata and requests do not change the scientific comparison ID; inventory and normalized-content checks protect their persistence.

```sh
PYTHONPATH=src python3 -m valpas.cli compare --bundle demo-b2 --outdir regenerated
```

Bundle regeneration preserves scientific settings; pool/depth analysis overrides are rejected with bundle input. Original input files are not reopened: retain the complete bundle for reproducibility. A different report scope is possible without a session, but attached sessions require exact scope or an explicit valid Python rebind; never silently change/drop decisions. Use a new directory. Default publication refuses existing paths, including empty directories. Explicit overwrite accepts only an intact owned comparison bundle with no foreign files or consumed inputs. Staging, validation, sibling rename and rollback protect the prior bundle. A loaded bundle cannot overwrite itself.

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

For in-memory inputs, [`compare_results(inputs, settings=None, *, dataset=None, profiles=None, sample_metadata=None, diagnostic_requests=(), references=None, query_groups=None)`](../src/valpas/comparison/engine.py:297) accepts validated profiles, sample metadata, reference and query-group objects, and an explicit list/tuple of [`DiagnosticRequest`](../src/valpas/comparison/diagnostics.py:121) objects or request dictionaries. [`load_sample_metadata(value, *, base_dir=".")`](../src/valpas/comparison/diagnostics.py:105) loads inline metadata or a local JSON path descriptor. Direct [`group_summary()`](../src/valpas/comparison/diagnostics.py:188) and [`covariance_diagnostic()`](../src/valpas/comparison/diagnostics.py:320) helpers return the same nested results as requested exports. For manifest input, default null optional inputs inherit the manifest, the default empty request tuple inherits manifest requests, and an explicit empty request **list** clears them. See the [schema/API reference](COMPARISON_SCHEMA_V1.md) for removing inherited reference inputs.

The [schema guide](COMPARISON_SCHEMA_V1.md) documents exact signatures, score/rank completeness, legacy counts, self exclusion, single-modality usage, pools and denominators. All ten A2 tables remain complete; optional profiles add two tables. Metadata adds a long-form metadata table even without requests; requests add one diagnostic row each and optional deduplicated per-feature/layer/field/fraction group summaries. Every CSV data cell is JSON-encoded, including nested result objects, namespaces, nulls and booleans. No separate spreadsheet-safe copy is supplied; treat canonical files as machine-readable data, not formulas for spreadsheet execution.

## Explicit query figures

Use the [CLI-first figure guide](COMPARISON_FIGURES.md) for source-free SVG/PDF from a full bundle, optional metadata/diagnostics and strict saved session/decision views. The public [figure exporter](../src/valpas/comparison/figures.py:261) lazily imports Matplotlib only for actual rendering. Choose explicit IDs/layer and a new caller-named file outside the bundle; existing paths are never overwritten. Scatter is jointly observed finite only; profiles distinguish imputed values and captions disclose masks, counts, units/transform, overlay, pool/depth and descriptive interpretation, never model attribution.

The browser's explicit per-layer SVG download is bounded to embedded data and warns that it is not identical to Python vector output. Notes and annotations remain literal and may be sensitive. Full Python export can use declared features omitted from the browser. No new strict session fields are introduced.

## Safety and limitations

Local does not mean anonymized. Canonical IDs, signed scores, configurations, observation IDs, metadata and profile values can be sensitive. Metadata omission removes output labels/provenance/configuration values, dataset descriptive context/evidence/observation IDs, profile values/labels/annotations, **sample metadata** and attestation statements **from HTML and its report-view payload only**. Canonical feature IDs, scientific values, statuses/reasons and warnings remain. The full bundle—including normalized metadata/profiles and requested diagnostic tables—is deliberately **not redacted** so it can regenerate. Inspect before sharing; share only the HTML when using omission. This is not an anonymization guarantee.

Embedded JSON escapes script closers and special Unicode separators. Imported text uses text-only DOM updates; no imported hyperlinks or dynamic markup are rendered. Content Security Policy prohibits connections and external resources. No browser storage, server or automatic filesystem writes are used. Explicit session and shortlist JSON downloads and file-input imports persist user decisions, notes, pins and B1 view settings; without an initial session or explicit import these reset on reopen. Shortlist CSV is spreadsheet-safe display text, unlike canonical scientific table CSV. Notes/rationales and reference selections may be sensitive; metadata omission does not redact newly entered notes, and an initial session must be explicitly detached before omitted-HTML export. Full bundles retain references and sessions. See the [B3 production guide](COMPARISON_PRODUCTION.md) for integration and measured scale limitations.

## Validation and manual smoke checklist

[Integrated B2 evidence](../plans/B2_VALIDATION_HANDOFF.md) retains its historical counts and artifact chronology. The [B3 validation record](../plans/B3_VALIDATION_HANDOFF.md) records production-boundary regressions, final artifacts/browser checks and the target-scale bounded stop. Retained isolated full-dependency environments are not fresh dependency resolution. Other OS/Python/browser combinations, manual visual/accessibility certification, Sphinx and broad training suites are not implied.

For B2 manual inspection, follow the endpoint/filter example above; save investigate/retain-alternative/abstain decisions with rationales; download both JSON forms and CSV; alter the view, then import each JSON twice and verify exact restoration without duplicates. Try a mismatched document and verify rejection preserves the old state. Download the bounded browser SVG and compare its stated scope with the CLI's full-bundle SVG/PDF—not identical layout or bytes. Inspect sensitive notes/captions before sharing.

Automated [A3 contract tests](../tests/comparison/test_a3_report.py) cover profiles, masks/alignment, parity, source-free reload/re-export, size rejection without partial publication, metadata omission, corruption, API/CLI and resource lookup outside the workspace. The [real-browser test](../tests/comparison/test_a3_browser.py) uses an already installed Chrome/Chromium and direct-file loading with external hostname resolution disabled. It installs nothing; environments without that browser explicitly skip it.

B1 has focused [diagnostic/metadata tests](../tests/comparison/test_b1_diagnostics.py), [persistence/scope tests](../tests/comparison/test_b1_persistence.py), and [browser parity/interactions](../tests/comparison/test_b1_browser.py), with independent hand-calculated fixtures. They cover missing groups, masks, recentering, constant/zero denominators, numeric range, exact Unicode ties, HTML-only omission and unchanged scientific identity/tables.

For manual visual validation: open a report with networking disabled; select a heat tile and depth point; search/sort queries; select a candidate; change depth and output visibility; pin/search an ID; inspect scatter/sample marks and hover values; verify unknown/missing profiles show reasons; open no-profile and metadata-omitted reports; move the HTML alone and reopen. In the B1 demo, try categorical and continuous colors, missing-metadata hovers, each display order, condition/batch grouping, fraction toggle, h = 1 and explicit omission; confirm saved ranks do not change. Inspect layout, keyboard focus, small-screen scrolling and long/duplicate Unicode labels. Automated interaction is not a pixel-level accessibility or cross-browser certification.

The [distribution validation guide](DISTRIBUTION_VALIDATION.md) supplies a repeatable full-dependency gate for both the checkout wheel and a wheel rebuilt from the extracted sdist. It checks installed resource bytes, outside-checkout CLI exports, original-input deletion and regeneration, complete table parity, real direct-file browser interactions and legacy imports. It downloads dependencies only into private environments. Comparison examples, guides and demo fixtures are sdist/source files; only package code and browser assets are installed by the wheel. Source regression tests alone are not evidence of a successful artifact installation.
