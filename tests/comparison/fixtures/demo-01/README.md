# A0 saved-score reference fixture

This is hand-authored test data, not a trained model result or a real measurement dataset. No fitting, rescoring, checkpoint loading, or downloads are required. There are **two methods, two configurations, and three outputs**. Six observation IDs establish the hypothetical shared observation selection; the original score-only manifest deliberately has no profiles. Separate A3/B1 manifests add illustrations without changing those saved scores.

- [Pearson scores](pearson-run.csv): signed values, ranked by absolute value descending.
- [AE seed 42 scores](ae-seed-42.csv) and [AE seed 123 scores](ae-seed-123.csv): ranked by native value descending.
- [Metadata](metadata.json): dataset/source attestation, exact axes and namespaces, orientation, completeness/missing policy, and shared non-seed configuration records. Both AE outputs reference the same configuration; only their run identity and seed differ.
- [Expected results](expected.json): hand-calculated ordered candidate IDs (one-based rank is position), strict availability, common pools/exclusions, and selected overlap/Jaccard calculations.

The original metadata keys remain **A0 fixture scaffolding**, preserved with the independent expected values. A1 supplements them with a supported [version-one manifest](manifest.json), validated by the production [loader](../../../../src/valpas/comparison/adapters.py). See the [schema/API reference](../../../../docs/COMPARISON_SCHEMA_V1.md) and [runnable saved-input example](../../../../examples/inspect_comparison_inputs.py).

The shared source identity is an explicit synthetic attestation, not a computed measurement fingerprint. The illustrative non-seed configuration specifies hypothetical training options; it is not evidence that any model was executed. A1 tests compare production native/common ranks and strict availability with the retained A0 expectations. [A2 engine tests](../../test_a2_engine.py) now check production agreement and recurrence against the hand-calculated values; the [A2 example](../../../../examples/compare_saved_results.py) exports/reloads tables without training or a target feature.

## Hand calculations

For M01, Pearson scores −0.9, +0.8, +0.1 order P01, P02, P03. Both AE outputs order P02, P01, P03. Thus Pearson versus either AE has top-one overlap 0/1 = 0 and top-two overlap 2/2 = 1; the respective Jaccard values are 0 and 1. The negative Pearson score remains negative in the saved file.

For M02, Pearson's P02 cell is blank: **unscored, not zero and not worst-ranked**. Its native list is P01, P03, whereas both AE lists include P02. Strict controlled comparison across the three outputs is unavailable for this query. In common mode, P02 is excluded because it is unscored in Pearson, leaving P01 and P03 in every output. Filtering the native orders gives:

| Output | Common order |
| --- | --- |
| Pearson | P01, P03 |
| AE seed 42 | P03, P01 |
| AE seed 123 | P01, P03 |

Pearson versus seed 42 therefore has common top-one overlap 0 and top-two overlap 1. Pearson versus seed 123 has common top-one overlap 1. A requested depth of five is bounded to two in this pool. Unavailable strict metrics are null, never zero.

The A0 tests verify fixture integrity using independent standard-library calculations. Production engine/bundle/CLI validation is kept in separate tests, preserving that independent reference. The original manifest remains a no-profile example.

## A3 offline browser and optional synthetic profiles

The [profile manifest](manifest-with-profiles.json) adds the [explicit JSON layers](profiles.json) without changing the original fixture or scores. These synthetic illustration values are **not the scoring layer** and explicitly declare a different relationship to every output. Two originally missing samples include one finite imputed value and one null; four jointly observed points remain. Duplicate display labels demonstrate canonical-ID disambiguation.

Use either manifest with the [Release A CLI](../../../../docs/COMPARISON_RELEASE_A.md) to produce single-file offline HTML and complete tables. No-profile mode retains all agreement/rank functionality. Profile arrays are saved once per layer/feature and reload after source deletion. The [A3 tests](../../test_a3_report.py) and [real offline browser smoke](../../test_a3_browser.py) validate parity, masks, security, payload rejection and interaction.

## B1 metadata and hand-calculable diagnostics (separate fixture)

The [B1 manifest](manifest-with-b1.json) references the **same three saved score files**, new [B1 profiles](b1-profiles.json), and [sample metadata](sample-metadata.json). The original [A3 manifest](manifest-with-profiles.json) and [A3 profiles](profiles.json) remain unchanged, including their mask/row-count expectations. All identity descriptors retain the historical score-only context verbatim for exact binding; the added profiles are illustrations, **not source measurements used to derive the scores**. Every algorithm-layer relationship is “different.”

Metadata declares condition, batch, genotype (categorical) and time_hours (continuous). S04 has explicit null genotype; S05 omits condition and time; S06 has no metadata record. These are missing values, not a new category, zero, or a removed observation. The metadata table contains 24 rows (six observations × four fields), seven marked missing. Condition grouping includes S01–S04; covariance still includes all six jointly observed points. Batch/genotype/color selections do not imply adjusted effects or confounding correction.

For the requested M01/P01 pair in the b1-observed layer, both profiles in dataset order S01–S06 are **0, 1, 2, 3, 4, 14**, all originally observed:

- Joint means are 4. Signed centered products are **16, 9, 4, 1, 0, 100**; their absolute sum is 130. Sample covariance is 130/5 = **26**, and correlation is 1.
- The request explicitly chooses h = 1, omission enabled, condition grouping, and the between-group fraction. S06 is selected, with largest-one absolute-product share **100/130 = 10/13**.
- Removing S06 leaves five points, recentered to mean **2**. Their squared deviations sum to 10, so remaining sample covariance is **10/4 = 2.5**, correlation 1. This is not the unrecentered retained product sum divided by four, and is not a model refit or leave-one-out model evaluation.
- Each feature's marginal condition summary has control count 2 / mean 0.5 and stress count 2 / mean 2.5. On the four included values, total SS = **5**, between-group SS = **4**, fraction = **0.8**. S05/S06 are missing-group exclusions; not-observed-finite exclusions are empty. Missing group takes precedence if both exclusion conditions apply.

Other embedded features support interactive edge cases without expanding requested exports: M02 is constant; P02 has a finite imputed 99 at S03 and a null at S05 with original mask false for both; P03 differs in its middle pair of values. Inspect M02/P01 for zero-product/zero-variance statuses, or group M01/P02 by condition to see separate marginal cohorts and disjoint exclusions. Imputed values never enter observed-only diagnostics.

The [runnable example](../../../../examples/compare_saved_results.py) defaults to this manifest, checks the calculations above, verifies unchanged comparison identity and all ten A2 tables against the no-profile manifest, and roundtrips all 15 tables: ten scientific, two profile, metadata, one requested diagnostic row, and two group-summary rows. Requests do **not** restrict the all-query overview. Browser calculations are on demand for embedded pairs, independent of the export request; set h to 1 and explicitly request omission to reproduce this preview (browser default h is 5). No model attribution, causality, retraining, new association scoring or rank change is implied. See the [exact B1 field/status contract](../../../../docs/COMPARISON_SCHEMA_V1.md#b1-sample-metadata-and-requested-diagnostics).
