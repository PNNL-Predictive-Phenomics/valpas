"""Optional, explicitly bound measurements; no association or model attribution."""
from dataclasses import dataclass
import math
from pathlib import Path

from .models import (fail, freeze, thaw, keys, ids, text, namespace,
                     validate_identity)

PROFILE_COLUMNS = {
    "feature_coverage": "layer_id namespace feature_id required_observations available_observations observed_count missing_count missing_fraction finite_unobserved_count mask_source status reason constant near_empty excluded_observation_ids".split(),
    "profile_values": "layer_id namespace feature_id observation_id value observed in_required_cohort mask_source".split(),
}


@dataclass(frozen=True)
class ProfileData:
    """Strict feature-by-observation layers, detached from input files.

    Explicit masks describe ORIGINAL observation, independently of imputed
    values. Only declared raw/unimputed data may derive masks from finiteness.
    """
    layers: tuple = ()
    source_fingerprints: tuple = ()

    def __post_init__(self):
        if not isinstance(self.layers, (tuple, list)):
            fail("profiles.layers", "expected a list")
        seen = set()
        normalized = []
        for original in self.layers:
            layer = thaw(original)
            keys(layer, ("layer_id", "dataset", "orientation", "observation_ids", "units",
                         "transform", "provenance", "raw_unimputed", "mask_source",
                         "subset_extra_observations", "algorithm_layers", "features"), field="profiles.layer")
            for name in ("layer_id", "units", "transform", "provenance"):
                text(layer[name], "profiles." + name)
            if layer["layer_id"] in seen:
                fail("profiles.layer_id", "duplicate layer ID")
            seen.add(layer["layer_id"])
            validate_identity(layer["dataset"], "profiles.dataset")
            obs = ids(layer["observation_ids"], "profiles.observation_ids")
            if layer["orientation"] != "feature_rows_observation_columns":
                fail("profiles.orientation", "explicit feature rows / observation columns required")
            for name in ("raw_unimputed", "subset_extra_observations"):
                if type(layer[name]) is not bool:
                    fail("profiles." + name, "expected boolean")
            mode = layer["mask_source"]
            if mode not in ("explicit_original", "raw_finite", "unavailable"):
                fail("profiles.mask_source", "expected explicit_original, raw_finite or unavailable")
            if mode == "raw_finite" and not layer["raw_unimputed"]:
                fail("profiles.mask_source", "finite-derived masks require declared raw unimputed data")
            keys(layer["algorithm_layers"], (), tuple(layer["algorithm_layers"]) if isinstance(layer["algorithm_layers"], dict) else (), "profiles.algorithm_layers")
            for oid, relation in layer["algorithm_layers"].items():
                text(oid, "profiles.algorithm_layers.output_id")
                if relation not in ("same", "different", "unknown"):
                    fail("profiles.algorithm_layers", "each output relation must be same, different or unknown")
            if not isinstance(layer["features"], list):
                fail("profiles.features", "expected a feature list")
            features = set()
            for feature in layer["features"]:
                keys(feature, ("namespace", "feature_id", "values", "observed"), ("label", "annotations"), "profiles.feature")
                namespace(feature["namespace"], "profiles.feature.namespace")
                text(feature["feature_id"], "profiles.feature_id")
                key = feature_key(feature["namespace"], feature["feature_id"])
                if key in features:
                    fail("profiles.features", "duplicate namespace/feature ID")
                features.add(key)
                for name in ("label", "annotations"):
                    if name in feature:
                        text(feature[name], "profiles.feature." + name)
                values = feature["values"]
                if not isinstance(values, list) or len(values) != len(obs):
                    fail("profiles.values", "one value required for each exact observation ID")
                if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in values):
                    fail("profiles.values", "expected finite numbers or explicit null, no coercion")
                mask = feature["observed"]
                if mode == "explicit_original":
                    if not isinstance(mask, list) or len(mask) != len(obs) or any(type(v) is not bool for v in mask):
                        fail("profiles.observed", "original boolean mask required independently of values")
                elif mask is not None:
                    fail("profiles.observed", "raw_finite/unavailable require null; derivation is explicit")
                if layer["raw_unimputed"] and mask is not None and any(v is not None and not m for v, m in zip(values, mask)):
                    fail("profiles.raw_unimputed", "finite unobserved values contradict raw/unimputed declaration")
            normalized.append(layer)
        object.__setattr__(self, "layers", freeze(normalized))
        object.__setattr__(self, "source_fingerprints", freeze(self.source_fingerprints))

    def to_dict(self):
        return {"schema_version": 1, "layers": thaw(self.layers)}

    @classmethod
    def from_dict(cls, value):
        keys(value, ("schema_version", "layers"), field="profiles")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            fail("profiles.schema_version", "unsupported profile schema")
        return cls(value["layers"])

    def validate_binding(self, dataset, outputs):
        from .compatibility import _equal
        for layer in self.layers:
            for field, value in dataset.items():
                other = layer["dataset"][field]
                if value is None or other is None or not _equal(field, value, other):
                    fail("profiles.dataset." + field, "profile binding must explicitly match the comparison dataset")
            if set(layer["algorithm_layers"]) != {o.output_id for o in outputs}:
                fail("profiles.algorithm_layers", "declare same/different/unknown relation for every output ID")
            allowed = (dataset["query_namespace"], dataset["candidate_namespace"])
            if any(f["namespace"] not in allowed for f in layer["features"]):
                fail("profiles.namespace", "feature namespace outside the comparison dataset")
            extra = set(layer["observation_ids"]) - set(dataset["observation_ids"])
            if extra and not layer["subset_extra_observations"]:
                fail("profiles.observation_ids", "extra observations require explicit subset_extra_observations=true")

    def iter_table(self, name, dataset, outputs):
        if name not in PROFILE_COLUMNS:
            fail("profiles.table", "unknown table")
        required = tuple(dataset["observation_ids"])
        required_set = set(required)
        expected = {}
        for output in outputs:
            for role in ("query", "candidate"):
                ns = dataset[role + "_namespace"]
                for fid in getattr(output, role + "_ids"):
                    expected[feature_key(ns, fid)] = (ns, fid)
        for layer in self.layers:
            found = {feature_key(f["namespace"], f["feature_id"]): f for f in layer["features"]}
            if name == "feature_coverage":
                universe = dict(expected)
                universe.update({k: (f["namespace"], f["feature_id"]) for k, f in found.items()})
                for key in sorted(universe):
                    ns, fid = universe[key]
                    yield feature_coverage(layer, ns, fid, required)
            else:
                for key in sorted(found):
                    f = found[key]
                    mask = observed_mask(layer, f)
                    for i, sid in enumerate(layer["observation_ids"]):
                        yield {"layer_id": layer["layer_id"], "namespace": thaw(f["namespace"]),
                               "feature_id": f["feature_id"], "observation_id": sid,
                               "value": f["values"][i], "observed": None if mask is None else mask[i],
                               "in_required_cohort": sid in required_set, "mask_source": layer["mask_source"]}


def feature_key(ns, fid):
    return (ns["id"], ns["modality"], fid)


def observed_mask(layer, feature):
    if layer["mask_source"] == "unavailable":
        return None
    if layer["mask_source"] == "raw_finite":
        return tuple(v is not None for v in feature["values"])
    return feature["observed"]


def feature_coverage(layer, ns, fid, required):
    feature = next((f for f in layer["features"] if feature_key(f["namespace"], f["feature_id"]) == feature_key(ns, fid)), None)
    obs = layer["observation_ids"]
    indices = {sid: i for i, sid in enumerate(obs)}
    missing = set(required) - set(obs)
    reason = "missing_feature" if feature is None else "missing_required_observations" if missing else "original_mask_unavailable" if layer["mask_source"] == "unavailable" else None
    row = {"layer_id": layer["layer_id"], "namespace": thaw(ns), "feature_id": fid,
           "required_observations": len(required), "available_observations": len(set(required) & set(obs)),
           "observed_count": None, "missing_count": None, "missing_fraction": None,
           "finite_unobserved_count": None, "mask_source": layer["mask_source"],
           "status": "unavailable" if reason else "available", "reason": reason,
           "constant": None, "near_empty": None,
           "excluded_observation_ids": sorted(set(obs) - set(required))}
    if reason:
        return row
    mask = observed_mask(layer, feature)
    observed = [feature["values"][indices[sid]] for sid in required if mask[indices[sid]]]
    # A mask can say originally observed while this transform has no finite
    # value. That does not turn it into an imputed observation or usable point.
    finite = [v for v in observed if v is not None]
    row.update(observed_count=len(observed), missing_count=len(required) - len(observed),
               missing_fraction=(len(required) - len(observed)) / len(required),
               finite_unobserved_count=sum(not mask[indices[sid]] and feature["values"][indices[sid]] is not None for sid in required),
               constant=len(finite) >= 2 and min(finite) == max(finite), near_empty=len(finite) < 3)
    return row


def pair_profile(layer, dataset, query_id, candidate_id):
    """Observed-only indices/counts computed in Python, not recomputed by JS."""
    required = dataset["observation_ids"]
    qns, cns = dataset["query_namespace"], dataset["candidate_namespace"]
    qc = feature_coverage(layer, qns, query_id, required)
    cc = feature_coverage(layer, cns, candidate_id, required)
    row = {"layer_id": layer["layer_id"], "query_id": query_id, "candidate_id": candidate_id,
           "status": "unavailable", "reason": qc["reason"] or cc["reason"], "joint_observed_count": None,
           "joint_indices": [], "query_indices": [], "candidate_indices": [],
           "query_unobserved_indices": [], "candidate_unobserved_indices": []}
    if row["reason"]:
        return row
    fs = {feature_key(f["namespace"], f["feature_id"]): f for f in layer["features"]}
    q, c = fs[feature_key(qns, query_id)], fs[feature_key(cns, candidate_id)]
    qm, cm = observed_mask(layer, q), observed_mask(layer, c)
    indices = {sid: i for i, sid in enumerate(layer["observation_ids"])}
    for role, f, mask in (("query", q, qm), ("candidate", c, cm)):
        row[role + "_indices"] = [indices[s] for s in required if mask[indices[s]] and f["values"][indices[s]] is not None]
        row[role + "_unobserved_indices"] = [indices[s] for s in required if not mask[indices[s]] and f["values"][indices[s]] is not None]
    row["joint_indices"] = [i for i in row["query_indices"] if i in set(row["candidate_indices"])]
    row["joint_observed_count"] = len(row["joint_indices"])
    row.update(status="available" if row["joint_indices"] else "unavailable",
               reason=None if row["joint_indices"] else "no_jointly_observed_finite_values")
    return row


def load_profile_data(value, *, base_dir="."):
    """Load an inline profile object or {path: local-json-name} descriptor."""
    from .adapters import _local_path, _read_fingerprinted, _json
    if isinstance(value, dict) and "path" in value:
        keys(value, ("path",), field="profiles")
        path = _local_path(value["path"], Path(base_dir), "profiles.path")
        if path.suffix.lower() != ".json":
            fail("profiles.path", "only explicit JSON profiles supported")
        raw, fingerprint = _read_fingerprinted(path, "profiles")
        profiles = ProfileData.from_dict(_json(raw, "profiles"))
        return ProfileData(profiles.layers, (fingerprint,))
    return ProfileData.from_dict(value)
