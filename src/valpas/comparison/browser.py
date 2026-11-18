"""Bounded offline payload and installed-package assets. Science stays in Python."""
from dataclasses import dataclass, replace, asdict
from importlib.resources import files
import hashlib

from .models import fail, thaw, ids, integer, keys
from .engine import canonical_json, _summarize, _agreement, _recurrence_groups, _top
from .compatibility import _iter_pools
from .profiles import pair_profile, feature_key


@dataclass(frozen=True)
class ReportSettings:
    query_ids: tuple | None = None
    max_interactive_depth: int = 50
    pinned_candidate_ids: tuple = ()
    max_payload_bytes: int = 50 * 1024 * 1024
    omit_metadata: bool = False

    def __post_init__(self):
        if self.query_ids is not None:
            object.__setattr__(self, "query_ids", ids(self.query_ids, "report.query_ids"))
        object.__setattr__(self, "pinned_candidate_ids", ids(self.pinned_candidate_ids, "report.pinned_candidate_ids", allow_empty=True))
        integer(self.max_interactive_depth, "report.max_interactive_depth", minimum=1)
        integer(self.max_payload_bytes, "report.max_payload_bytes", minimum=1)
        for name in ("omit_metadata",):
            if type(getattr(self, name)) is not bool:
                fail("report." + name, "expected boolean")

    @classmethod
    def from_dict(cls, value):
        keys(value, (), tuple(cls.__dataclass_fields__), "report")
        return cls(**value)

    def to_dict(self):
        return asdict(self) | {"query_ids": None if self.query_ids is None else list(self.query_ids),
                               "pinned_candidate_ids": list(self.pinned_candidate_ids)}


def safe_json(value):
    """JSON script data cannot terminate its element, even with hostile labels."""
    return (canonical_json(value).replace("&", "\\u0026").replace("<", "\\u003c")
            .replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def asset_text(name):
    if name not in ("dashboard.js", "dashboard.css", "shell.html"):
        fail("report.asset", "unknown packaged asset")
    return files("valpas.comparison").joinpath("assets", name).read_text(encoding="utf-8")


def build_report_payload(result, settings=None):
    """Embed whole-cohort overview; details only for explicit queries/top unions.

    Auxiliary depths use exactly the engine functions, without changing the
    comparison ID or its analysis tables. This payload is saved verbatim as a
    machine-readable report view alongside the complete scientific tables.
    """
    settings = settings or result.report_settings or ReportSettings()
    if not isinstance(settings, ReportSettings):
        fail("report", "expected validated ReportSettings")
    all_queries = sorted(set().union(*(set(o.query_ids) for o in result.outputs)))
    candidates = set().union(*(set(o.candidate_ids) for o in result.outputs))
    queries = all_queries if settings.query_ids is None else sorted(settings.query_ids)
    if not set(queries) <= set(all_queries):
        fail("report.query_ids", "unknown canonical query IDs")
    if not set(settings.pinned_candidate_ids) <= candidates:
        fail("report.pinned_candidate_ids", "unknown canonical candidate IDs")
    depths = tuple(sorted(set(result.settings.depths) | set(range(1, settings.max_interactive_depth + 1))))
    view = replace(result, settings=replace(result.settings, depths=depths))
    summaries = thaw(_summarize(view))
    selected = set(queries)
    details = {q: {"candidate_ids": [], "ranks": [], "coverage": [], "agreement": [],
                   "recurrence": [], "tops": [], "profiles": []} for q in queries}
    # All query/pair values drive the distribution drilldown. Never recompute a
    # new denominator from a displayed subset or a hidden output.
    agreement = []
    run_groups = []
    unions = {}
    for pool, _ in _iter_pools(result.outputs, result.settings, depth_independent=True):
        if pool is None:
            continue
        q = pool.query_id
        union = set(settings.pinned_candidate_ids)
        for oid, order in pool.active_orders.items():
            union.update(order[:settings.max_interactive_depth])
        if q in selected:
            unions[q] = union
            details[q]["candidate_ids"] = sorted(union)
        for depth in depths:
            rows = list(_agreement(result.outputs, pool, result.settings, depth))
            agreement.extend(rows)
            if q in selected:
                details[q]["agreement"].extend(rows)
                if depth <= settings.max_interactive_depth:
                    for o in result.outputs:
                        top, reason = _top(pool, o.output_id, depth)
                        details[q]["tops"].append({"output_id": o.output_id, "requested_depth": depth,
                                                   "candidate_ids": None if top is None else list(top), "reason": reason})
            for group, counts, cs in _recurrence_groups(result, pool, depth):
                run_groups.append({"query_id": q, "requested_depth": depth, **group})
                if q in selected:
                    for c in sorted(union & set(cs)) or [None]:
                        details[q]["recurrence"].append({"query_id": q, "candidate_id": c,
                            "pool_policy": result.settings.pool_policy, "requested_depth": depth, **group,
                            "nominations": counts[c] if c is not None else None,
                            "recurrence_fraction": counts[c] / group["expected_runs"] if group["status"] == "available" and c is not None else None})
    for q in queries:
        if q not in unions:
            unions[q] = set(settings.pinned_candidate_ids)
            details[q]["candidate_ids"] = sorted(unions[q])
    coverage = []
    for name, row in result.iter_detail_tables({"candidate_ranks", "coverage"}):
        q = row["query_id"]
        if name == "coverage":
            coverage.append(row)
        if q in selected and (name == "coverage" or row["candidate_id"] in unions[q]):
            details[q]["coverage" if name == "coverage" else "ranks"].append(row)
    # Sparse absent pairs still need an honest status in the browser, not a
    # fabricated table row/rank. Record these separately from canonical ranks.
    for q, detail in details.items():
        seen = {(r["candidate_id"], r["output_id"]) for r in detail["ranks"]}
        detail["omissions"] = []
        for c in detail["candidate_ids"]:
            for o in result.outputs:
                if (c, o.output_id) not in seen:
                    v = o.pair(q, c)
                    detail["omissions"].append({"candidate_id": c, "output_id": o.output_id,
                                                "status": v.status, "reason": v.reason})
    layers, feature_coverage = [], []
    if result.profiles is not None and not settings.omit_metadata:
        wanted = {feature_key(result.dataset["query_namespace"], q) for q in queries}
        wanted |= {feature_key(result.dataset["candidate_namespace"], c) for cs in unions.values() for c in cs}
        for original in result.profiles.layers:
            layer = thaw(original)
            layer["features"] = [f for f in layer["features"] if feature_key(f["namespace"], f["feature_id"]) in wanted]
            layers.append(layer)
            for q, detail in details.items():
                detail["profiles"].extend(pair_profile(original, result.dataset, q, c) for c in detail["candidate_ids"])
        feature_coverage = [r for r in result.iter_table("feature_coverage") if feature_key(r["namespace"], r["feature_id"]) in wanted]
    payload = {"schema_version": 1, "comparison_id": result.comparison_id,
               "analysis_settings": result.settings.to_dict(), "report_settings": settings.to_dict(),
               "dataset": thaw(result.dataset), "warnings": [asdict(w) for w in result.warnings],
               "summaries": summaries, "coverage": coverage, "agreement": agreement, "run_groups": run_groups,
               "query_ids": queries, "all_query_ids": all_queries, "details": details,
               "layers": layers, "feature_coverage": feature_coverage,
               "omissions": [], "sensitive_data_warning": "Local does not mean anonymized. Canonical IDs, scores, configuration and any included sample values may be sensitive. Full bundle retains original metadata; share only the HTML if using metadata omission."}
    if settings.omit_metadata:
        payload["omissions"] = ["HTML only: output labels/provenance; dataset context/evidence text and observation IDs; configuration values/difference values; profiles including feature labels/annotations/sample IDs/values; attestation statements. Complete bundle is NOT redacted."]
        payload["dataset"] = {k: v for k, v in payload["dataset"].items() if k in ("dataset_id", "query_namespace", "candidate_namespace")}
        payload["analysis_settings"]["attestations"] = "omitted from HTML"
        for row in summaries["outputs"]:
            row["label"] = row["output_id"]
            row["provenance"] = "omitted from HTML"
            row["configuration"] = "omitted from HTML"
        for row in summaries["configuration_differences"]:
            row["left"] = row["right"] = "omitted from HTML"
    return thaw(payload)


def render_report(result, settings=None):
    settings = settings or result.report_settings or ReportSettings()
    payload = build_report_payload(result, settings)
    data = safe_json(payload)
    size = len(data.encode("utf-8"))
    if size > settings.max_payload_bytes:
        fail("report.max_payload_bytes", f"embedded payload estimate {size} bytes exceeds limit {settings.max_payload_bytes} bytes before HTML wrapping",
             remediation="Choose explicit query_ids, lower max_interactive_depth, fewer pinned_candidate_ids, omit_metadata, increase the explicit limit, or use tables_only=True. No sampling or partial publication occurred.")
    js, css = asset_text("dashboard.js"), asset_text("dashboard.css")
    html = asset_text("shell.html").replace("/*PACKAGED_STYLE*/", css).replace("/*PACKAGED_SCRIPT*/", js).replace("{PAYLOAD}", data)
    return html, payload, {"payload_bytes": size, "payload_sha256": hashlib.sha256(data.encode("utf-8")).hexdigest()}
