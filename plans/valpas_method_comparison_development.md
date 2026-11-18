# VaLPAS within-dataset method comparison: development handoff

**Status:** implementation plan, not implemented. Written 2026-11-16 after targeted read-only inspection of the sibling VaLPAS repository. This document is sufficient context for a separate development session; the paper analyses need not be rerun.

**Development target:** the standalone VaLPAS package, currently located at [the sibling repository](../../valpas/README.md), not the paper repository's vendored copy. Source links below are relative to this document. Proposed source paths are recommendations, not claims that those files already exist.

## 1. Objective and interpretation

Build a comparison workspace for **different association approaches applied to the same dataset**. Its central question is:

> For this query, which candidates do the approaches nominate, how consistent are those nominations, and what in my data warrants closer inspection?

A query can be a metabolite, protein, or another molecular feature. A useful outcome is a documented decision to investigate a candidate, retain alternatives, or abstain. The feature is not an automatic method selector or a biological validation engine.

The initial implementation consumes existing scores or rankings. It must not train models, recompute associations, download annotations, load model checkpoints, or contact remote services. Observed-profile summaries are allowed and must be distinguished from the saved association scores.

### Why this feature is needed

Paper-level comparisons showed that aggregate reference recovery and candidate agreement answer different questions. Several approaches can recover some annotated candidates while nominating very different proteins for an individual query. Repeated autoencoder runs can also disagree substantially. A user therefore needs to inspect nominations, reproducibility across runs, measurement coverage, and underlying observations together.

The motivating paper examples include a knockout dataset, but the production feature must work with ordinary observational datasets. Strong covariance driven by a few observations is a diagnostic, not proof of a direct interaction. In particular, a covariance diagnostic does not attribute an autoencoder score to those observations. Shared pathways are not equivalent to direct reaction evidence, and unsupported candidates are not established negatives.

### Terminology that the UI and exports must preserve

| Term | Meaning |
| --- | --- |
| Dataset | Identified measurements, feature namespaces, observation identities, and experimental context. A name alone is insufficient identity evidence. |
| Method | Algorithm family, such as Pearson, Spearman, mutual information, or an autoencoder. |
| Configuration | Method plus non-seed parameters, preprocessing, training inputs, observation selection, and score definition. |
| Run / output | One saved result from a configuration; a stochastic run may have a seed. |
| Comparison pool | Explicit query and candidate eligibility rules used to compare outputs. |
| Native pool | Each output's original candidate universe, after declared self-edge exclusion. |
| Common pool | Shared eligible candidates with known finite scores or complete ranks in every included output for a query. |
| Nomination | A candidate appearing in a selected top list; not a validated prediction. |

Example: Pearson plus three seeds of the same autoencoder configuration is **two methods, two configurations, four outputs**, not four independent methods. An autoencoder with different architecture or preprocessing is a different configuration, not another seed replicate.

## 2. Scope and completion boundary

### Release A: usable core

- Import compatible saved scores, complete rankings, and explicitly limited legacy lists.
- Validate identity, orientation, pool, completeness, and ranking policy.
- Compare query-centric nominations with native scores and full-pool ranks where available.
- Separate between-method/configuration agreement from within-configuration run variability.
- Provide dataset-level coverage and overlap summaries.
- Show observed profiles and missingness when measurement data are supplied; operate without them otherwise.
- Export a self-contained offline HTML report, machine-readable tables, and reproducible settings/provenance.
- Add a public Python API, dedicated CLI command, documentation, synthetic example, and focused tests.

### Release B: complete the approved user workflow

- Sample-metadata overlays and generic condition/batch summaries.
- Descriptive covariance-influence diagnostics.
- Optional reference support and recovery, with reachability and weighting explicit.
- Candidate shortlists, notes, portable session state, and publication-oriented query figures.

Both releases are part of this handoff. A developer implementing only Release A must label Release B unfinished rather than declaring the entire feature complete.

### Explicitly deferred

Cross-organism or cross-experiment mapping; automated orthology; new training/scoring orchestration; leave-observation-out retraining; automatic confounder adjustment; permutation/bootstrap significance; calibrated correctness probabilities; automatic consensus rankings, ensembles, or best-method recommendations; remote annotation acquisition; collaborative accounts or hosted dashboards.

A future explicit sensitivity workflow may create new results and compare them, but selecting points or filtering a plot in this feature must never silently refit or rerank saved associations.

## 3. Existing code and integration constraints

These observations describe the inspected checkout, not an exhaustive code audit. Check the relevant signatures if the development checkout has changed; do not perform a broad repository review before starting.

| Existing interface | Integration consequence |
| --- | --- |
| [Public association entry point](../../valpas/src/valpas/valpas_core.py:21) | Performs preprocessing, association calculation, and output writing. Do not invoke it to load saved results. |
| [Association result container](../../valpas/src/valpas/_core/classes/results.py:297) | Holds score and count matrices, omics objects, optional annotations, and an edge list. Adapt the matrices directly without modifying the object. |
| [List conversion](../../valpas/src/valpas/_core/classes/results.py:373) and [result saving](../../valpas/src/valpas/_core/classes/results.py:399) | Can mutate metadata/matrices. Do not use these as supposedly read-only comparison adapters. |
| [Legacy output conversion](../../valpas/src/valpas/io.py:318) and [writing](../../valpas/src/valpas/io.py:369) | Drop all-missing rows/columns. Matrix text output combines score and count and rounds scores to five decimals. Lost identities/precision cannot be reconstructed. |
| [AE result persistence](../../valpas/src/valpas/_core/autoencoder.py:1590) | Saves a similarity CSV separately from a model checkpoint. Use the CSV, with explicit metadata; comparison does not need the checkpoint. |
| [Generic analysis results](../../valpas/src/valpas/_core/classes/results.py:27) | Offers metadata and JSON/HTML serialization, but is not a complete comparison contract. Prefer a dedicated result object rather than forcing comparison into existing confidence/report semantics. |
| [CLI](../../valpas/src/valpas/cli.py:30) | Add a dedicated comparison command. Its parsing must delegate to the same API used by Python callers, rather than duplicating scientific logic. |
| [Data conventions](../../valpas/README.md:102) | File workflows and direct AE workflows use different orientation conventions. Normalize from explicit identifiers, not shape-based guessing. |
| [Dependencies and package configuration](../../valpas/pyproject.toml) | Existing NumPy, pandas, Matplotlib, and Plotly are sufficient. Avoid a web framework or mandatory new runtime dependency. Include report assets in both wheel and source distributions. |

Do not route overlap/recurrence through existing confidence-evaluation functions. Do not inherit global warning suppression, automatic pickle deserialization, or unsafe HTML interpolation from unrelated code. Avoid opportunistic refactoring of the old result/export system.

### Paper prototypes: design references only

- [Query report builder](../scripts/build_query_results.py): candidate unions, inverse ranks, pairwise overlaps, offline query browser.
- [Query report](../analysis/30_query_results/RESULTS.md): examples of aggregate versus query-level disagreement.
- [Case-study builder](../scripts/build_query_case_studies.py): observed-profile plots and covariance diagnostics.
- [Case-study interpretation](../analysis/31_query_case_studies_v2/CASE_STUDIES.md): limitations of influence and reference evidence.

These have hardcoded datasets, paths, conventions, and selection policies. Do not import them as production dependencies or transplant their historical authorization/provenance machinery. Their rank arrays are zero-based **candidate permutations**, not inverse ranks; an adapter must never confuse the two.

## 4. Architecture and public interface

### Proposed package layout

Use a small cohesive package; combine modules if helpful, but keep adapters, scientific calculations, and rendering separate.

| Proposed location | Responsibility |
| --- | --- |
| [Comparison API](../../valpas/src/valpas/comparison/__init__.py) | Stable public imports and orchestration entry points. |
| [Models](../../valpas/src/valpas/comparison/models.py) | Versioned input/result/settings contracts and typed validation errors. |
| [Adapters](../../valpas/src/valpas/comparison/adapters.py) | In-memory result, labeled matrix, long-table, and rank-permutation conversion. |
| [Compatibility](../../valpas/src/valpas/comparison/compatibility.py) | Identity checks, comparisons of configuration metadata, pool construction, exclusions. |
| [Ranking and metrics](../../valpas/src/valpas/comparison/ranking.py) | Deterministic ranking, overlaps, recurrence, and summaries. |
| [Profiles](../../valpas/src/valpas/comparison/profiles.py) | Measurement alignment, missingness, overlays, and descriptive influence. |
| [Reference evaluation](../../valpas/src/valpas/comparison/reference.py) | Optional evidence attachment, reachability, retrieval, and grouped weighting. |
| [Report/export](../../valpas/src/valpas/comparison/report.py) | Tables, offline HTML, session/shortlist import/export, figure export. |
| [Packaged assets](../../valpas/src/valpas/comparison/assets/) | Local HTML/CSS/JavaScript templates; no remote dependencies. |
| [Focused tests](../../valpas/tests/test_comparison.py) | Core contract and metric tests; split further when warranted. |
| [Example](../../valpas/examples/compare_saved_results.py) | Small synthetic, score-only end-to-end example without training. |

### Proposed API contract

The following names are **new API proposals**. Implement equivalent named, documented interfaces; settle any renaming before adding examples.

- [ComparisonInput](../../valpas/src/valpas/comparison/models.py:1): one normalized output plus provenance, identity, score/rank representation, and completeness.
- [ComparisonSettings](../../valpas/src/valpas/comparison/models.py:1): pool policy, requested depths, self-edge rule, metadata attestations, report limits, and optional diagnostic/reference settings.
- [ProfileData](../../valpas/src/valpas/comparison/models.py:1): explicitly aligned measurement layers, masks, and sample metadata.
- [ReferenceData](../../valpas/src/valpas/comparison/models.py:1): optional local evidence records, coverage declaration, and optional query groups.
- [ComparisonResult](../../valpas/src/valpas/comparison/models.py:1): normalized settings, compatibility report, coverage, candidate ranks, pairwise agreement, run recurrence, optional profiles/diagnostics/reference tables, and warnings. No trained model objects.
- [load_comparison_input()](../../valpas/src/valpas/comparison/adapters.py:1): accepts a versioned input descriptor and loads only its named files.
- [from_association_result()](../../valpas/src/valpas/comparison/adapters.py:1): accepts an existing result plus required identity/ranking metadata and query/candidate axis selection; returns a detached comparison input without saving or mutating the source.
- [compare_results()](../../valpas/src/valpas/comparison/__init__.py:1): accepts a sequence of inputs, settings, optional profiles, and optional references; returns a comparison result. Requires at least two outputs, but can validly compare two runs of one configuration.
- [write_comparison()](../../valpas/src/valpas/comparison/report.py:1): accepts a comparison result and destination; writes the report and tables, refusing overwrite by default.
- [export_query_figure()](../../valpas/src/valpas/comparison/report.py:1): accepts the result, query/candidate selection, layer and display settings, and destination; exports SVG or PDF without recomputing associations.

Core import and saved-score comparison should not require importing the autoencoder/training modules. Use an adapter protocol or local import for the existing association result class if needed to avoid heavyweight import chains.

### CLI contract

Add a command named **compare**, with a required manifest argument and output-directory argument. The manifest holds substantive settings; flags may override pool policy, report depth limit, or overwrite behavior, and the resolved values must be recorded. Do not require users to encode a large multi-output comparison in dozens of positional arguments.

Provide an **export-query** subcommand or equivalent documented API for publication figures from a saved comparison bundle. It must work without original model checkpoints. An example comparison manifest shipped with the synthetic example is required.

CLI behavior: print a concise compatibility/coverage summary, warnings, and the report location. Use a nonzero exit status for invalid inputs or failed writes. Distinguish a valid report with unavailable metrics from a failed comparison. An empty common pool is an actionable error, not a successful blank report.

## 5. Versioned data contracts

### 5.1 Manifest and identity

Use schema version 1 and JSON plus UTF-8 CSV/TSV and, optionally, non-object NumPy arrays. No executable configuration, remote URLs, or pickle. Paths in an input manifest are relative to that manifest; explicit absolute paths may be accepted for local API use but exported records should favor portable relative paths. Never infer a path from a feature label.

Required top-level manifest sections: schema version, dataset descriptor, output descriptors, settings. Optional sections: profiles, sample metadata, references, query groups. Reject unsupported schema versions and unknown substantive settings rather than silently ignoring misspellings.

Dataset descriptor fields:

| Field | Contract |
| --- | --- |
| dataset_id | Stable user-visible identifier; must agree across compared outputs. |
| dataset_evidence | Content fingerprint or a documented user attestation tying legacy outputs to the same measurement source. Record evidence type and limitations. |
| observation_ids | Exact observation IDs used for each output, or explicit unknown status for legacy results. No inferred numeric/string coercion. |
| feature namespaces | Namespaces for query and candidate IDs, including modality; raw labels alone do not establish identity. |
| context | Experiment/condition/subset description. Same species or overlapping identifiers do not establish the same dataset. |

For new VaLPAS exports, record a dataset fingerprint from the actual source measurement artifact(s), the selected observation IDs, and selection metadata. Store preprocessing identity separately. Reordered labeled axes can be aligned; changed observations or measurements cannot be silently accepted as the same comparison.

For legacy imports with missing provenance, require a specific attestation naming the missing fields and the claimed common source. Display **user-attested compatibility; provenance incomplete**. This is not a generic force flag: it cannot override a known dataset or observation mismatch. Unknown preprocessing prevents claims of isolated method effects and prevents grouping outputs as seed replicates unless the user supplies an explicit non-seed configuration attestation.

### 5.2 Per-output descriptor

Required fields: output ID, display label, method ID, configuration ID, run ID, optional seed, dataset binding, observation binding, preprocessing description/fingerprint, non-seed method parameters, software/source provenance, query/candidate namespace and ordered IDs, orientation, representation, ranking policy, completeness, and input paths or in-memory arrays.

- Output IDs must be unique. A seed alone is not a run identity.
- Configuration identity includes preprocessing, score semantics, non-seed parameters, training supervision, and observation selection. Missing parameters remain unknown; do not manufacture equality from empty dictionaries.
- IDs are case-sensitive opaque strings. Preserve leading zeros and whitespace unless an explicit, recorded import normalization is requested. Duplicate canonical IDs are errors. Labels are optional and need not be unique.
- Canonical internal orientation is query rows by candidate columns. A square matrix still requires explicit axis semantics. Cross-omics matrices may be rectangular or selected blocks from a square matrix.
- Query-dependent eligibility can be expressed as an optional long table of query/candidate eligibility and reason. Otherwise the declared candidate list applies to all queries, subject to self-edge rules.
- Native scores retain their sign and units. Optional pairwise counts retain their original meaning; counts are not observation masks.

### 5.3 Supported representations and completeness

| Representation | Required information | Allowed behavior |
| --- | --- | --- |
| Labeled score matrix | Exact axes, score definition, direction/transform, finite-value status | Rank all finite eligible values deterministically. |
| Long score table | Explicit query, candidate, score columns; complete axis lists; duplicate/missing policy | Pivot/stream by IDs. Missing rows are not automatically zero or worst-ranked. |
| Full rank permutation | Ordered candidate-ID universe and integer permutations for every query; index base declared | Validate each row's exact permutation; derive one-based inverse ranks. Scores may be unavailable. |
| Complete ordered rank table | Unique consecutive one-based ranks among all scorable eligible candidates and complete eligibility/status metadata | Preserve declared ranking policy; filter/rerank by order when forming a common pool. |
| Certified top-prefix table | Per-query saved depth, original pool identity/size, exact native ranks, confirmation of complete prefix and tie policy | Native top-list comparisons only at depths fully covered; outside-prefix ranks remain unknown. |
| Arbitrary filtered/thresholded edge list | Declared filtering and explicitly unknown omissions | Inspection-only; no full-rank, top-k, overlap, or recovery claims unless sufficient completeness is separately established. |

Non-finite scores are unscored, not bottom-ranked. Infinity is invalid input unless an adapter explicitly converts it to an unscored status with a warning. NaN represents unscored only under the declared format policy. Preserve a status/reason for missing query, ineligible candidate, unscored pair, and unreported/truncated pair.

A saved top prefix can be used at a depth larger than its length only if it certifies that the original pool is exhausted. Common-pool reranking of truncated lists is not supported in version 1: unseen candidates might move into the top list. Request a complete saved result rather than pretending the filtered prefix is complete.

If both scores and ranks are supplied, validate their consistency with the declared policy. Reject contradictions; never silently choose whichever is convenient. Legacy rounded matrix imports are ranked on their available precision and flagged accordingly, without claiming exact reproduction of original full-precision ranks.

### 5.4 Concrete small example for documentation

Ship two labeled score matrices with query IDs M01 and M02, candidate IDs P01, P02, P03, and shared observation IDs S01 through S06. Use method IDs pearson and autoencoder, configuration IDs pearson-base and ae-base, and outputs pearson-run, ae-seed-42, and ae-seed-123. The two AE outputs share their complete non-seed configuration and differ in run ID and seed. All bind to dataset demo-01 with identical source identity.

For M01, a Pearson row of −0.9, +0.8, +0.1 ranks P01, P02, P03 under absolute-descending policy. An AE ordering P02, P01, P03 gives top-two overlap 1 and top-one overlap 0 against Pearson. Display the negative Pearson score unchanged. Include a second query with a missing score to demonstrate common-pool exclusions and unavailable native-pool comparability. This example requires no fitting.

## 6. Compatibility and pool rules

Perform validation once in the normal load/compare operation, before expensive materialization or output creation. Return structured errors/warnings with output ID, field, affected examples/counts, and remediation.

### Hard errors

- Known different datasets, incompatible feature namespaces, or different observation sets/context.
- Duplicate IDs, conflicting duplicate pairs, malformed rank permutations, missing axis mapping, inconsistent supplied scores/ranks, or unknown ranking direction.
- Conflicting configuration metadata for outputs assigned to the same seed/run group.
- Empty shared query or candidate cohorts for a requested common comparison.
- Requested operation requiring complete rankings when only uncertified/truncated lists exist.

Reordering observations is harmless when IDs and source identity establish equivalence. Different observation subsets are not fixed by intersecting feature lists. Comparing different experiments/conditions is outside this feature.

### Pool policies

1. **Strict (default):** equal query and eligible candidate sets, aligned by ID. Differences in row/column order are accepted. Keep native ranks. If finite/scorable candidate sets differ for a query, retain inspection results but mark controlled overlap/recurrence unavailable for that query, with a reason and a suggestion to choose common-pool mode. Certified prefixes require the same certified native pool and sufficient depth.
2. **Common:** explicitly intersect query identities and, separately for each query, eligible scorable candidates across all included outputs. Require complete representations. Recompute ranks within that common pool by filtering existing scores/order; never fit or score again. Export every exclusion with an output/reason and both original and retained counts. Different queries can have different common-pool sizes.
3. **Native inspection:** show each output in its own pool, retaining missing/unknown statuses. Native overlaps may be displayed only when top-list completeness is certified; label them **different search spaces; descriptive only**. Do not pool them into the controlled comparison summary or seed-stability headline.

Always retain native rank alongside common-pool rank when common mode is used. The UI must identify the active rank/pool. Exclusions change the scientific question, not merely a plotting detail. Annotation availability never defines the nomination pool.

Different preprocessing with the same source dataset is allowed, but triggers a persistent **analysis configurations differ; not an isolated method comparison** banner and a field-level difference table. Different model training feature sets should also be disclosed, even when the compared query/candidate block is shared.

## 7. Ranking and comparison calculations

### Ranking policies

Every scored output declares one of: native descending, native ascending, absolute descending, or absolute ascending. Do not apply absolute value universally; distance measures usually need ascending order. An explicit policy supplied by the user is recorded as such. Built-in defaults are allowed only for a known, documented metric—not inferred from a generic score column.

Use deterministic ordinal ranks: sort by transformed score in the declared direction, then canonical candidate ID in Unicode code-point order, independent of locale. Exact stored-value ties only; no hidden rounding or tolerance. Keep raw scores and optional tie-block sizes. Top lists contain exactly the requested number where possible, not all boundary ties. Certified external ranks must declare their tie policy; differing policies are visible configuration differences.

Self edges are excluded by default only when query and candidate denote the same canonical entity in the same namespace. Equal display text across different modalities is not a self edge. Within-modality undirected matrices provide a candidate list for every query; do not globally deduplicate edges and thereby lose one query's rankings. Legacy triangular tables require declared symmetry before reconstructing reciprocal entries; conflicting reciprocals are errors.

### Top-list agreement

For a query and requested depth k, use the same eligible scorable pool for controlled comparisons. Let d be the smaller of k and the pool size. Record both k and d. Lists A and B each contain d candidates:

- Shared count: size of the intersection.
- Overlap fraction: shared count divided by d.
- Jaccard: shared count divided by the union size.
- Report unavailable, not zero, when d is zero or the lists are not certified to cover d.

For native-inspection lists of unequal known lengths, report both lengths, shared count, union size, Jaccard, and each directional shared fraction. Do not call shared divided by k the overlap fraction when either list is shorter. Unknown truncation is not a short complete list.

Output pair classifications: same-configuration different-run; same-method different-configuration; different-method. Pairwise tables always retain output IDs, so extra AE runs cannot disappear into a misleading algorithm label.

### Run recurrence versus method agreement

For each candidate/query/configuration/depth, count the number of runs in whose top list the candidate appears, with the number of evaluable runs. Require at least two comparable runs to call this reproducibility; otherwise display not assessed. Strict/common pool rules apply. For a query with incomparable runs, do not quietly reduce the denominator and describe the remainder as the complete run group.

Candidate tables may show descriptive configuration presence and method presence, but must expose the rule: present in at least one evaluable output, plus per-configuration numerator/denominator. More runs create more chances for an any-run nomination. Therefore these counts are not votes, significance, or a consensus score; do not use them for a default leaderboard or merge configurations behind a single opaque method number.

When a user requests an algorithm-level pairwise summary, require an explicit representative output per method/configuration, or show all run-pair values and their spread. Do not silently choose a best seed or average raw scores.

### Dataset summaries

For each output pair and depth, report eligible/evaluable/excluded query counts, median, quartiles, and range of per-query overlap. Provide the per-query values and exclusion reasons. Histograms/distributions should allow navigation to individual queries. Do not average all run pairs into a single method score, pool incompatible query cohorts, or impose a universal stability cutoff.

Defaults: compute summary depths 5, 10, and 20; query browser supports integer depths from 1 through a recorded export maximum, initially 50. A smaller pool uses the explicit d rule. Filtering/searching the displayed table does not change ranks or metric denominators.

## 8. Query and dataset user interface

### Dataset overview

Display dataset identity/evidence, number of methods/configurations/outputs, observation count, query/candidate coverage, active pool policy, preprocessing differences, incomplete metadata, unavailable metrics, and report scope limits. Provide separate panels for between-output agreement and within-configuration variability.

Allow sorting queries by disagreement, recurrence, missingness, or optional reference opportunity. These are navigation aids, not a ranking of biological truth. Every summary metric links to the underlying query table and its denominator.

### Query workspace

- Search by canonical ID, label, modality, or optional annotation; duplicate labels remain disambiguated by ID.
- Show the union of all included outputs' top lists at the chosen depth, plus explicitly searched or pinned candidates.
- For every displayed candidate, show rank in each output's full active pool, native rank when different, native score/sign where available, and missing/unknown status otherwise.
- Show configuration-level run recurrence separately from descriptive cross-method presence.
- Allow user-selected sorting, filtering, and pinning. Default to canonical candidate ID rather than an undeclared consensus ranking.
- Show observed coverage and optional reference evidence without hiding unsupported candidates.
- Candidate selection opens paired profiles; unavailable data produce an explanation, not an empty plot or invented values.
- Persistent interpretation text: agreement is not correctness; low agreement alone does not invalidate every candidate; annotation support is incomplete; profile diagnostics are not model attribution.

### Offline behavior and scope limits

The main report must work when opened directly from local disk, without a server, network request, CDN, or browser filesystem permission prompt. Embed data and required assets; if Plotly is used, bundle its runtime locally/inline. A small custom SVG profile renderer is also acceptable.

Bound report size explicitly rather than silently truncating scientific tables. Default maximum embedded payload: 50 MiB before HTML wrapping; expose the resolved limit. If exceeded, stop report writing with a clear estimate and offer documented options: a specified query subset, a lower interactive depth maximum, or tables-only export. No automatic sampling or silent omission. Scientific table export can stream independently and remain complete.

Record report query subset and depth limit separately from analysis scope. Re-exporting a smaller/larger report uses saved normalized results and does not recompute associations. Store feature profiles once per layer rather than repeating them for every candidate pair. Include full rank information in the machine-readable bundle even when the browser embeds only the candidate union up to its maximum depth. Arbitrary candidate search beyond the embedded union must report that limitation and permit documented re-export with explicit pinned IDs.

## 9. Profiles, masks, and diagnostics

### Measurement contract

Profiles are optional. Each measurement layer has a layer ID, units/transform description, source provenance, exact feature and observation IDs, values, and mask availability. Normalize to feature rows by observation columns. Layers can include raw, transformed, and imputed data; there may be a different analysis layer for each output/configuration.

Preserve the original observation mask independently of finite imputed values. If only imputed values are supplied and the original mask is absent, observed missingness is unknown. Never infer an original observed mask from those imputed values. An explicitly declared raw/unimputed layer may use finite values to construct a mask, with that derivation recorded.

Align profiles by IDs, not position. Extra profile observations may be explicitly subset to the saved output's observation set, with exclusions recorded. Missing required observations/features disable the affected diagnostic or plot with a reason; do not silently change the plotted cohort. A separate data layer not demonstrably tied to the same dataset must not be presented as the underlying data for the score.

### Release A displays

Paired scatterplot on jointly observed values; per-feature sample profile; number jointly observed; missing counts/fractions for each feature; constant/near-empty profile flags. Hover or selection reveals sample ID and values. Imputed points, if shown, use a distinct style and are excluded from observed-only diagnostics. Plot titles/captions name the layer and disclose that it may differ from the layer used by the algorithm.

### Release B overlays and summaries

Accept sample metadata keyed by unique observation ID. Show missing metadata explicitly. Offer user-selected categorical coloring for condition, batch, genotype, or arbitrary supplied fields, and continuous coloring for numeric fields. Preserve sample order or apply an explicitly selected display order; neither changes association rankings.

For a selected categorical grouping and feature, compute group sample counts and means on observed values. Optionally report the between-group sum of squares divided by total sum of squares, using only observations with known group and observed feature value. Missing groups are excluded with counts; zero total variation is undefined. Condition and batch summaries are separate marginal descriptions, not adjusted variance components, causal effects, or automatic confounding corrections.

### Covariance influence: exact descriptive definition

On a selected query/candidate/layer, use only jointly observed finite pairs. For each observation, compute the product of its query deviation from the joint-sample mean and its candidate deviation from the joint-sample mean. Report its signed product, absolute-product share, and sample ID.

Report the largest-h absolute-product share, with default h = 5, as the sum of the largest h absolute products divided by the sum of all absolute products. Record the actual number selected; ties are resolved by observation ID. Zero denominator or fewer than three joint observations gives an unavailable result with reason.

Offer an explicit **descriptive omission preview**: remove the selected h observations, recenter both remaining profiles, and report original versus remaining Pearson covariance/correlation where defined. Require at least three remaining points and nonzero variance for correlation. This operation changes neither saved ranks nor AE scores. Label it as a profile diagnostic, not leave-one-out model evaluation; it must not be described as evidence that those points caused a nonlinear model's nomination.

Compute pair diagnostics on demand for displayed/pinned pairs or an explicitly requested export set. Do not evaluate every possible pair merely to populate the overview. Data flags use transparent counts and continuous summaries, not a new universal biological-quality threshold.

## 10. Optional reference evidence and recovery

This layer is absent by default and must not be required for ranking, overlap, or profiles. Accept a local long evidence table with query ID, candidate ID, evidence type, source/version, evidence identifier, and optional description. Keep one-to-many evidence records; deduplicate query/candidate support within an evidence endpoint before counting.

Minimum evidence types supported independently: pathway co-membership and reaction support. Preserve direct curated reaction evidence versus inferred enzyme/reaction support where supplied. Do not silently union distinct evidence classes or infer direct catalysis from a shared pathway. Source descriptions and identifiers remain inspectable.

The reference descriptor must state which queries/namespaces/source versions were assessed. An absent pair means unsupported by that source, not a biological negative. Queries lacking reference assessment must be distinguishable from assessed queries with zero known supported candidates.

For each query, output, active pool, evidence endpoint, and depth, record:

- Total known supported candidates in the declared reference universe.
- Supported candidates reachable in the active candidate pool.
- Nomination list size and supported nominations.
- Any-supported hit at depth: 1 if at least one nomination is supported, otherwise 0 for an evaluable assessed query.
- Supported fraction: supported nominations divided by actual list size, labeled **reference-supported fraction**, not true precision.
- Recovery: supported nominations divided by reachable supported candidates; undefined when there are none.
- Reachability fraction: reachable known support divided by total known support, where the reference universe is defined and nonempty.
- Status/reason for unassessed queries, empty pools, insufficient saved depth, and unreachable reference evidence.

Expose both all-assessed-query hit summaries (including assessed queries with no reachable support) and reachable-query summaries, naming their denominators. Do not turn unassessed queries into zero recovery. Provide annotation-opportunity strata based on reachable support counts, with recorded bin edges; default bins 0, 1, 2–5, and 6 or more.

Default aggregation is equal query-feature weighting. Optional equal-group weighting requires an explicit one-feature-to-one-group table: average evaluable feature-level metrics within each group, then average groups equally. Report group size, feature exclusions, and number of groups. Do not take the best peak. Reject ambiguous group membership unless the user resolves it before comparison. Multiple peaks and repeated seeds are not independent biological replication.

Reference filters affect only evidence display/evaluation, never the nomination pool. This release provides descriptive evaluation, not significance tests or a calibrated probability that an unsupported candidate is correct.

## 11. Saved outputs and reproducibility

A completed comparison directory contains the following proposed outputs. All tables include schema version through a companion schema/settings record, with explicit units and null/status meanings.

| File | Required content |
| --- | --- |
| [index.html](../../valpas/examples/comparison_output/index.html) | Offline report and embedded scope/settings. |
| [comparison.json](../../valpas/examples/comparison_output/comparison.json) | Versioned resolved manifest/settings, input provenance, report scope, schema descriptions, software version, completion state, warnings, and table inventory. |
| [outputs.csv](../../valpas/examples/comparison_output/outputs.csv) | Output/method/configuration/run IDs, seed, score/rank policy, completeness, preprocessing, source precision, identity-evidence status. |
| [coverage.csv](../../valpas/examples/comparison_output/coverage.csv) | Per-query/output native eligible/scorable counts, active pool size, retained/excluded counts, completeness/evaluability statuses. |
| [exclusions.csv](../../valpas/examples/comparison_output/exclusions.csv) | Excluded query/candidate IDs with output, pool policy, and reason; include cohort-level query exclusions. |
| [candidate_ranks.csv.gz](../../valpas/examples/comparison_output/candidate_ranks.csv.gz) | Long table keyed by query, candidate, output, and pool; native/active ranks, raw score, optional count, rank/score status. Complete available results, not only browser top lists. |
| [agreement.csv](../../valpas/examples/comparison_output/agreement.csv) | Query, pair IDs/class, pool, requested/effective depths, list sizes, shared/union counts, overlap/Jaccard, status. |
| [agreement_summary.csv](../../valpas/examples/comparison_output/agreement_summary.csv) | Pair/depth/cohort denominators and distribution summaries. |
| [run_recurrence.csv](../../valpas/examples/comparison_output/run_recurrence.csv) | Query/candidate/configuration/depth, nominations, evaluable/expected runs, status. |
| [feature_coverage.csv](../../valpas/examples/comparison_output/feature_coverage.csv) | Layer/feature observed/missing counts, observation cohort, mask source, profile availability. |
| [profile_values.csv.gz](../../valpas/examples/comparison_output/profile_values.csv.gz) | Optional feature/layer/sample values and observation status, stored once per feature; sufficient to reproduce included profiles. |
| [diagnostics.csv](../../valpas/examples/comparison_output/diagnostics.csv) | Optional pair/layer diagnostics, chosen h, joint count, shares, omission results, scope and reasons. |
| [reference_evidence.csv](../../valpas/examples/comparison_output/reference_evidence.csv) and [reference_recovery.csv](../../valpas/examples/comparison_output/reference_recovery.csv) | Optional source-specific evidence, query-level metrics, denominators, and reference coverage; also export grouped/stratified summaries when requested. |
| [shortlist.csv](../../valpas/examples/comparison_output/shortlist.csv) and [session.json](../../valpas/examples/comparison_output/session.json) | Optional user selections/notes and portable browser state. |
| [README.md](../../valpas/examples/comparison_output/README.md) | How to open/reproduce the report, supplied/missing layers, settings, limitations, and provenance completeness. |

These paths illustrate a future output directory, not files to add to the package as real analysis results.

For sparse/limited inputs, export all known rows and use the declared axes/coverage metadata to distinguish omitted unknown pairs; do not materialize fabricated worst ranks for every missing combination. Export labels separately or alongside canonical IDs, never as keys.

Hash only the input files actually consumed, once during ordinary reading, and record their roles. In-memory inputs need deterministic content fingerprints incorporating canonical IDs, values, and status masks, not object identities. Include VaLPAS version, schema version, ranking/metric policy versions, resolved settings, and user attestations. Hashes establish content identity, not historical authorization or correctness.

Keep a stable content/settings comparison identifier separate from creation timestamps and local paths. Reproduction requires source inputs plus resolved manifest, or the saved normalized bundle; neither requires original models. Numerical tables should reproduce deterministically, allowing timestamp/path fields to differ.

Write to a temporary sibling directory and publish the destination only after all required artifacts succeed. Refuse an existing destination by default; explicit overwrite must never delete source inputs or unrelated files. On failure, preserve useful diagnostics or clearly identify the partial directory, but do not mark it complete. Do not implement nested seals, repeated preflight runs, whole-repository hashes, or approval gates.

### Notes, shortlist, and figure export

Shortlist records: comparison ID, query/candidate IDs, active pool/depth, inspected outputs, user decision (investigate, retain alternative, or abstain), optional free-text rationale, and timestamp. Abstention may be query-level with no candidate. These are user decisions, not model labels.

A local HTML file cannot silently write back to its bundle. Provide explicit download/import of session and shortlist files; optional browser storage is only a convenience and must not be the sole persistence mechanism. Imported state must match the comparison identifier or require explicit migration with visible warnings. Validate IDs and escape imported notes as untrusted text.

Figure exports must include query/candidate IDs, plotted layer, sample counts/masks, selected metadata overlay, and an appropriate interpretation caption. Provide SVG/PDF via the Python export API and a browser SVG or print/export path. Do not claim screenshot rendering is identical to vector export. No training or association rerun is needed to regenerate a figure.

## 12. Safety, performance, and backwards compatibility

- Escape all labels, annotations, and notes. Embed JSON safely, including script-closing sequences; use text-only DOM insertion for user content. No execution of annotation HTML. Test malicious labels and Unicode.
- Restrict hyperlinks to explicitly allowed schemes; do not load remote content automatically. Reports can contain sensitive sample IDs and values: state that exports are local but include their embedded data, and provide an explicit metadata-omission option for sharing.
- Avoid object-array/pickle loading and model deserialization. External manifests are data, not importable modules.
- Keep exact IDs in canonical machine-readable tables. Spreadsheet users need an explicit formula-safe export option for text beginning with spreadsheet formula characters; record escaping and retain the unmodified canonical export separately.
- Stream/chunk long tables. Avoid a query × candidate × output × sample expansion and unnecessary duplication of score/rank arrays. Profile diagnostics scale with requested pairs, not all possible pairs.
- Target a useful initial scale of approximately 1,000 queries × 5,000 candidates × 8 outputs, with report-size limits applied separately. This is a design target, not a performance claim; record time/peak-memory observations from one representative synthetic smoke run during development, without repeated benchmark sweeps.
- Preserve existing association APIs, output formats, and training behavior. Add opt-in comparison-ready export sidecars/bundles to new result production; do not silently change legacy export precision or filenames.
- New sidecars should capture identity/configuration metadata when known at the time of result creation. Unknown fields remain unknown. Do not retroactively infer training seeds or preprocessing history from a filename.
- Implement the comparison-ready export adapter first; wire metadata capture into existing production paths only at their natural result-construction/export boundaries. Do not require a new model fit to export an existing in-memory result.

## 13. Implementation sequence and acceptance criteria

### A1. Contracts, adapters, and compatibility

Implement versioned models, score/rank adapters, explicit legacy metadata, pool validation, and deterministic ranking. Add the optional comparison-ready bundle export for existing in-memory results, without altering legacy outputs.

**Accepted when:** reordered IDs align correctly; native scores/signs are preserved; invalid identities and ranks fail with actionable messages; incomplete results never become complete by assumption; existing result objects remain unchanged; saved-score comparison does not call training/scoring routines.

### A2. Comparison engine and machine-readable export

Implement candidate ranks, pairwise overlaps, run recurrence, coverage/exclusions, summary tables, and reproducible resolved settings. Both CLI and Python paths call the same engine.

**Accepted when:** hand-calculated synthetic fixtures match all metrics; method/configuration/run counts are distinct; common-pool ranks are exact restrictions of saved orders; strict-mode coverage gaps produce unavailable metrics rather than misleading zeros; CSV output and API values agree.

### A3. Offline query browser and basic profiles

Implement overview, query search, candidate union/rank table, depth controls, filtering/pinning, profile/mask displays, report-size limits, and standalone export.

**Accepted when:** a report opens directly from disk with network disabled; query/depth/output selection and profile views work; displayed values match the exported tables; absent profiles/references are explained; filters do not alter rank denominators; report limits are visible and never silently omit queries.

### B1. Metadata overlays and diagnostics

Implement sample metadata alignment, grouping summaries, covariance-product diagnostics, explicit omission preview, and diagnostic export.

**Accepted when:** masks exclude imputed values from observed-only diagnostics; grouping denominators are exposed; influence fixtures match hand calculations; changing a plot/diagnostic leaves saved ranks unchanged; no AE attribution claim appears.

### B2. Reference evaluation, notes, and publication outputs

Implement source-separated support/recovery, reachability/strata, optional group weighting, shortlist/session round-trip, and query figures.

**Accepted when:** unsupported versus unassessed versus unreachable cases differ correctly; annotation filters do not change nominations; feature/group weighting matches fixtures; notes survive explicit save/import; exported figures reproduce the selected layer and candidate state without fitting.

### B3. User documentation and integration finish

Document file schemas, metadata requirements, migration from legacy exports, score-direction decisions, query workflow, interpretation boundaries, report limits, and how to export comparison-ready results from existing APIs. Add the synthetic example manifest and expected outputs. Ensure packaged report assets are available in an installed package.

**Accepted when:** a user can follow the synthetic example from saved results to a report without the paper repository, training data download, GPU, server, or original chat. Existing targeted association/export regression tests remain passing.

## 14. Focused test plan and validation budget

Use small deterministic fixtures and parameterized tests. Test as part of normal implementation; do not build a separate review/authorization framework. One integrated end-to-end example and one bounded size smoke test are sufficient initially; rerun only affected tests after fixing a failure.

| Area | Required cases |
| --- | --- |
| Identity/orientation | Reordered axes; rectangular/square data; duplicate IDs; leading zeros; namespace collision; mismatched observations; unknown legacy metadata with and without specific attestation. |
| Ranking | Negative/positive scores; each direction/transform; exact ties; distance metric; zero; unscored/nonfinite values; self edges; rank-permutation versus inverse-rank confusion; conflicting scores/ranks. |
| Legacy import | Rounded score:count matrix; labeled AE similarity CSV without checkpoint; filtered edge list; certified versus uncertified prefix; original object not mutated. |
| Pools/completeness | Different eligible pools; strict/common/native policies; per-query finite-score differences; empty intersections; k larger than complete pool; truncated prefix too shallow; triangular undirected expansion. |
| Agreement/recurrence | Identical/disjoint/partially overlapping lists; unequal native lengths; unavailable metric not zero; three seeds count as one method; different hyperparameters not seed replicates; unknown group configuration. |
| Profiles | Reordered samples; missing layer/feature; raw versus imputed mask; constant profiles; insufficient observations; missing metadata; influential single point; zero product denominator; omission recentering. |
| Reference layer | No annotations; unsupported/unassessed/unreachable distinctions; duplicated evidence; separate pathway/reaction endpoints; short lists; equal-feature versus equal-group weighting; annotation filters leave ranks intact. |
| Export/UI | API/CSV/HTML agreement; offline interaction; limits/subset disclosure; malicious labels/notes; Unicode; session round-trip; existing destination refusal; interrupted write not complete; installed asset availability. |
| No-compute invariant | Patch training/association entry points to fail if invoked, then run saved-result comparison, report regeneration, and figure export successfully. |

Perform one browser interaction check on the synthetic report, automated if an existing browser-test harness is available; otherwise document a brief manual offline check. Do not introduce a heavyweight browser dependency solely to create a new testing bureaucracy. Run relevant existing regression tests, not expensive training/performance suites by default.

## 15. Starting instructions for the development session

1. Work in the standalone VaLPAS repository. Read this document and the specific source interfaces in Section 3; do not rerun paper analyses or import their execution/authorization modules.
2. Implement A1–A3 as a coherent first release, preserving the schema extension points needed for B1–B3. Keep the no-fit/no-score invariant throughout.
3. Use the concrete synthetic example and focused tests to drive integration. Validate inputs once in the real operation; avoid extra preflight/review stages.
4. Implement B1–B3 to complete the approved workflow. If stopping after Release A, explicitly list remaining Release B work.
5. Report changed public interfaces, supported/unsupported legacy formats, focused test results, any unverified browser/performance claims, and the user-facing example location.

**Final success criterion:** a user can load saved outputs from the same dataset, inspect a query's competing nominations and observed evidence, distinguish algorithm differences from run variability, and save a reproducible decision without mistaking agreement, annotation support, or covariance influence for biological validation.
