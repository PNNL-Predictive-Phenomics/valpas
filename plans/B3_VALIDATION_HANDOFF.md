# B3 production integration: validation handoff

## Status — 2026-11-19

B3 implementation and its bounded validation are complete. The dense target-scale comparison did **not** complete; its measured limit is recorded below, not treated as a performance pass. The [production guide](../docs/COMPARISON_PRODUCTION.md) describes the user-facing workflow and contracts.

Delivered:

- Opt-in production input sidecars through the CLI, calculation/experiment boundaries, high-level association API, and existing result export. Existing positional compatibility, default dispatch, legacy filenames and legacy precision are preserved.
- Detached full-precision export before mutating legacy save/list conversion; no fitting, rescoring or checkpoint loading in export.
- Truthful capture of actual post-subset observations at the calculation boundary, method/CLR/count flags, classical unsupervised status, and namespaced CLI preprocessing facts. Unavailable identity, seed and prior history remain caller declarations or unknown.
- Strict requests, explicit orientation and count semantics, contradiction rejection, new-directory publication, and legacy/sidecar destination collision protection. Sidecar and legacy publication are independent: later legacy failure leaves a valid sidecar intact.
- A real synthetic Pearson/Spearman [production example](../examples/export_comparison_sidecar.py), CLI-first documentation, packaging coverage and a bounded [benchmark harness](../tools/benchmark_comparison.py).

A single production sidecar is an input bundle, not a completed comparison. At least two outputs must be combined before comparison. Existing similarity matrices can be exported without loading their models; export cannot recover information already discarded by legacy operations.

## Source validation

Using Python 3.12.3 with the retained full dependency environment, source imports selected through the checkout source path:

| Suite | Result | Elapsed |
|---|---|---|
| Comparison discovery | 242 passed, zero skips | 84.075 s |
| Packaging/benchmark harness discovery | 24 passed, zero skips | 1.120 s |

The [production regressions](../tests/comparison/test_b3_production.py) cover metadata preservation/conflicts, full precision, actual subsetting, unchanged default forwarding, no model computation, export before legacy mutation, independent legacy failure, strict requests/no clobber, and destination collisions before calculation. The [benchmark regressions](../tests/packaging/test_comparison_benchmark.py) exercise both a successful small run and a bounded timeout.

The real production example also passed locally and once against each installed wheel. It computes Pearson and Spearman once each on six synthetic observations, verifies positive/negative scores and captured metadata, combines saved inputs, and generates a two-output comparison. This is tiny real association calculation, not autoencoder training. Final whitespace validation passed.

## Final installed-artifact gate

The retained [machine-readable distribution evidence](validation/b3-distribution.json) records artifacts, all 90 commands and return codes, installed examples, figures, legacy checks and all browser cases. All **90 commands passed**. All **10 direct-file Chrome cases passed**: A3, B1, hostile text, no-profile and B2 for each wheel.

Environment: macOS 26.7.2 arm64, Python 3.12.3, Chrome 157.0.8103.80. Final gate ran from 23:10:37 to 23:12:35 UTC on 2026-11-19. Build source HEAD was b310a8cdc3ee5ab4c1e6927dd02101d7ec79dc79 plus the uncommitted B3 changes; HEAD alone does not identify this implementation.

Fresh artifacts were built from the checkout and from a Git-free extracted sdist, then installed non-editably in separate retained environments. Installed checks run outside the checkout under isolated Python. Dependency environments were reused: **fresh dependency resolution and backend build isolation were not exercised**. The exact validator invocations and local evidence paths are retained in the machine-readable record; the reuse-mode procedure is documented in the [distribution guide](../docs/DISTRIBUTION_VALIDATION.md).

Artifact version: **1.0.1.dev31+gb310a8cdc.d20261119**.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Checkout wheel | 219820 | ecd3ce482ad1eb0436eb1863de37b080f05574e752e1f018ec3325050815339d |
| Git-free sdist-built wheel | 219820 | ecd3ce482ad1eb0436eb1863de37b080f05574e752e1f018ec3325050815339d |
| Final sdist | 283710 | 4cdbc80e89325786053d5b27252b33fa86d2255c29d2a4843e9fcc6310660c21 |

The two wheels are byte-identical. Gate coverage includes installed module/assets checks, examples copied from the sdist, scientific inventories, source-input removal before bundle regeneration, reference/session restoration, API/CLI SVG and PDF export, and legacy smoke checks.

Browser reports were opened directly from local files with external hostname resolution disabled and report network connections prohibited. A3/B1/hostile/no-profile cases use disposable report copies with interaction assertions. B2 additionally exercises real downloads and file imports through local Chrome automation: reference denominator/rank invariants, decisions including abstention, inert hostile notes, session/shortlist/CSV downloads, exact repeated restoration, atomic tampered-file rejection, and actual SVG download/XML parsing. These are functional checks, not manual visual/accessibility certification.

### Artifact chronology

An earlier 90-command gate also passed, but some packaged documentation was subsequently finalized. The second gate above rebuilt and retested the final packaged content. Its sdist differs from the earlier 283711-byte artifact; use the final hash above. The root readme and all five packaged comparison/distribution guides were checked byte-for-byte against the final sdist. A first ad-hoc archive check ambiguously matched a nested fixture readme; exact archive-relative matching resolved this and all six comparisons passed.

This handoff, retained evidence and implementation-plan status are repository records written after the final build; they are not included by the current sdist allowlist. Their creation does not change the tested package contents. Documentation links to repository-only plans require a checkout or repository browser. Temporary build environments/artifacts were retained locally; their paths are not portable, while hashes and summarized evidence are retained here.

## Bounded scale measurement — not a passing target

The [target record](validation/b3-scale-target.json) measures 1,000 queries × 5,000 candidates × 8 outputs: **40,000,000 dense score pairs**. Budget: 600 seconds and 6144 MiB sampled RSS.

- Outcome: bounded stop at the time limit, worker terminated with return code -15.
- Total elapsed: **600.545442875009 seconds**.
- Sampled peak worker RSS: **5,418,418,176 bytes (5.05 GiB)**.
- Last progress: input loading, entered at 19.301477500004694 seconds.
- Comparison summaries and the separately bounded two-query report payload were **not reached**.
- Full comparison-bundle export was outside this benchmark's scope.

The [4 × 20 × 2 control](validation/b3-scale-small.json) passed: 160 pairs, 0.038084375 seconds worker elapsed, 0.538616041 seconds total elapsed, 29,589,504 bytes worker-reported peak RSS and 24,543,232 bytes sampled peak RSS. Its serialized report payload measured 645294 bytes; this is not the exact escaped HTML budget size.

RSS sampling is not an exact process high-water mark. The benchmark uses POSIX process reporting; Windows is unvalidated. Dense normalized Python pair objects remain an input-loading limitation. Bounding browser detail does not bound input loading memory. No claim is made that target-scale comparison or export is production-ready under this budget, and no dense-storage optimization was implemented in B3.

## Remaining boundaries

- Other OS/Python/browser combinations, fresh dependency resolution, manual accessibility/visual checks and target-scale completion remain unverified.
- Export does not infer source identity from shape, fabricate a random seed, or reconstruct preprocessing/training history. High-level combined/subset results do not claim a single captured observation cohort.
- Count semantics remain explicit; pandas correlation-callable diagonals can be unity rather than true counts.
- Legacy calculation behavior outside the opt-in boundary was not generally repaired. Legacy and sidecar exports are not transactional as a pair.
- Autoencoder training CLI work remains separate. Earlier cross-attention tests and the broader documentation-example/Sphinx build follow-ups were not run as part of B3.
