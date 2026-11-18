# Saved-output comparison: input/scientific schema v1 / Release A

A1 provides validated inputs, compatibility, ranking and pools. A2 adds comparison metrics, overview tables and normalized result bundles. A3 adds **offline HTML, optional original-mask profiles and source-free report regeneration**. Input/scientific schemas remain v1; new result bundles are v2, with A2 v1 reload support. See the [Release A quick start and profile/report contract](COMPARISON_RELEASE_A.md). No training, association scoring, checkpoint loading, network access or annotation lookup occurs. The implementation and public imports use only the standard library; root lazy exports and existing CLI behavior are preserved.

**Overview first:** no target metabolite or protein is required. Compare all declared queries under the chosen pool policy, inspect dataset/query summaries and the offline agreement/recurrence dashboard, then select queries and candidates for detailed inspection. Report filters never redefine scientific pools.

## Public API

All names below are exported by [the comparison namespace](../src/valpas/comparison/__init__.py).

| API | Contract |
| --- | --- |
| [ComparisonInput](../src/valpas/comparison/models.py) | Frozen, detached output descriptor, sparse pair records, warnings and consumed local paths. Direct construction is validated too. |
| [ComparisonSettings](../src/valpas/comparison/models.py) | Validated pool policy, self exclusion, requested depths and specific attestations. |
| [ComparisonValidationError](../src/valpas/comparison/models.py) / [Issue](../src/valpas/comparison/models.py) | Actionable error with field, reason, remediation, output ID when applicable, examples and count. Warnings are returned records, not global warning-filter changes. |
| [ComparisonManifest](../src/valpas/comparison/models.py) | Dataset descriptor, tuple of normalized outputs, settings and compatibility report. |
| [PairValue](../src/valpas/comparison/models.py) / [PairStatus](../src/valpas/comparison/models.py) | Raw score, optional count and supplied rank, plus explicit status and reason. |
| [RankingPolicy](../src/valpas/comparison/models.py) / [PoolPolicy](../src/valpas/comparison/models.py) | Supported policy enums. String values are accepted by the validated contracts. |
| [load_manifest()](../src/valpas/comparison/adapters.py:358) | Read local JSON, fingerprint the bytes consumed, load only named data, validate identity/configuration. A1 permits one input for inspection/export; A2 orchestration requires at least two. |
| [load_comparison_input()](../src/valpas/comparison/adapters.py:337) | Normalize one v1 descriptor; optional base directory defaults to the working directory. Does not assert cross-output compatibility by itself. |
| [from_association_result()](../src/valpas/comparison/adapters.py:379) | Structural adapter for existing labeled values/counts; explicit query axis and exact ordered query/candidate selections required. Copies scalar values; never calls legacy save/list conversion or imports the result class. |
| [validate_compatibility()](../src/valpas/comparison/compatibility.py:48) | Return configuration difference rows, configuration-to-run groups, identity status and persistent warning records. Known identity/configuration contradictions are errors. |
| [rank_output()](../src/valpas/comparison/ranking.py:22) | One query's native ordinal order/ranks, all declared candidate statuses, certification and exhaustion flags. |
| [top_list()](../src/valpas/comparison/ranking.py:60) | Return only a certified native prefix; reject unavailable query, arbitrary filtering, or insufficient saved depth. |
| [build_pools()](../src/valpas/comparison/compatibility.py:148) | Validate compatibility and return per-query native/active orders and ranks, explicit pools, coverage, controlled availability and exclusion records. Does not calculate overlap or recurrence. |
| [export_comparison_inputs()](../src/valpas/comparison/bundles.py:21) | Opt-in, full-precision detached input bundle. Accept normalized outputs, destination, optional dataset and settings. No overwrite mode. |
| [load_input_bundle()](../src/valpas/comparison/bundles.py:94) | Check completed A1 input-bundle inventory/checksums and reload without original input paths. Distinct from the A2 result-bundle loader. |
| [compare_results()](../src/valpas/comparison/engine.py:238) | Accept a validated manifest or sequence of at least two normalized inputs, optional settings, and keyword dataset anchor. Two distinct runs of one configuration are valid. Return an immutable result over all queries under policy. |
| [ComparisonResult](../src/valpas/comparison/engine.py:136) | Normalized inputs, settings, identity, fingerprints, warnings and compact summaries. Complete detail tables are generated query-by-query, not retained as expanded tables. |
| [iter_table()](../src/valpas/comparison/engine.py:157) / [materialize_table()](../src/valpas/comparison/engine.py:167) | Iterate detached row dictionaries by table name; materialization defaults to at most 10,000 rows and errors rather than silently truncating. |
| [write_comparison()](../src/valpas/comparison/report.py:282) | Accept a result and destination; HTML plus complete tables is default, overwrite defaults false. Optional validated report settings control detail scope and payload limits, not analysis. Explicit tables-only remains supported. |
| [load_comparison_bundle()](../src/valpas/comparison/report.py:180) | Validate A2 completion, schemas, checksums, normalized identity and exact table parity. Reconstruct the result without original files or models. |

Returned records also include [CompatibilityReport](../src/valpas/comparison/models.py), [RankView](../src/valpas/comparison/models.py), [Exclusion](../src/valpas/comparison/models.py), [QueryPool](../src/valpas/comparison/models.py) and [PoolResult](../src/valpas/comparison/models.py). Descriptors, nested metadata, pairs and returned scientific mappings are detached immutable mappings/tuples.

Run [the A2 comparison example](../examples/compare_saved_results.py) from a source checkout for the complete load/compare/write/reload workflow. The [A1 input example](../examples/inspect_comparison_inputs.py) still demonstrates input inspection/export separately. Both use [the validated demo manifest](../tests/comparison/fixtures/demo-01/manifest.json). The [A0 expected fixture](../tests/comparison/fixtures/demo-01/expected.json) remains the independent mathematical reference used by the A2 engine tests.

## Manifest and strictness

The top-level JSON object requires: schema_version (integer 1, not boolean), dataset, outputs (nonempty array), settings (object). A3 permits optional profiles and report sections, validated under the [Release A contract](COMPARISON_RELEASE_A.md). References and other unsupported sections remain rejected, not silently accepted as implemented.

All contract objects reject unknown keys, including nested identity, namespace, evidence, completeness certificates, input options, settings and attestations. JSON duplicate keys and nonstandard NaN/Infinity constants are errors. Scientific parameters/preprocessing are intentionally **open finite-JSON metadata maps**, not executable algorithm settings: arbitrary method-specific keys are preserved, not applied or claimed to be validated against a training API. Non-seed maps may not contain seed/random_seed/random_state at any nesting level.

IDs are nonempty, case-sensitive strings. Leading zeroes, whitespace, Unicode and formula-like text remain unchanged. There is no normalization or numeric coercion. Repeated axis IDs and duplicate pair rows (even equal duplicates) fail. Display labels are not identity keys. File orientation is explicit even for square matrices.

### Dataset and per-output identity

Both dataset and each output's identity object require:

| Field | Meaning |
| --- | --- |
| dataset_id | Exact stable dataset identifier; equality is necessary but not sufficient. |
| dataset_evidence | Null for explicitly unknown legacy provenance, or an object with exactly type, source, value, limitations. |
| observation_ids | Unique exact strings, or null for unknown legacy observations. Ordering does not define a different observation set. |
| query_namespace, candidate_namespace | Each has exactly id and modality strings. Equal text across different namespaces is not a self edge. |
| context | Nonempty experiment/subset description or explicit null for unknown. |

Evidence type is fingerprint or attestation. Source is an explicit common measurement artifact/source identity. Value is its content fingerprint or a specific textual assertion; limitations must be nonempty (use an explicit description, not an implied absence of limitations). Distinct known sources, contexts, observation sets, namespaces or fingerprints cannot be overridden. Two fingerprints for the same source must match. An attestation may bind a legacy output to that source but does not turn into a computed fingerprint. The loader cannot recompute a measurement fingerprint from score files; it validates supplied evidence and reports user-attested compatibility prominently.

The manifest dataset is an explicit common anchor. Supply known or attested anchor evidence/context/observations there; missing per-output metadata may be resolved through settings claims. Unknown source metadata stays null in the saved original descriptor, while its specific claim remains in settings.

### Output descriptor

Every output requires:

- schema_version; output_id; label; method_id; configuration_id; run_id; seed (nonnegative integer or null).
- identity, configuration, provenance.
- query_ids and candidate_ids: ordered unique complete declared axes/universes, not merely reported rows.
- orientation: query_rows_candidate_columns or candidate_rows_query_columns. Only matrices accept the latter.
- representation, ranking_policy, tie_policy, completeness, missing_policy, data.

Optional fields: eligibility, missing_queries, count_semantics. Counts require a nonempty count_semantics description; they are never treated as observation masks.

Provenance has exactly software, source and limitations, each a string or explicit null. It is descriptive software/output provenance, separate from measurement identity evidence.

Configuration has exactly parameters, preprocessing, score_semantics, supervision, training_features, observation_selection. Parameters/preprocessing are metadata objects or null; score semantics, supervision and observation selection are strings or null. Training features are null or an object with namespace and unique ids. Explicitly describe non-applicable training inputs rather than using null to claim completeness. Empty parameter/preprocessing maps do not establish known equality for seed grouping; use explicit declarations, for example an algorithm-defaults or no-transform entry. Different method, score policy, external tie policy, preprocessing, supervision, parameter values, training feature sets or observation selection produce field-level configuration differences. A shared configuration ID requires identical complete non-seed metadata (or a complete specific attestation); run IDs must be distinct within that configuration. Seed alone is not run identity. No automatic best seed or consensus is produced.

### Settings and attestations

Supported settings, all optional with defaults:

| Field | Default / rule |
| --- | --- |
| pool_policy | strict; alternatives common and native_inspection. |
| exclude_self | true, a JSON boolean. |
| depths | [5, 10, 20]; nonempty distinct positive integers. A2 summary/nomination depths, each assessed independently for certification and effective pool size. |
| attestations | Empty list. Every claim requires output_id, field, claimed_value, statement. |

Attestable fields are dataset_evidence, observation_ids, context and configuration. Claims target an existing output and a specific missing field; no generic force flag. Claimed identity values obey that field's schema. A configuration claim supplies the entire complete non-seed configuration and cannot contradict known leaves. Duplicate, unused, wrong-target and already-known-field claims are errors. Known identity mismatches are checked across all outputs before claims are considered. Attestation warnings remain visible in the compatibility report; unknown configuration prevents isolated-method claims and seed grouping.

## File and representation schemas

Data requires format and exactly one of path or inline. Optional index_base applies only to permutations; optional symmetric applies only to legacy matrices and long scores. Formats are json, csv, tsv, and normalized (JSON pair records used for full-precision input bundles). Inline content accepts json or normalized only. Extensions must match the declared format.

Paths are UTF-8 local manifest-relative names, contained in the manifest directory after symlink resolution. Absolute paths, parent traversal, URLs, backslashes, NULs, escaping symlinks, directories and executable/pickle/checkpoint/NumPy files are rejected. API callers can select an explicit base directory; there is no absolute-path escape option. IDs never determine input filenames. JSON/table contents remain data, never imports or code.

Missing policy has exactly blank (reject or unscored), nan (reject or unscored), absent (reject, unscored, unreported or truncated). CSV text NaN and inline floating NaN are accepted as unscored only when declared; JSON NaN is never valid JSON. Infinity always fails. Null and blank scored cells follow the blank policy. Nonfinite/missing values never acquire bottom ranks. Complete representations permit only reject/unscored omissions; filtered and prefix inputs require unreported and truncated respectively.

### Labeled score matrix: score_matrix

JSON/inline content has row_ids, column_ids, values, optionally counts. Values/counts are rectangular arrays with matching labeled dimensions. Axes must equal descriptor sets, but may be reordered. CSV/TSV uses a header with a first label column, then exact column IDs; each later row starts with an exact row ID. CSV/TSV matrices carry scores only. Counts can accompany JSON matrices. Native signs and precision are unchanged.

Completeness is an object containing only kind = complete. All matrix cells must exist; a blank cell can be explicitly unscored. Long scores or normalized records are preferable for entirely missing queries rather than fabricating matrix rows.

### Long score table: long_scores

JSON/inline contains a records array; CSV/TSV has named columns. Each row requires query_id, candidate_id, and score for scored entries. Optional rank, count, status, reason. Explicit non-scorable rows may omit score; a missing score column without status is an error. Absent pairs follow the declared missing policy, never default to zero. If ranks accompany scores, all scorable rows for that query must carry consecutive ranks, and must agree exactly with deterministic score order.

### Full candidate permutation: rank_permutation

JSON only: query_ids plus permutations, one integer array per query. Data index_base is explicitly 0 or 1. Each array is an exact permutation of the declared candidate-axis positions. For candidates [a, b, c], zero-based [2, 0, 1] means ordered candidates c, a, b and inverse one-based ranks c=1, a=2, b=3. It is **not** an inverse-rank array. Full permutations cannot contain missing queries or eligibility overrides. Namespace-aware self exclusion is applied later when constructing ranks. Native scores may be absent.

### Complete ordered ranks: ordered_ranks

Records/columns: query_id, candidate_id, optional score/count, rank, status, reason. Every scorable eligible candidate has a unique consecutive one-based rank. Every other declared pair needs an explicit non-scorable status/reason, a declared ineligible override, or a query-level missing declaration. An omitted candidate cannot silently become worst-ranked or unscored. Rank-only saved orders preserve their declared external tie policy. If scores are supplied too, they must cover every reported scorable pair and agree with the canonical Unicode tie policy.

### Certified native prefix: certified_prefix

Records use the ordered-rank format, with consecutive ranks 1 through saved depth. Completeness has kind = prefix and queries, a mapping with exactly one certificate per declared query. A certificate requires depth, pool_id, pool_size, exhausted, complete_prefix, self_excluded. Complete-prefix must be true; exhaustion is true exactly when depth equals pool size. The explicit candidate universe/status metadata must agree with native pool size after the certified self rule. The requested self-edge rule must match the certificate.

Omitted candidates are truncated, not unscored or lowest-ranked. A request beyond saved depth fails unless exhaustion is certified. Strict controlled availability additionally requires every input to have a matching native-pool certificate and sufficient depth. Mixing prefixes with uncertified full-pool identity is conservatively unavailable. **Common reranking is prohibited for every prefix in v1, including an exhausted prefix**; re-export as complete ordered ranks if appropriate.

### Arbitrary filtered list: filtered_list

Completeness has kind = inspection_only and a nonempty filter description. Omitted pairs are unreported. Rows may retain their supplied, nonconsecutive saved ranks, but the rank view returns no ranks/order and native top-list requests fail. No overlap, recovery or full-rank claims are authorized. Scores plus saved ranks must still have consistent relative order; duplicate ranks are errors.

### Legacy rounded score/count matrix: legacy_score_count

Uses labeled matrix layout with score:count text cells and explicitly declared blank policy. Count semantics are mandatory when counts exist. The adapter emits a persistent warning that legacy scores may have been rounded to five decimals; ranking uses only available precision. It cannot recover dropped axes, original values or original full-precision ties. Declare all known axes explicitly, and use missing/status metadata rather than inventing values.

Symmetric triangular expansion is opt-in through symmetric = true, requiring equal axis entity sets/namespaces. A known scored reciprocal fills only an absent/unscored reciprocal. Conflicting reciprocal scores or counts fail. Without symmetry, missing reciprocals remain missing. Within-modality ranks retain both query-specific directions; edges are not globally deduplicated. The same declared expansion is available for long scores.

### Pair status and eligibility

Statuses: scorable, unscored, ineligible, missing_query, unreported, truncated. Explicit non-scorable rows require a reason; format-derived missing scores receive a recorded missing-score reason. Scorable means a finite score or certified supplied rank is known. Ineligible scores/counts can be retained for inspection but never ranked. Other non-scorable statuses cannot carry a score/rank. Counts can remain known independently.

Eligibility is a list of exact query_id, candidate_id, eligible boolean, reason overrides. Otherwise all declared candidates are eligible subject to self exclusion. Duplicate/unknown overrides and conflicting statuses fail. Missing_queries lists declared query IDs with no reported values; it differs from a query whose every pair is unscored. Prefixes cannot certify missing queries.

Normalized bundle records have required query_id, candidate_id, status and optional score, rank, count, reason. They pass the same representation/completeness validation as original readers; normalized format is not a validation bypass.

## Ranking and pools

Policies are native_descending, native_ascending, absolute_descending, absolute_ascending. Transforming for ordering never changes the stored score. Ties are exact stored-value ties, resolved in canonical candidate-ID Unicode code-point order, independent of locale. There is no rounding tolerance or boundary tie expansion. External rank-only orders declare their own nonempty tie policy; differences are disclosed.

Strict requires equal query and per-query eligible candidate sets, aligned by exact IDs. Finite/scorable-set differences preserve native inspection and return controlled unavailable with reason scorable_candidate_sets_differ; they do not become zero metrics. Missing queries and inspection-only inputs also disable controlled availability. Empty scorable strict pools are unavailable.

Common intersects query identities and per-query eligible scorable candidate identities across every included output. It requires complete representations and errors on empty query or per-query candidate intersections. Active ranks are restrictions of saved native order, never newly fitted/scored values. Native ranks remain available. Every removed query is recorded for each output; every excluded candidate includes status/reason, including otherwise-scorable candidates excluded because another output lacks them. Coverage includes declared, eligible, scorable, retained and excluded counts and certification flags.

Native inspection preserves independent universes and reports controlled unavailable with “different search spaces; descriptive only.” Unknown omissions remain explicit. A2 reports descriptive pairwise Jaccard and directional shared fractions only when both native lists are certified; it never invents a common overlap denominator.

## Single modality: protein abundance or gene expression alone

No modality split or second omics layer is required. Compare **at least two saved association-score/rank outputs** from the same protein-abundance dataset or the same gene-expression dataset (different methods/configurations, or distinct runs of one configuration). An abundance/expression measurement matrix alone is not a comparison input: A1–A2 do not compute associations or train models.

- Declare the **same namespace on both axes**, in the manifest dataset and every output identity. A namespace has exactly two nonempty, case-sensitive strings: [`id` and `modality`](../src/valpas/comparison/models.py:121). For example, use ID “protein-feature-ids-v1” with modality “proteomics” on both axes, or ID “gene-feature-ids-v1” with modality “transcriptomics” on both axes. These are user-declared strings, not an inferred or enumerated vocabulary. Equality requires **both fields**; extra namespace fields such as species/version/label are rejected. Entity IDs must also match exactly to identify a self edge. Display labels, provenance and training-feature metadata are not part of the self-edge predicate; dataset/source evidence, observation set, context and namespaces still undergo separate cross-output compatibility validation. Supply the full descriptor metadata described above; shared-configuration runs require identical complete non-seed metadata and distinct run IDs.
- Declare labeled query/candidate axes and an explicit [`orientation`](../src/valpas/comparison/models.py:194), even for an N × N square matrix: “query_rows_candidate_columns” or “candidate_rows_query_columns”. Labels permit axis reordering, but square shape cannot detect an incorrectly declared transpose. Same-namespace rectangular query/candidate subsets also work; strict mode requires equal query sets and per-query eligible candidate sets **across outputs**, not equality of the two axes within an output. Common mode intersects the declared query/scorable candidate pools.
- [`exclude_self`](../src/valpas/comparison/models.py:264) defaults to true. For a fully scored same-namespace N × N matrix, each query has N−1 ranked candidates and effective depth is at most N−1 (smaller when scores/candidates are missing). Diagonals remain visible with self-edge exclusion status and no active rank; setting this option false permits scored self pairs. **Both directional nominations are preserved:** A → B in A's ranking and B → A in B's ranking are distinct, even for symmetric scores; there is no global undirected deduplication. Signed scores remain unchanged under absolute-value ranking.
- Missing off-diagonal scores need an explicit missing policy. Strict mode makes affected-query controlled metrics unavailable when scorable sets differ; common mode removes that candidate for that query and reranks, without automatically removing the reciprocal nomination. Recurrence uses all declared runs in its configuration denominator, never a reduced denominator for missing runs.
- Prefer full saved matrices or the detached [`from_association_result()` adapter](../src/valpas/comparison/adapters.py:379), which accepts labeled pandas values/counts with explicit axis selections, including a single-modality result whose second omic is absent. It does not call legacy save/list methods, infer metadata, mutate the source, or import the result class. Declare count semantics when counts exist. For a known symmetric legacy triangular score/count export, opt into [`symmetric`](../src/valpas/comparison/adapters.py:242) expansion with equal axis sets/namespaces and declared unscored blanks; otherwise the omitted reverse scores stay missing. Expansion restores reported reciprocals, not lost precision or dropped axes.

[Single-modality regression tests](../tests/comparison/test_single_modality.py) exercise protein-only and gene-only signed square outputs, rectangular subsets, missing scores/runs, exact namespace identity, explicit transposes/reordering, legacy symmetry, pandas structural adaptation, hand-calculated metric denominators, full A1/A2 bundle roundtrips and saved-CSV CLI manifests. The four-entity, three-output square case retains 48 full candidate rows (36 ranked off-diagonal rows and 12 excluded diagonal rows); requested depth 9 becomes 3. These are deterministic saved-output checks, **not evidence of real training or biological correctness**. A3 HTML/browser remains unimplemented.

## Detached input bundles and safety

The exporter writes generated numeric JSON member names, a portable [manifest](../tests/comparison/fixtures/demo-01/manifest.json)-shaped descriptor, and an input-bundle marker with schema, ownership kind, completion flag and SHA-256 inventory. Float serialization roundtrips Python binary float values, including signed zero; there is no legacy five-decimal formatting. Full available pair records, status/eligibility metadata, supplied ranks, configuration and attestations survive reload. Original representation and missing semantics are retained. Legacy precision warnings are regenerated on reload.

Files are staged in a temporary sibling, then published to an exclusively reserved new destination. Existing directories (even empty ones), files and symlinks are refused. The immediate parent must exist and not itself be a symlink; established ancestor aliases such as macOS's temporary-directory alias are resolved. Source-containing destinations are refused. Failed writes clean only exporter-owned staging/reservations; unrelated files are never recursively removed. There is intentionally no overwrite option. This is safe local publication, not a defense against a hostile concurrent filesystem writer.

Reload verifies completion and exact consumed-file inventory/checksums. Checksums detect changes, not malicious provenance forgery. Inputs are local and may contain sensitive identifiers or metadata; bundles retain them verbatim, with no spreadsheet/display escaping. Never present bundle files as privacy-filtered report exports.

## A2 scientific tables and denominators

The exact ordered column contract is [TABLE_COLUMNS](../src/valpas/comparison/engine.py:347), also embedded in every result bundle. Ten tables are exported:

| Table | Scope and interpretation |
| --- | --- |
| Output inventory | One row per saved output, with method/configuration/run, seed, representation, metadata, identity status and canonical content digest. |
| Configuration differences | Field-level differences for every output pair; configuration differences prevent isolated-method interpretation. |
| Dataset summary | Dataset identity, method/configuration/output counts, declared/included/excluded query counts and observation count. |
| Query summary | One row per declared query/depth, including common-excluded queries; coverage and available/descriptive/unavailable pair counts, plus expected/assessed recurrence group counts. No run-pair average or consensus score. |
| Agreement summary | One row per output-pair/depth; declared, policy-eligible, controlled-evaluable, descriptive and controlled-excluded query counts, exclusion reasons and min/Q1/median/Q3/max controlled overlap. Quartiles interpolate at the fraction times one less than the evaluable query count. |
| Coverage | Per included query/output native and retained counts, certification/exhaustion, active pool size and query-level controlled availability. Depth-specific availability is in agreement/recurrence. |
| Exclusions | Every policy exclusion or known non-scorable status with output/query/candidate and reason; query exclusions have a null candidate. |
| Candidate ranks | Full available native/active/saved ranks, signed scores, counts and statuses, not just top nominations. Complete inputs include all declared candidate rows; common-excluded queries retain native ranks with no active rank. Limited inputs export known rows only; omission semantics remain in the normalized descriptors. |
| Agreement | One row per included query/output-pair/requested depth, with classification, effective depth, list sizes, intersection, union, fractions and status/reason. |
| Run recurrence | Separate per query/configuration/depth/candidate counts. Includes zero-nomination active candidates; a null-candidate sentinel discloses an empty group. Never pooled into method agreement. |

Controlled overlap is intersection divided by effective depth; Jaccard is intersection divided by union. Effective depth is the smaller of requested depth and a certified exhausted pool size. Strict/common comparisons require cohort-wide comparability and depth certification, not merely a comparable pair. A too-deep prefix request does not invalidate a shallower request. Missing/unscored values and unavailable metrics are null, never zero or worst rank.

Native inspection has no shared effective depth or controlled overlap fraction. Its directional fractions divide the intersection by each list's own size. Descriptive queries are counted separately and excluded from controlled distributions; a descriptive comparison is not a controlled comparison even if its lists happen to match.

Recurrence groups require identical known or specifically attested non-seed configuration. The expected run denominator includes every declared run in the group. Missing or insufficiently certified runs remain visible as unavailable; known nominations/evaluable-run counts may still be shown, but no reduced-denominator recurrence fraction is substituted. One run is not assessed. Native-inspection recurrence fractions are unavailable. Seed runs are not biological replicates; agreement/recurrence is not correctness, confidence, reference recovery, or a best-method ranking.

## A2 result bundles, identity and publication

An A2 result bundle is distinct from an A1 input bundle. Its [completion record](../src/valpas/comparison/report.py:87) stores ownership kind, schema/software/policy versions, resolved settings, dataset scope, comparison ID, warnings, normalized descriptors, source fingerprints, table schemas/row counts and exact file inventory with SHA-256/byte counts. Gzip JSONL members contain explicit full-precision saved pair records; original completeness and implicit missing semantics remain in the descriptors. Candidate-rank, recurrence and exclusion CSV tables are gzip-compressed; the other tables are plain CSV. Original source files can be deleted after export; reload never opens recorded original paths.

**CSV encoding:** headers are ordinary column names, but **every data cell is a JSON value**. Decode each cell as JSON after CSV parsing. This distinguishes null, empty strings, numbers, booleans and structured metadata without coercing exact IDs. Python's standard JSON encoder roundtrips saved binary float precision. These canonical files are machine-readable, not spreadsheet-safe or privacy-filtered exports; identifiers, metadata and original source paths may be sensitive.

The comparison ID hashes canonical normalized IDs/values/statuses, scientific descriptors, resolved settings, dataset identity, and schema/policy/software versions. It is independent of input ordering, matrix-axis ordering, depth/attestation ordering, labels, descriptive provenance, source paths and export timestamps. Generic configuration arrays retain their declared order (for example architecture dimensions or training-input order); reordering them is not presumed semantically equivalent. Changing saved values, counts, missing statuses, scientific settings or run identity changes the ID. Raw source SHA-256 hashes cover exactly the bytes parsed and are separate provenance: rewriting a source file with equivalent formatting can change its raw digest without changing comparison identity. In-memory inputs receive canonical content hashes without pretending that file bytes existed.

Reload validates member names, no symlink members, exact inventory, checksums, completion/schema/version, normalized contracts, comparison identity, warnings, and every table row against recomputed saved-value ranks/metrics. This recomputation is not fitting or association scoring. Version-one reload currently requires the same software/policy version; no migration is implemented. Checksums are integrity checks, not proof against forged provenance.

Publication writes to a temporary sibling and writes completion last, then publishes by rename. Existing destinations, including empty directories, are refused by default. Explicit overwrite accepts only a fully validated owned A2 bundle with no foreign members, never a consumed-source directory, A1 bundle, symlink, or unrelated directory. The old bundle is moved to a sibling backup and restored on publication failure; exporter-owned staging is cleaned. A result loaded from a bundle cannot overwrite that supplying bundle. Use a new destination to re-export it. This is staged local publication with rollback, not a crash-durable filesystem transaction or protection against hostile concurrent modifications; a process crash during replacement may leave a sibling backup requiring recovery.

## CLI and example workflow

The [compare command](../src/valpas/cli.py:304) accepts an input manifest or saved result bundle, required outdir, report scope/pin/depth/budget controls, optional manifest analysis pool/depth overrides, explicit tables-only, and safe overwrite. HTML is the default. It calls the public loader, engine and writer; resolved overrides are persisted. Failures exit nonzero with field/reason/remediation rather than proceeding with partial scientific results. No target-query argument is required. See the [Release A guide](COMPARISON_RELEASE_A.md) for all options and regeneration.

From a source checkout, run the following command against the [demo manifest](../tests/comparison/fixtures/demo-01/manifest.json), choosing a new output directory:

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir demo-comparison --pool common --depths 1 2 5 --tables-only
```

The [Python example](../examples/compare_saved_results.py) prints the overview before detail, writes HTML and checks roundtrip parity. Begin with dataset/query/agreement summaries, then inspect coverage, exclusions, pairwise agreement and separate run recurrence. The explicit tables-only command above omits HTML.

## Phase boundary and limitations

- A3 completes the Release A offline browser/basic-profile workflow; B1–B3 remain unfinished.
- B1 diagnostics, B2 reference/session/figure features and export-query command, and B3 production export hooks/target-scale checks remain unimplemented. No placeholder APIs for those phases are exported. Build verification is blocked when optional build tooling is absent; packaged resources are exercised from a copied package outside the workspace.
- NumPy loading is deliberately omitted; all required representations work with JSON/CSV/TSV and standard-library code.
- The adapter reads structural labeled matrices; it does not introspect omics objects to guess namespaces or provenance. It requires explicit metadata and selections.
- File loaders materialize parsed input contents and complete inputs use per-pair Python records. A2 processes detail tables one query at a time and streams export/reload validation; compact summaries scale with query/output-pair/depth counts. No giant expanded rank/exclusion/recurrence table is retained. A 20-query × 100-candidate × 3-output smoke test verifies 6,000 full-rank rows and streamed write/reload, not target-scale performance. The B3 1,000 × 5,000 × 8 measurement and compact input storage remain future work.
- Bundle export is opt-in and separate from legacy production/save methods. Legacy filenames, behavior and precision are unchanged.
- Earlier full-dependency legacy imports, documentation/Sphinx and cross-attention environmental follow-ups remain separate from comparison validation. No dependencies are installed or training suites run for A2.
