"""Installed-artifact assertions, executed by a private venv with Python -I.

No checkout imports, sys.path changes, mocks, skipped dependencies or training.
"""
import csv
import gzip
import hashlib
from html.parser import HTMLParser
import importlib
import importlib.metadata as metadata
import importlib.resources as resources
import json
from pathlib import Path
import sys
import sysconfig
import zipfile
from urllib.parse import unquote, urlsplit


def require(value, message):
    if not value:
        raise AssertionError(message)


def check_direct_url(direct, wheel):
    url = urlsplit(direct["url"])
    require(url.scheme == "file" and Path(unquote(url.path)).resolve() == wheel.resolve(),
            "wrong installed artifact")
    require(direct["archive_info"]["hashes"]["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "installed artifact hash differs")


def environment(wheel):
    import valpas
    root = Path(sys.prefix).resolve()
    require(sys.prefix != sys.base_prefix, "not a venv")
    require("include-system-site-packages = false" in (root / "pyvenv.cfg").read_text(), "shared site-packages")
    module = Path(valpas.__file__).resolve()
    require(module.is_relative_to(root), "valpas imported outside venv: " + str(module))
    dist = metadata.distribution("valpas")
    require(Path(dist.locate_file("")).resolve().is_relative_to(root), "distribution outside venv")
    require(valpas.__version__ == dist.version, "module/metadata version mismatch")
    direct = json.loads(dist.read_text("direct_url.json"))
    require(not direct.get("dir_info", {}).get("editable"), "editable install")
    check_direct_url(direct, wheel)
    site = Path(sysconfig.get_path("purelib"))
    require(not list(site.glob("*.egg-link")), "editable egg-link")
    for path in site.glob("*.pth"):
        require("__editable__" not in path.read_text(), "editable pth")
    assets = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in ("dashboard.css", "dashboard.js", "shell.html"):
            data = resources.files("valpas.comparison").joinpath("assets", name).read_bytes()
            require(data == archive.read("valpas/comparison/assets/" + name), "installed asset differs: " + name)
            assets[name] = hashlib.sha256(data).hexdigest()
    return {"python": sys.version, "prefix": sys.prefix, "module_path": str(module),
            "version": dist.version, "direct_url": direct, "asset_sha256": assets,
            "distributions": sorted(({"name": d.metadata["Name"], "version": d.version}
                                     for d in metadata.distributions()), key=lambda d: d["name"].lower())}


class OfflineHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.policy = None
        self.payload = False
        self.inline_scripts = 0
        self.styles = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        require(not any(key in attrs for key in ("src", "href", "srcset")), "external/local resource reference")
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "content-security-policy":
            self.policy = attrs.get("content", "")
        if tag == "script":
            self.inline_scripts += 1
            self.payload |= attrs.get("id") == "comparison-data"
        if tag == "style":
            self.styles += 1


def read_table(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        return [{k: json.loads(v) for k, v in row.items()} for row in csv.DictReader(handle)]


SCIENTIFIC_TABLES = frozenset((
    "outputs", "configuration_differences", "coverage", "exclusions", "candidate_ranks",
    "agreement", "run_recurrence", "agreement_summary", "query_summary", "dataset_summary",
))
PROFILE_TABLES = frozenset(("profile_values", "feature_coverage"))
B1_REQUEST = {"query_id": "M01", "candidate_id": "P01", "layer_id": "b1-observed",
              "h": 1, "omission": True, "group_field": "condition", "include_fraction": True}


def expected_tables(record):
    """Independent exact v3 inventory oracle, including independently optional B1 tables."""
    require(type(record["schema_version"]) is int and record["schema_version"] == 3,
            "expected current result schema v3")
    require(record["complete"] is True, "incomplete bundle")
    profiles, b1 = record["report"]["profiles"], record["b1"]
    require(type(profiles) is bool and type(b1["sample_metadata"]) is bool,
            "presence flags must be boolean")
    requests = b1["diagnostic_requests"]
    require(isinstance(requests, list), "requests must be a list")
    require(not requests or profiles, "requests require profiles")
    groups = any(r["group_field"] is not None for r in requests)
    require(not groups or b1["sample_metadata"], "groups require metadata")
    return (SCIENTIFIC_TABLES | (PROFILE_TABLES if profiles else set())
            | ({"sample_metadata"} if b1["sample_metadata"] else set())
            | ({"diagnostics"} if requests else set())
            | ({"group_summaries"} if groups else set()))


def check_table_inventory(record):
    expected = expected_tables(record)
    require(set(record["tables"]) == expected, "wrong exact table inventory")
    require(set(record["table_schema"]) == expected, "wrong exact table schema inventory")
    return expected


def bundles(work):
    from valpas.comparison import load_comparison_bundle
    records, tables, identities = {}, {}, set()
    for name in ("html", "tables", "no-profile", "html-regenerated", "tables-regenerated",
                 "b1-html", "b1-tables", "b1-html-regenerated", "b1-tables-regenerated", "b1-hostile"):
        path = work / name
        record = json.loads((path / "comparison.json").read_text())
        # Public loader verifies every inventory checksum and exact scientific /
        # report parity from normalized data, with original inputs already gone.
        restored = load_comparison_bundle(path)
        check_table_inventory(record)
        require(record["software_version"] == metadata.version("valpas"), "wrong bundle version")
        require(restored.comparison_id == record["comparison_id"], "identity mismatch")
        identities.add(restored.comparison_id)
        is_b1 = name.startswith("b1-")
        require(record["b1"] == {"sample_metadata": is_b1,
                                  "diagnostic_requests": [B1_REQUEST] if is_b1 else []},
                "unexpected B1 request scope")
        tables[name] = {}
        for table, info in record["tables"].items():
            rows = read_table(path / info["path"])
            require(len(rows) == info["rows"], "row count differs")
            require(rows == list(restored.iter_table(table)), "API/table mismatch")
            tables[name][table] = rows
        dataset = tables[name]["dataset_summary"][0]
        require(dataset["outputs"] == 3 and dataset["declared_queries"] == 2 and dataset["observation_count"] == 6,
                "unexpected synthetic dataset")
        require(record["report"]["profiles"] == (name != "no-profile"), "profile metadata differs")
        if is_b1:
            require(len(tables[name]["diagnostics"]) == 1, "diagnostics expanded beyond requested pair")
            require(len(tables[name]["group_summaries"]) == 2, "groups expanded beyond requested features")
            rows = tables[name]["sample_metadata"]
            require(len(rows) == 24 and len({(r["observation_id"], r["field"]) for r in rows}) == 24,
                    "metadata must occur once per observation/field, not per pair")
            require(len(tables[name]["profile_values"]) == 30, "profiles duplicated per diagnostic")
            require({r["feature_id"] for r in tables[name]["group_summaries"]} == {"M01", "P01"},
                    "unexpected group feature scope")
            diagnostic = tables[name]["diagnostics"][0]
            require(all(diagnostic[k] == B1_REQUEST[k] for k in
                        ("query_id", "candidate_id", "layer_id", "h", "omission")), "wrong diagnostic request")
        html = path / "report.html"
        require(html.exists() == (name not in ("tables", "b1-tables")), "tables-only/HTML contract violated")
        if html.exists():
            parser = OfflineHTML()
            parser.feed(html.read_text(encoding="utf-8"))
            require(parser.policy and "connect-src 'none'" in parser.policy and "default-src 'none'" in parser.policy,
                    "missing offline CSP")
            require(parser.payload and parser.inline_scripts == 2 and parser.styles == 1, "assets not embedded")
        records[name] = {"comparison_id": restored.comparison_id, "path": str(path),
                         "schema_version": record["schema_version"], "b1": record["b1"],
                         "rows": {t: r["rows"] for t, r in record["tables"].items()},
                         "metadata_sha256": hashlib.sha256((path / "comparison.json").read_bytes()).hexdigest()}
    require(len(identities) == 1, "scientific identity changed between exports")
    for name in ("tables", "html-regenerated", "tables-regenerated"):
        require(tables["html"] == tables[name], "scientific/profile table parity failed: " + name)
    for name in ("b1-tables", "b1-html-regenerated", "b1-tables-regenerated"):
        require(tables["b1-html"] == tables[name], "B1 all-table parity failed: " + name)
    for name, exported in tables.items():
        for table in SCIENTIFIC_TABLES:
            require(exported[table] == tables["html"][table], "B1/profiles changed science: " + name + "/" + table)
    # Transport the installed Python results to the browser probe, not source imports.
    expected = {"diagnostic": tables["b1-html"]["diagnostics"][0]["result"],
                "groups": [r["result"] for r in tables["b1-html"]["group_summaries"]]}
    (work / "browser-expected.json").write_text(json.dumps(expected), encoding="utf-8")
    return records


def legacy():
    import valpas
    resolved = {}
    for name in valpas.__all__:
        value = getattr(valpas, name)
        require(value is getattr(valpas, name), "unstable legacy export")
        resolved[name] = getattr(value, "__module__", getattr(value, "__name__", str(type(value))))
    for name in ("valpas.valpas_core", "valpas.io", "valpas.visualization.heatmap"):
        importlib.import_module(name)
    return {"status": "passed", "exports": resolved, "torch_version": metadata.version("torch"),
            "training_performed": False}


def main():
    mode, *args = sys.argv[1:]
    destination = Path(args.pop())
    if mode == "environment":
        result = environment(Path(args[0]))
    elif mode == "bundles":
        result = bundles(Path(args[0]))
    elif mode == "legacy":
        result = legacy()
    else:
        raise ValueError("unknown smoke mode: " + mode)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
