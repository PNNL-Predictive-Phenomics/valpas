"""Explicit production-to-comparison boundary; no scientific imports or fitting.

A request contains an A1 descriptor, explicit query axis and a new destination.
Identity/source claims remain caller supplied. Capture is restricted to facts
available at the calculation boundary, not reconstructed training history.
"""
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

from .adapters import _json, from_association_result
from .bundles import export_comparison_inputs
from .models import (ComparisonSettings, fail, ids, keys, thaw,
                     validate_descriptor)


def load_export_request(value):
    """Read a strict request mapping or local JSON file (never executable data)."""
    if isinstance(value, (str, Path)):
        try:
            value = _json(Path(value).read_text(encoding="utf-8"), "comparison_export")
        except (OSError, UnicodeError) as exc:
            fail("comparison_export", "cannot read request: " + str(exc))
    keys(value, ("descriptor", "query_axis", "destination"), ("settings",),
         "comparison_export")
    request = thaw(value)
    validate_descriptor(request["descriptor"])
    if request["query_axis"] not in ("index", "columns"):
        fail("comparison_export.query_axis", "select index or columns explicitly")
    if not isinstance(request["destination"], str) or not request["destination"]:
        fail("comparison_export.destination", "expected a new directory path")
    if "settings" in request:
        ComparisonSettings.from_dict(request["settings"])
    return request


def validate_legacy_destination(request, legacy):
    """Keep independent legacy publication outside the owned sidecar inventory."""
    if not isinstance(legacy, (str, Path)):
        legacy = getattr(legacy, "name", None)
    if isinstance(legacy, (str, Path)) and not str(legacy).startswith("<"):
        destination = Path(request["destination"]).resolve()
        output = Path(legacy).resolve()
        if output == destination or destination in output.parents:
            fail("comparison_export.destination", "legacy output must be outside the sidecar directory")


def _merge_known(existing, known, field):
    """Fill unknown leaves; reject conflict, retain supplied extra metadata."""
    if existing is None:
        return thaw(known)
    if isinstance(existing, Mapping) and isinstance(known, Mapping):
        merged = thaw(existing)
        for key, value in known.items():
            merged[key] = _merge_known(merged.get(key), value, field + "." + key)
        return merged
    if existing != known:
        fail(field, "supplied metadata contradicts captured production facts")
    return existing


def export_association_result(result, destination, descriptor, *, query_axis,
                              settings=None, observation_ids=None, method=None,
                              transform_clr=None, thresholded=None, preprocessing=None):
    """Export existing labeled values without save/as_list, training or scoring.

    Works with AssociationResult and similarity_matrix-based analysis results.
    Optional capture arguments are facts supplied by the calculation boundary.
    No source fingerprint, seed, preprocessing history or model configuration
    is inferred from matrix shape, filenames, embeddings or global RNG state.
    Unknown descriptor fields stay unknown. Extra open configuration metadata
    is retained. Paths obey the A1 new-directory/no-overwrite contract.
    """
    d = thaw(descriptor)
    validate_descriptor(d)
    if observation_ids is not None:
        observations = list(ids(observation_ids, "captured.observation_ids"))
        supplied = d["identity"]["observation_ids"]
        if supplied is not None and set(supplied) != set(observations):
            fail("identity.observation_ids", "supplied cohort contradicts actual calculation cohort")
        d["identity"]["observation_ids"] = observations
    if preprocessing is not None:
        d["configuration"]["preprocessing"] = _merge_known(
            d["configuration"]["preprocessing"], preprocessing,
            "configuration.preprocessing")
    if method is not None:
        # method_id is a user identity, not necessarily the algorithm's name.
        known = {"valpas_method": method}
        if transform_clr is not None:
            known["transform_clr"] = transform_clr
        if thresholded is not None:
            known["thresholded_counts"] = thresholded
        d["configuration"]["parameters"] = _merge_known(
            d["configuration"]["parameters"], known, "configuration.parameters")
        if method in ("pearson", "spearman", "cosine_similarity", "cosine_distance",
                      "jaccard_similarity", "jaccard_distance", "jaccard_index",
                      "mutual_information"):
            d["configuration"]["supervision"] = _merge_known(
                d["configuration"]["supervision"], "unsupervised", "configuration.supervision")
    # Structural adaptation, without importing scientific result classes.
    if not hasattr(result, "values"):
        if not hasattr(result, "similarity_matrix"):
            fail("source", "expected labeled values or similarity_matrix")
        result = SimpleNamespace(values=result.similarity_matrix, counts=None)
    output = from_association_result(result, d, query_axis=query_axis,
                                     query_ids=d["query_ids"], candidate_ids=d["candidate_ids"])
    return export_comparison_inputs([output], destination, settings=settings)


def export_requested_result(result, request, **captured):
    """Validate an explicit request and export before any legacy mutation.

    Request paths are relative to the process working directory, not the JSON
    file. The sidecar and legacy export are separate publications; a subsequent
    legacy failure does not remove a successfully published sidecar.
    """
    request = load_export_request(request)
    return export_association_result(
        result, request["destination"], request["descriptor"],
        query_axis=request["query_axis"],
        settings=ComparisonSettings.from_dict(request.get("settings", {})),
        **captured)
