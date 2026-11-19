"""Explicit, source-free descriptive figures. Matplotlib is lazy at render time."""
from pathlib import Path
import colorsys
import json
import os
import tempfile
import textwrap
import xml.etree.ElementTree as ET

from .models import fail, integer, text, thaw
from .profiles import feature_key, feature_coverage, pair_profile
from .diagnostics import covariance_diagnostic, group_summary


INTERPRETATION = (
    "Descriptive observed-data diagnostics only; not model attribution, causal effects, "
    "adjusted variance components or automatic confounding correction. No retraining, "
    "rescoring or reranking. Omission recenters retained pairs, never changes plotted "
    "cohorts or saved scores. Agreement is not correctness."
)


def _json(value):
    return json.dumps(thaw(value), ensure_ascii=False, sort_keys=True, allow_nan=False)


def _literal(value):
    # XML 1.0 cannot represent these characters, even via numeric references.
    # Reject rather than silently changing an opaque scientific ID or user note.
    if any(not (c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or
                0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        fail('figure.text', 'text contains characters not representable in XML 1.0',
             remediation='Use XML-compatible labels/notes; canonical IDs are never silently changed.')
    return value


def _destination(output, result):
    path = Path(output)
    if '..' in path.parts or path.is_symlink() or path.exists():
        fail('figure.output', 'traversal, symlink or existing destination is not allowed',
             remediation='Choose a new explicit .svg or .pdf path outside input/result bundles.')
    if path.suffix.lower() not in ('.svg', '.pdf'):
        fail('figure.output', 'expected an explicit .svg or .pdf filename')
    if not path.parent.is_dir() or path.parent.is_symlink():
        fail('figure.output', 'parent must be an existing non-symlink directory')
    path = path.parent.resolve() / path.name
    for parent in path.parents:
        if any((parent / marker).exists() for marker in ('comparison.json', 'input-bundle.json')):
            fail('figure.output', 'figures must be outside owned comparison bundles',
                 remediation='Write a separate sibling figure, not an extra bundle member.')
    sources = list(result.protected_sources)
    sources.extend(row['path'] for row in result.source_fingerprints if 'path' in row)
    for source in sources:
        source = Path(source).resolve()
        if path == source or source in path.parents:
            fail('figure.output', 'destination collides with a consumed source')
    return path


def _context(result, query_id, candidate_id, layer_id, *, color, group, order,
             h, omission, include_fraction, depth, notes, session, decision_id,
             report_settings):
    for name, value in (('query_id', query_id), ('candidate_id', candidate_id), ('layer_id', layer_id)):
        text(value, 'figure.' + name)
    if not result.profiles or not result.profiles.layers:
        fail('figure.profiles', 'no profile layers supplied',
             remediation='Create a bundle with explicitly bound profile data, then export again.')
    layer = next((thaw(l) for l in result.profiles.layers if l['layer_id'] == layer_id), None)
    if layer is None:
        fail('figure.layer_id', 'unavailable layer: ' + layer_id,
             remediation='Choose an exact layer ID declared in the full saved profile data.')
    for role, fid in (('query', query_id), ('candidate', candidate_id)):
        if not any(fid in getattr(o, role + '_ids') for o in result.outputs):
            fail('figure.' + role + '_id', 'ID is outside declared output feature scope',
                 remediation='Choose an exact declared ID; browser labels are not canonical IDs.')
    pair = pair_profile(layer, result.dataset, query_id, candidate_id)
    if pair['reason'] and pair['reason'] != 'no_jointly_observed_finite_values':
        fail('figure.profiles', 'profile unavailable: ' + pair['reason'],
             remediation='Supply both namespace-specific features, the full required cohort and original masks.')
    options = dict(color=color, group=group, order=order, h=h, omission=omission,
                   include_fraction=include_fraction)
    snapshot = None
    if session is not None:
        from .session import Session, load_session
        obj = session if isinstance(session, Session) else load_session(session)
        obj.validate(result, report_settings)
        document = obj.to_dict()
        view = document['view']
        if decision_id is not None:
            snapshot = next((d for d in document['decisions'] if d['decision_id'] == decision_id), None)
            if snapshot is None:
                fail('figure.decision_id', 'decision not present in the validated session')
            view = snapshot['view']
        if (view['query'], view['candidate']) != (query_id, candidate_id):
            fail('figure.session', 'explicit query/candidate must match the selected saved view')
        saved = next((l for l in view['layers'] if l['layer_id'] == layer_id), None)
        if saved is None or view['selectedLayer'] not in (None, layer_id):
            fail('figure.session', 'layer is outside the selected saved view')
        for name, value in options.items():
            if value is not None and value != saved[name]:
                fail('figure.' + name, 'explicit option conflicts with the saved view')
            options[name] = saved[name]
        if depth is not None and depth != view['depth']:
            fail('figure.depth', 'explicit depth conflicts with the saved view')
        depth = view['depth']
        if notes is not None and notes != document['notes']:
            fail('figure.notes', 'explicit notes conflict with the saved session')
        notes = document['notes']
        snapshot = snapshot or {'view': view}
    elif decision_id is not None:
        fail('figure.decision_id', 'requires a validated session')
    defaults = dict(color=None, group=None, order='dataset', h=5, omission=False, include_fraction=True)
    options = {k: defaults[k] if v is None else v for k, v in options.items()}
    integer(options['h'], 'figure.h', minimum=1)
    for key in ('omission', 'include_fraction'):
        if type(options[key]) is not bool:
            fail('figure.' + key, 'expected boolean')
    if options['order'] not in ('dataset', 'id', 'metadata'):
        fail('figure.order', 'expected dataset, id or metadata')
    if depth is not None:
        integer(depth, 'figure.depth', minimum=1)
    metadata = result.sample_metadata.to_dict() if result.sample_metadata else None
    for key in ('color', 'group'):
        field = options[key]
        if field is not None:
            text(field, 'figure.' + key)
            if not metadata or field not in metadata['fields']:
                fail('figure.' + key, 'metadata field unavailable', remediation='Choose a declared metadata field or omit this option.')
            if key == 'group' and metadata['fields'][field] != 'categorical':
                fail('figure.group', 'group summaries require a categorical field; no automatic binning')
    if notes is None:
        notes = ''
    if not isinstance(notes, str):
        fail('figure.notes', 'expected literal text')
    features = {feature_key(f['namespace'], f['feature_id']): f for f in layer['features']}
    q = features[feature_key(result.dataset['query_namespace'], query_id)]
    c = features[feature_key(result.dataset['candidate_namespace'], candidate_id)]
    diagnostic = covariance_diagnostic(layer, result.dataset, query_id, candidate_id,
                                       h=options['h'], omission=options['omission'])
    from .session import session_content_id
    captions = [
        'VaLPAS descriptive query figure (Python vector export; full normalized feature scope).',
        'Comparison: ' + result.comparison_id + '; content: ' + session_content_id(result),
        'Query: ' + query_id + '; namespace: ' + _json(q['namespace']),
        'Candidate: ' + candidate_id + '; namespace: ' + _json(c['namespace']),
        'Layer: ' + layer_id + '; units: ' + layer['units'] + '; transform: ' + layer['transform'],
        'Provenance: ' + layer['provenance'] + '; algorithm layer relationships (not attribution): ' + _json(layer['algorithm_layers']),
        'Mask source: ' + layer['mask_source'] + '; required samples: ' + str(len(result.dataset['observation_ids'])) +
        '; layer samples: ' + str(len(layer['observation_ids'])) + '; jointly observed finite: ' + str(pair['joint_observed_count']),
        'Scatter uses jointly observed finite pairs only. Profiles: blue query / purple candidate when no metadata color; '
        'hollow orange points are finite originally unobserved/imputed and excluded from observed-only summaries.',
        'Pool policy: ' + result.settings.pool_policy + '; analysis depths: ' + _json(result.settings.depths) +
        '; inspection depth: ' + ('not selected (pair description, not top-list evidence)' if depth is None else str(depth)),
        'Display options: ' + _json(options) + '; missing metadata: gray. Metadata ordering without color retains dataset order.',
    ]
    for role, feature in (('query', q), ('candidate', c)):
        captions.append(role + ' coverage: ' + _json(feature_coverage(layer, feature['namespace'], feature['feature_id'], result.dataset['observation_ids'])))
        captions.append(role + ' observed finite: ' + str(len(pair[role + '_indices'])) + '; finite originally unobserved: ' + str(len(pair[role + '_unobserved_indices'])))
        for name in ('label', 'annotations'):
            if name in feature:
                captions.append(role + ' ' + name + ': ' + feature[name])
        if options['group'] is not None:
            captions.append(role + ' marginal group summary (separate observed-finite cohort): ' + _json(group_summary(
                layer, result.dataset, result.sample_metadata, feature['namespace'], feature['feature_id'], options['group'],
                include_fraction=options['include_fraction'])))
    captions.extend(['Joint-centered covariance diagnostic (sample covariance n-1): ' + _json(diagnostic), INTERPRETATION])
    if snapshot is not None:
        captions.append('Explicit saved session/decision context: ' + _json(snapshot))
    captions.append('User notes: ' + notes)
    return layer, pair, q, c, metadata, options, captions


def _render(path, fmt, result, context):
    # No pyplot/backend selection or scientific imports on package/help paths.
    try:
        import matplotlib as mpl
        from matplotlib.figure import Figure
        from matplotlib.text import Text
    except ImportError as exc:
        fail('figure.renderer', 'Matplotlib is required only for actual SVG/PDF export: ' + str(exc),
             remediation='Use an environment with Matplotlib available; comparison and browser export remain lightweight.')
    layer, pair, q, c, metadata, options, captions = context
    required = list(result.dataset['observation_ids'])
    records = {r['observation_id']: r['values'] for r in metadata['records']} if metadata else {}
    field = options['color']
    values = {sid: records.get(sid, {}).get(field) for sid in required}
    known = [v for v in values.values() if v is not None]
    kind = metadata['fields'][field] if field is not None else None
    categories = sorted(set(known)) if kind == 'categorical' else []
    palette = {v: colorsys.hls_to_rgb((i * 137.508 % 360) / 360, .38, .65) for i, v in enumerate(categories)}
    def point_color(sid, fallback):
        value = values[sid]
        if field is None:
            return fallback
        if value is None:
            return '#77818b'
        if kind == 'categorical':
            return palette[value]
        lo, hi = min(known), max(known)
        fraction = .5 if hi == lo else (value / 2 - lo / 2) / (hi / 2 - lo / 2)
        return colorsys.hls_to_rgb((245 - 230 * fraction) / 360, .4, .7)
    display = required[:]
    if options['order'] == 'id':
        display.sort()
    elif options['order'] == 'metadata' and field is not None:
        display.sort(key=lambda sid: (values[sid] is None, values[sid] if values[sid] is not None else (0 if kind == 'continuous' else ''), sid))
    if field is not None:
        captions.append('Metadata color key: ' + field + '; ' + (
            _json({v: palette[v] for v in categories}) + ' (RGB)' if kind == 'categorical' else
            ('no known values' if not known else f'{min(known)} (blue) to {max(known)} (red); constant field uses midpoint')))
    captions.append('Displayed observation IDs in order: ' + _json(display))
    caption = _literal('\n'.join(captions))
    lines = [line for paragraph in captions for part in (paragraph.splitlines() or [''])
             for line in (textwrap.wrap(part, width=125, replace_whitespace=False) or [''])]
    height = 6.5 + len(lines) * .12
    with mpl.rc_context({'text.usetex': False, 'text.parse_math': False, 'svg.fonttype': 'none',
                         'pdf.fonttype': 42, 'font.family': 'DejaVu Sans', 'axes.formatter.use_mathtext': False}):
        fig = Figure(figsize=(12, height))
        scatter = fig.add_axes((.09, 1 - 2.7 / height, .85, 2.1 / height))
        profile = fig.add_axes((.09, 1 - 5.6 / height, .85, 2.1 / height))
        joint = pair['joint_indices']
        scatter.scatter([c['values'][i] for i in joint], [q['values'][i] for i in joint],
                        c=[point_color(layer['observation_ids'][i], '#176d9b') for i in joint])
        scatter.set(xlabel=c['feature_id'] + ' (' + layer['units'] + ')',
                    ylabel=q['feature_id'] + ' (' + layer['units'] + ')', title='Jointly observed finite scatter')
        if not joint:
            scatter.text(.5, .5, 'No jointly observed finite values', transform=scatter.transAxes, ha='center')
        positions = {sid: i for i, sid in enumerate(display)}
        for role, feature, fallback in (('query', q, '#176d9b'), ('candidate', c, '#a34277')):
            for imputed in (False, True):
                indices = pair[role + ('_unobserved_indices' if imputed else '_indices')]
                profile.scatter([positions[layer['observation_ids'][i]] for i in indices],
                                [feature['values'][i] for i in indices], marker='o' if role == 'query' else 's',
                                facecolors='none' if imputed else [point_color(layer['observation_ids'][i], fallback) for i in indices],
                                edgecolors='#bc6015' if imputed else 'none',
                                label=role + (' originally unobserved/imputed' if imputed else ' observed finite'))
        profile.set(xlabel='Observation position (exact order in caption)', ylabel=layer['units'], title='Sample profiles; shared value scale')
        profile.legend(fontsize=7, ncols=2)
        fig.text(.04, 1 - 6.2 / height, '\n'.join(lines), va='top', fontsize=7, linespacing=1.2)
        for artist in fig.findobj(Text):
            artist.set_usetex(False)
            artist.set_parse_math(False)
            _literal(artist.get_text())
        try:
            fig.savefig(path, format=fmt, metadata={'Title': 'VaLPAS descriptive query figure',
                        **({'Description': caption} if fmt == 'svg' else {'Subject': caption})})
        finally:
            fig.clear()
    if fmt == 'svg':
        # Keep exact, unwrapped caption accessible independently of glyph layout.
        tree = ET.parse(path)
        root = tree.getroot()
        description = ET.Element('{http://www.w3.org/2000/svg}desc', {'id': 'valpas-caption'})
        description.text = caption
        root.insert(0, description)
        # XML parsers normalize raw CR; a character reference preserves it.
        serialized = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        Path(path).write_bytes(serialized.replace(b'\r', b'&#13;'))


def export_query_figure(result_or_bundle, *, query_id, candidate_id, layer_id, output,
                        color=None, group=None, order=None, h=None, omission=None,
                        include_fraction=None, depth=None, notes=None, session=None,
                        decision_id=None, report_settings=None):
    """Write a new SVG/PDF from an existing result or completed local result bundle.

    Explicit IDs are never used as filenames. Full normalized profiles are used,
    not bounded HTML data. Optional sessions/decision snapshots are strictly bound
    to the result and report scope; conflicting display overrides are rejected.
    Returns the absolute output Path. No output is published on render failure.
    """
    from .engine import ComparisonResult
    from .report import load_comparison_bundle
    result = result_or_bundle if isinstance(result_or_bundle, ComparisonResult) else load_comparison_bundle(result_or_bundle)
    path = _destination(output, result)
    context = _context(result, query_id, candidate_id, layer_id, color=color, group=group,
                       order=order, h=h, omission=omission, include_fraction=include_fraction,
                       depth=depth, notes=notes, session=session, decision_id=decision_id,
                       report_settings=report_settings)
    _literal('\n'.join(context[-1]))
    descriptor, staging = tempfile.mkstemp(prefix='.valpas-figure-', suffix=path.suffix, dir=path.parent)
    os.close(descriptor)
    try:
        _render(staging, path.suffix.lower()[1:], result, context)
        with open(staging, 'rb') as handle:
            os.fsync(handle.fileno())
        # Atomic no-clobber publication: unlike replace(), link() cannot overwrite
        # a destination created concurrently. Staging is on the same filesystem.
        os.link(staging, path)
    finally:
        Path(staging).unlink(missing_ok=True)
    return path
