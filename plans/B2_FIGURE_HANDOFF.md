# B2 figure integration handoff — 2026-11-19

## Status and boundaries

Figure API, saved-bundle CLI and explicit offline browser SVG download are implemented. Existing uncommitted reference/session work was preserved. **Overall B2/B3 is not declared complete.** No build, install, training, dependency download or external network operation was run. Existing Chrome uses the approved local CDP harness with external resolution disabled. Parent owns full-suite, packaging/install and final integration validation.

## Interfaces and contracts

- Public [`export_query_figure()`](../src/valpas/comparison/figures.py:261): existing result or completed saved bundle; required exact query/candidate/layer/output. Returns absolute output path. SVG/PDF selected by explicit suffix. Optional color/group/order/h/omission/fraction/depth/notes and strictly bound session/decision view; optional exact report scope for session validation. Bundle initial state is not implicitly applied.
- [CLI delegation](../src/valpas/cli.py:359): export-query requires bundle/query/candidate/layer/output; optional B1 display, notes, session and decision controls. Errors exit 2 without traceback. Help/public imports remain standard-library-only and preserve warning state. Matplotlib imports occur only inside actual rendering; no dependency added.
- Python uses full normalized profiles, including features/metadata absent from bounded or omitted HTML. No original sources are reopened. Sessions still impose their exact content/scope binding; conflicts are rejected rather than clamped. No new result/session fields, scientific tables or schema versions.
- Scatter is jointly observed finite only. Profiles distinguish originally unobserved/imputed values. Same/cross modality supported. No-joint cohorts retain marginal profiles; missing features/cohort/masks fail actionably.
- Captions include exact IDs/namespaces, scientific and descriptive content IDs, layer/units/transform/provenance, algorithm-layer relationships, mask source, required/layer/marginal/joint counts, exclusions, overlay/color key/order, pool/analysis/inspection depths, annotations/notes and exact descriptive diagnostics/groups. No attribution/causal/confounding-correction claims. Optional decision context preserves its rationale and full view.
- Literal text: TeX/mathtext disabled even under hostile rc settings. SVG text/description is XML-safe; Python PDF Subject retains exact caption. XML-incompatible control characters are rejected, never silently changed; SVG CR survives parsing. No external scripts or links are added.
- Safe publication: caller names a new file outside owned input/result bundles. Refuse existing paths, traversal, immediate parent/destination symlinks, missing parents and protected/recorded source collisions (including deleted sources). Render to sibling temporary, sync, atomically hard-link without overwrite, clean staging on failure/success. Concurrent destination creation is covered. Hostile parent replacement and crash recovery are outside contract.
- [Browser download](../src/valpas/comparison/assets/dashboard.js:496): explicit per-layer generic SVG filename, current plots/styles/B1 state plus caption and bounded-scope/privacy warning. Browser rendering is explicitly **not identical** to Python vector output. Existing strict session schema and B1 controls are unchanged. Browser handles filename collisions.

## Persistence compatibility change

[Report validation](../src/valpas/comparison/report.py:379) now accepts inventoried old presentation assets for session-bearing bundles too; changing dashboard assets must not strand existing saved sessions. Exact complete normalized session/payload parity, embedded/stored payload parity, hashes/sizes/budget and all existing scientific table checks remain required. Only pre-session bundles may omit the known additive session keys. Same software/policy restriction remains; this is not migration or authentication of saved scripts. A regression writes an older-asset session bundle, reloads/exports it, then confirms payload tampering is rejected even after refreshing its inventory entry. This supersedes the exact-current-HTML requirement recorded in the earlier session handoff.

## Validation — actual commands and results

Retained full-dependency interpreter; source tree only, no installation. Final focused command:

```sh
PYTHONPATH=src:tests/comparison /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest test_b2_figures test_b2_figure_browser test_a2_cli test_a3_report test_b1_diagnostics test_b1_persistence test_b1_browser test_b2_session test_b2_session_browser test_b2_reference_persistence test_b2_reference_browser test_single_modality test_import_isolation.TestLightweightImports -v
```

**131 tests passed, zero skips, 47.665 seconds.** Includes real SVG/PDF, hostile literal captions under enabled global TeX/mathtext, actual artist cohort checks, same/cross modality, source deletion/full bundle outside HTML scope, actual CLI, no-clobber race, failed/missing renderer cleanup, strict session/decision binding, old-asset compatibility and blocked training imports. Three new Chrome tests actually download files, parse XML in Python and Chrome, inspect masks/styles/captions, preserve B1/session state and reject illegal XML text. Existing B1/reference/session browser tests also passed.

Earlier figure-only command (after multiline/renderer tests, before final source-path/color-caption additions):

```sh
PYTHONPATH=src:tests/comparison /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest test_b2_figures test_b2_figure_browser -v
```

**15 passed, zero skips, 8.614 seconds.** The final 131-test command includes these same 15 cases after final changes. Initial development run exposed two test-fixture/assertion issues (no-profile fixture retained a diagnostic request; PDF byte assertion omitted PDF escaping); both corrected before successful runs.

The [CLI-first guide](../docs/COMPARISON_FIGURES.md) quick start was executed with temporary destinations using the same interpreter. Exact executable smoke sequence (shell form equivalent to the subprocess calls used):

```sh
PYTHON=/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python
RUN=$(mktemp -d)
PYTHONPATH=src "$PYTHON" -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-b1.json --outdir "$RUN/figure-demo"
PYTHONPATH=src "$PYTHON" -m valpas.cli export-query --bundle "$RUN/figure-demo" --query M01 --candidate P01 --layer b1-observed --output "$RUN/query-figure.svg"
PYTHONPATH=src "$PYTHON" -m valpas.cli export-query --bundle "$RUN/figure-demo" --query M01 --candidate P01 --layer b1-observed --color condition --group condition --order metadata --h 1 --omission --output "$RUN/query-figure.pdf"
```

All three commands succeeded; real SVG/PDF produced. Expected synthetic-fixture provenance/configuration warnings remained visible. Whitespace validation also passed:

```sh
git diff --check
```

## Parent integration checklist / limitations

- [API/schema](../docs/COMPARISON_SCHEMA_V1.md), [workflow](../docs/COMPARISON_RELEASE_A.md), [Sphinx comparison page](../docs/source/comparison.rst) and [figure guide](../docs/COMPARISON_FIGURES.md) updated. [Build configuration](../pyproject.toml) adds only the new guide to sdist inclusion, no dependencies. No new browser asset file; package module inclusion uses existing package rules. Parent must verify wheel/sdist/install and prior session resource integration.
- Source-focused evidence is not packaging/full-suite evidence. Training-based documentation examples were not run. Sphinx build, final accessibility/pixel review, cross-browser coverage and target-scale profiling remain pending.
- Long exact captions grow the page; inspect layout/fonts before publication. Byte-identical rendering across Matplotlib/platform versions is not promised. Exports are sensitive and not automatically redacted. Full result bundles remain authoritative; figures are not reloadable comparison bundles.
