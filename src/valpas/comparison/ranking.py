"""Deterministic ordinal ranks only; no agreement/recurrence metric engine."""
from .models import RankView, RankingPolicy, fail, freeze, integer


def score_order(scores, policy):
    """Order candidate IDs by exact stored score, then Unicode code point."""
    if policy not in tuple(p.value for p in RankingPolicy):
        fail("ranking_policy", "unknown ranking policy")
    absolute = policy.startswith("absolute_")
    descending = policy.endswith("descending")
    def key(candidate):
        value = abs(scores[candidate]) if absolute else scores[candidate]
        return (-value if descending else value, candidate)
    return tuple(sorted(scores, key=key))


def is_self(output, query_id, candidate_id):
    identity = output.descriptor["identity"]
    return query_id == candidate_id and identity["query_namespace"] == identity["candidate_namespace"]


def rank_output(output, query_id, *, exclude_self=True):
    """Native ranks and every declared candidate status for one query.

    Filtered lists expose scores/statuses but never manufacture ranks. Prefixes
    retain saved native ranks and cannot silently change their certified pool.
    """
    if type(exclude_self) is not bool:
        fail("exclude_self", "expected boolean", output.output_id)
    d = output.descriptor
    prefix = d["representation"] == "certified_prefix"
    if prefix and query_id in output.query_ids:
        cert = d["completeness"]["queries"][query_id]
        if cert["self_excluded"] != exclude_self:
            fail("completeness.self_excluded", "requested self-edge rule differs from prefix certificate", output.output_id)
    statuses, known = {}, {}
    for c in output.candidate_ids:
        v = output.pair(query_id, c)
        if exclude_self and is_self(output, query_id, c):
            statuses[c] = ("ineligible", "self_edge")
        else:
            statuses[c] = (v.status, v.reason)
            if v.status == "scorable":
                known[c] = v
    inspection = d["representation"] == "filtered_list"
    if inspection:
        order = ()
    elif known and all(v.rank is not None for v in known.values()):
        order = tuple(sorted(known, key=lambda c: known[c].rank))
    else:
        order = score_order({c: v.score for c, v in known.items()}, d["ranking_policy"])
    certified = not inspection and query_id in output.query_ids and query_id not in d.get("missing_queries", ())
    exhausted = output.complete
    if prefix and query_id in output.query_ids:
        exhausted = d["completeness"]["queries"][query_id]["exhausted"]
    return RankView(output.output_id, query_id, order,
                    freeze({c: i for i, c in enumerate(order, 1)}), freeze(statuses), certified, exhausted)


def top_list(output, query_id, depth, *, exclude_self=True):
    """Return a certified native prefix; reject inspection/insufficient depth."""
    integer(depth, "depth", output.output_id, minimum=1)
    view = rank_output(output, query_id, exclude_self=exclude_self)
    if not view.certified:
        fail("depth", "top lists unavailable for inspection-only or missing queries", output.output_id)
    if depth > len(view.order) and not view.exhausted:
        fail("depth", "requested depth exceeds certified prefix", output.output_id,
             "Request a shallower depth or a complete saved output.")
    return view.order[:depth]
