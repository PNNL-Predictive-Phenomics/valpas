# A0 saved-score reference fixture

This is hand-authored test data, not a trained model result or a real measurement dataset. No fitting, rescoring, checkpoint loading, or downloads are required. There are **two methods, two configurations, and three outputs**. Six observation IDs establish the hypothetical shared observation selection; observed profiles are deliberately absent.

- [Pearson scores](pearson-run.csv): signed values, ranked by absolute value descending.
- [AE seed 42 scores](ae-seed-42.csv) and [AE seed 123 scores](ae-seed-123.csv): ranked by native value descending.
- [Metadata](metadata.json): dataset/source attestation, exact axes and namespaces, orientation, completeness/missing policy, and shared non-seed configuration records. Both AE outputs reference the same configuration; only their run identity and seed differ.
- [Expected results](expected.json): hand-calculated ordered candidate IDs (one-based rank is position), strict availability, common pools/exclusions, and selected overlap/Jaccard calculations.

The original metadata keys remain **A0 fixture scaffolding**, preserved with the independent expected values. A1 supplements them with a supported [version-one manifest](manifest.json), validated by the production [loader](../../../../src/valpas/comparison/adapters.py). See the [schema/API reference](../../../../docs/COMPARISON_SCHEMA_V1.md) and [runnable saved-input example](../../../../examples/inspect_comparison_inputs.py).

The shared source identity is an explicit synthetic attestation, not a computed measurement fingerprint. The illustrative non-seed configuration specifies hypothetical training options; it is not evidence that any model was executed. A1 tests compare production native/common ranks and strict availability with the retained A0 expectations; overlap/recurrence metric implementation remains A2.

## Hand calculations

For M01, Pearson scores −0.9, +0.8, +0.1 order P01, P02, P03. Both AE outputs order P02, P01, P03. Thus Pearson versus either AE has top-one overlap 0/1 = 0 and top-two overlap 2/2 = 1; the respective Jaccard values are 0 and 1. The negative Pearson score remains negative in the saved file.

For M02, Pearson's P02 cell is blank: **unscored, not zero and not worst-ranked**. Its native list is P01, P03, whereas both AE lists include P02. Strict controlled comparison across the three outputs is unavailable for this query. In common mode, P02 is excluded because it is unscored in Pearson, leaving P01 and P03 in every output. Filtering the native orders gives:

| Output | Common order |
| --- | --- |
| Pearson | P01, P03 |
| AE seed 42 | P03, P01 |
| AE seed 123 | P01, P03 |

Pearson versus seed 42 therefore has common top-one overlap 0 and top-two overlap 1. Pearson versus seed 123 has common top-one overlap 1. A requested depth of five is bounded to two in this pool. Unavailable strict metrics are null, never zero.

The A0 tests verify only the integrity of these fixtures using small independent standard-library calculations. They do not implement or validate the future production comparison engine.
