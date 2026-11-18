"""Identity, configuration/run grouping, and explicit comparison pools."""
from collections.abc import Mapping
from itertools import combinations

from .models import (CONFIG_FIELDS, ComparisonSettings, CompatibilityReport, Exclusion,
                     Issue, PoolResult, QueryPool, fail, freeze, thaw,
                     validate_descriptor, validate_identity)
from .ranking import rank_output


def _equal(field, left, right):
    if field == "observation_ids":
        return set(left) == set(right)
    if field == "dataset_evidence":
        if left["source"] != right["source"]:
            return False
        if left["type"] == right["type"] == "fingerprint":
            return left["value"] == right["value"]
        return True
    return left == right


def _unknown_config(config):
    return any(config[k] is None or (k in ("parameters", "preprocessing") and not config[k]) for k in CONFIG_FIELDS)


def _known_conflict(left, right):
    """Unknown fields can be filled by claims, but known leaves cannot change."""
    if left is None or left == {}:
        return False
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return any(k not in right or _known_conflict(v, right[k]) for k, v in left.items())
    return left != right


def _differences(left, right, prefix="configuration"):
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        result = []
        for k in sorted(set(left) | set(right)):
            if k not in left or k not in right:
                result.append((prefix + "." + k, left.get(k), right.get(k)))
            else:
                result.extend(_differences(left[k], right[k], prefix + "." + k))
        return result
    return [] if left == right else [(prefix, left, right)]


def validate_compatibility(outputs, settings=None, *, dataset=None):
    """Validate explicit identity and group runs; never infer source from axes."""
    outputs = tuple(outputs)
    settings = settings or ComparisonSettings()
    if not isinstance(settings, ComparisonSettings):
        fail("settings", "expected validated ComparisonSettings")
    if not outputs:
        fail("outputs", "at least one output required")
    names = [o.output_id for o in outputs]
    if len(set(names)) != len(names):
        fail("output_id", "duplicate output IDs")
    claims = {(a["output_id"], a["field"]): a for a in settings.attestations}
    if any(oid not in names for oid, field in claims):
        fail("settings.attestations.output_id", "attestation targets unknown output")
    identities = [(o.output_id, o.descriptor["identity"]) for o in outputs]
    if dataset is not None:
        validate_identity(dataset)
        identities.append(("manifest.dataset", dataset))
    # Compare all known values first, including peers separated by unknown ones.
    for field in ("dataset_id", "dataset_evidence", "observation_ids", "query_namespace", "candidate_namespace", "context"):
        known = [(oid, ident[field]) for oid, ident in identities if ident[field] is not None]
        for (aid, a), (bid, b) in combinations(known, 2):
            if not _equal(field, a, b):
                fail("identity." + field, "known identity mismatch with " + aid, bid,
                     "Use outputs from the same measurements, observations, context and namespaces; attestations cannot override mismatches.")
    warnings, resolved, used = [], [], set()
    for oid, ident in identities:
        current = thaw(ident)
        for field in ("dataset_evidence", "observation_ids", "context"):
            claim = claims.get((oid, field))
            if current[field] is None:
                if claim is None:
                    fail("identity." + field, "unknown identity requires a field-specific attestation", oid,
                         "Supply the missing metadata or an attestation naming this field and its claimed common value.")
                current[field] = thaw(claim["claimed_value"])
                used.add((oid, field))
                warnings.append(Issue("identity." + field, "user-attested compatibility; provenance incomplete",
                                      "Retain this limitation in downstream reporting.", oid))
            elif claim is not None:
                fail("settings.attestations", "attestation can only fill a missing identity field", oid)
        validate_identity(current, "identity", oid)
        if current["dataset_evidence"]["type"] == "attestation":
            warnings.append(Issue("identity.dataset_evidence", "user-attested compatibility; provenance incomplete",
                                  "A source claim is not a measured-content fingerprint.", oid))
        resolved.append((oid, current))
    for (aid, a), (bid, b) in combinations(resolved, 2):
        for field in a:
            if not _equal(field, a[field], b[field]):
                fail("identity." + field, "attested identity contradicts common source " + aid, bid)
    groups, configs, run_ids = {}, {}, set()
    for output in outputs:
        d, oid = output.descriptor, output.output_id
        group = d["configuration_id"]
        run_key = (group, d["run_id"])
        if run_key in run_ids:
            fail("run_id", "duplicate run within configuration", oid)
        run_ids.add(run_key)
        groups.setdefault(group, []).append(oid)
        config = thaw(d["configuration"])
        claim = claims.get((oid, "configuration"))
        if claim:
            if not _unknown_config(config):
                fail("settings.attestations.configuration", "configuration is already known", oid)
            proposed = thaw(claim["claimed_value"])
            descriptor = thaw(d)
            descriptor["configuration"] = proposed
            validate_descriptor(descriptor)
            if _known_conflict(config, proposed) or _unknown_config(proposed):
                fail("configuration", "non-seed attestation is incomplete or contradicts known configuration", oid)
            config = proposed
            used.add((oid, "configuration"))
            warnings.append(Issue("configuration", "user-attested non-seed configuration; provenance incomplete",
                                  "Do not describe attested metadata as recovered training history.", oid))
        if _unknown_config(config):
            warnings.append(Issue("configuration", "unknown non-seed configuration; isolated method effects cannot be claimed",
                                  "Supply complete metadata before grouping seed replicates.", oid))
        configs[oid] = {"method_id": d["method_id"], "configuration": config,
                        "ranking_policy": d["ranking_policy"], "tie_policy": d["tie_policy"]}
    if set(claims) != used:
        fail("settings.attestations", "unused or inappropriate attestation")
    for group, members in groups.items():
        if len(members) > 1:
            for oid in members:
                if _unknown_config(configs[oid]["configuration"]):
                    fail("configuration", "unknown non-seed configuration cannot establish seed replicates", oid,
                         "Supply complete metadata or a specific non-seed configuration attestation.")
                if configs[oid] != configs[members[0]]:
                    fail("configuration_id", "conflicting method/non-seed metadata in run group " + group, oid)
    differences = []
    for a, b in combinations(outputs, 2):
        for field, left, right in _differences(configs[a.output_id], configs[b.output_id], ""):
            differences.append(freeze({"left_output_id": a.output_id, "right_output_id": b.output_id,
                                       "field": field.lstrip("."), "left": left, "right": right}))
    if differences:
        warnings.append(Issue("configuration", "analysis configurations differ; not an isolated method comparison",
                              "Inspect the field-level configuration differences, including training feature sets."))
    return CompatibilityReport(tuple(differences), freeze(groups), tuple(warnings),
                               "user_attested" if any("attested" in w.reason for w in warnings) else "source_evidenced")


def build_pools(outputs, settings=None):
    """Build per-query native/active orders, statuses, coverage and exclusions.

    Strict finite-set gaps are unavailable, not errors or zeros. Common mode
    rejects every limited representation, even a prefix marked exhausted.
    """
    outputs = tuple(outputs)
    settings = settings or ComparisonSettings()
    report = validate_compatibility(outputs, settings)
    policy = settings.pool_policy
    if policy == "common" and any(not o.complete for o in outputs):
        fail("settings.pool_policy", "common reranking requires complete representations; truncated/filtered inputs prohibited",
             remediation="Re-export complete saved scores or complete ordered ranks.")
    query_sets = [set(o.query_ids) for o in outputs]
    union_q = set.union(*query_sets)
    shared_q = set.intersection(*query_sets)
    if policy == "strict" and any(qs != query_sets[0] for qs in query_sets):
        fail("query_ids", "strict requires equal query sets", remediation="Choose common or native_inspection explicitly.")
    if policy == "common" and not shared_q:
        fail("query_ids", "empty common query cohort")
    queries = shared_q if policy == "common" else union_q
    exclusions, results = [], {}
    if policy == "common":
        for q in sorted(union_q - shared_q):
            for o in outputs:
                exclusions.append(Exclusion(o.output_id, q, None, "missing_query" if q not in o.query_ids else "excluded_query",
                                            "query_not_shared_by_all_outputs"))
    for q in sorted(queries):
        native = {o.output_id: rank_output(o, q, exclude_self=settings.exclude_self) for o in outputs}
        eligible, scorable = {}, {}
        for o in outputs:
            view = native[o.output_id]
            eligible[o.output_id] = {c for c, (status, reason) in view.statuses.items() if status != "ineligible"}
            scorable[o.output_id] = set(view.order)
        all_eligible = list(eligible.values())
        if policy == "strict" and any(s != all_eligible[0] for s in all_eligible):
            fail("eligibility", "strict requires equal eligible candidate sets for query " + q,
                 remediation="Choose common or native_inspection explicitly.")
        common = set.intersection(*scorable.values())
        if policy == "common" and not common:
            fail("pool", "empty common scorable pool for query " + q,
                 remediation="Inspect missing/ineligible statuses or use native_inspection; no candidates can be fabricated.")
        reason = None
        if policy == "native_inspection":
            reason = "different search spaces; descriptive only"
        elif policy == "strict":
            if any(not v.certified for v in native.values()):
                reason = "inspection_only_or_missing_query"
            elif any(o.descriptor["representation"] == "certified_prefix" for o in outputs):
                # Mixing uncertified native-pool identity with prefixes is unsafe.
                if not all(o.descriptor["representation"] == "certified_prefix" for o in outputs):
                    reason = "native_pool_certificate_unavailable"
                else:
                    certs = [o.descriptor["completeness"]["queries"][q] for o in outputs]
                    certified_sets = [{c for c, (status, why) in native[o.output_id].statuses.items()
                                       if status not in ("ineligible", "unscored", "missing_query")}
                                      for o in outputs]
                    if len({(c["pool_id"], c["pool_size"]) for c in certs}) != 1 or any(s != certified_sets[0] for s in certified_sets):
                        reason = "certified_native_pools_differ"
                    elif any(any(min(k, c["pool_size"]) > c["depth"] for k in settings.depths) for c in certs):
                        reason = "insufficient_certified_depth"
            elif any(s != next(iter(scorable.values())) for s in scorable.values()):
                reason = "scorable_candidate_sets_differ"
            elif not common:
                reason = "empty_scorable_pool"
        active, ranks, pools, coverage = {}, {}, {}, {}
        union_c = set.union(*(set(o.candidate_ids) for o in outputs))
        for o in outputs:
            oid, view = o.output_id, native[o.output_id]
            active[oid] = tuple(c for c in view.order if policy != "common" or c in common)
            ranks[oid] = {c: i for i, c in enumerate(active[oid], 1)}
            pools[oid] = tuple(sorted(common if policy == "common" else eligible[oid]))
            known_scorable = sum(status == "scorable" for status, why in view.statuses.values())
            retained = len(active[oid]) if policy == "common" else known_scorable
            coverage[oid] = {"declared_candidates": len(o.candidate_ids), "native_eligible": len(eligible[oid]),
                             "native_scorable": known_scorable, "native_ranked": len(view.order),
                             "retained_scorable": retained, "excluded_scorable": known_scorable - retained,
                             "complete": o.complete, "certified": view.certified,
                             "exhausted": view.exhausted}
            for c in sorted(union_c):
                status, why = view.statuses.get(c, ("ineligible", "candidate_not_in_output"))
                if status != "scorable":
                    exclusions.append(Exclusion(oid, q, c, status, why or status))
                elif policy == "common" and c not in common:
                    exclusions.append(Exclusion(oid, q, c, "excluded_from_common", "not_scorable_in_every_output"))
        results[q] = QueryPool(q, freeze(native), freeze(active), freeze(ranks), freeze(pools),
                               reason is None, reason, freeze(coverage))
    return PoolResult(policy, freeze(results), tuple(exclusions), report)
