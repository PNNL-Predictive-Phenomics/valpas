# Query figures from saved results (B2 complete)

## CLI-first workflow

Start with a completed result bundle containing explicitly bound profile measurements. From a checkout with project dependencies installed, use the [combined synthetic B2 manifest](../tests/comparison/fixtures/demo-01/manifest-with-b2.json), not training or real experimental evidence. Choose new output paths for each run. The [complete B2 workflow](COMPARISON_RELEASE_A.md) covers overview-first reference inspection and decision/session download/import before figures.

```sh
PYTHONPATH=src python3 -m valpas.cli compare --manifest tests/comparison/fixtures/demo-01/manifest-with-b2.json --outdir figure-demo --pool common --depths 1 2 5
PYTHONPATH=src python3 -m valpas.cli export-query --bundle figure-demo --query M01 --candidate P01 --layer b1-observed --output query-figure.svg
PYTHONPATH=src python3 -m valpas.cli export-query --bundle figure-demo --query M01 --candidate P01 --layer b1-observed --color condition --group condition --order metadata --h 1 --omission --output query-figure.pdf
```

The [export-query handler](../src/valpas/cli.py:359) delegates to the public figure API. SVG/PDF suffix selects the renderer. Query, candidate, layer and output are required and exact; IDs are never turned into filenames. Original inputs can be removed after bundle creation. No model, checkpoint, training, association scoring, annotation lookup or network access is used.

**Write outside the bundle.** Bundles have exact file inventories; figures are independent artifacts, not extra bundle members. Existing destinations, symlinks, traversal, missing parents and consumed-source collisions are rejected. Rendering uses a temporary sibling followed by atomic no-clobber publication. A failed render leaves no final file and cleans staging. This is local staged publication, not crash recovery or defense against hostile concurrent directory replacement.

Actual Python rendering needs Matplotlib, already a declared project dependency; no dependency was added for this feature. Package/API imports and CLI help remain standard-library-only, without changing warning filters. Matplotlib is imported only for an actual export. A missing renderer produces an actionable error; nothing is installed automatically.

## What the figure means

- Scatter includes **only jointly observed finite pairs**, with candidate on x and query on y.
- Profiles share a value scale. Blue circles represent query, purple squares candidate when metadata color is not selected. Hollow orange marks are finite originally unobserved/imputed values, excluded from observed-only summaries. A zero-joint cohort still permits marginal profiles; it does not create imputed scatter points.
- The caption records exact IDs and namespaces, layer, units, transform, provenance, algorithm-layer relationships, mask source, required/layer sample counts, marginal observed-finite/imputed counts, joint count, coverage exclusions, scientific pool/analysis depths, optional inspection depth, display ordering and metadata overlay.
- Categorical colors have a caption RGB key; continuous colors run blue to red (constant field uses midpoint); missing metadata is gray. Ordering changes only display positions. Exact observation order is in the caption.
- Optional categorical grouping describes each feature's own known-group observed-finite cohort, not the joint cohort. Continuous fields are never automatically binned. The SS fraction is optional.
- Joint-centered products, largest-h absolute shares and optional omission/recentering are descriptive diagnostics. They are **not model attribution, causal effects, adjusted variance components, confounding correction or leave-one-out model evaluation**. Scores, ranks, nominations and scientific pools never change. Agreement is not correctness.

The caption retains exact diagnostic results, including availability reasons and cohorts, rather than substituting unexplained correlation values. Long captions grow the figure vertically and may produce large pages; inspect layout before publication. Fonts and vector layout can vary across Matplotlib/platform versions; byte-for-byte reproduction is not promised.

## Display options and saved views

The [public exporter](../src/valpas/comparison/figures.py:261) accepts either a result object or a result-bundle path:

```python
from valpas.comparison import export_query_figure

export_query_figure(
    "figure-demo", query_id="M01", candidate_id="P01",
    layer_id="b1-observed", output="api-query.svg",
    color="condition", group="condition", order="metadata",
    h=1, omission=True, include_fraction=False, depth=2,
    notes="User-authored inspection, not a model conclusion.",
)
```

Without a session, defaults are no metadata color/group, dataset order, h=5, omission off, fraction on, no selected inspection depth and empty notes. Optional CLI controls are color, group, order, h, omission, no-fraction, depth and notes. Explicit depth is inspection context only, not a claim of top-list membership.

An optional [Session](../src/valpas/comparison/session.py:223), local session path or session document can supply the saved current view, notes and per-layer B1 options. An exact decision ID selects that decision's full view snapshot instead; its rationale and inspection context are included. Explicit query/candidate must match the selected view, and explicit layer must fit that view. Conflicting options are rejected, not silently overridden. Query-level abstention cannot supply a candidate figure.

```sh
PYTHONPATH=src python3 -m valpas.cli export-query --bundle figure-demo --query M01 --candidate P01 --layer b1-observed --session saved-session.json --decision-id inspection-1 --output decision-figure.svg
```

Sessions bind both comparison and descriptive content identities and require exact report scope. The optional API report-settings argument supports the exact original scope; there is no implicit migration. Rebind a session explicitly through the existing session API if needed. An initial session stored in a bundle is **not implicitly applied**: pass the desired session explicitly. No new session fields or schema versions were introduced for figures.

Without a session, Python uses full normalized profiles even when HTML omits metadata, embeds only selected queries or bounds candidate depth. Browser embedding is not a Python export restriction. Missing profiles, unknown layers, undeclared IDs, missing namespace-specific features/cohort observations and unavailable original masks yield actionable errors rather than silent subsetting.

## Explicit offline browser download

Select a query/candidate and use **Download this query figure (SVG)** below a measurement layer. This explicitly downloads that layer's scatter/profiles, current B1 display settings and caption to a fixed generic name. No file is written automatically. Existing browser download-name collision behavior is controlled by the browser, unlike the Python no-overwrite contract.

Browser SVG is a **bounded embedded-scope rendering, not identical to Python SVG/PDF**. It preserves the current plot geometry/styles, legends, exact diagnostic/group summaries, scope, view, notes and annotations. For features or metadata omitted from HTML, export from the full bundle using the CLI. Browser controls, strict session state and scientific results are unchanged by download.

User text remains literal: Python disables both TeX and mathtext even under hostile global plotting settings; browser text uses text-only SVG nodes. SVG captions are XML-escaped, with exact unwrapped text in the description element; Python PDF retains the caption in its Subject metadata. Neither path adds external scripts or links. XML-incompatible control characters are rejected rather than silently changing opaque IDs or notes.

**Privacy:** notes, rationales, annotations, IDs, metadata categories and sample IDs can be sensitive. HTML omission does not redact full bundles or figures exported from them. Inspect captions and downloads before sharing. No automatic correctness labels are generated.

## Validation boundary

[Vector/API/CLI tests](../tests/comparison/test_b2_figures.py) exercise real SVG/PDF, literal hostile text, masks/cohorts, same/cross modality, source deletion, safe publication, renderer failure, full-bundle scope, session binding, compatibility and import isolation. [Actual Chrome download tests](../tests/comparison/test_b2_figure_browser.py) parse downloaded SVG with both Python XML and Chrome, check hostile IDs/notes/annotations, masks, B1 settings and strict session persistence.

The [figure handoff](../plans/B2_FIGURE_HANDOFF.md) preserves the earlier focused checkpoint. Subsequent [integrated B2 validation](../plans/B2_VALIDATION_HANDOFF.md) passed **232 full-dependency comparison tests (zero skips), 22 harness tests, 88 installed validation commands and 10 actual Chrome cases across both wheels**, including real SVG/PDF and source-free export. That historical run used retained isolated full-dependency environments, not fresh dependency resolution. See the [B3 validation record](../plans/B3_VALIDATION_HANDOFF.md) for final production integration, rebuilt-artifact evidence and measured scale limitations. Manual visual/accessibility/cross-browser certification is not implied.
