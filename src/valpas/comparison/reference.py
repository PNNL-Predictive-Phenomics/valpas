"""Local, source-separated reference descriptions; never nomination eligibility.

An endpoint is one source/version/evidence-type/support-class combination. Missing
pairs are not biological negatives. Retrieval uses the engine's unchanged active
orders and certification. Reference and group documents have independent v1 schemas.
"""
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path

from .models import fail, freeze, thaw, keys, text, ids, validate_identity, json_value

STRATA = (("0", 0, 0), ("1", 1, 1), ("2-5", 2, 5), ("6+", 6, None))
METRICS = ("hit", "reference_supported_fraction", "recovery", "reachability_fraction")


def _list(value, field):
    if not isinstance(value, (list, tuple)):
        fail(field, "expected an explicit record list")


def _version(value, field):
    if type(value) is not int or value != 1:
        fail(field, "unsupported schema version")


def _binding(bound, dataset, field):
    # Reference annotation does not require known observations, but every supplied
    # dataset field must match, including nulls. Reordering observations is harmless.
    for name in dataset:
        left, right = thaw(bound[name]), thaw(dataset[name])
        if name == "observation_ids" and left is not None and right is not None:
            left, right = sorted(left), sorted(right)
        if left != right:
            fail(field + ".dataset." + name, "reference/group binding must explicitly match the comparison dataset")


@dataclass(frozen=True)
class QueryGroups:
    """Explicit one-feature-to-one-group mapping; unmapped queries are excluded.

    Repeated rows, including identical membership, are rejected rather than taking
    the best peak or assigning a feature to multiple biological groups.
    """
    dataset: Mapping
    records: tuple
    source_fingerprints: tuple = ()

    def __post_init__(self):
        validate_identity(self.dataset, "query_groups.dataset")
        _list(self.records, "query_groups.records")
        seen = set()
        for row in self.records:
            keys(row, ("query_id", "group_id"), field="query_groups.record")
            for key in row:
                text(row[key], "query_groups." + key)
            if row["query_id"] in seen:
                fail("query_groups.query_id", "duplicate or ambiguous feature membership")
            seen.add(row["query_id"])
        _list(self.source_fingerprints, "query_groups.source_fingerprints")
        json_value(self.source_fingerprints, "query_groups.source_fingerprints")
        for name in ("dataset", "records", "source_fingerprints"):
            object.__setattr__(self, name, freeze(getattr(self, name)))

    @classmethod
    def from_dict(cls, value):
        keys(value, ("schema_version", "dataset", "records"), field="query_groups")
        _version(value["schema_version"], "query_groups.schema_version")
        return cls(value["dataset"], value["records"])

    def to_dict(self):
        return {"schema_version": 1, "dataset": thaw(self.dataset),
                "records": sorted(thaw(self.records), key=lambda r: r["query_id"])}

    def validate_binding(self, dataset, outputs):
        _binding(self.dataset, dataset, "query_groups")
        queries = {q for o in outputs for q in o.query_ids}
        if any(r["query_id"] not in queries for r in self.records):
            fail("query_groups.query_id", "unknown comparison query ID")


@dataclass(frozen=True)
class ReferenceData:
    """Evidence, explicit assessed cohorts and candidate universes per endpoint.

    Endpoint fields: endpoint_id, source, version, evidence_type (pathway/reaction),
    support_class (co_membership/direct/inferred/unspecified), assessed_query_ids,
    candidate_universe, optional description. Evidence fields: endpoint_id, query_id,
    candidate_id, evidence_id, optional description. Exact duplicate evidence rows
    normalize once; distinct evidence identifiers/descriptions remain inspectable.
    """
    dataset: Mapping
    endpoints: tuple
    evidence: tuple
    weighting: str = "feature"
    source_fingerprints: tuple = ()

    def __post_init__(self):
        validate_identity(self.dataset, "references.dataset")
        _list(self.endpoints, "references.endpoints")
        _list(self.evidence, "references.evidence")
        if not self.endpoints:
            fail("references.endpoints", "declare at least one independent endpoint (evidence may be empty)")
        if self.weighting not in ("feature", "group"):
            fail("references.weighting", "expected feature or group")
        endpoints, signatures = {}, set()
        for e in self.endpoints:
            keys(e, ("endpoint_id", "source", "version", "evidence_type", "support_class",
                     "assessed_query_ids", "candidate_universe"), ("description",), "references.endpoint")
            for name in ("endpoint_id", "source", "version", "evidence_type", "support_class"):
                text(e[name], "references.endpoint." + name)
            if e["evidence_type"] not in ("pathway", "reaction"):
                fail("references.evidence_type", "expected pathway or reaction; endpoints cannot be silently unioned")
            allowed = ("co_membership",) if e["evidence_type"] == "pathway" else ("direct", "inferred", "unspecified")
            if e["support_class"] not in allowed:
                fail("references.support_class", "evidence class contradicts endpoint type")
            signature = tuple(e[k] for k in ("source", "version", "evidence_type", "support_class"))
            if e["endpoint_id"] in endpoints or signature in signatures:
                fail("references.endpoints", "duplicate endpoint ID or source/version/type/class endpoint")
            signatures.add(signature)
            ids(e["assessed_query_ids"], "references.assessed_query_ids", allow_empty=True)
            ids(e["candidate_universe"], "references.candidate_universe", allow_empty=True)
            if "description" in e:
                text(e["description"], "references.description")
            endpoints[e["endpoint_id"]] = e
        unique = {}
        from .engine import canonical_json
        for row in self.evidence:
            keys(row, ("endpoint_id", "query_id", "candidate_id", "evidence_id"),
                 ("description",), "references.evidence")
            for key in row:
                text(row[key], "references.evidence." + key)
            e = endpoints.get(row["endpoint_id"])
            if e is None:
                fail("references.evidence.endpoint_id", "unknown endpoint")
            if row["query_id"] not in e["assessed_query_ids"]:
                fail("references.evidence.query_id", "evidence query not declared assessed")
            if row["candidate_id"] not in e["candidate_universe"]:
                fail("references.evidence.candidate_id", "evidence outside explicit reference universe")
            unique[canonical_json(row)] = row
        _list(self.source_fingerprints, "references.source_fingerprints")
        json_value(self.source_fingerprints, "references.source_fingerprints")
        object.__setattr__(self, "evidence", freeze([unique[k] for k in sorted(unique)]))
        for name in ("dataset", "endpoints", "source_fingerprints"):
            object.__setattr__(self, name, freeze(getattr(self, name)))

    @classmethod
    def from_dict(cls, value):
        keys(value, ("schema_version", "dataset", "endpoints", "evidence"), ("weighting",), "references")
        _version(value["schema_version"], "references.schema_version")
        return cls(value["dataset"], value["endpoints"], value["evidence"], value.get("weighting", "feature"))

    def to_dict(self):
        endpoints = sorted(thaw(self.endpoints), key=lambda e: e["endpoint_id"])
        for e in endpoints:
            for name in ("assessed_query_ids", "candidate_universe"):
                e[name].sort()
        return {"schema_version": 1, "dataset": thaw(self.dataset), "endpoints": endpoints,
                "evidence": thaw(self.evidence), "weighting": self.weighting}

    def validate_binding(self, dataset, outputs):
        _binding(self.dataset, dataset, "references")
        queries = {q for o in outputs for q in o.query_ids}
        for e in self.endpoints:
            if not set(e["assessed_query_ids"]) <= queries:
                fail("references.assessed_query_ids", "unknown comparison query ID")


def _load(value, base_dir, cls, role):
    from .adapters import _local_path, _read_fingerprinted, _json
    if isinstance(value, Mapping) and "path" in value:
        keys(value, ("path",), field=role)
        path = _local_path(value["path"], Path(base_dir), role + ".path")
        if path.suffix.lower() != ".json":
            fail(role + ".path", "only local JSON reference/group documents supported")
        raw, fingerprint = _read_fingerprinted(path, role)
        return replace(cls.from_dict(_json(raw, role)), source_fingerprints=(fingerprint,))
    return cls.from_dict(value)


def load_reference_data(value, *, base_dir="."):
    """Load inline schema-1 evidence or contained local {path: ...} JSON."""
    return _load(value, base_dir, ReferenceData, "references")


def load_query_groups(value, *, base_dir="."):
    """Load inline schema-1 one-feature-one-group records or local JSON."""
    return _load(value, base_dir, QueryGroups, "query_groups")


def validate_references(dataset, outputs, references, query_groups):
    for name, value, cls in (("references", references, ReferenceData), ("query_groups", query_groups, QueryGroups)):
        if value is not None:
            if not isinstance(value, cls):
                fail(name, "expected validated " + cls.__name__)
            value.validate_binding(dataset, outputs)
    if references is None and query_groups is not None:
        fail("query_groups", "query groups require reference evaluation")
    if references is not None and references.weighting == "group" and query_groups is None:
        fail("references.weighting", "group weighting requires explicit one-feature-one-group records")


def reference_provenance_hash(references, query_groups=None):
    """Deterministic normalized evidence/group/policy hash, independent of paths.

    Kept separate from the saved-score comparison ID. Includes descriptions and
    endpoint IDs, assessment coverage, universe, weighting and group membership.
    """
    if references is None:
        return None
    from .engine import canonical_json
    value = {"reference_policy": 1, "strata": STRATA, "references": references.to_dict(),
             "query_groups": query_groups.to_dict() if query_groups is not None else None}
    for doc in (value["references"], value["query_groups"]):
        if doc is not None and doc["dataset"]["observation_ids"] is not None:
            doc["dataset"]["observation_ids"].sort()
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _stratum(count):
    if count is None:
        return None
    return next(label for label, lo, hi in STRATA if count >= lo and (hi is None or count <= hi))


def iter_reference_recovery(result):
    """One row per declared query/output/endpoint/depth, including excluded queries.

    Strict cohort incompatibility disables retrieval comparisons, not the known
    support counts. In native inspection evaluation is explicitly descriptive.
    An unexhausted prefix can certify hit/fraction, but cannot establish the full
    reachable-support denominator; recovery/reachability remain null.
    """
    from .compatibility import _iter_pools
    from .engine import _top, _pool_size
    refs = result.references
    support = defaultdict(set)
    for r in refs.evidence:
        support[r["endpoint_id"], r["query_id"]].add(r["candidate_id"])
    all_queries = {q for o in result.outputs for q in o.query_ids}
    seen = set()

    def rows(q, pool):
        for e in sorted(refs.endpoints, key=lambda e: e["endpoint_id"]):
            assessed = q in e["assessed_query_ids"]
            known = support[e["endpoint_id"], q]
            for o in result.outputs:
                oid = o.output_id
                view = pool.native[oid] if pool is not None else None
                reachable = (len(known & set(pool.active_orders[oid]))
                             if assessed and view is not None and view.certified and view.exhausted else None)
                total = len(known) if assessed else None
                for depth in sorted(result.settings.depths):
                    top, why = _top(pool, oid, depth) if pool is not None else (None, "query_not_shared_by_all_outputs")
                    if pool is not None and result.settings.pool_policy != "native_inspection":
                        why = pool.reason or why
                    if not assessed:
                        why = "query_unassessed"
                    elif not why and not top:
                        why = "empty_scorable_pool"
                    available = why is None
                    row = {"endpoint_id": e["endpoint_id"], "query_id": q, "output_id": oid,
                           "pool_policy": result.settings.pool_policy, "requested_depth": depth,
                           "assessment_status": "assessed" if assessed else "unassessed",
                           "evaluation_scope": "descriptive_different_search_spaces" if result.settings.pool_policy == "native_inspection" else "controlled",
                           "total_known_support": total, "reachable_support": reachable,
                           "active_pool_size": _pool_size(o, pool, result.settings.pool_policy) if pool is not None else None,
                           "nomination_list_size": len(top) if top is not None else None,
                           "nominations_in_reference_universe": len(set(top) & set(e["candidate_universe"])) if top is not None else None,
                           "supported_nominations": len(known & set(top)) if available else None,
                           "hit": None, "reference_supported_fraction": None, "recovery": None,
                           "reachability_fraction": reachable / total if reachable is not None and total else None,
                           "opportunity_stratum": _stratum(reachable), "status": "available", "reason": why,
                           "metric_reasons": {}}
                    if available:
                        n = row["supported_nominations"]
                        row.update(hit=int(n > 0), reference_supported_fraction=n / len(top),
                                   recovery=n / reachable if reachable else None)
                    if not assessed:
                        row["status"] = "unassessed"
                    elif why:
                        row["status"] = "limited_depth" if why == "insufficient_certified_depth" else "unavailable"
                    elif total == 0:
                        row.update(status="assessed_zero", reason="no_known_support")
                    elif reachable == 0:
                        row.update(status="unreachable", reason="no_reachable_support")
                    elif reachable is None:
                        row.update(status="limited_depth", reason="reachable_support_unknown_for_limited_input")
                    for metric in METRICS:
                        if row[metric] is None:
                            reason = why
                            if metric == "reachability_fraction":
                                reason = ("query_unassessed" if not assessed else "no_known_support" if not total
                                          else "reachable_support_unknown_for_limited_input" if reachable is None else None)
                            elif metric == "recovery" and not reason:
                                reason = "reachable_support_unknown_for_limited_input" if reachable is None else "no_reachable_support"
                            row["metric_reasons"][metric] = reason
                    yield row

    for pool, _ in _iter_pools(result.outputs, result.settings, depth_independent=True):
        if pool is not None:
            seen.add(pool.query_id)
            yield from rows(pool.query_id, pool)
    for q in sorted(all_queries - seen):
        yield from rows(q, None)


def reference_summaries(result, rows=None):
    """Metric-specific denominators; equal features or equal within-group means.

    Each output remains separate (runs are not biological replication). All-assessed
    includes zero opportunity. Reachable cohort requires known support > 0. Missing
    membership is a named exclusion only for group weighting. Empty strata persist.
    """
    rows = list(iter_reference_recovery(result)) if rows is None else rows
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["endpoint_id"], row["output_id"], row["requested_depth"]].append(row)
    membership = {r["query_id"]: r["group_id"] for r in result.query_groups.records} if result.query_groups else {}
    weighting = result.references.weighting
    for (endpoint, output, depth), bucket in sorted(buckets.items()):
        for cohort in ("all_assessed", "reachable"):
            for stratum in ("all", *(s[0] for s in STRATA)):
                for metric in METRICS:
                    included, excluded, groups = [], {}, defaultdict(list)
                    eligible = 0
                    for row in bucket:
                        q = row["query_id"]
                        why = None
                        if row["assessment_status"] != "assessed":
                            why = "query_unassessed"
                        elif cohort == "reachable" and row["reachable_support"] is None:
                            why = "reachable_support_unknown"
                        elif cohort == "reachable" and row["reachable_support"] == 0:
                            why = "no_reachable_support"
                        elif stratum != "all" and row["opportunity_stratum"] != stratum:
                            why = "outside_opportunity_stratum"
                        if why is None:
                            eligible += 1
                            if row[metric] is None:
                                why = row["metric_reasons"].get(metric) or row["reason"] or "metric_unavailable"
                            elif weighting == "group" and q not in membership:
                                why = "missing_query_group"
                        if why:
                            excluded[q] = why
                        else:
                            included.append(row)
                            if q in membership:
                                groups[membership[q]].append(row)
                    group_rows = []
                    # Report every mapped group, including groups with zero evaluable features.
                    for group in sorted(set(membership.values())):
                        members = sorted(q for q, g in membership.items() if g == group)
                        values = groups[group]
                        group_rows.append({"group_id": group, "group_size": len(members),
                            "evaluable_features": len(values), "included_query_ids": sorted(r["query_id"] for r in values),
                            "excluded_features": {q: excluded[q] for q in members if q in excluded},
                            "mean": math.fsum(r[metric] for r in values) / len(values) if values else None})
                    values = ([g["mean"] for g in group_rows if g["mean"] is not None] if weighting == "group"
                              else [r[metric] for r in included])
                    yield {"endpoint_id": endpoint, "output_id": output, "pool_policy": result.settings.pool_policy,
                           "requested_depth": depth, "cohort": cohort, "opportunity_stratum": stratum,
                           "stratum_edges": [list(s) for s in STRATA], "metric": metric, "weighting": weighting,
                           "declared_queries": len(bucket), "assessed_queries": sum(r["assessment_status"] == "assessed" for r in bucket),
                           "eligible_queries": eligible, "evaluable_queries": len(included),
                           "excluded_queries": len(excluded), "included_query_ids": sorted(r["query_id"] for r in included),
                           "feature_exclusions": excluded, "exclusion_reasons": dict(Counter(excluded.values())),
                           "declared_groups": len(set(membership.values())),
                           "evaluable_groups": sum(g["mean"] is not None for g in group_rows),
                           "aggregation_denominator": len(values), "groups": group_rows,
                           "mean": math.fsum(values) / len(values) if values else None,
                           "status": "available" if values else "unavailable"}


REFERENCE_COLUMNS = {
    "reference_endpoints": "endpoint_id source version evidence_type support_class assessed_query_ids candidate_universe description".split(),
    "reference_evidence": "endpoint_id query_id candidate_id evidence_id description".split(),
    "reference_recovery": "endpoint_id query_id output_id pool_policy requested_depth assessment_status evaluation_scope total_known_support reachable_support active_pool_size nomination_list_size nominations_in_reference_universe supported_nominations hit reference_supported_fraction recovery reachability_fraction opportunity_stratum status reason metric_reasons".split(),
    "reference_summary": "endpoint_id output_id pool_policy requested_depth cohort opportunity_stratum stratum_edges metric weighting declared_queries assessed_queries eligible_queries evaluable_queries excluded_queries included_query_ids feature_exclusions exclusion_reasons declared_groups evaluable_groups aggregation_denominator groups mean status".split(),
    "query_groups": "query_id group_id".split(),
}


def reference_columns(references, query_groups):
    if not references:
        return {}
    return {name: cols for name, cols in REFERENCE_COLUMNS.items() if name != "query_groups" or query_groups is not None}


def iter_reference_table(result, name):
    if name == "reference_recovery":
        yield from iter_reference_recovery(result)
    elif name == "reference_summary":
        yield from reference_summaries(result)
    elif name == "query_groups":
        yield from result.query_groups.to_dict()["records"]
    else:
        records = result.references.to_dict()["endpoints" if name == "reference_endpoints" else "evidence"]
        for row in records:
            yield {key: row.get(key) for key in REFERENCE_COLUMNS[name]}
