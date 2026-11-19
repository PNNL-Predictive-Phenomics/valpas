Offline saved-output comparison (B2 complete)
============================================

Compare saved methods/configurations/runs without training, scoring, a server,
network access, or a target feature. HTML plus complete scientific tables is the
default; explicit tables-only export remains supported.

.. code-block:: sh

   PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-b2.json --outdir demo-b2 --pool common --depths 1 2 5

Run from the checkout with project dependencies installed and a new destination.
Open the generated ``demo-b2/report.html`` directly from disk. Start with the dataset overview,
output-pair heatmap and depth chart, inspect separate run recurrence, then search
queries and drill down into candidate ranks and optional original-mask profiles.
Filters never change scientific pools. Agreement is not correctness.

The full `B2 workflow guide <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_RELEASE_A.md>`_ (historical filename retained)
covers usable manifests, optional profile contracts, payload limits, metadata
omission, regeneration, API usage, schema versions and validation limitations.
The `input/scientific schema reference <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_SCHEMA_V1.md>`_
documents completeness, missingness, legacy formats and denominators.

Reports embed at most the explicit query/top-union/pinned scope, with a default
50 MiB JSON payload limit before HTML wrapping. Full scientific tables remain
independent. Sensitive metadata is retained unless explicitly omitted from HTML;
the normalized bundle is never redacted. New result bundles use schema version
three, with same-software/policy version-one and version-two reload support.
**B2 is DONE**, including integrated full-suite/distribution validation.
B3 production metadata capture/export integration and target-scale validation
remain future; the full Release B/project is not complete. Input/scientific
schemas remain v1; result v3 has strict optional schema-v1 reference/session
extensions. Same-software/policy reload is not cross-version migration.

Optional local reference evidence
---------------------------------

``valpas.comparison.ReferenceData`` and ``QueryGroups`` provide strict, detached
schema-v1 contracts. ``load_reference_data`` and ``load_query_groups`` accept inline
JSON documents or contained local JSON paths. Supply validated objects through
``compare_results(..., references=..., query_groups=...)``, or use the optional
manifest sections. No annotations are downloaded or inferred.

Each source/version/pathway-or-reaction/support-class endpoint remains separate.
Explicit assessed-query coverage and candidate universes distinguish unassessed,
assessed-zero, unreachable, unavailable and limited-depth results. Tables and the
offline overview report all-assessed and reachable cohorts, metric-specific
denominators, opportunity strata and feature or explicit equal-group weighting.
Reference-supported fraction divides supported nominations by actual nomination-list
size, not requested depth; it is not biological precision. Recovery divides by
known reachable support; reachability divides by total known support. Zero/unknown
denominators give unavailable/null, not zero. All-assessed includes zero opportunity;
the reachable cohort requires known positive reachable support. Strata are 0, 1,
2–5 and 6+, with unknown opportunity separate. Default weighting is equal-feature;
explicit group weighting averages evaluable features within each group, then equally
averages nonempty groups, never choosing a best peak. Denominators/exclusions are
metric-specific; output/run summaries stay independent. Multiple evidence records
for one query/candidate count as one supported pair. Missing evidence is not a
biological negative. Evidence filters only change candidate display.

The combined demo uses explicit group weighting and independent direct, inferred
and pathway endpoints. At M01 and depth 5, all candidates are P01/P02/P03;
direct-supported shows P01, inferred-supported P02, pathway-supported P03, and
direct-unsupported P02/P03. M02 is inferred-unassessed, pathway-assessed-zero,
and has unreachable direct support. Outside-universe/unassessed is distinct from
unsupported by the selected endpoint. Synthetic profiles illustrate diagnostics;
they did not generate the saved scores. Seed recurrence is not biological replication.

Reference inputs never change scientific comparison identity, ranks or nominations.
The separate ``result.reference_provenance_hash`` binds normalized references,
groups and reference policy. An optional version-one ``b2_references`` extension
inside result schema three inventories normalized documents and exact reference
tables. Existing reference-free bundles retain their contracts. Reference payload
bytes count toward the HTML budget; metadata omission removes reference data from
HTML but does not redact the complete bundle. Full-cohort reference summaries
remain independent of detail-query scope.

See the reference section of the schema guide linked above and the
`known-math reference fixture <https://github.com/PNNL-Predictive-Phenomics/valpas/tree/main/tests/comparison/fixtures/b2-reference>`_.
The reference path uses only the standard library and saved values; no training,
rescoring, server or scientific-library import is required.

Portable user sessions and shortlists
------------------------------------

``valpas.comparison.Session`` and ``Shortlist`` are immutable schema-v1 documents.
``Session.create(result, settings)`` derives a bounded view; ``with_view`` returns
an updated copy. ``add_decision`` requires an explicit action ID, rationale and
per-action UTC timestamp. The only decisions are ``investigate``,
``retain_alternative`` and query-level ``abstain`` (null candidate). These are user
judgments, never automatic model labels. Each decision retains the exact
comparison ID, pool policy, depth, inspected outputs and full view snapshot.

``session.shortlist()`` retains all decisions, including abstentions, current view,
notes and scope. ``write(path)`` explicitly creates a new JSON file and refuses
overwrite. ``load_session(path_or_document, result=result, settings=settings)``
and ``load_shortlist`` validate exact scientific identity, separate content
identity and report scope. Without a result they validate structure and integrity
only. ``to_dict`` is detached; ``to_json`` preserves exact IDs and escapes script
closers. ``Shortlist.to_csv`` prefixes every data cell with an apostrophe for
spreadsheet safety; CSV is not the canonical or importable representation.

Content identity additionally binds profiles, sample metadata, descriptive output
provenance and reference provenance, without changing scientific identity.
Unknown nested fields, duplicate JSON keys, altered checksums, incompatible IDs,
out-of-scope selections and invalid timestamps are rejected. No migration or
silent clamping occurs. ``rebind_scope(result, settings)`` is an explicit Python-only
operation, required even for expanded scope, and succeeds only when all current
settings and every decision snapshot survive unchanged. No decisions are dropped.
Scope binds query/candidate embedding, depth, pins, omission, output/layer inventory,
metadata fields and endpoints separately from content identity.
Keep the matching self-contained HTML or result bundle: sessions store
inspection state, not a duplicate of scientific scores and profiles.

In the offline report, select a query/candidate and record investigate or retain
alternative with a nonblank rationale; choose query abstention to defer without a
candidate (null in both decision and snapshot). Use the explicit session/shortlist
JSON download buttons and separate file inputs. Download formula-safe shortlist
CSV for display only, not import. Import atomically replaces view, notes and decisions;
repeated imports do not merge or accumulate duplicates. Tampering or mismatch is
rejected without changing old state. Search, selected
query/candidate/output pair, hidden outputs, depth, pins, portable order selectors,
reference filter/endpoint, selected layer, and per-layer B1 color/group/order/h/
omission/fraction settings are restored. Generic table-header sorts are temporary.
No local storage, automatic filesystem writes, server or network is required.
Imports are capped at 50 MiB; only explicit downloads persist browser changes.

``write_comparison(..., initial_session=session)`` persists an inventoried initial
session in an optional ``b2_session`` extension within result schema three.
Reload exposes ``result.initial_session``; the report starts at that state. Its
escaped JSON bytes count toward the default 50 MiB HTML payload budget. Use an
explicit result-field replacement to detach an initial session; the writer's
omitted/default argument retains it. Tables-only bundles may also retain sessions.

Notes, rationales, canonical IDs and reference selections may be sensitive.
Metadata-omitted HTML export with an initial session is rejected rather than
silently redacting text or changing settings. Notes subsequently entered in an
omitted report still appear in explicit downloads. Full bundles retain references,
metadata and sessions and are not redacted. Integrity hashes detect corruption,
not forged authorship. See the schema guide above for complete field tables and
an executable API example. The initial session is an optional document, not a table.

Source-free query figures
-------------------------

Use the saved-bundle CLI with explicit IDs and a new output outside the bundle:

.. code-block:: sh

   PYTHONPATH=src python3 -m valpas.cli export-query --bundle demo-b2 --query M01 --candidate P01 --layer b1-observed --output query-figure.svg
   PYTHONPATH=src python3 -m valpas.cli export-query --bundle demo-b2 --query M01 --candidate P01 --layer b1-observed --color condition --group condition --order metadata --h 1 --omission --output query-figure.pdf

The combined B2 manifest above supplies that measurement layer.
The public ``export_query_figure`` accepts a result or saved bundle, with explicit
query/candidate/layer/output and optional metadata, diagnostic, notes or strictly
validated session/decision context. Matplotlib is imported only during actual
SVG/PDF rendering. Help, comparison and public imports remain lightweight.
No new dependency, training, scoring or network access is involved.

Scatter uses jointly observed finite pairs; profiles distinguish originally
unobserved/imputed values. Captions disclose exact identities, masks, counts,
units, transform, overlays, pools/depths and descriptive interpretation, never
model attribution. Output paths cannot overwrite existing files or pollute owned
bundles. Python uses full normalized data even outside the bounded HTML scope.
The browser offers an explicit per-layer SVG download with a bounded-scope warning;
it is not identical to Python vector rendering. Inspect sensitive notes and
annotations before sharing. An initial session in a bundle is not implicitly used
for Python figures; pass the desired session explicitly. Query abstention cannot
supply a candidate figure. No session schema change is needed.

The complete normalized bundle also regenerates a report without original inputs:

.. code-block:: sh

   PYTHONPATH=src python3 -m valpas.cli compare --bundle demo-b2 --outdir regenerated

Use a new destination. Pool/analysis-depth overrides are rejected on bundle input.
Old assets are verified by inventory integrity and exact normalized/stored/embedded
payload parity, including session-bearing bundles, not today's HTML bytes.

See the `CLI-first figure guide <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_FIGURES.md>`_
for complete options, privacy, regeneration, literal text and validation boundaries.

Validation and remaining scope
------------------------------

The `integrated B2 validation record <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/plans/B2_VALIDATION_HANDOFF.md>`_
records **232 full-dependency comparison tests (zero skips), 22 harness tests,
88 installed validation commands and 10 actual direct-file Chrome cases across
both wheels**. Both wheels ran in retained isolated full-dependency environments,
not fresh dependency resolution. Those artifacts predate this documentation
finalization; no rebuild was performed for these docs-only changes. Historical
slice handoffs retain their earlier counts/status. No target-scale, other
OS/Python/browser matrix, manual visual/accessibility certification, Sphinx build
or broad training-suite claim is made by that historical B2 record.

B3 production integration
-------------------------

The `CLI-first production guide <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/docs/COMPARISON_PRODUCTION.md>`_
explains opt-in sidecar requests, explicit identity/orientation, known versus
unknown provenance, full-precision export before legacy mutation, and independent
publication failures. Run the shipped production example from the source
archive against an installed wheel; it calculates tiny synthetic Pearson and
Spearman matrices, never trains, then compares the exported saved values offline.

The public ``export_association_result`` also adapts existing labeled results
without fitting again. ``AssociationResult.export_comparison`` is a convenience
wrapper; calculation and file-based association entry points accept the optional
keyword-only ``comparison_export`` request. Legacy defaults are unchanged.

The `B3 validation record <https://github.com/PNNL-Predictive-Phenomics/valpas/blob/main/plans/B3_VALIDATION_HANDOFF.md>`_
records final integration evidence. The bounded 1,000 × 5,000 × 8 dense run stopped
during loading at 600.545 seconds and 5.05 GiB sampled peak RSS; full comparison,
report generation and full bundle writing were not validated at that size.
Browser scope bounds do not bound full input memory. This is a measured limitation,
not a passing performance target.
