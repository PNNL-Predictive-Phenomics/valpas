"""Observed-data descriptions, never attribution of saved scores or model outputs.

Inputs are validated ProfileData layers and dataset descriptors. Returned dictionaries
are detached, JSON-safe data. Cohort lists preserve dataset order; selected influence
IDs use decreasing absolute product, then exact Unicode observation ID. Group
exclusions give missing metadata precedence, so their counts never overlap.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import math
from pathlib import Path

from .models import (fail, freeze, thaw, keys, text, integer, json_value,
                     namespace as validate_namespace, validate_identity)
from .profiles import feature_key, feature_coverage, observed_mask, pair_profile


@dataclass(frozen=True)
class SampleMetadata:
    """Exact observation-keyed metadata; absent records/values are explicitly missing.

    All three containers (dataset, fields, records) are required, but fields and
    records may be empty. Values may omit declared fields or supply explicit null.
    Source fingerprints are transport provenance, not part of the schema-1 document.
    """
    dataset: Mapping
    fields: Mapping
    records: tuple
    subset_extra_observations: bool = False
    source_fingerprints: tuple = ()

    def __post_init__(self):
        validate_identity(self.dataset, "sample_metadata.dataset")
        if not isinstance(self.fields, Mapping):
            fail("sample_metadata.fields", "expected a field-name/type mapping")
        for name, kind in self.fields.items():
            text(name, "sample_metadata.fields.name")
            if kind not in ("categorical", "continuous"):
                fail("sample_metadata.fields", "expected categorical or continuous")
        if type(self.subset_extra_observations) is not bool:
            fail("sample_metadata.subset_extra_observations", "expected boolean")
        if not isinstance(self.records, (list, tuple)):
            fail("sample_metadata.records", "expected an explicit record list")
        seen = set()
        for record in self.records:
            keys(record, ("observation_id", "values"), field="sample_metadata.record")
            sid = text(record["observation_id"], "sample_metadata.observation_id")
            if sid in seen:
                fail("sample_metadata.observation_id", "duplicate canonical ID")
            seen.add(sid)
            keys(record["values"], (), tuple(self.fields), "sample_metadata.values")
            for name, value in record["values"].items():
                if value is None:
                    continue
                if self.fields[name] == "categorical":
                    if not isinstance(value, str):
                        fail("sample_metadata.values." + name, "expected string or null, no coercion")
                elif not _finite_number(value):
                    fail("sample_metadata.values." + name, "expected finite number or null, no bool or coercion")
        if not isinstance(self.source_fingerprints, (tuple, list)):
            fail("sample_metadata.source_fingerprints", "expected a fingerprint list")
        json_value(self.source_fingerprints, "sample_metadata.source_fingerprints")
        for name in ("dataset", "fields", "records", "source_fingerprints"):
            object.__setattr__(self, name, freeze(getattr(self, name)))

    def to_dict(self):
        return {"schema_version": 1, "dataset": thaw(self.dataset),
                "fields": thaw(self.fields), "records": thaw(self.records),
                "subset_extra_observations": self.subset_extra_observations}

    @classmethod
    def from_dict(cls, value):
        keys(value, ("schema_version", "dataset", "fields", "records"),
             ("subset_extra_observations",), "sample_metadata")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            fail("sample_metadata.schema_version", "unsupported sample metadata schema")
        return cls(value["dataset"], value["fields"], value["records"],
                   value.get("subset_extra_observations", False))

    def validate_binding(self, dataset, outputs=()):
        """Use the same explicit identity equality as profiles; outputs are unused."""
        _validate_dataset_binding(self.dataset, dataset, "sample_metadata")
        extra = {r["observation_id"] for r in self.records} - set(dataset["observation_ids"])
        if extra and not self.subset_extra_observations:
            fail("sample_metadata.observation_ids", "extra observations require explicit subset_extra_observations=true")

    def iter_table(self, dataset):
        """One row per required/extra observation and declared field, including nulls.

        Required observations retain dataset order, extras use Unicode ID order,
        and fields use Unicode name order. Extra rows are not dropped from export.
        """
        self.validate_binding(dataset)
        records = {r["observation_id"]: r["values"] for r in self.records}
        required = tuple(dataset["observation_ids"])
        required_set = set(required)
        for sid in (*required, *sorted(set(records) - required_set)):
            for name in sorted(self.fields):
                value = records.get(sid, {}).get(name)
                yield {"observation_id": sid, "field": name, "field_type": self.fields[name],
                       "value": value, "status": "missing" if value is None else "available",
                       "in_required_cohort": sid in required_set}


def load_sample_metadata(value, *, base_dir="."):
    """Load an inline schema-1 document or a contained local {path: ...} JSON file."""
    from .adapters import _local_path, _read_fingerprinted, _json
    if isinstance(value, Mapping) and "path" in value:
        keys(value, ("path",), field="sample_metadata")
        path = _local_path(value["path"], Path(base_dir), "sample_metadata.path")
        if path.suffix.lower() != ".json":
            fail("sample_metadata.path", "only explicit JSON sample metadata supported")
        raw, fingerprint = _read_fingerprinted(path, "sample_metadata")
        metadata = SampleMetadata.from_dict(_json(raw, "sample_metadata"))
        return SampleMetadata(metadata.dataset, metadata.fields, metadata.records,
                              metadata.subset_extra_observations, (fingerprint,))
    return SampleMetadata.from_dict(value)


@dataclass(frozen=True)
class DiagnosticRequest:
    """One requested pair/layer; no schema wrapper inside a manifest request list."""
    query_id: str
    candidate_id: str
    layer_id: str
    h: int = 5
    omission: bool = False
    group_field: str | None = None
    include_fraction: bool = True

    def __post_init__(self):
        for name in ("query_id", "candidate_id", "layer_id"):
            text(getattr(self, name), "diagnostics." + name)
        integer(self.h, "diagnostics.h", minimum=1)
        for name in ("omission", "include_fraction"):
            if type(getattr(self, name)) is not bool:
                fail("diagnostics." + name, "expected boolean")
        if self.group_field is not None:
            text(self.group_field, "diagnostics.group_field")

    def to_dict(self):
        return {name: getattr(self, name) for name in
                ("query_id", "candidate_id", "layer_id", "h", "omission", "group_field", "include_fraction")}

    @classmethod
    def from_dict(cls, value):
        keys(value, ("query_id", "candidate_id", "layer_id"),
             ("h", "omission", "group_field", "include_fraction"), "diagnostics.request")
        return cls(**value)


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_dataset_binding(bound, dataset, prefix):
    from .compatibility import _equal
    validate_identity(dataset)
    validate_identity(bound, prefix + ".dataset")
    for name, value in dataset.items():
        other = bound[name]
        if value is None or other is None or not _equal(name, value, other):
            fail(prefix + ".dataset." + name, "binding must explicitly match the comparison dataset")


def _validate_layer_binding(layer, dataset):
    _validate_dataset_binding(layer["dataset"], dataset, "profiles")
    if set(layer["observation_ids"]) - set(dataset["observation_ids"]) and not layer["subset_extra_observations"]:
        fail("profiles.observation_ids", "extra observations require explicit subset_extra_observations=true")


def _checked(value):
    if not math.isfinite(value):
        raise OverflowError("numeric_range")
    return value


def _mean(values):
    # Divide before summing to avoid overflowing an otherwise representable mean.
    return _checked(math.fsum(v / len(values) for v in values))


def group_summary(layer, dataset, metadata, namespace, feature_id, field, *, include_fraction=True):
    """Marginal categorical summaries on known-group, observed finite values only.

    Missing groups take precedence over not_observed_finite in the disjoint
    exclusions. Missing profile rows or unavailable masks disable the summary,
    rather than silently shrinking the required cohort. Continuous overlays are
    valid metadata but are not automatically binned into categorical groups.
    """
    text(feature_id, "diagnostics.feature_id")
    text(field, "diagnostics.group_field")
    validate_namespace(namespace, "diagnostics.namespace")
    if type(include_fraction) is not bool:
        fail("diagnostics.include_fraction", "expected boolean")
    _validate_layer_binding(layer, dataset)
    if not isinstance(metadata, SampleMetadata):
        fail("sample_metadata", "expected SampleMetadata")
    metadata.validate_binding(dataset)
    required = list(dataset["observation_ids"])
    required_set = set(required)
    coverage = feature_coverage(layer, namespace, feature_id, required)
    records = {r["observation_id"]: r["values"] for r in metadata.records}
    reason = ("missing_group_field" if field not in metadata.fields else
              "categorical_field_required" if metadata.fields[field] != "categorical" else coverage["reason"])
    row = {"layer_id": layer["layer_id"], "namespace": thaw(namespace), "feature_id": feature_id,
           "field": field, "field_type": metadata.fields.get(field), "include_fraction": include_fraction,
           "required_count": len(required), "required_observation_ids": required,
           "known_group_count": None, "known_group_observation_ids": [],
           "observed_finite_count": None, "observed_finite_observation_ids": [],
           "included_count": None, "included_observation_ids": [], "groups": [],
           "exclusions": {name: {"count": None, "observation_ids": []}
                          for name in ("missing_group", "not_observed_finite")},
           "excluded_profile_observation_ids": sorted(set(layer["observation_ids"]) - required_set),
           "excluded_metadata_observation_ids": sorted(set(records) - required_set),
           "mask_source": layer["mask_source"], "status": "unavailable", "reason": reason,
           "between_group_ss": None, "total_ss": None, "between_group_fraction": None,
           "fraction_status": "unavailable" if include_fraction else "not_requested",
           "fraction_reason": reason if include_fraction else "not_requested"}
    if reason:
        return row
    feature = next(f for f in layer["features"]
                   if feature_key(f["namespace"], f["feature_id"]) == feature_key(namespace, feature_id))
    mask = observed_mask(layer, feature)
    indices = {sid: i for i, sid in enumerate(layer["observation_ids"])}
    known = [sid for sid in required if records.get(sid, {}).get(field) is not None]
    observed = [sid for sid in required if mask[indices[sid]] and feature["values"][indices[sid]] is not None]
    known_set, observed_set = set(known), set(observed)
    included = [sid for sid in known if sid in observed_set]
    missing_group = [sid for sid in required if sid not in known_set]
    not_observed = [sid for sid in known if sid not in observed_set]
    row.update(known_group_count=len(known), known_group_observation_ids=known,
               observed_finite_count=len(observed), observed_finite_observation_ids=observed,
               included_count=len(included), included_observation_ids=included,
               exclusions={"missing_group": {"count": len(missing_group), "observation_ids": missing_group},
                           "not_observed_finite": {"count": len(not_observed), "observation_ids": not_observed}})
    if not included:
        row.update(reason="no_known_group_observed_finite_values")
        if include_fraction:
            row["fraction_reason"] = row["reason"]
        return row
    groups = {}
    for sid in included:
        groups.setdefault(records[sid][field], []).append(feature["values"][indices[sid]])
    row["groups"] = [{"group": group, "count": len(groups[group]), "mean": None} for group in sorted(groups)]
    try:
        means = [_mean(groups[g["group"]]) for g in row["groups"]]
    except (OverflowError, ValueError):
        row.update(reason="numeric_range")
        if include_fraction:
            row["fraction_reason"] = "numeric_range"
        return row
    for group, mean in zip(row["groups"], means):
        group["mean"] = mean
    row.update(status="available", reason=None)
    if include_fraction:
        values = [feature["values"][indices[sid]] for sid in included]
        try:
            mean = _mean(values)
            total = _checked(math.fsum(_checked((v - mean) ** 2) for v in values))
            between = _checked(math.fsum(_checked(g["count"] * (g["mean"] - mean) ** 2) for g in row["groups"]))
            fraction = _checked(between / total) if total else None
            row.update(total_ss=total, between_group_ss=between, between_group_fraction=fraction,
                       fraction_status="available" if total else "unavailable",
                       fraction_reason=None if total else "zero_total_variation")
        except (OverflowError, ValueError):
            row.update(fraction_status="unavailable", fraction_reason="numeric_range")
    return row


def _empty_stats(count, reason):
    return {"count": count, "mean_x": None, "mean_y": None, "covariance": None, "correlation": None,
            "status": "unavailable", "reason": reason,
            "covariance_status": "unavailable", "covariance_reason": reason,
            "correlation_status": "unavailable", "correlation_reason": reason}


def _stats(xs, ys):
    """Sample covariance (n-1) and Pearson correlation, with >=3 pairs required.

    Overall availability follows covariance. A constant variable still has a
    defined zero covariance; correlation's independent status explains its null.
    """
    row = _empty_stats(len(xs), "insufficient_observations")
    if len(xs) < 3:
        return row
    try:
        mx, my = _mean(xs), _mean(ys)
        dx = [_checked(x - mx) for x in xs]
        dy = [_checked(y - my) for y in ys]
        products = [_checked(x * y) for x, y in zip(dx, dy)]
        covariance = _checked(math.fsum(p / (len(xs) - 1) for p in products))
        row.update(mean_x=mx, mean_y=my, covariance=covariance, status="available", reason=None,
                   covariance_status="available", covariance_reason=None)
    except (OverflowError, ValueError):
        return _empty_stats(len(xs), "numeric_range")
    try:
        # Scale deviations before squaring, avoiding overflow in Pearson's
        # denominator even when covariance and products are representable.
        sx, sy = max(abs(v) for v in dx), max(abs(v) for v in dy)
        if sx == 0 or sy == 0:
            row.update(correlation_reason="zero_variance")
        else:
            ux, uy = [v / sx for v in dx], [v / sy for v in dy]
            corr = _checked(math.fsum(x * y for x, y in zip(ux, uy)) /
                            (math.sqrt(math.fsum(x * x for x in ux)) *
                             math.sqrt(math.fsum(y * y for y in uy))))
            row.update(correlation=max(-1.0, min(1.0, corr)),
                       correlation_status="available", correlation_reason=None)
    except (OverflowError, ValueError, ZeroDivisionError):
        row.update(correlation_reason="numeric_range")
    return row


def covariance_diagnostic(layer, dataset, query_id, candidate_id, *, h=5, omission=False):
    """Joint-centered signed products and largest-h absolute-product share.

    Fewer than three joint points, zero absolute denominator, or nonfinite
    arithmetic makes influence unavailable. No points are selected/omitted in
    that case. Explicit omission recenters retained pairs and requires >=3.
    Original/remaining statistics have separate covariance/correlation statuses.
    """
    request = DiagnosticRequest(query_id, candidate_id, layer["layer_id"], h, omission)
    _validate_layer_binding(layer, dataset)
    profile = pair_profile(layer, dataset, request.query_id, request.candidate_id)
    obs = layer["observation_ids"]
    required = list(dataset["observation_ids"])
    joint = [obs[i] for i in profile["joint_indices"]]
    joint_set = set(joint)
    reason = profile["reason"]
    row = {"layer_id": layer["layer_id"], "query_id": query_id, "candidate_id": candidate_id,
           "h": h, "omission": omission, "required_observation_ids": required,
           "joint_observed_count": profile["joint_observed_count"], "joint_observation_ids": joint,
           "excluded_observation_ids": [sid for sid in required if sid not in joint_set],
           "excluded_profile_observation_ids": sorted(set(obs) - set(required)),
           "mask_source": layer["mask_source"], "status": "unavailable", "reason": reason,
           "products": [], "absolute_product_sum": None, "selected_observation_ids": [],
           "effective_h": 0, "largest_h_share": None,
           "original": _empty_stats(profile["joint_observed_count"], reason),
           "remaining": _empty_stats(None, reason if omission else "not_requested"),
           "omitted_observation_ids": [], "retained_observation_ids": list(joint)}
    if reason:
        return row
    features = {feature_key(f["namespace"], f["feature_id"]): f for f in layer["features"]}
    q = features[feature_key(dataset["query_namespace"], query_id)]
    c = features[feature_key(dataset["candidate_namespace"], candidate_id)]
    xs = [q["values"][i] for i in profile["joint_indices"]]
    ys = [c["values"][i] for i in profile["joint_indices"]]
    row["original"] = _stats(xs, ys)
    if len(joint) < 3:
        row["reason"] = "insufficient_joint_observations"
    else:
        try:
            mx, my = _mean(xs), _mean(ys)
            products = [_checked(_checked(x - mx) * _checked(y - my)) for x, y in zip(xs, ys)]
            denominator = _checked(math.fsum(abs(p) for p in products))
            row["products"] = [{"observation_id": sid, "product": p,
                                "absolute_share": _checked(abs(p) / denominator) if denominator else None}
                               for sid, p in zip(joint, products)]
            row["absolute_product_sum"] = denominator
            if denominator == 0:
                row["reason"] = "zero_absolute_product_sum"
            else:
                selected = sorted(range(len(joint)), key=lambda i: (-abs(products[i]), joint[i]))[:h]
                share = _checked(math.fsum(abs(products[i]) / denominator for i in selected))
                row.update(status="available", reason=None, effective_h=len(selected),
                           selected_observation_ids=[joint[i] for i in selected], largest_h_share=share)
        except (OverflowError, ValueError):
            row.update(reason="numeric_range", products=[], absolute_product_sum=None)
    if omission:
        if row["status"] == "available":
            omitted = set(row["selected_observation_ids"])
            retained = [i for i, sid in enumerate(joint) if sid not in omitted]
            row.update(omitted_observation_ids=list(row["selected_observation_ids"]),
                       retained_observation_ids=[joint[i] for i in retained],
                       remaining=_stats([xs[i] for i in retained], [ys[i] for i in retained]))
        else:
            row["remaining"] = _empty_stats(len(joint), row["reason"])
    return row
