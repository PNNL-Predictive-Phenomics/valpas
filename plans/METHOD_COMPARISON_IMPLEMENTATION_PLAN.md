# Implementation plan: within-dataset method comparison

**Current status — 2026-11-19: A0–A3, B1 and B2 DONE.** Integrated B2 validation passed **232 full-dependency comparison tests, zero skips; 22 packaging-harness tests; 88 installed validation commands; 10 actual direct-file Chrome cases across checkout and Git-free-sdist wheels**. Both wheels used retained isolated full-dependency environments, **not fresh dependency resolution**. B3 production metadata capture/export integration and target-scale validation remain future; **the full Release B/two-release project is not complete**. Result bundles use v3 with strict optional schema-v1 references/sessions; v1/v2/v3 reload is same-software/policy only. Input/scientific contracts remain v1; A1 input bundles are distinct. See the integrated completion record below and [final validation handoff](B2_VALIDATION_HANDOFF.md). Tested artifacts precede this docs-only finalization; no rebuild was performed or claimed.

**Historical packaging evidence only:** the original A3 tree passed **134 full-dependency tests without skips**, **12 packaging-harness tests**, and checkout-wheel/Git-free-sdist-wheel fresh-install, outside-checkout CLI/resource/table/regeneration, real direct-file Chrome and legacy-import checks on macOS arm64 / Python 3.12.3. That resolved the original A3 packaging blocker, but **does not validate subsequently modified B1 code, browser assets, guides or fixtures**. The separate B1 evidence below validates newly built modified artifacts.

**Requirements:** [development handoff](valpas_method_comparison_development.md). This plan turns that handoff into implementation increments and acceptance gates; the handoff remains the scientific specification. Both Release A and Release B are in scope. This work does not depend on completing CLI autoencoder training support.

## 1. Scope and invariants

Build a local workspace for inspecting saved nominations from the same dataset. It compares outputs, not fitted model objects, and must distinguish methods, configurations, and runs.

**Overview-first workflow:** no target metabolite/protein is required up front. Compare all declared queries under the explicit pool policy, inspect overall/query summaries, then drill into selected queries. A3 implements output-pair agreement heatmap tiles and a depth chart with evaluable denominators, separate run recurrence, and query/candidate/profile drilldown.

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

These were target contracts across phases; exact implemented names and module locations are documented in the [schema/API reference](../docs/COMPARISON_SCHEMA_V1.md) and [complete B2 workflow](../docs/COMPARISON_RELEASE_A.md). A3 adds validated profiles/report settings; B1 adds validated sample metadata, requests and observed-data helpers. B2 adds reference/group contracts, strict sessions/shortlists, explicit decisions and full-result/bundle figure export.

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

The [compare command](../src/valpas/cli.py:304) accepts a manifest or saved result bundle and an output directory. A3 defaults to offline HTML plus full tables and supports report query/pin/depth/budget/metadata controls, tables-only export, source-free regeneration and safe overwrite. Manifest analysis pool/summary-depth overrides remain separate from report settings. All resolved settings are recorded.

B2 implements **export-query** for a saved comparison bundle with explicit query/candidate, layer, and output destination, SVG/PDF rendering and optional strict saved-session/decision context. Both commands delegate to the public API. Training configuration and the earlier autoencoder CLI proposal are separate concerns.

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

#### A1 implementation and validation record

Implemented 2026-11-18:

- Standard-library-only [contracts and structured issues](../src/valpas/comparison/models.py), strict nested schema validation, explicit unknown metadata, immutable detached descriptors and pair records.
- [Adapters](../src/valpas/comparison/adapters.py) for labeled/transposed matrices, long scores, full candidate permutations (not inverse ranks), complete ordered ranks, certified native prefixes, inspection-only filtered lists, and legacy score:count matrices. Local UTF-8 JSON/CSV/TSV paths are manifest-relative and contained; unsupported executable/checkpoint/NumPy formats fail. Legacy precision warnings and opt-in symmetric reciprocal expansion are explicit.
- [Compatibility and pools](../src/valpas/comparison/compatibility.py) validate source evidence, exact observation sets, context, namespaces, field-specific legacy attestations and complete non-seed run grouping. Field-level configuration differences, native/active ranks, statuses, coverage and exclusions are retained. Strict finite-set gaps are unavailable; common reranking rejects limited inputs.
- [Deterministic ranking](../src/valpas/comparison/ranking.py) implements all four policies, Unicode candidate-ID tie breaks, unchanged signed raw scores and namespace-aware self exclusion. Prefix depth/exhaustion and native-pool identity are checked; filtered lists never receive a fabricated rank view.
- Detached structural result adaptation copies explicitly selected labeled values/counts without importing the legacy class or calling mutating methods. [Input bundle helpers](../src/valpas/comparison/bundles.py) export full-precision normalized records to a new staged destination and reload via completion/inventory/checksum validation, independently of original files. Existing destinations are always refused; no overwrite mode is provided.
- Published [A1 API and schema](../docs/COMPARISON_SCHEMA_V1.md), [validated demo manifest](../tests/comparison/fixtures/demo-01/manifest.json), and [runnable input inspection/export example](../examples/inspect_comparison_inputs.py). Original A0 metadata, matrices, expected values and tests are retained. No A2 metric/report/CLI APIs or later-phase placeholder contracts were added.

Validation with Python 3.12.3: standard-library unittest discovery over [comparison tests](../tests/comparison/) ran **51 tests: 48 passed, 3 skipped**. All **31 new A1 tests passed**. The skips are the existing A0 real autoencoder/experiment imports blocked by missing PyTorch, not new A1 skips. Tests cover each representation, malformed/nested settings, identity/configuration contradictions, exact/reordered IDs, score signs/ties, permutation semantics, missing/eligibility states, prefix restrictions, source immutability, full-precision roundtrip, unsafe destinations, failure cleanup, and a full load/rank/export/reload path with heavy/training modules blocked and warning state unchanged. The saved-input example, focused static compilation, Git whitespace checks and changed-file review passed. Pytest remains unavailable; test classes support unittest/pytest. No dependencies were installed, training was run, checkpoints were loaded, or remote services were contacted.

Limitations/boundary: optional NumPy support is deliberately omitted. Measurement evidence is validated as supplied rather than recovered from scores. External rank-only tie policies remain declared metadata. Prefixes with mixed/unmatched native-pool certificates remain conservatively unavailable in strict mode; all prefixes are prohibited in common mode. Input bundles have no overwrite support. File parsing currently materializes each input and complete records use Python pair objects; the target-scale compact storage/streaming optimization and benchmark remain unverified later work. A2 metric orchestration/result bundles, A3 profiles/UI/CLI, and B1–B3 diagnostics/reference/production hooks/packaging remain unimplemented. Existing full-dependency legacy import, documentation/Sphinx and cross-attention environmental follow-ups remain separate from this phase.

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

#### A2 implementation and validation record

Implemented 2026-11-18:

- Public [compare_results()](../src/valpas/comparison/engine.py:238) and [ComparisonResult](../src/valpas/comparison/engine.py:136) accept a manifest or at least two normalized saved outputs, including two runs of one configuration. They compare all queries selected by policy without a target feature. Full native/active ranks (including native ranks for common-excluded queries), coverage/exclusions, pair classifications, agreement, separate run recurrence, configuration differences, and dataset/query/distribution summaries are available through bounded iterators/materialization.
- Strict controlled availability remains cohort-wide. Prefix certification is assessed independently at each requested depth; exhausted shorter lists retain honest effective depth. Native unequal-list comparisons expose directional denominators and descriptive Jaccard, not controlled overlap. Missing runs retain the full expected denominator and unavailable recurrence fractions. No consensus, average across run pairs, best-method, correctness or biological-replication claim is made.
- Query-wise [pool iteration](../src/valpas/comparison/compatibility.py:161) supports streamed detail export without retaining expanded rank/recurrence/exclusion tables. Existing A1 pool behavior is preserved. Compact summaries remain in memory; input parsing still uses Python pair objects.
- [Adapters](../src/valpas/comparison/adapters.py:110) hash exactly the source bytes parsed. Canonical normalized hashes include IDs, values, counts, statuses and scientific metadata. Stable comparison identity additionally binds resolved settings and dataset/software/policy versions; transport paths, export timestamps, labels and equivalent axis/output/depth ordering do not define identity.
- [write_comparison()](../src/valpas/comparison/report.py:220) exports normalized gzip JSONL inputs and ten exact-schema CSV tables, compressing long detail tables. Every CSV data cell is JSON encoded. Completion metadata contains inventory/checksums, source fingerprints, versions, scope, settings and warnings. [load_comparison_bundle()](../src/valpas/comparison/report.py:180) validates completion/schema/inventory, normalized content identity and exact table parity without original sources/models.
- Staged sibling publication refuses existing destinations by default. Explicit overwrite fully validates an owned A2 bundle, rejects foreign files/symlinks/source containment, rechecks before mutation, and restores the old bundle if publication fails. A loaded bundle cannot overwrite itself. This is local rename publication with rollback, not crash-durable transactional storage or hostile-concurrency protection.
- [CLI dispatch](../src/valpas/cli.py:332) delegates to public loader/engine/writer, records overrides, prints concise overview/warnings, and fails nonzero with actionable messages. Existing legacy handlers/science are unchanged. No HTML is generated.
- Updated [schema/API guide](../docs/COMPARISON_SCHEMA_V1.md), [README](../README.md), [saved-input example](../examples/inspect_comparison_inputs.py), [fixture guide](../tests/comparison/fixtures/demo-01/README.md), and added the overview-first [comparison example](../examples/compare_saved_results.py).

Validation with Python 3.12.3: standard-library unittest discovery over [comparison tests](../tests/comparison/) ran **89 tests: 86 passed, 3 skipped**. All **38 new A2 tests passed**: [16 scientific engine tests](../tests/comparison/test_a2_engine.py), [17 identity/persistence/safety tests](../tests/comparison/test_a2_persistence.py), and [5 CLI/API/import tests](../tests/comparison/test_a2_cli.py). Coverage includes the independent A0 expected calculations; native unequal lists; missing runs; deep prefix failures; full-rank/common-excluded-query retention; source-byte snapshot hashes; identity invariance/sensitivity; all-table/API parity; deleted-source reload; schema/inventory/content corruption; safe overwrite and injected staging/rename failure rollback; public CLI delegation/overrides/errors; and a fresh-process full A2 path blocking scientific/training imports while preserving warnings. The bounded **20 × 100 × 3** smoke workload exported/reloaded **6,000 rank rows** while forbidding materialized detail tables; it is not the B3 target-scale benchmark.

Both saved-input and A2 comparison examples passed. A separate module-CLI invocation exported/reloaded the common-pool demo successfully using a temporary destination; generated bundles were cleaned up. Focused source/test/example compilation, Git whitespace checks and changed-file review passed. Final focused rerun: 89 tests in 10.231 seconds, 86 passed and 3 skipped.

The three skips remain real legacy experiment/autoencoder imports blocked by missing PyTorch. Pytest remains unavailable; unittest-compatible tests require no installation. No training, new association scoring, checkpoints, network access, broad benchmarks or full training suites were used. Full-dependency legacy import, Sphinx/documentation-build and cross-attention follow-ups remain separate. A3 HTML/browser/profiles and all B-phase features remain unimplemented; no release-complete claim is made. Input compact-storage optimization, software-version migration, installed example/assets packaging and the B3 1,000 × 5,000 × 8 measurement remain unverified future work.

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

**At the original A3 gate, Release A was usable and B1–B3 remained unfinished. B1's later implementation record follows below; this historical gate is not final validation of the modified tree.**

#### A3 implementation and validation record

- Implemented standard-library [profile contracts](../src/valpas/comparison/profiles.py), [bounded report view](../src/valpas/comparison/browser.py), [versioned publication/reload](../src/valpas/comparison/report.py), and packaged vanilla [dashboard assets](../src/valpas/comparison/assets/dashboard.js). No heavy imports, models, scoring, remote loads or new mandatory dependencies.
- HTML defaults on in API/CLI, with explicit tables-only. Whole-cohort overview survives report detail subsets. All ten A2 scientific tables and comparison identity remain unchanged by profiles/report settings. Optional profile tables retain complete values/coverage. Result schema v2 stores report settings, normalized profiles, report-view payload and HTML; v1 result reload is tested. Profile and report-view documents use independent v1 schemas.
- Heatmap/depth selections, searchable/sortable queries, canonical candidate union/pins/search, output visibility and observed/imputed SVG plots are implemented. Original masks, exact alignment, extra-observation exclusions, unknown/missing/constant/near-empty disclosures and algorithm-layer relationships remain explicit. No links, spreadsheet-safe copies or B1/B2 features were added.
- Default payload budget is 50 MiB of escaped JSON before HTML wrapping; oversized reports fail before publication without sampling, preserving existing bundles. Scope is explicit and does not change scientific pools. Metadata omission is HTML-only, not anonymization; complete bundles remain sensitive.
- Python 3.12.3 focused suite: **134 tests, 131 passed, 3 existing torch-related skips**, including the preserved 22 single-modality tests and 23 new A3 tests. Tests cover mask/alignment failures, parity, exact IDs/security, source deletion, regeneration, corruption, budget rollback, CLI/API, same/cross-modality, fixture validation and outside-workspace resource lookup. Existing A2 assertions were changed only for HTML default and the newly supported result schema version.
- **Actual Chrome 157.0.8103.80 direct-file headless interaction passed**, without server or installed automation dependencies, with external hostname resolution disabled and a connection-blocking document policy. Covered overview, chart drilldown, query/candidate search, sorting, depth/output controls, pins, scatter/profiles/hover data, malicious labels, no-profile mode, detail subsets and metadata omission. This is not cross-browser, pixel-level or accessibility certification; a manual checklist is in the [guide](../docs/COMPARISON_RELEASE_A.md).
- Compilation, the runnable saved-comparison example and diff whitespace check passed. Resource loading from a copied package in an external temporary working directory passed. **Wheel/sdist build/install remains unverified:** build, hatchling, hatch-vcs and wheel are absent; no dependencies were installed. Packaging configuration includes source assets and the source-distribution guide/examples/fixtures. Sphinx rendering and full training tests were not run.
- Limitations: JSON-only profile transport; payload built in memory before serialized-size check; whole-cohort report data scales with queries/output pairs/depths; no target-scale benchmark or production-performance claim. UI pins are transient, not portable sessions. B1–B3 stay incomplete.

#### Original A3 packaging/install validation record — 2026-11-19

This record describes the **pre-B1 artifacts**, not a validation of subsequently modified code/assets/docs. Its hashes, versions, tests and limitations are retained as original packaging evidence. References below to unchanged artifacts or unfinished B1 apply at that historical checkpoint only.

- Added the standard-library [distribution validator](../tools/validate_distribution.py), separate [installed smoke assertions](../tools/distribution_smoke.py), [12 focused harness tests](../tests/packaging/test_distribution_validation.py), and [reproduction/cleanup guide](../docs/DISTRIBUTION_VALIDATION.md). The only package-configuration change includes these tools and their guide in the sdist. Existing Seaborn and other dependency declarations needed no fixes. No application or B1 behavior changed.
- Executed `python3 tools/validate_distribution.py --keep-envs`: **passed, 47 commands**, on macOS 26.7.2 arm64, Python 3.12.3, Chrome 157.0.8103.80. Build backend logs record hatchling 1.33.0 and hatch-vcs 0.5.0. All artifacts have the genuine dirty-checkout version **1.0.1.dev29+g1a5f1dd97.d20261119**, from commit 1a5f1dd9763caeac9ac0565f0920d6c40aaa4fe1; no fabricated version or Git dependency in the extracted sdist.
- Checkout wheel and sdist-rebuilt wheel are byte-identical: SHA-256 **c3999a5907b61fa2bf83d7ce26422f4284e30411a1d67800c2d10a11884b127d**. Sdist SHA-256: **e18d93a2cc4aa4c8f10305b3954f3a3bb8f6f92d50e9cd1eeb8842b926d7acfd**. Artifacts precede this plan-only evidence update; packaged application/tools/guides were unchanged afterward.
- Both wheels installed with all 12 declared dependencies into distinct fresh environments; dependency consistency checks passed. Key resolved versions: torch 2.15.0, numpy 2.5.5, pandas 3.1.1, scipy 1.18.1, matplotlib 3.11.2, plotly 7.1.0, scikit-learn 1.9.1, seaborn 0.13.2, bspline-mutual-information 1.0.0. Exact transitive versions and download identities are retained in the machine-readable installation reports and summary. No editable installs, dependency suppression, global installs or shared site-packages.
- Each installed path verified environment-local imports, wheel provenance/hash, resource byte equality, console/module help, profile HTML, profile tables-only and no-profile HTML. Copied sdist inputs were removed before regeneration from both saved profile bundles. Public reload validated checksums, normalized values, complete schemas/tables/report parity and comparison identity. Both paths retained ten scientific tables plus two profile tables (18 candidate-rank rows, 30 profile-value rows, five feature-coverage rows).
- Both installed paths opened standalone regenerated HTML directly with headless Chrome and hostname resolution disabled. Actual interactions passed: heatmap drilldown, query/candidate selection/search, sorting, depth/output controls, pinning, profile SVGs, original masks and hover IDs. The disposable copy alone contains injected test assertions; published bundles remain untouched. No server or external report resources. All nine real legacy public exports and representative legacy modules resolved in each environment without training.
- Both sdist comparison examples additionally executed with isolated Python against the installed sdist-built wheel, from outside the checkout, and passed. Comparison guides/examples/fixtures are sdist assets, not installed wheel data; README and Release A documentation now make that boundary explicit.
- Baseline source suite: 134 tests, 131 passed and three missing-PyTorch skips. Repeated with a full-dependency temporary environment: **134 passed, zero skips in 85.643 seconds**, including actual browser tests. These are source regressions (some tests deliberately inject source paths), not the installed-artifact evidence above. Harness suite: **12 passed**. Static compilation and Git whitespace checks passed. Sphinx, full training/cross-attention suites, target-scale performance, other operating systems/Python versions, manual visual/accessibility and cross-browser review remain unverified; B1–B3 remain incomplete.
- Evidence workspace: `/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102`. It retains the machine-readable summary, numbered logs, artifacts, installation reports, example logs, result bundles and environments. The earlier diagnostic workspace ending `valpas-distribution-d26ivk3m` retains the first-run failure and full-dependency source-regression log. That initial failure was a **harness URL-encoding assertion**, not a package/install failure: pip encoded the development-version plus sign. Fixed with decoded exact-path and artifact-hash validation plus a regression test; the successful run rebuilt and installed both wheels into new environments. No failure was relabeled as success.
- Main interpreter and existing checkout changes were preserved; the generated version file was restored. Downloads and all large builds/environments are outside repository status. No training, model loading, new association scoring or GPU work was performed. Retained temporary environments may be removed after evidence review; the validator defaults to removing them while retaining useful logs/artifacts.

### B1 — Sample metadata, grouping summaries, influence diagnostics

Deliverables:

1. Metadata keyed by unique observation ID, categorical/continuous overlays, missing metadata indicators, and explicit display ordering.
2. Observed-value group counts/means and optional between-group/total sums-of-squares fraction, with exclusions and zero-variation status.
3. Joint-sample-centered covariance products, signed values and absolute-product shares; largest-h summary with default h of five and ID tie breaking.
4. Explicit omission preview that removes selected observations, recenters, and reports covariance/correlation only with sufficient remaining observations and nonzero variance where required.
5. On-demand browser diagnostics for embedded pairs and matching Python calculations for requested exports; shared hand-calculated fixtures prevent formula divergence.
6. Diagnostic scope, masks, denominators, and reasons in exports and captions.

**Acceptance:** influential-point, zero-denominator, constant-profile, missing-group, and recentering fixtures match expectations. Changing overlays or diagnostic selection leaves saved scores/ranks unchanged. No model-attribution claim appears.

#### B1 implementation and validation record — 2026-11-19

**Historical B1 checkpoint:** counts, artifacts and statements about then-future B2/transient UI below are preserved. Current B2 status is recorded separately after the chronological slice records.

- Implemented exact-ID, immutable [`SampleMetadata`](../src/valpas/comparison/diagnostics.py:19), [`DiagnosticRequest`](../src/valpas/comparison/diagnostics.py:121), [`load_sample_metadata()`](../src/valpas/comparison/diagnostics.py:105), [`group_summary()`](../src/valpas/comparison/diagnostics.py:188), and [`covariance_diagnostic()`](../src/valpas/comparison/diagnostics.py:320), with manifest sections and [`compare_results()`](../src/valpas/comparison/engine.py:282) keyword integration. Metadata may be absent or incomplete; types/IDs/binding are explicit, extras require permission, and missing grouping takes precedence in disjoint exclusions.
- Group counts/means and optional between-group/total SS fraction use marginal known-group observed finite values. Covariance uses joint observed finite values, signed centered products, absolute shares, default h = 5, exact Unicode tie order and explicit omission with recentering. Counts, masks, included/excluded/retained IDs and independent covariance/correlation/fraction reasons are exposed. Imputed values are excluded; zero variation, insufficient counts and numeric range have honest unavailable states.
- Lazy requested-only diagnostic exports and deduplicated group summaries preserve all ten A2 scientific tables and comparison identity. Result schema v3 persists normalized metadata/requests and optional nested-JSON-cell tables, with source-free parity checks. A2 v1/A3 v2 reload requires the same software/policy versions; legacy HTML uses verified old inventory hashes and normalized old-shape payload checks, then regenerates current assets.
- Browser categorical/continuous colors, missing metadata, explicit display order, marginal grouping/fraction controls and on-demand omission previews are descriptive only. HTML-only omission removes metadata/profiles from the payload, not sensitive full-bundle tables. Metadata counts toward the payload budget. No causality, model attribution, retraining, new association scoring or ranking changes.
- Added a separate [B1 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b1.json), [metadata](../tests/comparison/fixtures/demo-01/sample-metadata.json), [six-observation profiles](../tests/comparison/fixtures/demo-01/b1-profiles.json), [hand calculations](../tests/comparison/fixtures/demo-01/README.md) and overview-first [example](../examples/compare_saved_results.py), preserving the existing A3 manifest/profile fixture and user packaging edits. Updated README, guide and schema/API documentation, retaining single-modality and no-profile guidance.
- **Full-dependency source regressions before and after builds: 174 tests passed, zero skips**, preserving the original 134 tests including 22 single-modality tests and adding 40 B1 tests. The main interpreter run had 171 passes and the three existing missing-PyTorch skips. New coverage: [19 diagnostics tests](../tests/comparison/test_b1_diagnostics.py), [17 persistence tests](../tests/comparison/test_b1_persistence.py), and [four actual Chrome tests](../tests/comparison/test_b1_browser.py). Shared hand-calculated fixtures compare complete Python/JavaScript results, including masks, recentering, Unicode ties, constants, missing cohorts/groups and numeric overflow. Browser interaction tests verify malicious metadata stays inert and overlay/group/order/h changes preserve scientific results.
- **17 packaging-harness tests passed**, preserving the original 12. The updated [distribution validator](../tools/validate_distribution.py) and [installed smoke](../tools/distribution_smoke.py) require exact optional table sets rather than weakening counts. B1 fixtures require 15 tables: ten scientific, two profile, and three B1; one requested diagnostic, two feature group summaries, 24 unique metadata rows and 30 profile values. A3 and no-profile cases remain covered.
- **Fresh checkout wheel, sdist and Git-free extracted-sdist wheel passed**, version **1.0.1.dev29+g1a5f1dd97.d20261119**. Both wheels are byte-identical, SHA-256 **c5a5faa7c7f1d01cabf3728bb8a73757b49a3414843d4a3c7c578ea0176deb03**; sdist SHA-256 **b79138b3c43172cd1001eb2c81812d3e53f9d6ab5005597cb8de757473bb2687**. This plan-only evidence update follows those artifacts; application code, browser assets, fixtures, examples and harness are unchanged after validation.
- Both wheels were force-reinstalled noneditably into distinct **retained isolated full-dependency environments**, followed by dependency consistency checks, installed resource-byte equality, outside-checkout CLI/public reload/legacy imports and both copied sdist examples. Copied source inputs were deleted before regeneration. All scientific tables retained parity across report cases. **Eight actual direct-file Chrome 157 cases passed**: A3, B1, hostile metadata and no-profile for each artifact; hostname resolution disabled, standalone HTML and no server. This is not a new fresh dependency-resolution/install claim. Missing backend tooling was installed only in the retained isolated build environment from cached wheels; no global installs.
- Final distribution evidence workspace: `/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-a6gbnxsx`. Its summary records **58 successful commands**, artifacts, installed environments and browser results; final-evidence and source-regressions summaries retain exact commands/logs. Full-dependency runtime: `/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python`; second installed runtime is the sibling `sdist-wheel-env`; build tooling is the sibling `build-env`.
- Reproduction from the checkout: run that runtime with `PYTHONPATH=src` and arguments `-m unittest discover -s tests/comparison -v`, then `-m unittest discover -s tests/packaging -v`. Rebuild/install/browser reproduction: `python3 tools/validate_distribution.py --reuse-envs /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102 --keep-envs`. See the [distribution guide](../docs/DISTRIBUTION_VALIDATION.md) for fresh-environment mode and scope distinctions. Source tests intentionally use source paths; they do not replace the independent installed-artifact evidence.
- Two new harness issues were fixed, not relabeled successes: macOS temporary-path alias comparison and a script-closing literal in the injected browser probe. Failure logs remain in the final evidence index. Generated version-file state and existing user work were preserved. Compilation and Git whitespace checks passed. No training, checkpoint loading, association scoring, performance sweep or feature network calls occurred.

B1 acceptance is met for this focused scope. B2 reference evidence/notes/sessions/publication figures is next; B3 production hooks and target-scale validation remain future. The two-release project is not complete. Other OS/Python/browser combinations, Sphinx, manual visual/accessibility review, broad training suites and target-scale performance remain unverified. UI display settings are transient, not portable B2 session state; legacy bundle reload retains the same-software/policy-version restriction. Full bundles remain sensitive even when HTML metadata is omitted.

### B2 — Reference evidence, decisions, sessions, figures (DONE)

Implement [reference evaluation](../src/valpas/comparison/reference.py) and extend reporting/session/figure APIs.

Deliverables:

1. Local evidence import with source/version and assessment coverage; preserve separate pathway and reaction endpoints and direct versus inferred evidence where supplied.
2. Total/reachable support, supported nominations, hit, reference-supported fraction, recovery, and reachability, with explicit assessed/unassessed/unsupported/unreachable statuses.
3. All-assessed versus reachable-query summaries, recorded opportunity strata, and equal-feature or explicit equal-group weighting. Reject ambiguous feature/group membership.
4. Candidate decisions including query-level abstention, notes, inspected outputs, pool/depth, and timestamps.
5. Explicit session/shortlist download and import; scientific/content/scope matching, ID validation and safe note rendering. Implemented policy is strict rejection, **not migration**, with explicit Python scope rebind only when all current settings and every decision snapshot survive unchanged. Browser storage is not used; JSON is authoritative, formula-safe shortlist CSV is display-only/nonimportable.
6. Python SVG/PDF query figure export and CLI bundle-based export; browser SVG or print path with documented rendering differences.

**Acceptance:** evidence filtering never changes nominations; duplicated evidence does not inflate support; weighting matches fixtures; session/notes round-trip; figures disclose layer/masks/counts/overlay and regenerate without fitting.

The following three records are **historical slice checkpoints**. Their partial-completion statements and counts remain as recorded; the integrated completion record afterward supersedes them for current status.

#### Reference-only implementation record — 2026-11-19

Reference deliverables 1–3 are implemented with strict local reference/group schemas, independent source/version/evidence endpoints, explicit denominators/strata/group weighting, optional exact-integrity tables and normalized documents, separate reference provenance, full-cohort overview and display-only evidence filtering. Result schema remains v3 with an optional version-one reference extension; existing same-version v1/v2/v3 reference-free reload remains supported. The [reference handoff](B2_REFERENCE_HANDOFF.md) records interfaces, persistence boundaries, known limitations and exact focused validation: 109 tests passed, including existing and new real Chrome cases. Full-suite and packaging checks are deferred to parent integration. **Overall B2 remains unfinished:** decisions, notes, sessions, shortlists and figures/export-query are not implemented by this reference-only task.

#### Sessions/decisions/shortlists implementation record — 2026-11-19

Deliverables 4–5 are implemented: strict immutable session/shortlist contracts, explicit user decisions including query-level abstention, separate content/report-scope binding, portable B1/reference settings, real offline JSON download/file import, spreadsheet-safe shortlist CSV, and optional inventoried initial sessions. Imports replace state deterministically and reject incompatible content/scope without migration or silent loss. The [session handoff](B2_SESSION_HANDOFF.md) records APIs/schema, privacy and compatibility behavior, and focused validation: **179 tests passed, zero skips**, including four actual Chrome download/upload cases. Existing reference changes are retained. Figures/export-query, parent full-suite/install checks and B3 work remain pending; **overall B2 is not complete**.

#### Figure implementation record — 2026-11-19

Deliverable 6 is implemented: public full-result/saved-bundle SVG/PDF export with lazy Matplotlib, explicit IDs and safe no-clobber staged paths, bundle-based CLI delegation, and an explicit bounded browser SVG download. Captions preserve masks/cohorts, exact literal IDs and annotations/notes, units/transform, metadata, pool/depth and descriptive diagnostic interpretation. Optional sessions/decision snapshots use existing strict content/scope contracts; no new session fields. Session-bearing old assets reload by inventoried-byte integrity plus exact normalized payload/session parity. The [figure handoff](B2_FIGURE_HANDOFF.md) records exact focused tests, actual Chrome download/XML evidence, interfaces and integration limitations. Existing reference/session work is retained. Parent full-suite/install checks and B3 remain pending; **overall B2 is not declared complete**.

#### Integrated B2 completion record — 2026-11-19

**B2 acceptance is met; B2 is DONE.** The [complete workflow](../docs/COMPARISON_RELEASE_A.md), [user guide](../docs/USER_GUIDE.md), [combined synthetic manifest](../tests/comparison/fixtures/demo-01/manifest-with-b2.json), [schema](../docs/COMPARISON_SCHEMA_V1.md) and [figure guide](../docs/COMPARISON_FIGURES.md) cover CLI-first overview, independent reference endpoints/denominators, strict decisions/session restoration, bounded browser SVG and full-bundle SVG/PDF, privacy and source-free reproduction.

- **232 full-dependency comparison tests, zero skips**, before and after builds (90.818 s / 90.971 s); **22 harness tests**, zero skips before and after (0.605 s / 0.497 s). **88 successful installed validation commands** and **10 actual Chrome cases**: A3, B1, hostile metadata, no-profile and B2 for each wheel. Exact commands/logs and limitations are in the [validation handoff](B2_VALIDATION_HANDOFF.md); these are prior integrated results, not reruns during documentation finalization.
- Artifact version **1.0.1.dev30+g4d572bc23.d20261119**. Checkout wheel and extracted-Git-free-sdist wheel: **215680 bytes each**, SHA-256 **cc70f3da10a73d1b0903b945f8527986ff90b9d71ea7196f275c329d3e08443e**. Sdist: **269049 bytes**, SHA-256 **da5c1088ceebe4d869336b3046b9cc20c7b94fe493c0bd82173fa2959bdaffef**. Observed wheel byte equality is not a general reproducible-build guarantee.
- Evidence root: `/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i`; the summary records 15:23:27–15:24:51 UTC, artifacts, commands, dependencies, inventories and restored source/version state. macOS 26.7.2 arm64, Python 3.12.3, Chrome 157.0.8103.80. Both wheels were force-reinstalled noneditably into retained isolated full-dependency environments under `/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102`, **not freshly resolved dependencies**; installed checks ran outside the checkout.
- Exact inventories: ten base tables, twelve with profiles, fifteen B1, fifteen reference-only with groups, **twenty combined B2 tables**. The combined common-pool/depths 1, 2, 5 case retains three endpoints, five evidence rows, 54 recovery rows, 1080 summary rows and two group-membership rows; sessions add an inventoried document, not a table. The handoff retains every table count. Eighteen demo variants plus two reference-only bundles passed; copied inputs were deleted before source-free regeneration/vector exports.
- Each installed B2 browser case restored two initial decisions, added three for five total, downloaded session/shortlist JSON, formula-safe CSV and SVG, then imported each JSON twice with exact restoration. Hostile notes remained inert; tampering was atomically rejected; scientific payload was unchanged. Direct/inferred/pathway filters retained independent support. Downloaded M01/P01 SVG had six scatter circles, twelve profile circles and zero imputed marks.
- Same-software/policy v1/v2/v3 reload is not migration. Session-bearing old HTML is accepted only with inventory integrity and exact normalized/stored/embedded payload parity; current asset bytes are not required. Strict content/scope binding, explicit lossless scope rebind, HTML-only omission and full-bundle sensitivity remain boundaries.
- **Artifact/documentation boundary:** tested wheels/sdist precede the validation handoff and this final README/workflow/user-guide/plan update. They contain the validated implementation, harness, fixtures and then-current guides, not these final docs. No rebuild is needed or performed for docs-only finalization; documentation CLI smoke/static checks are separate evidence, not installed-artifact revalidation. Parent final review follows this documentation report.
- **Still unverified/out of scope:** B3 opt-in production metadata capture/export hooks and the 1,000 × 5,000 × 8 elapsed-time/peak-memory benchmark; other OS/Python/browser combinations, manual visual/accessibility certification, Sphinx and broad training suites. Synthetic evidence is not biological validation. No full Release B/project-complete claim.

### B3 — Production boundaries, packaging, documentation, final validation (DONE; scale limit recorded)

Production hooks, regressions, CLI-first documentation and the bounded scale measurement are implemented. The [B3 validation record](B3_VALIDATION_HANDOFF.md) records final artifact/browser results and limitations. The 1,000 × 5,000 × 8 dense run stopped during loading at the 600-second budget (5.05 GiB sampled peak RSS), not a completed target-scale comparison. This phase records measured limits rather than asserting an unachieved performance target.

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
