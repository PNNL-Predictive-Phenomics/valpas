# Saved-output comparison inputs: schema v1 / phase A1

A1 provides validated **inputs, compatibility, ranking and pools**, not a comparison metric engine, report, or command. No training, association scoring, checkpoint loading, network access or annotation lookup occurs. The implementation and public imports use only the standard library; root lazy exports and existing CLI localization are preserved.

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
| [load_manifest()](../src/valpas/comparison/adapters.py:346) | Read local JSON, load only named data, validate identity/configuration. A1 permits one input for inspection/export; A2 orchestration will require at least two. |
| [load_comparison_input()](../src/valpas/comparison/adapters.py:325) | Normalize one v1 descriptor; optional base directory defaults to the working directory. Does not assert cross-output compatibility by itself. |
| [from_association_result()](../src/valpas/comparison/adapters.py:366) | Structural adapter for existing labeled values/counts; explicit query axis and exact ordered query/candidate selections required. Copies scalar values; never calls legacy save/list conversion or imports the result class. |
| [validate_compatibility()](../src/valpas/comparison/compatibility.py:48) | Return configuration difference rows, configuration-to-run groups, identity status and persistent warning records. Known identity/configuration contradictions are errors. |
| [rank_output()](../src/valpas/comparison/ranking.py:22) | One query's native ordinal order/ranks, all declared candidate statuses, certification and exhaustion flags. |
| [top_list()](../src/valpas/comparison/ranking.py:60) | Return only a certified native prefix; reject unavailable query, arbitrary filtering, or insufficient saved depth. |
| [build_pools()](../src/valpas/comparison/compatibility.py:148) | Validate compatibility and return per-query native/active orders and ranks, explicit pools, coverage, controlled availability and exclusion records. Does not calculate overlap or recurrence. |
| [export_comparison_inputs()](../src/valpas/comparison/bundles.py:21) | Opt-in, full-precision detached input bundle. Accept normalized outputs, destination, optional dataset and settings. No overwrite mode. |
| [load_input_bundle()](../src/valpas/comparison/bundles.py:94) | Check completed input-bundle inventory/checksums and reload without original input paths. Not the future A2 comparison-result bundle loader. |

Returned records also include [CompatibilityReport](../src/valpas/comparison/models.py), [RankView](../src/valpas/comparison/models.py), [Exclusion](../src/valpas/comparison/models.py), [QueryPool](../src/valpas/comparison/models.py) and [PoolResult](../src/valpas/comparison/models.py). Descriptors, nested metadata, pairs and returned scientific mappings are detached immutable mappings/tuples.

Run [the saved-input example](../examples/inspect_comparison_inputs.py) from a source checkout. It loads [the validated demo manifest](../tests/comparison/fixtures/demo-01/manifest.json), prints native/common orders and strict availability, and can optionally export/reload an input bundle. The [A0 expected fixture](../tests/comparison/fixtures/demo-01/expected.json) remains the independent reference; no A2 metrics are asserted as implemented.

## Manifest and strictness

The top-level JSON object requires exactly: schema_version (integer 1, not boolean), dataset, outputs (nonempty array), settings (object). Other sections are rejected in A1, including future profiles/references/report options; they are not silently accepted as implemented.

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
| depths | [5, 10, 20]; nonempty distinct positive integers. Used to check prefix availability, not compute metrics. |
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

Native inspection preserves independent universes and reports controlled unavailable with “different search spaces; descriptive only.” Unknown omissions remain explicit. A1 does not calculate even descriptive overlap metrics.

## Detached input bundles and safety

The exporter writes generated numeric JSON member names, a portable [manifest](../tests/comparison/fixtures/demo-01/manifest.json)-shaped descriptor, and an input-bundle marker with schema, ownership kind, completion flag and SHA-256 inventory. Float serialization roundtrips Python binary float values, including signed zero; there is no legacy five-decimal formatting. Full available pair records, status/eligibility metadata, supplied ranks, configuration and attestations survive reload. Original representation and missing semantics are retained. Legacy precision warnings are regenerated on reload.

Files are staged in a temporary sibling, then published to an exclusively reserved new destination. Existing directories (even empty ones), files and symlinks are refused. The immediate parent must exist and not itself be a symlink; established ancestor aliases such as macOS's temporary-directory alias are resolved. Source-containing destinations are refused. Failed writes clean only exporter-owned staging/reservations; unrelated files are never recursively removed. There is intentionally no overwrite option. This is safe local publication, not a defense against a hostile concurrent filesystem writer.

Reload verifies completion and exact consumed-file inventory/checksums. Checksums detect changes, not malicious provenance forgery. Inputs are local and may contain sensitive identifiers or metadata; bundles retain them verbatim, with no spreadsheet/display escaping. Never present bundle files as privacy-filtered report exports.

## Phase boundary and limitations

- A2 metric orchestration, recurrence, summaries, stable comparison IDs and comparison-result bundles are not implemented. Input-bundle checksums do not claim to implement those features.
- A3 reports/profiles/CLI, B1 diagnostics, B2 reference/session/figure features, and B3 production export hooks/packaging/scale checks remain unimplemented. No placeholder APIs for those phases are exported.
- NumPy loading is deliberately omitted; all required representations work with JSON/CSV/TSV and standard-library code.
- The adapter reads structural labeled matrices; it does not introspect omics objects to guess namespaces or provenance. It requires explicit metadata and selections.
- File loaders currently materialize a file's parsed contents, and complete inputs use per-pair Python records. Export writes records incrementally, but no target-scale memory/performance claim is made. Compact arrays, bounded processing and the planned scale measurement remain later work.
- Bundle export is opt-in and separate from legacy production/save methods. Legacy filenames, behavior and precision are unchanged.
- Earlier full-dependency legacy imports, documentation/Sphinx and cross-attention environmental follow-ups remain separate from A1 validation.
