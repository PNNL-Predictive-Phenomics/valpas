"""Saved-value comparison, query-bounded tables, and overview-first summaries."""
from dataclasses import dataclass, asdict
import hashlib
import json
from itertools import combinations
from collections import Counter

from valpas import __version__
from .models import (ComparisonManifest, ComparisonSettings, fail, freeze, thaw,
                     integer, validate_b1)
from .compatibility import validate_compatibility, _iter_pools
from .ranking import rank_output

POLICY_VERSIONS = {"schema": 1, "ranking": 1, "metrics": 1, "identity": 1}


def canonical_json(value):
    return json.dumps(thaw(value), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _identity(value):
    value = thaw(value)
    if value["observation_ids"] is not None:
        value["observation_ids"].sort()
    return value


def input_fingerprint(output):
    """Canonical values/statuses and scientific metadata; no transport paths."""
    d = thaw(output.descriptor)
    for name in ("data", "orientation", "provenance", "label"):
        d.pop(name, None)
    d["identity"] = _identity(d["identity"])
    for name in ("query_ids", "candidate_ids", "missing_queries"):
        if name in d:
            d[name].sort()
    if "eligibility" in d:
        d["eligibility"].sort(key=lambda r: (r["query_id"], r["candidate_id"]))
    digest = hashlib.sha256(canonical_json(d).encode("utf-8"))
    # One pair at a time; implicit status semantics participate too.
    for q in sorted(output.query_ids):
        for c in sorted(output.candidate_ids):
            v = output.pair(q, c)
            record = asdict(v)
            for name in ("score", "count"):
                if record[name] is not None:
                    record[name] = float(record[name])
            digest.update(b"\n" + canonical_json([q, c, record]).encode("utf-8"))
    return digest.hexdigest()


def normalized_descriptor(output):
    d = thaw(output.descriptor)
    d["data"] = {k: v for k, v in d["data"].items() if k in ("index_base", "symmetric")}
    d["data"].update(format="normalized", inline={"records": []})
    return d


def _classification(a, b):
    if a.descriptor["configuration_id"] == b.descriptor["configuration_id"]:
        return "same_configuration_different_run"
    if a.descriptor["method_id"] == b.descriptor["method_id"]:
        return "same_method_different_configuration"
    return "different_method"


def _top(pool, oid, depth):
    view, order = pool.native[oid], pool.active_orders[oid]
    if not view.certified:
        return None, "inspection_only_or_missing_query"
    if depth > len(order) and not view.exhausted:
        return None, "insufficient_certified_depth"
    return order[:depth], None


def _agreement(outputs, pool, settings, depth):
    tops = {o.output_id: _top(pool, o.output_id, depth) for o in outputs}
    native = settings.pool_policy == "native_inspection"
    # Controlled availability is cohort-wide, including depth certification.
    reason = None if native else pool.reason or next((r for _, r in tops.values() if r), None)
    for a, b in combinations(outputs, 2):
        left, lr = tops[a.output_id]
        right, rr = tops[b.output_id]
        why = reason or lr or rr
        row = {"query_id": pool.query_id, "left_output_id": a.output_id,
               "right_output_id": b.output_id, "pair_class": _classification(a, b),
               "pool_policy": settings.pool_policy, "requested_depth": depth,
               "effective_depth": None, "left_list_size": None if left is None else len(left),
               "right_list_size": None if right is None else len(right),
               "shared_count": None, "union_size": None, "overlap_fraction": None,
               "jaccard": None, "left_shared_fraction": None, "right_shared_fraction": None,
               "status": "unavailable", "reason": why}
        if not why and (not left or not right):
            row["reason"] = "empty_scorable_pool"
        elif not why:
            shared, union = len(set(left) & set(right)), len(set(left) | set(right))
            row.update(shared_count=shared, union_size=union, jaccard=shared / union,
                       left_shared_fraction=shared / len(left), right_shared_fraction=shared / len(right),
                       status="descriptive" if native else "available",
                       reason="different search spaces; descriptive only" if native else None)
            if not native:
                row.update(effective_depth=len(left), overlap_fraction=shared / len(left))
        yield row


def _recurrence_groups(result, pool, depth):
    tops = {o.output_id: _top(pool, o.output_id, depth) for o in result.outputs}
    cohort_reason = pool.reason or next((r for _, r in tops.values() if r), None)
    for config, members in result.compatibility.run_groups.items():
        known = [tops[oid][0] for oid in members if tops[oid][0] is not None and tops[oid][0]]
        reason = cohort_reason
        if len(members) < 2:
            status, reason = "not_assessed", "fewer_than_two_runs"
        elif reason or len(known) != len(members):
            status, reason = "unavailable", reason or "empty_scorable_pool"
        else:
            status = "available"
        counts = Counter(c for top in known for c in top)
        candidates = sorted(set().union(*(set(pool.active_orders[oid]) for oid in members)))
        yield {"configuration_id": config, "expected_runs": len(members),
               "evaluable_runs": len(known), "status": status, "reason": reason,
               "effective_depth": len(known[0]) if status == "available" else None}, counts, candidates


def _quantile(values, fraction):
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


@dataclass(frozen=True)
class ComparisonResult:
    """Normalized inputs plus compact summaries, never an expanded long table.

    iter_table streams complete rows; materialize_table refuses over-limit
    requests rather than silently returning a truncated scientific table.
    """
    outputs: tuple
    settings: ComparisonSettings
    dataset: object
    compatibility: object
    comparison_id: str
    input_fingerprints: object
    source_fingerprints: tuple
    protected_sources: tuple
    warnings: tuple
    summaries: object

    profiles: object = None
    report_settings: object = None
    sample_metadata: object = None
    diagnostic_requests: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "diagnostic_requests", validate_b1(
            self.dataset, self.outputs, self.profiles, self.sample_metadata, self.diagnostic_requests))

    @property
    def table_columns(self):
        from .profiles import PROFILE_COLUMNS
        return {**TABLE_COLUMNS, **(PROFILE_COLUMNS if self.profiles is not None else {}),
                **b1_columns(self.sample_metadata is not None, self.diagnostic_requests)}

    @property
    def table_names(self):
        return tuple(self.table_columns)

    def iter_table(self, name):
        if name not in self.table_columns:
            fail("table", "unknown table: " + str(name))
        if name == "sample_metadata":
            yield from self.sample_metadata.iter_table(self.dataset)
        elif name in ("diagnostics", "group_summaries"):
            yield from self._iter_diagnostics(name)
        elif name not in TABLE_COLUMNS:
            yield from self.profiles.iter_table(name, self.dataset, self.outputs)
        elif name in self.summaries:
            for row in self.summaries[name]:
                yield thaw(row)
        else:
            for table, row in self.iter_detail_tables({name}):
                yield row

    def _iter_diagnostics(self, name):
        from .diagnostics import covariance_diagnostic, group_summary
        from .profiles import feature_key
        layers = {layer["layer_id"]: layer for layer in self.profiles.layers}
        seen = set()
        for request in self.diagnostic_requests:
            layer = layers[request.layer_id]
            if name == "diagnostics":
                scope = {k: getattr(request, k) for k in
                         ("query_id", "candidate_id", "layer_id", "h", "omission")}
                yield {**scope, "result": covariance_diagnostic(layer, self.dataset,
                    request.query_id, request.candidate_id, h=request.h, omission=request.omission)}
            elif request.group_field is not None:
                for role, fid in (("query", request.query_id), ("candidate", request.candidate_id)):
                    ns = self.dataset[role + "_namespace"]
                    key = (request.layer_id, feature_key(ns, fid), request.group_field, request.include_fraction)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield {"layer_id": request.layer_id, "namespace": thaw(ns), "feature_id": fid,
                           "field": request.group_field, "include_fraction": request.include_fraction,
                           "result": group_summary(layer, self.dataset, self.sample_metadata, ns, fid,
                               request.group_field, include_fraction=request.include_fraction)}

    def materialize_table(self, name, *, max_rows=10000):
        integer(max_rows, "max_rows", minimum=1)
        rows = []
        for row in self.iter_table(name):
            if len(rows) >= max_rows:
                fail("max_rows", "table exceeds materialization limit", remediation="Use iter_table or streamed bundle export; increase the explicit limit only for a bounded workload.")
            rows.append(row)
        return rows

    def iter_detail_tables(self, selected=None):
        selected = set(TABLE_COLUMNS) if selected is None else selected
        policy = self.settings.pool_policy
        if policy == "common" and "candidate_ranks" in selected:
            shared = set.intersection(*(set(o.query_ids) for o in self.outputs))
            for o in self.outputs:
                for q in sorted(set(o.query_ids) - shared):
                    view = rank_output(o, q, exclude_self=self.settings.exclude_self)
                    for c in sorted(o.candidate_ids):
                        v = o.pair(q, c)
                        status, why = view.statuses[c]
                        yield "candidate_ranks", {"query_id": q, "candidate_id": c,
                            "output_id": o.output_id, "pool_policy": policy,
                            "native_rank": view.ranks.get(c), "active_rank": None,
                            "saved_rank": v.rank, "score": v.score, "count": v.count,
                            "status": status, "reason": why, "active_status": "excluded_query"}
        for pool, exclusions in _iter_pools(self.outputs, self.settings, depth_independent=True):
            if "exclusions" in selected:
                for e in exclusions:
                    yield "exclusions", {**asdict(e), "pool_policy": policy}
            if pool is None:
                continue
            q = pool.query_id
            for o in self.outputs:
                oid, view = o.output_id, pool.native[o.output_id]
                if "coverage" in selected:
                    yield "coverage", {"query_id": q, "output_id": oid, "pool_policy": policy,
                        **thaw(pool.coverage[oid]), "active_pool_size": _pool_size(o, pool, policy),
                        "controlled_available": pool.controlled_available, "reason": pool.reason}
                if "candidate_ranks" in selected:
                    # Limited representations export known records only. Axes and
                    # omission rules remain in normalized descriptors, not fake rows.
                    candidates = sorted(o.candidate_ids) if o.complete else sorted(c for qq, c in o.pairs if qq == q)
                    for c in candidates:
                        v = o.pair(q, c)
                        status, why = view.statuses[c]
                        active = pool.active_ranks[oid].get(c)
                        yield "candidate_ranks", {"query_id": q, "candidate_id": c, "output_id": oid,
                            "pool_policy": policy, "native_rank": view.ranks.get(c), "active_rank": active,
                            "saved_rank": v.rank, "score": v.score, "count": v.count,
                            "status": status, "reason": why, "active_status":
                            "ranked" if active is not None else "excluded_from_common" if policy == "common" and c in view.ranks else status if status != "scorable" else "rank_unavailable"}
            for depth in self.settings.depths:
                if "agreement" in selected:
                    for row in _agreement(self.outputs, pool, self.settings, depth):
                        yield "agreement", row
                if "run_recurrence" in selected:
                    for group, counts, candidates in _recurrence_groups(self, pool, depth):
                        for c in candidates or [None]:
                            yield "run_recurrence", {"query_id": q, "candidate_id": c,
                                "pool_policy": policy, "requested_depth": depth, **group,
                                "nominations": counts[c] if c is not None else None,
                                "recurrence_fraction": counts[c] / group["expected_runs"] if group["status"] == "available" and c is not None else None}


def _pool_size(output, pool, policy):
    if policy != "common" and output.descriptor["representation"] == "certified_prefix" and pool.query_id in output.query_ids:
        return output.descriptor["completeness"]["queries"][pool.query_id]["pool_size"]
    return len(pool.active_orders[output.output_id]) if pool.native[output.output_id].certified else None


def compare_results(inputs, settings=None, *, dataset=None, profiles=None,
                    sample_metadata=None, diagnostic_requests=()):
    """Compare >=2 saved outputs over all queries selected by the pool policy.

    A ComparisonManifest retains its dataset anchor and consumed manifest hash.
    Passing a sequence instead uses the first canonical output's identity unless
    an explicit dataset anchor is supplied. No target feature is required.
    Metadata and requested diagnostics are descriptive, excluded from identity
    and scientific tables. The default empty tuple inherits manifest requests;
    an explicit empty list clears them. No diagnostics are computed eagerly.
    """
    sources = ()
    report_settings = None
    if isinstance(inputs, ComparisonManifest):
        settings = settings or inputs.settings
        dataset = inputs.dataset if dataset is None else dataset
        sources = inputs.source_fingerprints
        profiles = inputs.profiles if profiles is None else profiles
        report_settings = inputs.report_settings
        sample_metadata = inputs.sample_metadata if sample_metadata is None else sample_metadata
        diagnostic_requests = inputs.diagnostic_requests if diagnostic_requests == () else diagnostic_requests
        inputs = inputs.outputs
    outputs = tuple(sorted(inputs, key=lambda o: o.output_id))
    if len(outputs) < 2:
        fail("outputs", "comparison requires at least two saved outputs", remediation="Supply two methods/configurations or two distinct runs of one configuration.")
    settings = settings or ComparisonSettings()
    if dataset is None:
        dataset = thaw(outputs[0].descriptor["identity"])
        for claim in settings.attestations:
            if claim["output_id"] == outputs[0].output_id and claim["field"] in dataset and dataset[claim["field"]] is None:
                dataset[claim["field"]] = thaw(claim["claimed_value"])
    report = validate_compatibility(outputs, settings, dataset=dataset)
    dataset = freeze(dataset)
    fingerprints = {o.output_id: input_fingerprint(o) for o in outputs}
    resolved = settings.to_dict()
    resolved["depths"].sort()
    resolved["attestations"].sort(key=lambda a: (a["output_id"], a["field"]))
    for a in resolved["attestations"]:
        if a["field"] == "observation_ids":
            a["claimed_value"].sort()
    identity = {"versions": POLICY_VERSIONS, "software_version": __version__,
                "dataset": _identity(dataset), "settings": resolved, "inputs": fingerprints}
    cid = "cmp-v1-" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    sources = tuple(sources) + tuple(freeze({**thaw(f), "output_id": o.output_id}) for o in outputs for f in o.source_fingerprints)
    if profiles is not None:
        from .profiles import ProfileData
        if not isinstance(profiles, ProfileData):
            fail("profiles", "expected validated ProfileData")
        profiles.validate_binding(dataset, outputs)
        sources += tuple(profiles.source_fingerprints)
    diagnostic_requests = validate_b1(dataset, outputs, profiles, sample_metadata, diagnostic_requests)
    if sample_metadata is not None:
        sources += tuple(sample_metadata.source_fingerprints)
    protected = tuple(sorted({f["path"] for f in sources} | {p for o in outputs for p in o.source_files}))
    # The dataset anchor duplicates output identity checks; do not add a
    # transport-dependent warning when an implicit anchor is persisted explicitly.
    warnings = tuple(w for w in report.warnings if w.output_id != "manifest.dataset") + tuple(w for o in outputs for w in o.warnings)
    result = ComparisonResult(outputs, settings, dataset, report, cid, freeze(fingerprints),
                              freeze(sources), protected, warnings, freeze({}))
    summaries = _summarize(result)
    return ComparisonResult(outputs, settings, dataset, report, cid, freeze(fingerprints),
                            freeze(sources), protected, warnings, freeze(summaries), profiles, report_settings,
                            sample_metadata, diagnostic_requests)


def _summarize(result):
    outputs, settings = result.outputs, result.settings
    union_q = set().union(*(set(o.query_ids) for o in outputs))
    pair_values, query_rows = {}, []
    active_queries = set()
    for pool, _ in _iter_pools(outputs, settings, depth_independent=True):
        if pool is None:
            continue
        active_queries.add(pool.query_id)
        for depth in sorted(settings.depths):
            agreements = list(_agreement(outputs, pool, settings, depth))
            for row in agreements:
                key = (row["left_output_id"], row["right_output_id"], row["pair_class"], depth)
                bucket = pair_values.setdefault(key, {"values": [], "descriptive": 0, "excluded": Counter()})
                if row["status"] == "available":
                    bucket["values"].append(row["overlap_fraction"])
                elif row["status"] == "descriptive":
                    bucket["descriptive"] += 1
                else:
                    bucket["excluded"][row["reason"]] += 1
            groups = [g for g, _, _ in _recurrence_groups(result, pool, depth)]
            query_rows.append({"query_id": pool.query_id, "pool_policy": settings.pool_policy,
                "requested_depth": depth, "status": "included", "reason": pool.reason,
                "outputs": len(outputs), "native_scorable": sum(c["native_scorable"] for c in pool.coverage.values()),
                "excluded_scorable": sum(c["excluded_scorable"] for c in pool.coverage.values()),
                "output_pairs": len(agreements), "controlled_evaluable_pairs": sum(r["status"] == "available" for r in agreements),
                "descriptive_pairs": sum(r["status"] == "descriptive" for r in agreements),
                "unavailable_pairs": sum(r["status"] == "unavailable" for r in agreements),
                "expected_run_groups": sum(g["expected_runs"] >= 2 for g in groups),
                "assessed_run_groups": sum(g["status"] == "available" for g in groups)})
    excluded_queries = len(union_q - active_queries)
    for q in sorted(union_q - active_queries):
        for depth in sorted(settings.depths):
            query_rows.append({k: None for k in TABLE_COLUMNS["query_summary"]} | {
                "query_id": q, "pool_policy": settings.pool_policy, "requested_depth": depth,
                "status": "excluded", "reason": "query_not_shared_by_all_outputs", "outputs": len(outputs)})
    summary = []
    for (a, b, cls, depth), bucket in sorted(pair_values.items()):
        values = sorted(bucket["values"])
        reasons = dict(bucket["excluded"])
        if excluded_queries:
            reasons["query_not_shared_by_all_outputs"] = excluded_queries
        summary.append({"left_output_id": a, "right_output_id": b, "pair_class": cls,
            "pool_policy": settings.pool_policy, "requested_depth": depth,
            "declared_queries": len(union_q), "eligible_queries": len(active_queries),
            "evaluable_queries": len(values), "descriptive_queries": bucket["descriptive"],
            "excluded_queries": len(union_q) - len(values), "exclusion_reasons": reasons,
            "status": "available" if values else "not_controlled" if settings.pool_policy == "native_inspection" else "unavailable",
            "minimum": min(values) if values else None, "q1": _quantile(values, .25),
            "median": _quantile(values, .5), "q3": _quantile(values, .75), "maximum": max(values) if values else None})
    inventory = [{"output_id": o.output_id, **{k: thaw(o.descriptor[k]) for k in (
        "label", "method_id", "configuration_id", "run_id", "seed", "ranking_policy", "tie_policy", "representation", "completeness", "configuration", "provenance")},
        "identity_status": result.compatibility.identity_status, "content_sha256": result.input_fingerprints[o.output_id]} for o in outputs]
    return {"outputs": inventory, "configuration_differences": list(result.compatibility.configuration_differences),
        "agreement_summary": summary, "query_summary": sorted(query_rows, key=lambda r: (r["query_id"], r["requested_depth"])),
        "dataset_summary": [{"dataset_id": result.dataset["dataset_id"], "pool_policy": settings.pool_policy,
            "methods": len({o.descriptor["method_id"] for o in outputs}), "configurations": len(result.compatibility.run_groups),
            "outputs": len(outputs), "declared_queries": len(union_q), "included_queries": len(active_queries),
            "excluded_queries": excluded_queries, "identity_status": result.compatibility.identity_status,
            "observation_count": len(result.dataset["observation_ids"]) if result.dataset["observation_ids"] is not None else None}]}


# Descriptive B1 tables are opt-in and never expand the all-pair universe.
B1_COLUMNS = {
    "sample_metadata": "observation_id field field_type value status in_required_cohort".split(),
    "diagnostics": "query_id candidate_id layer_id h omission result".split(),
    "group_summaries": "layer_id namespace feature_id field include_fraction result".split(),
}


def b1_columns(has_metadata, requests):
    names = (["sample_metadata"] if has_metadata else [])
    if requests:
        names.append("diagnostics")
    if any(r.group_field is not None for r in requests):
        names.append("group_summaries")
    return {name: B1_COLUMNS[name] for name in names}


# Ordered columns are part of the v1 table contract. JSON cells preserve exact
# strings (including empty strings) versus null; CSV readers use these schemas.
TABLE_COLUMNS = {
    "outputs": "output_id label method_id configuration_id run_id seed ranking_policy tie_policy representation completeness configuration provenance identity_status content_sha256".split(),
    "configuration_differences": "left_output_id right_output_id field left right".split(),
    "coverage": "query_id output_id pool_policy declared_candidates native_eligible native_scorable native_ranked retained_scorable excluded_scorable complete certified exhausted active_pool_size controlled_available reason".split(),
    "exclusions": "output_id query_id candidate_id status reason pool_policy".split(),
    "candidate_ranks": "query_id candidate_id output_id pool_policy native_rank active_rank saved_rank score count status reason active_status".split(),
    "agreement": "query_id left_output_id right_output_id pair_class pool_policy requested_depth effective_depth left_list_size right_list_size shared_count union_size overlap_fraction jaccard left_shared_fraction right_shared_fraction status reason".split(),
    "run_recurrence": "query_id candidate_id pool_policy requested_depth configuration_id expected_runs evaluable_runs status reason effective_depth nominations recurrence_fraction".split(),
    "agreement_summary": "left_output_id right_output_id pair_class pool_policy requested_depth declared_queries eligible_queries evaluable_queries descriptive_queries excluded_queries exclusion_reasons status minimum q1 median q3 maximum".split(),
    "query_summary": "query_id pool_policy requested_depth status reason outputs native_scorable excluded_scorable output_pairs controlled_evaluable_pairs descriptive_pairs unavailable_pairs expected_run_groups assessed_run_groups".split(),
    "dataset_summary": "dataset_id pool_policy methods configurations outputs declared_queries included_queries excluded_queries identity_status observation_count".split(),
}
