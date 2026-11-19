# Release A / B1 distribution validation

Run the standard-library [validator](../tools/validate_distribution.py) with Python 3.12+ from a checkout (or an extracted source distribution):

```sh
python3 tools/validate_distribution.py
```

This is a **full dependency install**, not an editable or dependency-free smoke. It downloads the build frontend, isolated PEP 517 backend requirements, and all wheel-declared dependencies, including PyTorch. Allow several GB of temporary disk space and a network connection to PyPI. It never installs into the invoking Python environment and never trains, scores new associations, loads checkpoints, or runs GPU jobs. An existing Chrome/Chromium is required; it does not download a browser. Select a nonstandard browser with the validator's `--chrome` option.

## What the gate checks

1. Build the current source into a wheel and sdist using a private build environment and backend isolation. Record real VCS-derived versions; no version overrides. Preserve pre-existing generated version-file bytes after the run.
2. Inspect wheel assets and dependencies, and sdist comparison guides, examples, fixture inputs (including profiles), assets, and validation tools. Reject unsafe archive paths, links, special members and duplicate members before extraction into an exclusively owned external directory.
3. Rebuild a wheel from the extracted sdist, outside the checkout and without Git metadata. Require matching artifact versions and declared requirements.
4. Install each wheel noneditably, with **all declared dependencies**, into a separate new environment without shared site-packages. Run the package dependency consistency check and record complete installed versions and pip installation reports.
5. Run [installed-package assertions](../tools/distribution_smoke.py) with isolated Python, cleared Python search-path/home settings, and working directories outside the checkout. Verify module location, distribution identity and packaged resource bytes; run installed console and module help.
6. Copy the sdist's synthetic fixture inputs into each smoke workspace. Retain the original A3 HTML/tables-only cases and no-profile case; add separately named B1 HTML/tables-only and malicious-metadata cases. Delete the copies before regenerating both A3 and B1 saved bundles. Require **result schema v3**, exact named table and schema inventories, exact API/table parity and unchanged scientific identity. Independently optional metadata, requests and grouping determine the inventory: ten scientific tables, two profile tables when present, metadata when present, diagnostics only for requests, and groups only for grouped requests. The B1 demo has exactly **15 tables, one diagnostic, two marginal group rows, 24 unique observation/field metadata rows and 30 profile values**, not an all-pairs expansion. All ten scientific tables must match every A3/B1/no-profile/hostile export. Check embedded assets and connection-blocking policy.
7. Copy regenerated HTML alone into a separate directory. Use headless Chrome directly from disk with hostname resolution disabled; append assertions only to this disposable copy. Retain A3 heatmap drilldown, searches, sorting, depth/output visibility, pins, SVG profiles, masks and hover checks. B1 exercises categorical/continuous selectors, missing metadata, actual metadata reordering plus ID/dataset order, grouping/fraction controls, h/omission/reset/invalid h, and full nested diagnostic/group parity against the **installed Python API**. Assert unchanged overview, rank DOM and saved payload after diagnostic changes. A disposable fixture copy supplies script-closing malicious metadata through the installed CLI; its group/hover text must remain inert. A separate no-profile browser case requires an explicit reason and no fallback plots. Follow the [A3](../tests/comparison/test_a3_browser.py) and [B1](../tests/comparison/test_b1_browser.py) direct-file contracts; no checkout package imports. This is not cross-browser, visual or accessibility certification.
8. In separate installed processes, resolve all legacy public exports and representative legacy modules with real dependencies. Importing PyTorch is not a training test.

The wheel supplies package code and browser assets. Comparison guides, examples and demo inputs are supplied in the **sdist**, not as installed wheel data. Extract the sdist to use those examples against an installed wheel; the source snippets in the Release A guide are explicitly checkout-oriented. This gate does not claim that all general README-linked notebook/training/documentation files are shipped in the comparison sdist.

## Installed B1 example inputs

The [comparison example](../examples/compare_saved_results.py) defaults to the [B1 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b1.json). For an installed-wheel run outside the checkout, copy the **entire** [demo directory](../tests/comparison/fixtures/demo-01/README.md) from the newly extracted sdist, not just the manifest. It includes all three saved-score CSVs, [B1 profiles](../tests/comparison/fixtures/demo-01/b1-profiles.json), [sample metadata](../tests/comparison/fixtures/demo-01/sample-metadata.json), and the original A3/no-profile fixtures. Use the installed console entry point with that copied B1 manifest and an external output directory. The API example has no manifest override: preserve the relative layout, with the copied example under an examples directory and the fixtures under tests/comparison/fixtures/demo-01 in the same external parent. Run the copied script with isolated installed Python. The validator runs both sdist-shipped comparison examples this way, then removes their disposable input copies; separate CLI smoke inputs are also removed before regeneration.

## Explicit retained-environment validation

The default command above still performs fresh full dependency installations. To reuse a previous validator's three **isolated full-dependency environments**, explicitly supply its external workspace:

```sh
python3 tools/validate_distribution.py --reuse-envs /external/previous-validation --keep-envs
```

This mode always allocates a **new** workspace and builds a new checkout wheel, sdist, and extracted-sdist wheel. It installs missing frontend/backend tooling only into the retained build environment, then builds without backend isolation. Each new wheel is force-reinstalled without dependency resolution into its corresponding retained runtime environment, followed by dependency consistency checks and all current installed/browser assertions. Both wheels' resource hashes must equal the current checkout assets, and installed resource bytes must equal the respective wheel. Retained environments are never automatically deleted.

This is **retained full dependencies, not fresh dependency installation**. It establishes current artifact/install/runtime behavior, not a fresh resolver/network gate. The summary marks this distinction and records exact commands, environment paths, package versions and installation reports. Missing runtime dependencies cause failure; no silent dependency skips or host/global installs. Missing build tooling may require a small isolated download. No prior artifacts or prior success summaries count as current evidence.

## Evidence and cleanup

The first output line names a unique external temporary workspace. That directory retains a machine-readable summary, numbered command logs, both wheels, the sdist, extracted source, pip installation reports, synthetic result bundles, and disposable browser pages. The summary records commands, working directories, timing, return codes, artifact SHA-256 identities/versions, module locations, dependency versions, table counts, browser results and any failure traceback. A successful exit requires both artifact paths and browser checks to pass; there is no no-dependency or silent browser-skip mode.

By default, large environments and browser profiles are removed on success or failure; diagnostic evidence remains. Retain them for additional regressions with:

```sh
python3 tools/validate_distribution.py --keep-envs --timeout 1200
```

The timeout applies per command (20 minutes by default). On POSIX, timed-out command process groups are killed. Use the validator's `--work-parent` option to choose an existing external disk directory; a unique child is allocated and a path inside the source tree is rejected. Only fixed children of that newly allocated workspace are automatically deleted. Remove the reported workspace when its evidence is no longer needed. Pip's normal download cache may be shared, **not installed site-packages**. User pip configuration and Python/VCS version overrides are cleared to prevent redirected installs and source leakage; proxy/certificate environment settings remain available. Private-index-only environments may therefore fail with an explicit network/index diagnostic rather than accidentally using an unrelated configuration.

Current tracked and untracked source changes are not reset or stashed. Build archive membership depends on the configured backend's inclusion rules; the validator checks required members rather than assuming that every untracked file is shipped. Artifact identities and recorded Git status identify the tested state, which may carry a dirty development version.

## Focused automation tests

```sh
python3 -m unittest discover -s tests/packaging -v
PYTHONPATH=src python3 -m unittest discover -s tests/comparison -v
```

Harness tests exercise environment sanitization, archive safety/content requirements, command failure/timeout evidence and offline HTML rejection without downloads. The comparison suite is a **source regression suite**, not installed-artifact evidence: some existing tests deliberately insert the source tree into subprocess paths. The separate distribution pipeline above supplies installed-artifact evidence.

Network or resolver failure is a failed validation, recorded with its exact command/log; it is not full-install success. Sphinx rendering, training suites, B2/B3 features, target-scale performance, cross-platform Python support and manual visual/accessibility review remain separate gates. Run the full comparison source suite and packaging harness in a full-dependency interpreter before/after builds; report exact counts and skips. These intentionally source-oriented runs do not replace installed checks. Top-level model-training/performance tests are outside this distribution gate.
