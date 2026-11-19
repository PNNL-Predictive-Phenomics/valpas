# Saved-output comparison: input/scientific schema v1 / result schema v3

A1 provides validated inputs, compatibility, ranking and pools. A2 adds comparison metrics, overview tables and normalized result bundles. A3 adds **offline HTML, optional original-mask profiles and source-free report regeneration**. B1 adds optional sample metadata, marginal group summaries and observed-data covariance diagnostics. Input/scientific schemas remain v1; new result bundles are v3, with A2 v1 and A3 v2 reload support **only under the same software/policy versions**, not cross-version migration. See the [Release A and B1 guide](COMPARISON_RELEASE_A.md). No training, association scoring, checkpoint loading, network access or annotation lookup occurs. The implementation and public imports use only the standard library; root lazy exports and existing CLI behavior are preserved.

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
| [`compare_results(inputs, settings=None, *, dataset=None, profiles=None, sample_metadata=None, diagnostic_requests=())`](../src/valpas/comparison/engine.py:282) | Accept a validated manifest or sequence of at least two normalized inputs. Profiles and metadata must be validated objects. Requests accept an explicit list/tuple of validated requests or request dictionaries. Two distinct runs of one configuration are valid. Return an immutable result over all queries under policy; B1 calculations are lazy, requested-only descriptions. |
| [ComparisonResult](../src/valpas/comparison/engine.py:136) | Normalized inputs, settings, identity, fingerprints, warnings and compact summaries. Complete detail tables are generated query-by-query, not retained as expanded tables. |
| [iter_table()](../src/valpas/comparison/engine.py:157) / [materialize_table()](../src/valpas/comparison/engine.py:167) | Iterate detached row dictionaries by table name; materialization defaults to at most 10,000 rows and errors rather than silently truncating. |
| [write_comparison()](../src/valpas/comparison/report.py:282) | Accept a result and destination; HTML plus complete tables is default, overwrite defaults false. Optional validated report settings control detail scope and payload limits, not analysis. Explicit tables-only remains supported. |
| [`load_comparison_bundle()`](../src/valpas/comparison/report.py:266) | Validate result v1/v2/v3 completion, versions, schemas, checksums, normalized identity, exact table parity and applicable report parity. Reconstruct the result without original files or models. |
| [`ProfileData`](../src/valpas/comparison/profiles.py:15) / [`load_profile_data(value, *, base_dir=".")`](../src/valpas/comparison/profiles.py:209) | Validated optional measurement layers; load inline schema-v1 JSON or a contained local JSON path descriptor. |
| [`ReportSettings`](../src/valpas/comparison/browser.py:13) | Independent HTML detail scope, payload budget and metadata-omission controls. |
| [`SampleMetadata(dataset, fields, records, subset_extra_observations=False, source_fingerprints=())`](../src/valpas/comparison/diagnostics.py:19) | Frozen exact-ID metadata. All three containers are required; fields and records may be empty. Dataset binding is checked at comparison/group-summary use. Source fingerprints are transport provenance, not schema-v1 document fields. |
| [`load_sample_metadata(value, *, base_dir=".")`](../src/valpas/comparison/diagnostics.py:105) | Load inline schema-v1 metadata or a contained local JSON path descriptor; fingerprint file bytes. Does not infer fields, types, IDs or binding. |
| [`DiagnosticRequest(query_id, candidate_id, layer_id, h=5, omission=False, group_field=None, include_fraction=True)`](../src/valpas/comparison/diagnostics.py:121) | One explicit pair/layer request, with optional categorical marginal summaries for its two features. No schema wrapper inside the manifest request list. |
| [`group_summary(layer, dataset, metadata, namespace, feature_id, field, *, include_fraction=True)`](../src/valpas/comparison/diagnostics.py:188) | One feature's categorical marginal summary on known-group, observed finite values; returns a detached JSON-safe dictionary with exact cohorts and independent fraction status. Namespace is the explicit ID/modality mapping, not a string. |
| [`covariance_diagnostic(layer, dataset, query_id, candidate_id, *, h=5, omission=False)`](../src/valpas/comparison/diagnostics.py:320) | One pair's joint-centered products, absolute shares and optional recentered omission preview; returns a detached JSON-safe dictionary. Layer is a validated profile-layer mapping, not the whole profile container. Metadata is not needed for covariance. |

Returned records also include [CompatibilityReport](../src/valpas/comparison/models.py), [RankView](../src/valpas/comparison/models.py), [Exclusion](../src/valpas/comparison/models.py), [QueryPool](../src/valpas/comparison/models.py) and [PoolResult](../src/valpas/comparison/models.py). Descriptors, nested metadata, pairs and returned scientific mappings are detached immutable mappings/tuples.

Run [the comparison example](../examples/compare_saved_results.py) from a source checkout for the complete load/compare/write/reload workflow, now using the separate [B1 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b1.json). The [A1 input example](../examples/inspect_comparison_inputs.py) still demonstrates input inspection/export using the original [no-profile manifest](../tests/comparison/fixtures/demo-01/manifest.json). The [A0 expected fixture](../tests/comparison/fixtures/demo-01/expected.json) remains the independent mathematical reference used by the A2 engine tests.

## Manifest and strictness

The top-level JSON object requires: schema_version (integer 1, not boolean), dataset, outputs (nonempty array), settings (object). Optional sections are profiles, report, sample_metadata and diagnostic_requests, validated by the [manifest loader](../src/valpas/comparison/adapters.py:358). Profiles/report follow the [Release A contract](COMPARISON_RELEASE_A.md); B1 sections are specified below. Omit optional metadata/profiles when absent rather than supplying null. Requests default to an empty list. References and other unsupported sections remain rejected, not silently accepted as implemented.

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

[Single-modality regression tests](../tests/comparison/test_single_modality.py) exercise protein-only and gene-only signed square outputs, rectangular subsets, missing scores/runs, exact namespace identity, explicit transposes/reordering, legacy symmetry, pandas structural adaptation, hand-calculated metric denominators, full A1/A2 bundle roundtrips and saved-CSV CLI manifests. The four-entity, three-output square case retains 48 full candidate rows (36 ranked off-diagonal rows and 12 excluded diagonal rows); requested depth 9 becomes 3. These are deterministic saved-output checks, **not evidence of real training or biological correctness**. The A3 browser and optional B1 metadata/diagnostics also support these namespaces; no second modality is required.

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

## B1 sample metadata and requested diagnostics

### Metadata document and binding

The optional manifest [sample_metadata section](../src/valpas/comparison/adapters.py:385) is either an inline document or an object containing only a local path to JSON, as in the [B1 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b1.json). Path containment and duplicate-key rules are the same as for other inputs; no CSV inference or coercion is supported. The [schema-v1 metadata document](../src/valpas/comparison/diagnostics.py:71) has exactly:

| Field | Shape / rule |
|---|---|
| schema_version | Integer 1, not boolean. |
| dataset | Complete identity descriptor explicitly matching the comparison dataset: source evidence, observation **set**, context and both namespaces as well as dataset ID. Unknown/null identity leaves cannot establish binding. |
| fields | Mapping of nonempty exact field names to categorical or continuous; an empty mapping is valid. |
| records | Explicit list of objects with exactly observation_id and values. Each ID is a unique nonempty exact string; values is a mapping using only declared field names. The list may be empty. |
| subset_extra_observations | Optional boolean, default false. Extra record IDs otherwise fail binding. When true, extras remain in normalized metadata and its table, flagged outside the required cohort, and are excluded from diagnostics with IDs disclosed. |

Categorical values are strings (including the **empty string**, which is available, not missing) or null. Continuous values are finite numbers or null, never booleans or numeric strings. IDs are not trimmed, case-folded, converted or matched by display label. Missing record, omitted declared field and explicit null all mean missing. Missing metadata **does not remove a sample from covariance**; categorical summaries exclude only the relevant missing grouping values. Metadata can be supplied without profiles or requests.

### Request scope and defaults

Each [DiagnosticRequest](../src/valpas/comparison/diagnostics.py:121) dictionary has required query_id, candidate_id and layer_id strings, and optional h (integer ≥1, default 5), omission (boolean, default false), group_field (nonempty categorical field name or null, default null), include_fraction (boolean, default true). No schema_version belongs in a request. The [validator](../src/valpas/comparison/models.py:414) requires profiles for nonempty requests, IDs on the union of declared query/candidate axes, an existing layer, and categorical metadata when grouping is requested. A declared feature missing from that layer is an **unavailable diagnostic**, not an invalid request. Requests are not restricted by top-list depth, report query scope, pair score availability or active scientific pool.

For manifest input, [`compare_results()`](../src/valpas/comparison/engine.py:282) inherits profiles and metadata when their arguments are None. The default empty tuple for diagnostic_requests inherits manifest requests; an explicit empty **list** clears them. A supplied nonempty list/tuple replaces them. For a sequence of outputs there is no manifest inheritance. Metadata and requests never alter all-query comparison scope, comparison ID, saved scores, ranks, eligibility, agreement or recurrence. Diagnostics are calculated lazily for export/iteration; browser diagnostics are independently on demand for embedded pairs, **not** an all-pairs overview computation or an automatic export of UI selections.

### Optional tables and nested JSON cells

[B1_COLUMNS](../src/valpas/comparison/engine.py:410) defines the following **ordered** columns. All CSV data cells, including result and namespace, are JSON encoded; parse CSV first, then decode each cell as JSON. Nested results are objects, not flattened extra columns. Full tables are independent of HTML scope/privacy settings.

| Table | Ordered columns | Presence / rows |
|---|---|---|
| sample_metadata | observation_id, field, field_type, value, status, in_required_cohort | Present whenever metadata is supplied, even with no fields/rows. One row per required observation and declared field, then permitted extra observations. Required IDs retain dataset order, extras and field names use Unicode order. Status is missing exactly when value is null; otherwise available. |
| diagnostics | query_id, candidate_id, layer_id, h, omission, result | Present only for nonempty requests. One covariance result per request in request order, including repeated scopes. Group/fraction options are persisted in the normalized request list, not extra columns here. |
| group_summaries | layer_id, namespace, feature_id, field, include_fraction, result | Present only if any request names a group field. Query then candidate marginal summaries, deduplicated at first occurrence by layer, full namespace/feature ID, field and include_fraction. No pair or output axis is implied. |

The [persisted table schemas](../src/valpas/comparison/report.py:35) record null/status meanings and units. Metadata values have supplied semantics, with no inferred units. Means use layer units; products and sample covariance use query-unit × candidate-unit; sums of squares use squared feature units; shares, correlations and fractions are unitless. Counts/h count observations. Null is unavailable, missing or not requested as explained by status/reason, **never a fabricated zero**.

### Exact group result shape and availability

The [group_summary result](../src/valpas/comparison/diagnostics.py:211) contains all of these fields on every path:

| Fields | Shape / meaning |
|---|---|
| layer_id, namespace, feature_id, field, field_type, include_fraction | Scope; namespace has id/modality. Field type is null if the field is absent. |
| required_count, required_observation_ids | Dataset cohort size and ordered exact IDs. |
| known_group_count, known_group_observation_ids | Required observations with a known group, irrespective of feature mask. |
| observed_finite_count, observed_finite_observation_ids | Required observations with an originally observed finite feature value, irrespective of group availability. |
| included_count, included_observation_ids | Intersection of the preceding two cohorts, in dataset order. |
| groups | Unicode-group-ordered list of objects with exactly group (string), count (integer), mean (number or null). Only included groups appear. |
| exclusions | Object with exactly missing_group and not_observed_finite, each an object with count and observation_ids. **Missing group has precedence**; not_observed_finite contains only known-group observations lacking an observed finite value. Counts are disjoint. |
| excluded_profile_observation_ids, excluded_metadata_observation_ids | Unicode-sorted permitted extras outside the required cohort. |
| mask_source, status, reason | Mask provenance; status available/unavailable describes group means. Available means have null reason. |
| between_group_ss, total_ss, between_group_fraction | Numeric values or null; calculated only when requested and available. |
| fraction_status, fraction_reason | Independent fraction availability: available/unavailable/not_requested, with null reason on success. |

Counts not yet evaluable are null and their ID lists empty; empty lists do not imply a known zero count. Once coverage/group type is usable, all cohort and exclusion counts are integers, including zero. Group means use each feature's **marginal**, not joint-pair, known-group observed finite cohort; cohorts can differ between the two features and from covariance. Condition/batch/genotype summaries are separate marginal descriptions, not adjusted variance components, causal effects or confounding corrections.

For included values, total SS is the sum of squared deviations from their overall mean; between-group SS sums each group count times its squared mean deviation from that overall mean. Their ratio is the optional fraction. Zero total variation leaves means available and both sums zero, but fraction null with fraction_status unavailable and fraction_reason zero_total_variation. If not requested, all three numeric fraction fields are null and both fraction status/reason are not_requested.

[Group reasons](../src/valpas/comparison/diagnostics.py:209), in precedence order, are missing_group_field, categorical_field_required, then profile coverage reasons missing_feature, missing_required_observations, original_mask_unavailable. Direct helper calls can return the first two; comparison requests reject invalid group fields earlier. Usable coverage but no included values gives no_known_group_observed_finite_values. Overflow/nonfinite intermediate arithmetic gives numeric_range: mean failure leaves means null and the summary unavailable; fraction-only failure leaves means available but the fraction unavailable. Finite imputed values and originally observed transformed nulls are excluded. Missing required profile IDs or unavailable original masks disable the summary rather than silently shrinking the required cohort.

### Exact covariance result shape and availability

The [covariance_diagnostic result](../src/valpas/comparison/diagnostics.py:336) always contains:

| Fields | Shape / meaning |
|---|---|
| layer_id, query_id, candidate_id, h, omission | Explicit diagnostic scope/settings. |
| required_observation_ids | Dataset cohort in dataset order. |
| joint_observed_count, joint_observation_ids | Joint originally observed finite cohort; count can be null when coverage cannot be evaluated. IDs use dataset order. |
| excluded_observation_ids | Required IDs not in the joint cohort, in dataset order. |
| excluded_profile_observation_ids | Permitted extra layer IDs, Unicode sorted. |
| mask_source, status, reason | Mask provenance and **influence** availability, independent of covariance/correlation availability. |
| products | List of objects with observation_id, product (signed centered product), absolute_share (number or null), in joint dataset order. |
| absolute_product_sum, largest_h_share | Absolute-product denominator and selected share, numbers or null. |
| selected_observation_ids, effective_h | IDs in descending absolute-product order, ties by exact Unicode code point; actual selected count, at most h and joint size. |
| original, remaining | Statistics objects with exactly count, mean_x, mean_y, covariance, correlation, status, reason, covariance_status, covariance_reason, correlation_status, correlation_reason. |
| omitted_observation_ids, retained_observation_ids | Selected-order omitted IDs when explicitly previewed; retained IDs in joint dataset order. Otherwise omissions are empty and the full joint cohort is retained. |

On the joint cohort of size n, each product is (x − joint mean x) × (y − joint mean y). Absolute share divides the product's absolute value by the sum of all absolute products; largest-h share sums those selected absolute shares. **Signed products are retained**, not replaced by their absolute values. Sample covariance divides the signed product sum by **n−1**, not n. Original/remaining statistics require at least three points. Pearson correlation additionally requires nonzero variance in both variables. A constant variable can therefore have available zero covariance and unavailable null correlation (zero_variance). Overall statistics status follows covariance, not correlation or influence.

Explicit omission removes selected observations and **recomputes both means** on retained pairs before covariance/correlation; at least three retained points are required. This does not refit, retrain, rescore or rerank any method, and is not leave-one-out model evaluation or evidence of what caused an AE nomination. Default h = 5 can leave too few points in a small cohort; request a smaller h explicitly when appropriate.

[Influence reasons](../src/valpas/comparison/diagnostics.py:335) include missing_feature, missing_required_observations, original_mask_unavailable (query coverage takes precedence over candidate coverage), no_jointly_observed_finite_values, insufficient_joint_observations (one or two pairs), zero_absolute_product_sum and numeric_range. When influence is unavailable, selection/omission lists stay empty, effective_h is zero and largest_h_share is null. A zero denominator retains zero products with null absolute_share; insufficient pairs/coverage or product arithmetic failure leave products empty. Original statistics may still be available independently of influence (for example zero products). No omission is performed if influence is unavailable.

[Statistics reasons](../src/valpas/comparison/diagnostics.py:276) include insufficient_observations and numeric_range; correlation has its independent zero_variance/numeric_range reason. When omission is false, remaining count/means/covariance/correlation are null, all three statuses unavailable and all three reasons not_requested. With requested but unavailable influence, remaining carries the influence failure reason (and joint count if known), not a fabricated omission result. On successful statistics, corresponding reasons are null. Overflow/nonfinite intermediate arithmetic is reported as numeric_range, never serialized as Infinity/NaN or silently treated as zero.

### Persistence, browser scope and privacy

New [result-schema-v3 completion records](../src/valpas/comparison/report.py:148) add a b1 object with exactly sample_metadata (presence boolean) and diagnostic_requests (normalized list including every default). When present, the metadata document is stored once as [sample_metadata.json](../src/valpas/comparison/report.py:135); profiles are likewise stored once as [profiles.json](../src/valpas/comparison/report.py:133). Optional tables have the scopes above, not an implicit all-pairs expansion. Normalized metadata, requests and tables are validated on source-free reload. A1 input bundles remain a separate contract; the B1 workflow uses a manifest or result bundle.

Report settings, profiles, sample metadata and requests are descriptive and do **not** enter the scientific comparison ID. Their persisted bytes/settings are instead covered by inventory and normalized-content/report checks. Categorical/continuous color and explicit display ordering affect only presentation. The [HTML payload budget](../src/valpas/comparison/browser.py:163) includes embedded sample metadata as well as profiles and other escaped JSON; a smaller detail-query scope does not automatically subset metadata records. Metadata omission removes profiles and sample metadata **from HTML/report-view payload only**. The complete bundle retains metadata, profiles, diagnostic tables, canonical IDs and other sensitive data; it is not redacted or anonymized. Share only inspected HTML when using omission.

## Result bundles, identity and publication

An A2 result bundle is distinct from an A1 input bundle. Its [completion record](../src/valpas/comparison/report.py:87) stores ownership kind, schema/software/policy versions, resolved settings, dataset scope, comparison ID, warnings, normalized descriptors, source fingerprints, table schemas/row counts and exact file inventory with SHA-256/byte counts. Gzip JSONL members contain explicit full-precision saved pair records; original completeness and implicit missing semantics remain in the descriptors. Candidate-rank, recurrence and exclusion CSV tables are gzip-compressed; the other tables are plain CSV. Original source files can be deleted after export; reload never opens recorded original paths.

**CSV encoding:** headers are ordinary column names, but **every data cell is a JSON value**. Decode each cell as JSON after CSV parsing. This distinguishes null, empty strings, numbers, booleans and structured metadata without coercing exact IDs. Python's standard JSON encoder roundtrips saved binary float precision. These canonical files are machine-readable, not spreadsheet-safe or privacy-filtered exports; identifiers, metadata and original source paths may be sensitive.

The comparison ID hashes canonical normalized IDs/values/statuses, scientific descriptors, resolved settings, dataset identity, and schema/policy/software versions. It is independent of input ordering, matrix-axis ordering, depth/attestation ordering, labels, descriptive provenance, source paths and export timestamps. Generic configuration arrays retain their declared order (for example architecture dimensions or training-input order); reordering them is not presumed semantically equivalent. Changing saved values, counts, missing statuses, scientific settings or run identity changes the ID. Raw source SHA-256 hashes cover exactly the bytes parsed and are separate provenance: rewriting a source file with equivalent formatting can change its raw digest without changing comparison identity. In-memory inputs receive canonical content hashes without pretending that file bytes existed.

Reload validates member names, no symlink members, exact inventory, checksums, completion/schema/version, normalized contracts, comparison identity, warnings, and every table row against recomputed saved-value ranks/metrics and requested B1 descriptions. This recomputation is not fitting or association scoring. The writer emits result v3, including when B1 data is absent. A2 v1 and A3 v2 reload are supported only with the **same software/policy versions and expected table schemas**; no cross-software-version migration is implemented. Checksums are integrity checks, not proof against forged provenance.

For A3 v2 HTML bundles, [legacy report validation](../src/valpas/comparison/report.py:335) checks inventory hashes/sizes for the old HTML/assets rather than demanding byte equality with today's assets. The stored and embedded payload must agree and match normalized saved values/settings under the known A3 projection (removing only the additive B1 metadata field and corresponding omission wording); the stored payload hash, byte count and old budget are also checked. Legacy payloads cannot carry B1 metadata. Regeneration deliberately writes **current assets and result v3**, subject to the current payload budget. Current v3 HTML/payload is checked against current rendering exactly.

Publication writes to a temporary sibling and writes completion last, then publishes by rename. Existing destinations, including empty directories, are refused by default. Explicit overwrite accepts only a fully validated owned A2 bundle with no foreign members, never a consumed-source directory, A1 bundle, symlink, or unrelated directory. The old bundle is moved to a sibling backup and restored on publication failure; exporter-owned staging is cleaned. A result loaded from a bundle cannot overwrite that supplying bundle. Use a new destination to re-export it. This is staged local publication with rollback, not a crash-durable filesystem transaction or protection against hostile concurrent modifications; a process crash during replacement may leave a sibling backup requiring recovery.

## CLI and example workflow

The [compare command](../src/valpas/cli.py:304) accepts an input manifest or saved result bundle, required outdir, report scope/pin/depth/budget controls, optional manifest analysis pool/depth overrides, explicit tables-only, and safe overwrite. HTML is the default. It calls the public loader, engine and writer; resolved overrides are persisted. Failures exit nonzero with field/reason/remediation rather than proceeding with partial scientific results. No target-query argument is required. See the [Release A guide](COMPARISON_RELEASE_A.md) for all options and regeneration.

From a source checkout, run the following command against the [demo manifest](../tests/comparison/fixtures/demo-01/manifest.json), choosing a new output directory:

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest.json --outdir demo-comparison --pool common --depths 1 2 5 --tables-only
```

The [Python example](../examples/compare_saved_results.py) prints the overview before detail, writes HTML and checks roundtrip parity. Begin with dataset/query/agreement summaries, then inspect coverage, exclusions, pairwise agreement and separate run recurrence. The explicit tables-only command above omits HTML.

## Phase boundary and limitations

- A0–A3 and B1 are implemented; B2/B3 remain unfinished. Neither release is being declared finally complete for the modified B1 tree.
- B2 reference/session/figure features and export-query command, and B3 production export hooks/target-scale checks remain unimplemented. No placeholder APIs for those phases are exported. The [implementation plan](../plans/METHOD_COMPARISON_IMPLEMENTATION_PLAN.md) separates original A3 packaging evidence from pending final validation of modified B1 assets.
- NumPy loading is deliberately omitted; all required representations work with JSON/CSV/TSV and standard-library code.
- The adapter reads structural labeled matrices; it does not introspect omics objects to guess namespaces or provenance. It requires explicit metadata and selections.
- File loaders materialize parsed input contents and complete inputs use per-pair Python records. A2 processes detail tables one query at a time and streams export/reload validation; compact summaries scale with query/output-pair/depth counts. No giant expanded rank/exclusion/recurrence table is retained. A 20-query × 100-candidate × 3-output smoke test verifies 6,000 full-rank rows and streamed write/reload, not target-scale performance. The B3 1,000 × 5,000 × 8 measurement and compact input storage remain future work.
- Bundle export is opt-in and separate from legacy production/save methods. Legacy filenames, behavior and precision are unchanged.
- Earlier full-dependency legacy imports, documentation/Sphinx and cross-attention environmental follow-ups remain separate from comparison validation. No dependencies are installed or training suites run for A2.
