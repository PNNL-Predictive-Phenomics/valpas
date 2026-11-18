# Implementation plan: within-dataset method comparison

**Status:** A0 implemented; focused validation passed with three dependency-blocked legacy import checks (see below). A1–B3 remain unimplemented.

**Requirements:** [development handoff](valpas_method_comparison_development.md). This plan turns that handoff into implementation increments and acceptance gates; the handoff remains the scientific specification. Both Release A and Release B are in scope. This work does not depend on completing CLI autoencoder training support.

## 1. Scope and invariants

Build a local workspace for inspecting saved nominations from the same dataset. It compares outputs, not fitted model objects, and must distinguish methods, configurations, and runs.

All increments preserve these invariants:

- No training, new association scoring, checkpoint loading, remote access, or automatic annotations.
- Identity and eligibility come from explicit metadata and identifiers, never matrix shape or overlapping labels alone.
- Native scores retain their sign, precision, and units. Ranks always have an explicit policy and pool.
- Missing, unscored, ineligible, truncated, and unassessed are distinct statuses; unavailable metrics are not zero.
- Recurrence across runs is separate from agreement across methods/configurations. Neither is correctness, confidence, or a consensus ranking.
- Profile diagnostics describe observed data, not attribution of an autoencoder nomination.
- Existing result objects, legacy exports, and training behavior remain unchanged except for opt-in metadata/export additions.

The feature is not complete at Release A. Release B delivers metadata overlays, diagnostics, reference evaluation, portable decisions, and publication figures.

## 2. Targeted findings and integration decisions

| Current integration point | Finding | Planned action |
| --- | --- | --- |
| [Package initializer](../src/valpas/__init__.py:28) | Importing a subpackage first executes the root initializer, which eagerly imports training and other analysis modules. | Introduce narrowly scoped lazy public exports, preserving existing names. Test both lightweight comparison imports and legacy public imports. Merely avoiding a direct training import in the comparison package is insufficient. |
| [CLI imports](../src/valpas/cli.py:9) | The entry module imports experiment, processing, and visualization dependencies before dispatch. | Move legacy dependencies to their command handlers as necessary; add comparison handlers without duplicating scientific calculations. Do not refactor classical analysis behavior. |
| [Association result container](../src/valpas/_core/classes/results.py:297) | Score/count matrices are directly available. List conversion and saving modify metadata or matrices. | Copy matrices and explicitly selected axes through a structural adapter; never call the old list/save methods during comparison. |
| [Legacy conversion](../src/valpas/io.py:318) | Conversion and writing drop all-missing axes; legacy score/count serialization can lose precision. | Implement dedicated read-only legacy parsers with required completeness/provenance declarations. Do not reconstruct lost information. |
| [Autoencoder persistence](../src/valpas/_core/autoencoder.py:1590) | A labeled similarity CSV is saved separately from a serialized checkpoint. | Load only the CSV and supplied descriptor. Never use the model loader. |
| [Association entry point](../src/valpas/valpas_core.py:21) | Performs computation and saving. | Do not call it to compare saved outputs. Later attach opt-in metadata capture at natural result-construction boundaries, before mutating legacy export. |
| [Package configuration](../pyproject.toml:60) | Source distribution explicitly includes only the source tree. | Verify assets in wheel and source distribution; explicitly include the documented comparison example/fixtures as appropriate. Test installed-package asset lookup rather than repository-relative paths. |

No broad redesign of the existing confidence, result, or training systems is required.

## 3. Proposed design decisions

### Public contracts

Use standard-library dataclasses/enums and explicit validation rather than adding a mandatory schema framework. The canonical schema is version 1. Publish a field/status reference and example manifest; reject unsupported versions, unknown substantive settings, and nested misspellings.

Implement the handoff's proposed contracts and API names in the new [comparison package](../src/valpas/comparison/__init__.py):

- [ComparisonInput](../src/valpas/comparison/models.py:1), [ComparisonSettings](../src/valpas/comparison/models.py:1), [ProfileData](../src/valpas/comparison/models.py:1), [ReferenceData](../src/valpas/comparison/models.py:1), and [ComparisonResult](../src/valpas/comparison/models.py:1).
- [load_comparison_input()](../src/valpas/comparison/adapters.py:1), [from_association_result()](../src/valpas/comparison/adapters.py:1), [compare_results()](../src/valpas/comparison/__init__.py:1), [write_comparison()](../src/valpas/comparison/report.py:1), and [export_query_figure()](../src/valpas/comparison/report.py:1).

Add narrowly scoped helpers for manifest loading, comparison-ready input export, and saved-bundle loading. The bundle loader is necessary for offline report regeneration, session validation, and figure export without original source paths. Finalize these helper names in A1 before documentation/examples depend on them.

The locations above are proposed new files, not existing implementations.

### Internal representation and scaling

- Keep output-level labeled numeric arrays, compact status masks, and metadata separate from display labels.
- Retain native and active rank views explicitly; rank only known finite eligible values or certified saved order.
- Represent limited inputs sparsely with declared universes and status metadata. Do not expand unknown omissions into fabricated ranks.
- Process one query or bounded query block at a time for ranking, agreement, and table export. Avoid a giant pandas table with repeated strings as the primary in-memory representation.
- Expose complete tables through bounded iterators/materialization helpers in the result API; small summaries can remain DataFrames.
- Store each profile once per feature/layer; compute pair diagnostics only for requested pairs.

The target scale contains 40 million query/candidate/output entries before profiles. Full long-table export is appropriate, but simultaneous dense arrays plus multiple expanded string tables is not.

### Offline UI and persistence

Prefer packaged vanilla JavaScript/CSS and SVG profile rendering; use Matplotlib for Python SVG/PDF export. This avoids a web framework and a mandatory browser automation dependency. Existing Plotly remains an option if its runtime is embedded and included in the size budget.

The report must open directly from disk with all required assets/data embedded. Do not use local-file fetch requests for companion tables. Complete tables remain in the bundle; the browser embeds the declared candidate union and pinned IDs only.

Browser depth/output/filter controls operate within the exported scope. Hiding an output does not redefine a common pool. Changing the included comparison cohort requires explicit re-comparison of saved results, never silent reranking during display filtering.

### CLI surface

Add a manifest-driven **compare** command with required **--manifest** and **--outdir** options. Allow limited overrides for pool policy, interactive depth, tables-only export, and overwrite; record all resolved settings.

Add **export-query** for a saved comparison bundle with explicit query/candidate, layer, and output destination. Both commands delegate to the public API. Training configuration and the earlier autoencoder CLI proposal are separate concerns.

## 4. Implementation increments

### A0 — Lightweight entry points and baseline fixtures

**Purpose:** remove the import barrier and establish deterministic expected behavior before building the engine.

Deliverables:

1. Narrow lazy-import changes to the root package and CLI, preserving public names and old command behavior.
2. A score-only synthetic fixture: two queries, three candidates, six observations, one Pearson output, and two AE runs sharing one complete non-seed configuration.
3. Positive/negative Pearson scores, one missing score in the second query, explicit namespaces/source identity, and manually calculated expected ranks/overlaps.
4. Subprocess import tests that reject loading training modules or changing global warning filters during saved-score comparison imports.

**Acceptance:** comparison imports and command help can load without importing autoencoder/training code; representative legacy imports still resolve. The fixture explicitly has two methods, two configurations, and three outputs.

**Specification clarification:** Section 5.4 mentions two matrices but names three outputs. Ship three saved output files, one for each named output; no fitting is needed.

#### A0 implementation and validation record

- [Root exports](../src/valpas/__init__.py) now resolve lazily, retaining the existing public names, version attributes, and cached object identities. Discovering public names does not load analysis modules.
- [CLI dependencies](../src/valpas/cli.py) are imported inside their consuming handlers/helpers. Existing parser options and scientific calculations are unchanged.
- The [comparison namespace](../src/valpas/comparison/__init__.py) is deliberately only an import-safe entry point: no production comparison APIs, loaders, schema, engine, or new commands have been introduced.
- The [saved-score fixture](../tests/comparison/fixtures/demo-01/README.md) includes three matrices, explicit synthetic provenance/configuration records, and hand-calculated expected orders, pools, exclusions, and overlaps. Its metadata is test scaffolding, not the finalized A1 manifest schema.
- [Import/compatibility tests](../tests/comparison/test_import_isolation.py) use fresh subprocesses and reject attempted heavy imports, loaded heavy modules, and warning-filter changes on lightweight paths. They cover all nine existing help/no-argument paths, public discovery/version behavior, lazy caching/retry, real legacy export identity, and mocked legacy CLI dispatch.
- [Fixture tests](../tests/comparison/test_reference_fixture.py) check inventory, source/observation bindings, signed scores, missing status, orders, strict availability, common pools, and hand-calculated metrics. These checks do not claim validation of a future production engine.

Validation on 2026-11-18 with Python 3.12.3: standard-library unittest discovery over [the A0 tests](../tests/comparison/) ran **20 tests: 17 passed, 3 skipped**. Real imports of the two experiment classes and the autoencoder module were blocked by missing PyTorch. The remaining six real legacy exports passed. Pytest is also unavailable in this interpreter; these unittest tests are compatible with pytest when installed. Focused source/test compilation and Git whitespace checks passed. No dependencies were installed and no training was run. Full-dependency legacy import validation remains outstanding; earlier documentation, Sphinx, and cross-attention checks are separate follow-up work.

### A1 — Contracts, adapters, compatibility, ranking

Implement [models](../src/valpas/comparison/models.py), [adapters](../src/valpas/comparison/adapters.py), [compatibility](../src/valpas/comparison/compatibility.py), and [ranking](../src/valpas/comparison/ranking.py).

Deliverables:

1. Versioned manifest/output/settings contracts, structured errors with field/output/reason/remediation, and explicit unknown metadata.
2. Local manifest-relative loading; exact string IDs; permitted JSON/CSV/TSV and optional non-object NumPy files only.
3. Read-only adapters for labeled matrices, long scores, full rank permutations, complete ordered ranks, certified prefixes, and inspection-only filtered lists.
4. Legacy score/count parsing, precision warnings, and declared-symmetry expansion with conflicting reciprocal checks.
5. Detached in-memory result adaptation and an opt-in full-precision comparison-ready input bundle exporter.
6. Dataset/observation/namespace validation, specific legacy attestations, configuration-difference tables, and configuration/run grouping validation.
7. Deterministic ordinal ranking for all four policies, Unicode ID tie breaks, and namespace-aware self-edge exclusion.
8. Strict, common, and native-inspection pool construction with complete exclusion/status records.

**Acceptance:** hand-calculated ranks match; reordered IDs align; score signs remain unchanged; source objects are unmodified; known identity mismatches cannot be overridden; truncated lists cannot enter common-pool reranking; conflicting scores/ranks and malformed permutations fail.

### A2 — Comparison engine, bundle export/reload, CLI

Deliverables:

1. Public orchestration requiring at least two outputs, including valid comparisons of two runs from one configuration.
2. Candidate ranks, coverage/exclusions, pairwise agreement and classifications, run recurrence, and dataset summaries.
3. Requested versus effective depths, complete denominators, and explicit unavailable reasons. Native unequal-length lists use directional fractions rather than a false shared denominator.
4. Full available rank export, compressed/chunked long tables, output inventory/schema records, resolved settings, and stable content/settings comparison ID.
5. Source fingerprints calculated during ordinary reading; deterministic in-memory fingerprints include IDs, values, and statuses. Paths/timestamps do not define comparison identity.
6. Bundle reload and tables-only output, with explicit completion state and inventory checks.
7. Temporary-sibling staging and publication after successful writes. Default destination refusal; overwrite limited to recognized owned bundles and prohibited where it could remove source inputs or unrelated files.
8. CLI dispatch to the same loader/engine/writer used by Python, concise summaries, nonzero error exits, and actionable empty-common-pool errors.

**Acceptance:** API and exported values agree; strict finite-score gaps produce unavailable controlled metrics; common ranks are restrictions of saved scores/order; missing runs are not silently removed from recurrence denominators; bundle reload reproduces numerical tables; interrupted output is never marked complete.

### A3 — Offline query browser and basic profiles: Release A gate

Implement [profile handling](../src/valpas/comparison/profiles.py), [report rendering](../src/valpas/comparison/report.py), and [packaged assets](../src/valpas/comparison/assets/).

Deliverables:

1. Dataset identity/configuration/coverage overview with separate agreement and recurrence panels.
2. Query search and candidate-union table, native/active ranks, raw scores, statuses, depth controls, sorting, and pinning. Default candidate order is canonical ID.
3. Optional feature-by-observation layers aligned by exact IDs; independent observed masks and explicit unknown mask provenance.
4. Jointly observed scatterplots, feature profiles, coverage counts, and explained unavailable displays. Imputed values are visually distinct and excluded from observed-only calculations.
5. Escaped text/JSON embedding, text-only DOM updates, allowed-link schemes, no remote loads, metadata-omission controls, and optional separate spreadsheet-safe exports.
6. Explicit browser scope and 50 MiB default embedded-payload budget checked before publication; no silent sampling. Support smaller report scope/pinned IDs or tables-only export while preserving full scientific tables.
7. Report regeneration from the saved normalized bundle, without original models or association execution.
8. Release A quick start, schema/legacy-format documentation, and synthetic manifest/example.

**Acceptance:** direct-file offline interaction works; displayed numbers match tables; filters do not change scientific denominators; no-profile mode is usable; malicious labels cannot execute; size-limit failures provide actionable alternatives.

**Release A is usable here, but B1–B3 remain unfinished.**

### B1 — Sample metadata, grouping summaries, influence diagnostics

Deliverables:

1. Metadata keyed by unique observation ID, categorical/continuous overlays, missing metadata indicators, and explicit display ordering.
2. Observed-value group counts/means and optional between-group/total sums-of-squares fraction, with exclusions and zero-variation status.
3. Joint-sample-centered covariance products, signed values and absolute-product shares; largest-h summary with default h of five and ID tie breaking.
4. Explicit omission preview that removes selected observations, recenters, and reports covariance/correlation only with sufficient remaining observations and nonzero variance where required.
5. On-demand browser diagnostics for embedded pairs and matching Python calculations for requested exports; shared hand-calculated fixtures prevent formula divergence.
6. Diagnostic scope, masks, denominators, and reasons in exports and captions.

**Acceptance:** influential-point, zero-denominator, constant-profile, missing-group, and recentering fixtures match expectations. Changing overlays or diagnostic selection leaves saved scores/ranks unchanged. No model-attribution claim appears.

### B2 — Reference evidence, decisions, sessions, figures

Implement [reference evaluation](../src/valpas/comparison/reference.py) and extend reporting/session/figure APIs.

Deliverables:

1. Local evidence import with source/version and assessment coverage; preserve separate pathway and reaction endpoints and direct versus inferred evidence where supplied.
2. Total/reachable support, supported nominations, hit, reference-supported fraction, recovery, and reachability, with explicit assessed/unassessed/unsupported/unreachable statuses.
3. All-assessed versus reachable-query summaries, recorded opportunity strata, and equal-feature or explicit equal-group weighting. Reject ambiguous feature/group membership.
4. Candidate decisions including query-level abstention, notes, inspected outputs, pool/depth, and timestamps.
5. Explicit session/shortlist download and import; comparison-ID matching, ID validation, safe note rendering, and visible migration warnings. Browser storage is optional, not authoritative persistence.
6. Python SVG/PDF query figure export and CLI bundle-based export; browser SVG or print path with documented rendering differences.

**Acceptance:** evidence filtering never changes nominations; duplicated evidence does not inflate support; weighting matches fixtures; session/notes round-trip; figures disclose layer/masks/counts/overlay and regenerate without fitting.

### B3 — Production boundaries, packaging, documentation, final validation

Deliverables:

1. Wire opt-in comparison-ready sidecar export into natural result-creation/export boundaries using the A1 adapter; preserve unknown fields and old filenames/precision.
2. Capture source identity, observations, configuration, supervision, preprocessing, and seed only where actually known. Existing in-memory results can be exported with supplied metadata without fitting again.
3. CLI-first guide covering manifests, complete versus limited inputs, ranking policy, pool choice, run variability, reference limits, profiles, decisions, report limits, and re-export.
4. Synthetic example and expected tables independent of the paper repository. Link from the main user guide and Sphinx navigation.
5. Wheel/source-distribution build/install checks for report assets and example availability.
6. One bounded scale smoke run near 1,000 queries × 5,000 candidates × 8 outputs, recording elapsed time and peak memory. Keep report scope separately bounded; report measurements rather than claiming a performance target was met without evidence.
7. One offline browser interaction check and relevant import/CLI/association/export regressions.

**Acceptance:** a user can generate a comparison, inspect nominations/profiles, save a decision, and export a figure from the shipped saved-data example without the paper repository, downloads, a server, GPU, or model checkpoints. Both releases' acceptance cases pass or are explicitly recorded as unverified.

## 5. Dependency order and review checkpoints

Recommended commit-sized sequence:

1. A0 lightweight imports and fixtures.
2. A1 contracts and adapters.
3. A1 compatibility, pools, and deterministic ranking.
4. A2 engine and metric tables.
5. A2 durable bundles and CLI.
6. A3 offline UI, basic profiles, and Release A documentation.
7. B1 metadata and diagnostics.
8. B2 references and weighted summaries.
9. B2 sessions, decisions, and figures.
10. B3 production export hooks, packaging, and integration finish.

Schema and scientific tests precede UI implementation. Reference evaluation consumes the established pools/ranks; it cannot redefine them. Bundle reload precedes publication figures. Production hooks come after the detached exporter, not before it.

Review the v1 contract/fixtures at the A1 boundary and the usable offline workflow at the Release A boundary. These are ordinary implementation reviews, not an extra authorization framework.

## 6. Focused validation strategy

Split tests by responsibility under the proposed [comparison test directory](../tests/comparison/): contracts/adapters, compatibility/ranking, metrics, profiles/diagnostics, references, export/security, CLI, and integration.

Required guardrails:

- Parameterized identity, orientation, completeness, ranking, and tie fixtures from the handoff.
- Full source-object immutability checks, including axes, metadata, and missing rows.
- Subprocess lightweight-import checks plus training/scoring/checkpoint functions patched to fail if called during comparison, regeneration, or figure export.
- Small mathematical fixtures for overlap/Jaccard, recurrence denominators, group summaries, covariance omission, and reference weighting.
- Export/API parity and normalized-bundle round trips.
- Malicious labels, script-closing strings, Unicode, formula-like IDs, rejected executable/object-array inputs, unsafe links, and untrusted session notes.
- Failure-injected writes, existing-directory refusal, overwrite/source collision protection, and installed-package asset availability.
- One integrated synthetic example and one offline browser check; use existing browser tooling if available, otherwise document a manual check. Do not add a heavy browser dependency solely for this feature.
- One representative bounded scale run; no broad training or performance sweeps.

The earlier environment lacked pytest and Sphinx. Recheck the active development interpreter before validation; report blocked checks honestly rather than treating static compilation as runtime validation.

## 7. Decisions and limitations to keep visible

- Default pool is strict. Default summary depths are 5, 10, and 20; browser maximum is 50, with actual depth bounded by pool size and certified completeness.
- Common-pool reranking is prohibited for truncated input in schema v1.
- Unknown provenance requires field-specific attestations; known mismatches remain errors.
- No default consensus score, automatic best seed, or best-method recommendation.
- Zero reachable reference support makes recovery undefined, not evidence of poor method quality.
- Comparison-ready sidecars are opt-in and cannot recover metadata already lost by legacy exports.
- Offline reports contain embedded scientific data; sharing/privacy controls must describe what is included.
- No implementation estimates are asserted before the schema/UI scope is reviewed. The import isolation, completeness semantics, durable bundle design, and offline payload limit are the highest-risk integration points.

## 8. Definition of done

Release A supplies a trustworthy saved-result comparison engine, machine-readable bundle, CLI/API, offline query browser, and basic profiles. Release B adds diagnostics, source-specific reference evaluation, portable decisions, and reproducible figures. Final completion additionally requires documentation, packaged assets, opt-in production exports, focused tests, and explicit reporting of any unverified browser or scale claims.

No source implementation or analysis execution is authorized by this planning document alone.
