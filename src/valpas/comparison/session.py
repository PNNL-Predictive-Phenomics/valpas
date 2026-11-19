"""Portable user-authored views and decisions, never scientific/model labels.

Integrity hashes detect accidental edits, not malicious authorship forgery. Restore
is atomic replacement, not merge. Scope changes require explicit rebind_scope().
"""
from dataclasses import dataclass
from datetime import datetime
import csv
import hashlib
import io
from pathlib import Path
import re

from .models import fail, freeze, thaw, keys, ids, integer, text
from .engine import canonical_json, normalized_descriptor

VIEW_KEYS = ('depth', 'query', 'candidate', 'pair', 'search', 'candidateSearch',
             'hidden', 'pins', 'referenceEndpoint', 'evidenceFilter', 'selectedLayer',
             'layers', 'queryOrder', 'candidateOrder')
LAYER_KEYS = ('layer_id', 'color', 'group', 'order', 'include_fraction', 'h', 'omission')
SCOPE_KEYS = ('query_ids', 'candidates', 'max_depth', 'report_pins', 'omit_metadata',
              'output_ids', 'layer_ids', 'metadata_fields', 'reference_endpoint_ids')
DECISION_KEYS = ('decision_id', 'comparison_id', 'query_id', 'candidate_id', 'pool_policy',
                 'depth', 'inspected_output_ids', 'decision', 'rationale', 'timestamp', 'view')
DOCUMENT_KEYS = ('schema_version', 'kind', 'comparison_id', 'content_id', 'pool_policy',
                 'scope', 'view', 'notes', 'decisions', 'integrity_sha256')


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def session_content_id(result):
    """Scope-independent binding including descriptive data omitted by science ID."""
    return _digest({'policy': 1, 'comparison_id': result.comparison_id,
                    'dataset': thaw(result.dataset),
                    'outputs': [normalized_descriptor(o) for o in sorted(result.outputs, key=lambda o: o.output_id)],
                    'profiles': result.profiles.to_dict() if result.profiles else None,
                    'sample_metadata': result.sample_metadata.to_dict() if result.sample_metadata else None,
                    'reference_provenance_hash': result.reference_provenance_hash})


def report_scope(payload):
    """Explicit embedded capabilities; byte budget is not a semantic scope."""
    return {'query_ids': payload['query_ids'],
            'candidates': [{'query_id': q, 'candidate_ids': payload['details'][q]['candidate_ids']}
                           for q in payload['query_ids']],
            'max_depth': payload['report_settings']['max_interactive_depth'],
            'report_pins': payload['report_settings']['pinned_candidate_ids'],
            'omit_metadata': payload['report_settings']['omit_metadata'],
            'output_ids': [o['output_id'] for o in payload['summaries']['outputs']],
            'layer_ids': [l['layer_id'] for l in payload['layers']],
            'metadata_fields': (payload.get('sample_metadata') or {}).get('fields', {}),
            'reference_endpoint_ids': [e['endpoint_id'] for e in (payload.get('references') or {}).get('endpoints', [])]}


def default_view(scope):
    return {'depth': min(10, scope['max_depth']), 'query': None, 'candidate': None,
            'pair': None, 'search': '', 'candidateSearch': '', 'hidden': [],
            'pins': list(scope['report_pins']),
            'referenceEndpoint': next(iter(scope['reference_endpoint_ids']), None),
            'evidenceFilter': 'all', 'selectedLayer': None,
            'layers': [{'layer_id': lid, 'color': None, 'group': None, 'order': 'dataset',
                        'include_fraction': True, 'h': 5, 'omission': False} for lid in scope['layer_ids']],
            'queryOrder': 'id_asc', 'candidateOrder': 'id_asc'}


def _string(value, field, nonblank=False):
    if not isinstance(value, str) or (nonblank and not value.strip()):
        fail(field, 'expected text' + (' with a meaningful rationale' if nonblank else ''))


def _member(value, choices, field, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or value not in choices:
        fail(field, 'unknown or outside embedded scope; re-export or explicitly rebind scope')


def _list(value, field):
    if not isinstance(value, (list, tuple)):
        fail(field, 'expected an explicit list')


def _subset(value, choices, field):
    ids(value, field, allow_empty=True)
    if not set(value) <= set(choices):
        fail(field, 'unknown or outside embedded scope')


def _boolean(value, field):
    if type(value) is not bool:
        fail(field, 'expected boolean')


def _portable_integer(value, field):
    integer(value, field, minimum=1)
    if value > 9007199254740991:
        fail(field, 'exceeds exact browser integer range')


def _scope(scope):
    keys(scope, SCOPE_KEYS, field='session.scope')
    for name in ('query_ids', 'report_pins', 'output_ids', 'layer_ids', 'reference_endpoint_ids'):
        ids(scope[name], 'session.scope.' + name, allow_empty=name not in ('query_ids', 'output_ids'))
    _portable_integer(scope['max_depth'], 'session.scope.max_depth')
    _boolean(scope['omit_metadata'], 'session.scope.omit_metadata')
    _list(scope['candidates'], 'session.scope.candidates')
    seen = []
    for row in scope['candidates']:
        keys(row, ('query_id', 'candidate_ids'), field='session.scope.candidates')
        seen.append(row['query_id'])
        ids(row['candidate_ids'], 'session.scope.candidate_ids', allow_empty=True)
    if seen != list(scope['query_ids']):
        fail('session.scope.candidates', 'expected one candidate scope for each query in order')
    _subset(scope['report_pins'], set().union(*(set(r['candidate_ids']) for r in scope['candidates'])), 'session.scope.report_pins')
    if not isinstance(scope['metadata_fields'], dict):
        fail('session.scope.metadata_fields', 'expected a metadata field map')
    for field, kind in scope['metadata_fields'].items():
        text(field, 'session.scope.metadata_fields')
        _member(kind, ('categorical', 'continuous'), 'session.scope.metadata_fields')
    if scope['omit_metadata'] and (scope['layer_ids'] or scope['metadata_fields'] or scope['reference_endpoint_ids']):
        fail('session.scope', 'omitted metadata cannot be restored')


def validate_view(view, scope):
    keys(view, VIEW_KEYS, field='session.view')
    _portable_integer(view['depth'], 'session.view.depth')
    if view['depth'] > scope['max_depth']:
        fail('session.view.depth', 'outside embedded scope')
    _member(view['query'], scope['query_ids'], 'session.view.query', nullable=True)
    candidates = {r['query_id']: r['candidate_ids'] for r in scope['candidates']}
    _member(view['candidate'], candidates.get(view['query'], ()), 'session.view.candidate', nullable=True)
    if view['pair'] is not None:
        _subset(view['pair'], scope['output_ids'], 'session.view.pair')
        if len(view['pair']) != 2:
            fail('session.view.pair', 'expected two distinct outputs')
    for name in ('search', 'candidateSearch'):
        _string(view[name], 'session.view.' + name)
    _subset(view['hidden'], scope['output_ids'], 'session.view.hidden')
    _subset(view['pins'], set().union(*(set(v) for v in candidates.values())), 'session.view.pins')
    _member(view['referenceEndpoint'], scope['reference_endpoint_ids'], 'session.view.referenceEndpoint', nullable=not scope['reference_endpoint_ids'])
    _member(view['evidenceFilter'], ('all', 'supported', 'unsupported'), 'session.view.evidenceFilter')
    if not scope['reference_endpoint_ids'] and view['evidenceFilter'] != 'all':
        fail('session.view.evidenceFilter', 'references unavailable')
    _member(view['selectedLayer'], scope['layer_ids'], 'session.view.selectedLayer', nullable=True)
    for name in ('queryOrder', 'candidateOrder'):
        _member(view[name], ('id_asc', 'id_desc'), 'session.view.' + name)
    _list(view['layers'], 'session.view.layers')
    seen = []
    for layer in view['layers']:
        keys(layer, LAYER_KEYS, field='session.view.layers')
        seen.append(layer['layer_id'])
        _member(layer['color'], scope['metadata_fields'], 'session.view.color', nullable=True)
        _member(layer['group'], [f for f, k in scope['metadata_fields'].items() if k == 'categorical'], 'session.view.group', nullable=True)
        _member(layer['order'], ('dataset', 'id', 'metadata'), 'session.view.order')
        _portable_integer(layer['h'], 'session.view.h')
        for name in ('include_fraction', 'omission'):
            _boolean(layer[name], 'session.view.' + name)
    if seen != list(scope['layer_ids']):
        fail('session.view.layers', 'expected exactly all layer settings in scope order')


def _validate_document(doc, kind):
    keys(doc, DOCUMENT_KEYS, field=kind)
    if type(doc['schema_version']) is not int or doc['schema_version'] != 1 or doc['kind'] != kind:
        fail(kind, 'unsupported schema/kind; no migration is performed')
    text(doc['comparison_id'], kind + '.comparison_id')
    for name in ('content_id', 'integrity_sha256'):
        if not isinstance(doc[name], str) or not re.fullmatch('[0-9a-f]{64}', doc[name]):
            fail(kind + '.' + name, 'expected SHA-256 hex digest')
    _member(doc['pool_policy'], ('strict', 'common', 'native_inspection'), kind + '.pool_policy')
    _scope(doc['scope'])
    validate_view(doc['view'], doc['scope'])
    _string(doc['notes'], kind + '.notes')
    _list(doc['decisions'], kind + '.decisions')
    seen = set()
    for decision in doc['decisions']:
        keys(decision, DECISION_KEYS, field=kind + '.decisions')
        did = text(decision['decision_id'], kind + '.decision_id')
        if did in seen:
            fail(kind + '.decisions', 'duplicate decision_id; imports replace, never merge')
        seen.add(did)
        validate_view(decision['view'], doc['scope'])
        view = decision['view']
        if (decision['comparison_id'] != doc['comparison_id'] or decision['pool_policy'] != doc['pool_policy'] or
                decision['query_id'] != view['query'] or decision['depth'] != view['depth']):
            fail(kind + '.decisions', 'decision binding/context mismatch')
        _member(decision['query_id'], doc['scope']['query_ids'], kind + '.query_id')
        _member(decision['decision'], ('investigate', 'retain_alternative', 'abstain'), kind + '.decision')
        if decision['decision'] == 'abstain':
            if decision['candidate_id'] is not None or view['candidate'] is not None:
                fail(kind + '.candidate_id', 'abstain is query-level and requires null candidate')
        elif decision['candidate_id'] is None or decision['candidate_id'] != view['candidate']:
            fail(kind + '.candidate_id', 'candidate decision requires selected embedded candidate')
        _portable_integer(decision['depth'], kind + '.depth')
        ids(decision['inspected_output_ids'], kind + '.inspected_output_ids')
        if list(decision['inspected_output_ids']) != [o for o in doc['scope']['output_ids'] if o not in view['hidden']]:
            fail(kind + '.inspected_output_ids', 'must equal visible inspected outputs in scope order')
        _string(decision['rationale'], kind + '.rationale', nonblank=True)
        stamp = decision['timestamp']
        if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', stamp):
            fail(kind + '.timestamp', 'expected per-decision UTC RFC3339 timestamp with seconds and Z')
        try:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.year < 1970:
                raise ValueError('before Unix epoch')
        except ValueError:
            fail(kind + '.timestamp', 'invalid calendar timestamp or before 1970')
    expected = _digest({k: v for k, v in doc.items() if k != 'integrity_sha256'})
    if expected != doc['integrity_sha256']:
        fail(kind + '.integrity_sha256', 'content checksum mismatch')


def _seal(doc):
    doc = thaw(doc)
    doc.pop('integrity_sha256', None)
    doc['integrity_sha256'] = _digest(doc)
    return doc


@dataclass(frozen=True)
class Session:
    """Immutable schema-v1 document. Use create/from_dict; direct input is validated."""
    document: object

    def __post_init__(self):
        doc = thaw(self.document)
        _validate_document(doc, self.kind)
        object.__setattr__(self, 'document', freeze(doc))

    @property
    def kind(self):
        return 'valpas-session'

    @classmethod
    def from_dict(cls, value):
        return cls(value)

    @classmethod
    def create(cls, result, settings=None, *, view=None, notes='', decisions=()):
        from .browser import build_report_payload
        payload = build_report_payload(result, settings, include_session=False)
        scope = report_scope(payload)
        doc = {'schema_version': 1, 'kind': 'valpas-shortlist' if cls is Shortlist else 'valpas-session',
               'comparison_id': result.comparison_id, 'content_id': session_content_id(result),
               'pool_policy': result.settings.pool_policy, 'scope': scope,
               'view': default_view(scope) if view is None else thaw(view),
               'notes': notes, 'decisions': thaw(decisions)}
        return cls(_seal(doc))

    def to_dict(self):
        return thaw(self.document)

    def to_json(self):
        from .browser import safe_json
        return safe_json(self.to_dict())

    def validate_payload(self, payload, *, allow_scope_change=False):
        doc = self.to_dict()
        if doc['comparison_id'] != payload['comparison_id']:
            fail(self.kind, 'comparison ID mismatch; no migration')
        if doc['content_id'] != payload['session_content_id'] or doc['pool_policy'] != payload['analysis_settings']['pool_policy']:
            fail(self.kind, 'content binding mismatch (profiles/metadata/reference provenance)')
        scope = report_scope(payload)
        if doc['scope'] != scope and not allow_scope_change:
            fail(self.kind + '.scope', 'report scope changed; use explicit rebind_scope, never silent restore')
        if allow_scope_change:
            doc['scope'] = scope
            type(self)(_seal(doc))  # validate every view/decision; no loss or defaults
        return self

    def validate(self, result, settings=None):
        from .browser import build_report_payload
        return self.validate_payload(build_report_payload(result, settings, include_session=False))

    def rebind_scope(self, result, settings=None):
        """Explicit scope change; every selected ID/setting/decision must still fit."""
        from .browser import build_report_payload
        payload = build_report_payload(result, settings, include_session=False)
        self.validate_payload(payload, allow_scope_change=True)
        return type(self)(_seal(self.to_dict() | {'scope': report_scope(payload)}))

    def with_view(self, view, *, notes=None):
        doc = self.to_dict() | {'view': thaw(view)}
        if notes is not None:
            doc['notes'] = notes
        return type(self)(_seal(doc))

    def add_decision(self, *, decision_id, decision, rationale, timestamp, view=None):
        """Append an explicit user action. No timestamp or rationale is fabricated."""
        doc = self.to_dict()
        view = thaw(view) if view is not None else doc['view'].copy()
        if decision == 'abstain':
            view['candidate'] = None
        row = {'decision_id': decision_id, 'comparison_id': doc['comparison_id'],
               'query_id': view['query'], 'candidate_id': view['candidate'],
               'pool_policy': doc['pool_policy'], 'depth': view['depth'],
               'inspected_output_ids': [o for o in doc['scope']['output_ids'] if o not in view['hidden']],
               'decision': decision, 'rationale': rationale, 'timestamp': timestamp, 'view': view}
        doc['decisions'].append(row)
        return type(self)(_seal(doc))

    def shortlist(self):
        return Shortlist(_seal(self.to_dict() | {'kind': 'valpas-shortlist'}))

    def write(self, path):
        """Explicit exclusive file creation; never silently overwrites a source."""
        with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(self.to_json())
        return Path(path)


@dataclass(frozen=True)
class Shortlist(Session):
    """Portable user decisions plus full view snapshots, including abstentions."""
    @property
    def kind(self):
        return 'valpas-shortlist'

    def to_csv(self):
        """Human spreadsheet export; JSON, not CSV, is canonical/importable."""
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        columns = list(DECISION_KEYS)
        writer.writerow(columns)
        for row in self.document['decisions']:
            writer.writerow([_csv_cell(thaw(row[k])) for k in columns])
        return buffer.getvalue()


def _csv_cell(value):
    value = value if isinstance(value, str) else canonical_json(value)
    # Prefix every cell: preserves leading zero display and blocks whitespace/
    # control-prefixed formulas as well as = + - @. JSON retains exact raw IDs.
    return "'" + value


def _load(value, cls, result, settings):
    from .adapters import _json
    if isinstance(value, (str, Path)):
        value = _json(Path(value).read_text(encoding='utf-8'), cls.__name__)
    obj = cls.from_dict(value)
    return obj.validate(result, settings) if result is not None else obj


def load_session(value, *, result=None, settings=None):
    """Read a local JSON path or document; bind authoritatively when result supplied."""
    return _load(value, Session, result, settings)


def load_shortlist(value, *, result=None, settings=None):
    return _load(value, Shortlist, result, settings)
