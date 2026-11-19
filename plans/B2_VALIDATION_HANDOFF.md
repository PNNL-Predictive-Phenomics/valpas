# B2 integrated validation and installed-packaging handoff

## Status and chronology — 2026-11-19

**The focused B2 integrated validation gate passed.** Both the checkout-built wheel and the wheel rebuilt from a safely extracted, Git-free sdist were force-reinstalled into the authorized retained full-dependency environments and passed installed checks, including actual Chrome downloads and file imports. No B2 runtime blocker remains in this gate.

The full comparison suite passed **232 tests, zero skips**, and the packaging harness passed **22 tests, zero skips**, both before and after the installed run. The comparison count retains the prior 174 tests and adds 58 B2 tests. The distribution run recorded **88 successful commands** and **10 installed Chrome cases** (A3, B1, hostile, no-profile, and B2 for each wheel).

The tested artifacts include the updated [distribution validation guide](../docs/DISTRIBUTION_VALIDATION.md), implementation, harness, fixtures, and figure guide. **They precede this handoff and the parent's subsequent general README, CLI/user-guide, and implementation-plan documentation updates.** These artifact hashes must not be described as covering those later edits. This is not blanket Release B/B3 acceptance.

Existing uncommitted reference, session, figure, source, test, and documentation work was preserved. No reset, stash, or commit was performed. The validator confirms the generated version-file state was restored; cleanup reported no errors.

## Implementation delivered by this integration

- Extended [distribution validator](../tools/validate_distribution.py) and [installed smoke assertions](../tools/distribution_smoke.py) with full B2 reference/group/profile/metadata/session workflows, strict optional inventories, source-free regeneration, and API/CLI vector exports.
- Added [combined B2 demo manifest](../tests/comparison/fixtures/demo-01/manifest-with-b2.json), retaining B1 dataset identity, scores, profiles, metadata, and diagnostic requests. Its reference and query-group documents are inline.
- Added [installed browser helper](../tools/distribution_browser.py), reusing the existing [stdlib Chrome CDP helper](../tests/comparison/chrome_cdp.py), without a duplicated transport or downloaded browser driver.
- Extended [sdist configuration](../pyproject.toml) to carry the browser helper, CDP helper, and [reference fixture](../tests/comparison/fixtures/b2-reference/README.md). The demo fixture directory already carries the combined manifest.
- Wheel and sdist inspection now require the [session asset](../src/valpas/comparison/assets/sessions.js) and [reference](../src/valpas/comparison/reference.py), [session](../src/valpas/comparison/session.py), and [figure](../src/valpas/comparison/figures.py) modules, in addition to prior resources. Installed modules/assets are checked against wheel bytes and isolated installation paths.
- Retained all prior harness cases and added five B2 cases in [packaging tests](../tests/packaging/test_distribution_validation.py): exact optional inventories, strict extension schemas, required archive contents, malformed/unsafe vector rejection, and missing wheel resources/modules.
- Updated [reproduction documentation](../docs/DISTRIBUTION_VALIDATION.md). General README/guide/plan status updates remain the parent's responsibility.

No new dependency or production implementation fix was required for this integration. The fixture README was not changed.

## Environment and exact reproduction

Working directory: `/Users/d3p620/lib/valpas`.

Authorized retained environment root:

```text
/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102
```

The checkout-wheel interpreter below was used for source suites and orchestration. Sibling sdist-wheel and build environments were reused. Platform: **macOS-26.7.2-arm64-arm-64bit**, Python **3.12.3**, Google Chrome **157.0.8103.80**. Built version: **1.0.1.dev30+g4d572bc23.d20261119**.

Commands (source suites were run both before and after distribution validation):

```sh
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest discover -s tests/comparison -v
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest discover -s tests/packaging -v

/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python tools/validate_distribution.py --reuse-envs /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102 --keep-envs

PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m compileall -q src/valpas/comparison src/valpas/cli.py tools tests/comparison tests/packaging
git diff --check
```

Existing build tooling was import-probed successfully. There was no fresh dependency resolution, global installation, or unnecessary tooling installation. Each new wheel was installed noneditably with dependency reuse; dependency checks, installed examples, and real legacy imports passed. This proves compatibility with the retained full-dependency environments, **not a clean resolver experiment**.

Installed assertions run with Python isolated mode outside the checkout after source/path/version overrides are cleared. Source suites intentionally use the checkout through the explicit source path above. The Git-free rebuild uses the extracted sdist, not the checkout as its source.

## Retained evidence and suite results

Evidence root (external temporary workspace, retained with environments):

```text
/private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i
```

The [distribution summary](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/summary.json) records exact argument vectors, working directories, numbered logs, return codes, timings, installed dependency versions, installation reports, archive inventories, hashes, Chrome version, source Git state, and version restoration. Status is passed; all 88 commands succeeded. Run interval: **15:23:27–15:24:51 UTC**.

| Check | Result | Log relative to evidence root |
| --- | --- | --- |
| Comparison before build | 232 tests; 90.818 s; OK; zero skips | [pre-build comparison](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/valpas-b2-full-comparison-before.log) |
| Harness before build | 22 tests; 0.605 s; OK; zero skips | [pre-build harness](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/valpas-b2-harness-before.log) |
| Installed orchestration | 88 successful commands | [captured validator output](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/valpas-b2-distribution-run1.log) |
| Comparison after build | 232 tests; 90.971 s; OK; zero skips | [post-build comparison](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/comparison-after.log) |
| Harness after build | 22 tests; 0.497 s; OK; zero skips | [post-build harness](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/harness-after.log) |
| Compilation | exit 0 | [compile log](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/compile.log) |
| Whitespace validation | exit 0 | [diff log](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/diff-check.log) |

The [source regression record](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/source-regressions.json) contains exact post-build commands and process timings (which include startup overhead and therefore differ from unittest durations). Expected argument-parser diagnostics in negative tests are not failed tests.

## Built artifacts and SHA-256

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| [Checkout wheel](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/checkout-dist/valpas-1.0.1.dev30+g4d572bc23.d20261119-py3-none-any.whl) | 215680 | `cc70f3da10a73d1b0903b945f8527986ff90b9d71ea7196f275c329d3e08443e` |
| [Git-free-sdist wheel](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/sdist-dist/valpas-1.0.1.dev30+g4d572bc23.d20261119-py3-none-any.whl) | 215680 | `cc70f3da10a73d1b0903b945f8527986ff90b9d71ea7196f275c329d3e08443e` |
| [Source distribution](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/checkout-dist/valpas-1.0.1.dev30+g4d572bc23.d20261119.tar.gz) | 269049 | `da5c1088ceebe4d869336b3046b9cc20c7b94fe493c0bd82173fa2959bdaffef` |

The two wheels happened to be byte-identical in this run. This is recorded evidence, not a general reproducible-build guarantee.

## Exact inventories and scientific invariants

Bundle schema remains v3. References and sessions are strict optional schema-v1 extensions. Inventories are exact: **10 base**, **12 A3/profile**, **15 full B1**, **15 reference-only with query groups**, and **20 full B2 tables**. References add four tables, query groups add one; attaching a session adds a document, not a scientific table. Cases without profiles, metadata, groups, or sessions remain independently supported and tested; malformed flags, extension shapes, digest values, substitutions, and missing required archive contents are rejected.

For the combined fixture, common candidate pool and depths 1, 2, 5 produce these exact row counts:

| Table | Rows | Table | Rows |
| --- | ---: | --- | ---: |
| outputs | 3 | configuration_differences | 62 |
| coverage | 6 | exclusions | 3 |
| candidate_ranks | 18 | agreement | 18 |
| run_recurrence | 30 | agreement_summary | 9 |
| query_summary | 6 | dataset_summary | 1 |
| feature_coverage | 5 | profile_values | 30 |
| sample_metadata | 24 | diagnostics | 1 |
| group_summaries | 2 | reference_endpoints | 3 |
| reference_evidence | 5 | reference_recovery | 54 |
| reference_summary | 1080 | query_groups | 2 |

Direct, inferred, and pathway endpoints are independent. The two direct records for M01/P01 do not double-count pair support; M02's outside-pool direct pair remains unreachable with undefined reachable recovery; an unassessed endpoint is not negative evidence. Both queries belong to the same query group. Ten base scientific tables remain equal to the original A3 results; all twenty tables remain equal through session attachment and regeneration.

Installed smoke checks cover 18 demo bundle variants plus two independent reference-only bundles. Copied input files are deleted before regeneration and vector export, proving those paths use persisted bundle content rather than the original inputs. Old A3/B1, hostile text, no-profile, tables-only, optional inventory, compatibility, and integrity checks were retained rather than weakened.

## Actual installed Chrome evidence

Each wheel ran five Chrome modes. B2 uses an unchanged generated report copied alone outside its bundle, opened directly from a local file URI. Hostname resolution is disabled; the report forbids network connections. Localhost CDP is browser control, not a report data server.

The [checkout B2 log](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/logs/047.log) and [sdist B2 log](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/logs/087.log) passed. Detailed [checkout browser record](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/checkout-wheel/browser-b2.json) and [sdist browser record](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/sdist-wheel/browser-b2.json) retain actions, file paths, sizes, hashes, report URI, and five decisions each.

Verified actions and invariants:

1. Restore the attached initial session with two decisions. Exercise all-candidate, direct, inferred, pathway, and unsupported filters through actual DOM controls. Expected subsets are all P01/P02/P03, direct P01, inferred P02, pathway P03, and unsupported-direct P02/P03. Restore exact rank-cell markup; overview HTML and embedded scientific payload are unchanged.
2. Set metadata color/group/order, first-order diagnostics and omission controls. Enter hostile notes containing a spreadsheet formula prefix, a closing-script/opening-script sequence, a newline, and Unicode. Add investigate, retain-alternative, and abstain decisions, reaching five total.
3. Actually download session JSON, shortlist JSON, and formula-safe shortlist CSV through Chrome. Python loaders validate the downloaded documents against the installed result. Abstention has no candidate in either decision or snapshot; reference and B1 state survive.
4. Open a fresh report, upload each actual JSON file through its DOM file input twice, download again, and require exact restored content/bytes. Repeated imports replace state idempotently, without storage fallback. Tampered session import is rejected atomically without changing notes.
5. Actually download browser SVG; parse it with both Python XML and the browser XML parser. Verify exact notes and bounded-scope/non-identical-renderer disclosures, six observed scatter circles, twelve profile circles, and zero imputed circles for this M01/P01 fixture view. No malicious content executes; no external resources are used; final embedded payload equals the installed bundle payload.

Both copied reports have SHA-256 `7653f6d40440c8fedfac25a2b7e11a0bce2e8ab9a6f02b76505d9dc2a7c1ea95`.

| Actual download | Checkout SHA-256 | Sdist-wheel SHA-256 |
| --- | --- | --- |
| Session, original and restored | `da315fec2e81c04b7f4bfeccf37b10ce820ee522854ad532b6ff36a78136ab58` | `4f62c81ee1647ea00f99cb1fe0b6cd871c8d9a5151d787c2730745f3c2cde982` |
| Shortlist, original and restored | `d65935675a0f57126c1bb8558cf9554920e4997ca61eaed3b7bf6c757d9b7908` | `452a53e24976de8a842b8a50db94cc9fb12da74ff4d0f35c1a58be78eb7093a6` |
| Browser SVG, 35166 bytes | `ed1284242a260bf67d0eb6fd18740645ec873debe4a6afe8ef7d2334a8fde289` | `ed1284242a260bf67d0eb6fd18740645ec873debe4a6afe8ef7d2334a8fde289` |

The files are retained under each artifact's browser-b2 directory: [checkout downloads](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/checkout-wheel/browser-b2) and [sdist-wheel downloads](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/sdist-wheel/browser-b2). Cross-run session/shortlist hashes differ because browser decisions have runtime timestamps/action identifiers; original/restored equality is required within each run.

## Source-free figure API and CLI evidence

Both installations passed console/module export help, CLI SVG/PDF export after original inputs were deleted, API SVG/PDF export, and strict session-bound decision SVG export. SVG validation checks XML namespace, contextual captions, and absence of scripts, images, foreign objects, or external links. PDF validation checks opening and closing framing; it is not a manual PDF visual inspection.

The [checkout figure record](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/checkout-wheel/figures.json) and [sdist-wheel figure record](../../../../../private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-eabker0i/sdist-wheel/figures.json) contain all output paths, sizes, and hashes. Exact installed CLI invocations are in the distribution summary. Sdist command logs 079/080 cover CLI SVG/PDF, 081 bundle assertions, and 082 API/vector assertions; 083–086 cover retained browser modes, 087 B2, and 088 legacy imports.

| CLI vector | Checkout SHA-256 | Sdist-wheel SHA-256 |
| --- | --- | --- |
| SVG | `103e32f6fc280c46d16e8f7291e1af3a70168b07bcdc27bbb2a7a2380a2487c8` | `7e17963c22b904eff9e93378089c8181443e14c8b663c730c69466269ed94497` |
| PDF | `07dff8e4104ca1bd5be5ea835a9fe74232907d60b80a60b00caa3599fbe3d8a3` | `9f8a611fae349862488afc17af94618b17df90823fdcb8ef1067049928e2d456` |

API SVGs are 53148 bytes and API PDFs are 39644 bytes. Matplotlib metadata/timestamps/identifiers can vary; browser and Python renderers are not claimed to be byte-identical or visually identical. Figures remain descriptive observations, not model attribution or scientific validation labels.

## Boundaries and parent follow-through

- Finalize general README, CLI/user-guide, and implementation-plan status documentation after this gate. Preserve the artifact chronology above; rebuild if claiming a later source/documentation snapshot is the exact validated release artifact.
- No target-scale benchmark, model training, Sphinx build, B3 production-boundary completion, cross-platform/browser matrix, or manual publication-layout/accessibility review was performed or claimed.
- Dependency reuse was explicitly authorized and used. A fresh dependency-resolution/install gate remains a distinct experiment.
- Synthetic local fixtures establish contract/integration behavior, not biological truth or broad real-world reference coverage. Reference evidence does not change scientific nominations; notes/decisions are user-authored assessments, not learned or validated labels.
- Temporary evidence and retained environments are local and may eventually be removed by system cleanup. Archive the evidence root before cleanup if durable release evidence is required.
- No further runtime suite rerun is needed solely for this post-build handoff. Any subsequent implementation, packaged resource, fixture, or harness change requires appropriate revalidation.
