"""Opt-in comparison-ready INPUT bundles (not A2 comparison results/reports)."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from .adapters import _json, _local_path, _read, load_manifest
from .compatibility import validate_compatibility
from .models import ComparisonSettings, fail, keys, thaw, validate_identity


def _write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


def export_comparison_inputs(outputs, destination, *, dataset=None, settings=None):
    """Export detached normalized values at full Python-float precision.

    No overwrite mode: existing files/directories/symlinks are always refused.
    The destination and its immediate parent must not be symlinks. Existing
    ancestor aliases (such as macOS /var) are resolved before staging.
    Files use generated numeric names, never feature/output IDs. Publication
    reserves a new empty destination and renames a completed sibling into it.
    """
    outputs = tuple(outputs)
    settings = settings or ComparisonSettings()
    if not outputs:
        fail("outputs", "at least one input required")
    dataset = thaw(dataset if dataset is not None else outputs[0].descriptor["identity"])
    validate_identity(dataset)
    validate_compatibility(outputs, settings, dataset=dataset)
    destination = Path(destination)
    if ".." in destination.parts:
        fail("destination", "parent traversal is prohibited")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        fail("destination", "existing destination refused; overwrite is not supported")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        fail("destination", "parent must exist and must not be a symlink")
    destination = destination.parent.resolve() / destination.name
    for output in outputs:
        for source in output.source_files:
            if Path(source).resolve().is_relative_to(destination):
                fail("destination", "destination contains a consumed source")
    staging = Path(tempfile.mkdtemp(prefix="." + destination.name + ".partial-", dir=destination.parent))
    reserved = False
    try:
        descriptors, inventory = [], {}
        for i, output in enumerate(outputs):
            name = f"input-{i:04d}.json"
            # Write records incrementally; do not construct a second long table.
            with (staging / name).open("x", encoding="utf-8", newline="\n") as handle:
                handle.write('{"records":[')
                first = True
                for (q, c), value in sorted(output.pairs.items()):
                    if not first:
                        handle.write(",")
                    json.dump({"query_id": q, "candidate_id": c, **asdict(value)}, handle,
                              ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    first = False
                handle.write("]}\n")
            d = thaw(output.descriptor)
            d["data"] = {k: v for k, v in d["data"].items() if k in ("index_base", "symmetric")}
            d["data"].update({"format": "normalized", "path": name})
            descriptors.append(d)
        _write_json(staging / "manifest.json", {"schema_version": 1, "dataset": dataset,
                    "outputs": descriptors, "settings": settings.to_dict()})
        for path in sorted(staging.iterdir()):
            inventory[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        _write_json(staging / "input-bundle.json", {"schema_version": 1, "kind": "valpas-comparison-inputs",
                                                   "complete": True, "sha256": inventory})
        # Exclusive reservation prevents clobbering an existing empty directory.
        destination.mkdir()
        reserved = True
        os.replace(staging, destination)
        reserved = False
    except (OSError, ValueError) as exc:
        if reserved:
            destination.rmdir()  # only our still-empty reservation, never recursive
        if hasattr(exc, "issue"):
            raise
        fail("destination", "input bundle write failed: " + str(exc))
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def load_input_bundle(directory):
    """Validate completed owned inventory and reload without original sources."""
    directory = Path(directory)
    marker = _local_path("input-bundle.json", directory, "bundle")
    metadata = _json(_read(marker), "bundle")
    keys(metadata, ("schema_version", "kind", "complete", "sha256"), field="bundle")
    if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1 or metadata["kind"] != "valpas-comparison-inputs" or metadata["complete"] is not True:
        fail("bundle", "not a completed version-one input bundle")
    inventory = metadata["sha256"]
    if not isinstance(inventory, dict) or "manifest.json" not in inventory:
        fail("bundle.sha256", "manifest inventory missing")
    for name, digest in inventory.items():
        path = _local_path(name, directory, "bundle.inventory")
        if path.parent != directory.resolve() or path.suffix != ".json":
            fail("bundle.inventory", "only direct JSON bundle members permitted")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            fail("bundle.inventory", "content checksum mismatch: " + name)
    raw = _json(_read(directory / "manifest.json"), "manifest")
    if not isinstance(raw, dict) or not isinstance(raw.get("outputs"), list):
        fail("manifest", "invalid bundle manifest")
    named = {"manifest.json"}
    for d in raw["outputs"]:
        if not isinstance(d, dict) or not isinstance(d.get("data"), dict) or "path" not in d["data"]:
            fail("bundle", "bundle outputs require inventoried normalized files")
        if d["data"].get("format") != "normalized":
            fail("bundle", "expected normalized input records")
        named.add(d["data"]["path"])
    if named != set(inventory):
        fail("bundle.inventory", "inventory does not match consumed files")
    return load_manifest(directory / "manifest.json")
