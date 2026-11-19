# B3: production exports and final integration

## CLI-first path

The existing [saved-output workflow](COMPARISON_RELEASE_A.md) remains the starting point for comparison, profiles, reference evidence, decisions and figures. Production export is **opt-in**; old filenames, output precision and default dispatch are unchanged.

From a checkout or extracted source distribution, run the self-contained [production example](../examples/export_comparison_sidecar.py):

```sh
python examples/export_comparison_sidecar.py --outdir production-demo
```

It creates six synthetic observations, calculates Pearson and Spearman once each, exports full-precision comparison input sidecars **before** legacy save, verifies signed values and metadata, combines the saved inputs, then creates an offline comparison. No model is trained or loaded. Without the output argument it uses and cleans a temporary directory. With an installed wheel, run the example from the extracted sdist; examples/fixtures are not wheel package data.

For your own association command, add the opt-in request option:

```sh
valpas associate from_file --csv --infile experiment__proteomics.csv \
  --association_type pearson --output_type correlation_matrix \
  --outfile legacy.csv --comparison-export request.json
```

The strict JSON request contains a complete [A1 output descriptor](COMPARISON_SCHEMA_V1.md), an explicit query axis, a **new** destination directory, and optional comparison settings. Use the example's generated request as an executable illustration, not as provenance for real data. The descriptor must declare the actual dataset, namespaces, exact query/candidate IDs, orientation, score semantics, ranking policy, eligibility, missingness and completeness. Do not copy hypothetical fixture identity into real analyses. Count-bearing results require explicit count semantics; the legacy pandas correlation callable produces diagonal unity rather than genuine observation counts. The legacy CSV importer requires a double-underscore experiment/modality separator in the filename and feature-by-observation data.

Comparison requires **at least two outputs**. The example uses [`load_input_bundle()`](../src/valpas/comparison/bundles.py:94) and [`export_comparison_inputs()`](../src/valpas/comparison/bundles.py:21) to combine separately captured sidecars without rescoring. Compare that combined manifest, rather than a single-output sidecar:

```sh
valpas compare --manifest production-demo/combined-inputs/manifest.json --outdir another-comparison
```

Request and destination paths are relative to the working directory, not the request file. Duplicate JSON keys, unknown request fields, malformed descriptors, axis guessing, contradictory captured facts and existing destinations are rejected. A sidecar is an **input bundle**, not a completed comparison-result bundle: feed its manifest to comparison, not the saved-result bundle option.

## Existing results and calculation boundaries

The public [`export_association_result()`](../src/valpas/comparison/production.py:63) accepts existing labeled association values/counts or a similarity-matrix analysis result. [`AssociationResult.export_comparison()`](../src/valpas/_core/classes/results.py:399) is a convenience wrapper. Both require a complete descriptor and explicit query axis. Export **before** legacy save or list conversion: those operations can mutate or discard information. Export cannot recover lost precision, removed edges, original masks or training history.

The optional keyword-only request is also accepted by [`Experiment.associate()`](../src/valpas/_core/classes/experiments.py:81), [`calculate_association()`](../src/valpas/_core/association.py:44), and the high-level [`associate()`](../src/valpas/valpas_core.py:21). Existing positional calls are unchanged. The calculation hook captures the actual post-subsetting observation IDs. The high-level hook runs before list conversion, annotations and legacy save; it does not claim a single observation cohort for combined/subset results. The CLI captures its actual cohort except for post-normalized combined outputs.

### Known facts versus caller declarations

- Actual calculation observations, method, CLR flag and threshold-count flag are captured at the applicable boundary and checked against supplied metadata.
- Known classical methods are recorded as unsupervised; contradictory supplied supervision is rejected.
- CLI preprocessing records actual zero-to-missing conversion, filtering cutoff, thresholding, input normalization and mean combination. These facts are namespaced, not a fabricated complete history.
- Source identity/evidence, namespaces, seed, prior preprocessing, training configuration and other provenance remain caller declarations unless explicitly captured. No identity is inferred from shape or filenames, and no seed is inferred from global random state. Unknown remains unknown. Configuration seed fields remain forbidden: seeds belong on runs.
- Open configuration metadata is retained; fixed-schema unknown keys are rejected, not silently dropped. No fitting, rescoring, checkpoint loading or global warning-filter changes occur in export.

Legacy and sidecar publication are independent, **not a two-output transaction**. Sidecar failure prevents subsequent legacy publication at these hooks; later legacy failure leaves the valid sidecar intact. Use separate destinations outside owned bundles and do not point legacy output inside a sidecar. A source conflict or destination collision never authorizes overwriting. Legacy calculation behavior is not generally repaired by this feature; the opt-in CLI supplies explicit no-subset arguments needed by its calculation path. Autoencoder CLI training remains a separate feature.

## Bounded scale evidence

The [benchmark tool](../tools/benchmark_comparison.py) generates dense synthetic saved CSV scores, loads them through the production comparison reader, computes complete summaries, and requests a separate two-query report payload. It does not train or measure full bundle export. It uses a child process, sampled RSS and an explicit time/memory budget; exit status 2 means failed or bounded stop, not success. The RSS monitor uses POSIX process reporting; Windows execution is not validated.

```sh
PYTHONPATH=src python tools/benchmark_comparison.py \
  --queries 1000 --candidates 5000 --outputs 8 \
  --max-rss-mib 6144 --timeout 600 --record scale.json
```

The macOS arm64 / Python 3.12.3 run measured **600.545 seconds**, **5,418,418,176 bytes sampled peak RSS (5.05 GiB)**, and stopped at the time limit during input loading. The 40-million-pair comparison and bounded report **did not complete**. Full bundle export was not measured. RSS sampling is not an exact process high-water mark. The small 4 × 20 × 2 control completed. Dense normalized pair objects remain a scale limitation; a bounded browser does not make full input loading bounded. This is a measured limitation, not a passing performance target.

See the [B3 validation record](../plans/B3_VALIDATION_HANDOFF.md) for final test/build/browser evidence and artifact chronology. Other OS/browser/Python combinations and manual visual/accessibility certification are not implied by this gate.
