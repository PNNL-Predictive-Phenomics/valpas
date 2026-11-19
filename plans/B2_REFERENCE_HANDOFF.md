# B2 reference subsystem handoff — 2026-11-19

## Scope and completion boundary

Implemented only B2 reference evidence: strict local contracts/import, source-separated evaluation, optional exact-integrity persistence, full-cohort overview and display-only evidence filtering, known-math fixtures and focused tests. **Overall B2 is not complete.** Decisions, abstention/notes, session/shortlist persistence and figures/export-query remain for the next integration. B3 and final release validation remain unfinished. No training, network annotation retrieval, dependency installation, build or packaging was performed.

## Integration interfaces

- Public [ReferenceData](../src/valpas/comparison/reference.py:85), [QueryGroups](../src/valpas/comparison/reference.py:41), [load_reference_data()](../src/valpas/comparison/reference.py:184), [load_query_groups()](../src/valpas/comparison/reference.py:189), and [reference_provenance_hash()](../src/valpas/comparison/reference.py:206) are exported from [the comparison package](../src/valpas/comparison/__init__.py).
- [compare_results()](../src/valpas/comparison/engine.py:296) adds optional validated references/query_groups keywords; None inherits the manifest values. [ComparisonManifest](../src/valpas/comparison/models.py:398) and [ComparisonResult](../src/valpas/comparison/engine.py:136) append the corresponding fields, retaining existing positional-field order. Groups require references; group weighting requires groups.
- [Reference tables](../src/valpas/comparison/reference.py:378) are optional endpoint, evidence, recovery and summary tables, plus query groups when supplied. Iterate through the existing result table interface; no new eager expanded base-engine tables. Exact ordered schemas are persisted. CSV cells remain JSON values, including nested exclusions/group details.
- Scientific comparison ID and the ten base scientific tables are unchanged by references. The [separate provenance digest](../src/valpas/comparison/reference.py:206) includes normalized endpoints/evidence/groups, descriptions, assessment/universe, weighting, policy 1 and strata. It excludes transport paths/order and exact duplicate evidence rows. Raw consumed-file hashes remain separate. Future sessions retaining evidence choices should bind **both** comparison ID and reference digest, and preserve endpoint ID rather than silently unioning endpoints. This digest does not version profiles, diagnostics or presentation.
- The [manifest loader](../src/valpas/comparison/adapters.py:358) accepts inline schema-v1 documents or contained local JSON paths. No automatic matching/coercion/annotation lookup; IDs and namespaces bind explicitly.

## Persistence contract for subsequent extensions

The [writer](../src/valpas/comparison/report.py:129) still emits **result schema v3**, not v4. References add an optional b2_references object containing exactly schema_version (integer 1), query_groups (boolean), and provenance_hash. Normalized [references.json](../src/valpas/comparison/report.py:141), optional [query_groups.json](../src/valpas/comparison/report.py:143), and optional tables enter the exact inventory. Without references, this extension and all reference payload fields are absent.

[Reload](../src/valpas/comparison/report.py:289) verifies extension shape, inventory/digests, binding, normalized provenance and exact table parity; original paths are never opened. Existing same-software/policy v1/v2/v3 reference-free bundles reload. Because packaged JavaScript changed, reference-free v3 HTML now uses the [legacy asset-validation path](../src/valpas/comparison/report.py:366): verify saved inventory, embedded/stored JSON, payload size/hash and normalized science/settings rather than demanding byte equality with current assets. V2 additionally applies its existing B1-free projection. Reference-bearing v3 bundles still require exact current rendering. Future asset/schema additions need an explicit compatibility decision here; do not silently weaken science/payload validation.

A1 input bundles are unchanged; references travel through manifests or comparison-result bundles. Exact ownership/inventory checks reject unrelated files, so a future session export must deliberately define its own contract or update inventory rules rather than placing ad hoc files in an owned result bundle.

## Browser integration

[Payload construction](../src/valpas/comparison/browser.py:52) adds the provenance digest and reference object only when supplied. It includes full-cohort recovery/summaries over analysis plus interactive depths. Evidence records are bounded to embedded detail queries and top-union/pinned candidates; endpoint assessment/universe declarations remain explicit. Python computes all reference metrics.

[Dashboard reference controls](../src/valpas/comparison/assets/dashboard.js:260) maintain a selected endpoint and an all/supported/unsupported-by-source display filter. Filtering is downstream of saved nominations and never changes top lists, pools, ranks or metric denominators. Unassessed and outside-reference-universe are separate display statuses. Candidate evidence preserves multiple records, rendered via text DOM operations. Later session support may capture these controls but must not treat filtered rows as scientific selection.

Metadata omission removes all reference content from HTML (including summaries/groups), with explicit disclosure; the digest remains. Complete normalized bundles are not redacted. All escaped reference bytes count toward the report budget; over-budget reports fail rather than sample. Report detail subsets do not subset full-cohort reference metrics.

## Scientific interpretation

[Schema documentation](../docs/COMPARISON_SCHEMA_V1.md) and [fixture mathematics](../tests/comparison/fixtures/b2-reference/README.md) define exact counts, fractions, cohorts and null reasons. Source/version/pathway/reaction/direct/inferred endpoints never merge. Duplicate records do not multiply pair support. Missing evidence is not a biological negative; supported fraction is not biological precision. Recovery divides by known reachable support, supported fraction by actual nomination-list size. All-assessed includes known zero opportunity; reachable requires known positive opportunity. Strata are 0, 1, 2–5, 6+. Each metric has independent evaluable/excluded denominators. Explicit group weighting is an equal mean of within-group evaluable-feature means, never a best peak. Runs remain separate outputs, not biological replication.

Unexhausted certified prefixes may yield shallow hit/fraction but unknown reachable denominator. Missing/filtered/unavailable inputs are not zeros. Strict availability is cohort-wide; native inspection remains descriptive. Reference evaluation consumes the existing engine pools and certification without changing them.

## Exact validation commands and results

All commands ran from the repository root with the user-designated existing interpreter. No tests were skipped in the reference or combined focused runs.

Initial contract/math and existing B1 persistence checks:

```sh
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest discover -s tests/comparison -p 'test_b2_reference.py' -v
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest discover -s tests/comparison -p 'test_b1_persistence.py' -v
```

Results: **20 passed in 0.101 s**, **17 passed in 3.387 s**.

Full new reference subset:

```sh
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -m unittest discover -s tests/comparison -p 'test_b2_reference*.py' -v
```

Result: **32 passed in 13.342 s**, including actual direct-file Chrome interactions. Two unclosed test CSV readers emitted warnings; both were subsequently changed to context-managed reads.

Clean focused regression after fixing those readers:

```sh
PYTHONPATH=src:tests/comparison /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -W error::ResourceWarning -m unittest test_a2_engine test_a2_persistence test_a3_report test_a3_browser test_b1_persistence test_b1_browser test_b2_reference test_b2_reference_persistence test_b2_reference_browser -v
```

Result: **109 passed in 37.340 s**, no skips/warnings. Includes existing A3/B1 and new B2 real Chrome cases; new browser tests cover independent endpoints, supported/unsupported filtering, pinned candidates, depth/output controls, unchanged nominations, hostile text, one-to-many evidence, full-cohort subset behavior, omission and no external resources. Persistence tests cover CLI source-free regeneration, optional schemas, byte hashes, tampering with refreshed inventory, budget/rollback, v1/v2/v3 compatibility and blocked heavy imports.

Final reference-only rerun after documentation/docstring edits:

```sh
PYTHONPATH=src /private/var/folders/zg/2qynpgpn60qf_kd5d0lrnvrr0000gn/T/valpas-distribution-8evqy102/checkout-wheel-env/bin/python -W error::ResourceWarning -m unittest discover -s tests/comparison -p 'test_b2_reference*.py' -v
```

Result: **32 passed in 12.947 s**, no skips/warnings, including actual Chrome. Whitespace validation: `git diff --check` passed. Full suite, installed-asset/packaging validation and Sphinx build are deliberately deferred to the parent integration workflow.

## Known limitations / next integrator checklist

1. JSON-only reference/group transport; no download, annotation inference, cross-source unions or CSV reference importer.
2. Reference inputs and summary recovery rows are materialized; full-cohort HTML metrics can dominate payload size. No target-scale performance claim or benchmark was made. Smaller detail scope may not materially shrink reference overview bytes; use explicit omission, an appropriate budget or tables-only export.
3. Prefix reachability is conservatively unknown unless the engine knows a complete certified active order. There is no guessed full-pool support denominator.
4. Backward reload is same-software/policy only, not cross-version migration. Checksums detect corruption, not malicious provenance forgery.
5. Extend session/figure schemas without changing existing scientific IDs. Bind reference choices to the separate digest and endpoint ID; account for absent/omitted reference metadata and metric-specific null availability.
6. Preserve full-cohort summaries and bounded evidence behavior when adding UI controls. Apply any session display filtering after scientific nominations.
7. Parent must run final full validation/packaging after concurrent work, and implement remaining B2/B3 deliverables before declaring completion.
