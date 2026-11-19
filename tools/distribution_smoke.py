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
        for name in ("dashboard.css", "dashboard.js", "sessions.js", "shell.html"):
            data = resources.files("valpas.comparison").joinpath("assets", name).read_bytes()
            require(data == archive.read("valpas/comparison/assets/" + name), "installed asset differs: " + name)
            assets[name] = hashlib.sha256(data).hexdigest()
        modules = {}
        for name in ("reference", "session", "figures"):
            installed = importlib.import_module("valpas.comparison." + name)
            path = Path(installed.__file__).resolve()
            require(path.is_relative_to(root), "B2 module outside venv")
            data = path.read_bytes()
            require(data == archive.read("valpas/comparison/" + name + ".py"), "B2 module differs")
            modules[name] = hashlib.sha256(data).hexdigest()
    return {"python": sys.version, "prefix": sys.prefix, "module_path": str(module), "module_sha256": modules,
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
REFERENCE_TABLES = frozenset(("reference_endpoints", "reference_evidence", "reference_recovery", "reference_summary"))
B1_REQUEST = {"query_id": "M01", "candidate_id": "P01", "layer_id": "b1-observed",
              "h": 1, "omission": True, "group_field": "condition", "include_fraction": True}


def expected_tables(record):
    """Independent exact v3 oracle: optional B1, reference and session extensions."""
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
    references = record.get("b2_references")
    if "b2_references" in record:
        require(isinstance(references, dict) and set(references) == {"schema_version", "query_groups", "provenance_hash"},
                "invalid reference extension")
        require(type(references["schema_version"]) is int and references["schema_version"] == 1
                and type(references["query_groups"]) is bool, "invalid reference flags")
        value = references["provenance_hash"]
        require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
                "invalid reference digest")
    if "b2_session" in record:
        session = record["b2_session"]
        require(isinstance(session, dict) and set(session) == {"schema_version"}
                and type(session["schema_version"]) is int and session["schema_version"] == 1,
                "invalid session extension")
    return (SCIENTIFIC_TABLES | (PROFILE_TABLES if profiles else set())
            | (REFERENCE_TABLES if references else set())
            | ({"query_groups"} if references and references["query_groups"] else set())
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
                 "b1-html", "b1-tables", "b1-html-regenerated", "b1-tables-regenerated", "b1-hostile",
                 "b2-html", "b2-tables", "b2-html-regenerated", "b2-tables-regenerated",
                 "b2-session", "b2-session-tables", "b2-session-regenerated", "b2-session-tables-regenerated"):
        path = work / name
        record = json.loads((path / "comparison.json").read_text())
        # Public loader verifies every inventory checksum and exact scientific /
        # report parity from normalized data, with original inputs already gone.
        restored = load_comparison_bundle(path)
        check_table_inventory(record)
        require(record["software_version"] == metadata.version("valpas"), "wrong bundle version")
        require(restored.comparison_id == record["comparison_id"], "identity mismatch")
        identities.add(restored.comparison_id)
        is_b1 = name.startswith(("b1-", "b2-"))
        is_b2 = name.startswith("b2-")
        require(("b2_references" in record) == is_b2, "reference extension presence")
        require(("b2_session" in record) == name.startswith("b2-session"), "session extension presence")
        if is_b2:
            require(len(record["tables"]) == 20, "full B2 requires exactly twenty tables")
            require(restored.references is not None and restored.query_groups is not None, "B2 normalized content absent")
        if name.startswith("b2-session"):
            require(restored.initial_session is not None, "initial session missing")
            require(len(restored.initial_session.to_dict()["decisions"]) == 2, "initial decisions lost")
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
        if is_b2:
            for table, count in (("reference_endpoints", 3), ("reference_evidence", 5),
                                 ("reference_recovery", 54), ("reference_summary", 1080), ("query_groups", 2)):
                require(len(tables[name][table]) == count, "unexpected B2 count: " + table)
            rows = tables[name]["reference_recovery"]
            direct = next(r for r in rows if r["endpoint_id"] == "direct" and r["query_id"] == "M01"
                          and r["output_id"] == "pearson-run" and r["requested_depth"] == 1)
            require(direct["supported_nominations"] == direct["reachable_support"] == direct["total_known_support"] == 1,
                    "duplicate evidence inflated support")
            unreachable = next(r for r in rows if r["endpoint_id"] == "direct" and r["query_id"] == "M02")
            require(unreachable["total_known_support"] == 1 and unreachable["reachable_support"] == 0
                    and unreachable["recovery"] is None, "unreachable support became zero recovery")
            unassessed = next(r for r in rows if r["endpoint_id"] == "inferred" and r["query_id"] == "M02")
            require(unassessed["total_known_support"] is None and unassessed["hit"] is None, "unassessed became negative")
        html = path / "report.html"
        require(html.exists() == (name not in ("tables", "b1-tables", "b2-tables", "b2-session-tables")), "tables-only/HTML contract violated")
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
    for name in ("b2-tables", "b2-html-regenerated", "b2-tables-regenerated", "b2-session",
                 "b2-session-tables", "b2-session-regenerated", "b2-session-tables-regenerated"):
        require(tables["b2-html"] == tables[name], "B2 all-table parity failed: " + name)
    for name, exported in tables.items():
        for table in SCIENTIFIC_TABLES:
            require(exported[table] == tables["html"][table], "B1/profiles changed science: " + name + "/" + table)
    # Transport the installed Python results to the browser probe, not source imports.
    expected = {"diagnostic": tables["b1-html"]["diagnostics"][0]["result"],
                "groups": [r["result"] for r in tables["b1-html"]["group_summaries"]]}
    (work / "browser-expected.json").write_text(json.dumps(expected), encoding="utf-8")
    reference_tables = None
    for name in ("reference-only", "reference-only-regenerated"):
        path = work / name
        result = load_comparison_bundle(path)
        record = json.loads((path / "comparison.json").read_text())
        require(len(check_table_inventory(record)) == 15, "reference-only exact inventory")
        current = {t: read_table(path / info["path"]) for t, info in record["tables"].items()}
        require(all(rows == list(result.iter_table(t)) for t, rows in current.items()), "reference-only API parity")
        if reference_tables is not None:
            require(current == reference_tables, "source-free reference-only parity")
        reference_tables = current
        records[name] = {"comparison_id": result.comparison_id, "rows": {t: len(rows) for t, rows in current.items()}}
    return records


def session(work):
    from valpas.comparison import Session, load_comparison_bundle, load_session, load_shortlist, write_comparison
    result = load_comparison_bundle(work / "b2-html")
    state = Session.create(result, notes="Installed initial session: descriptive evidence, not validation")
    view = state.to_dict()["view"]
    view.update(query="M01", candidate="P01", referenceEndpoint="direct", evidenceFilter="all")
    state = state.with_view(view)
    for decision in ("investigate", "abstain"):
        state = state.add_decision(decision_id="initial-" + decision, decision=decision,
                                   rationale="Synthetic installed API decision", timestamp="2026-11-19T00:00:00Z")
    path = state.write(work / "api-session.json")
    require(load_session(path, result=result) == state, "API session roundtrip")
    short = state.shortlist()
    require(load_shortlist(short.write(work / "api-shortlist.json"), result=result) == short, "API shortlist roundtrip")
    write_comparison(result, work / "b2-session", initial_session=state)
    write_comparison(result, work / "b2-session-tables", initial_session=state, tables_only=True)
    return {"status": "passed", "decisions": 2, "content_id": state.to_dict()["content_id"]}


def check_figure(path, *, browser=False):
    import xml.etree.ElementTree as ET
    data = path.read_bytes()
    if path.suffix == ".pdf":
        require(data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:], "not a complete PDF")
    else:
        root = ET.fromstring(data)
        require(root.tag == "{http://www.w3.org/2000/svg}svg", "not SVG XML")
        require(not any(n.tag.rsplit("}", 1)[-1] in ("script", "image", "foreignObject") for n in root.iter()), "unsafe SVG elements")
        require(not any(k.rsplit("}", 1)[-1] == "href" and not v.startswith("#")
                        for n in root.iter() for k, v in n.attrib.items()), "external SVG resource")
        text = "".join(root.itertext())
        for token in ("M01", "P01", "b1-observed", "condition", "not model attribution"):
            require(token in text, "missing figure disclosure: " + token)
        if browser:
            require("bounded embedded scope" in text and "Not identical to Python" in text, "browser scope caption")
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def figures(work):
    from valpas.comparison import export_query_figure, load_comparison_bundle, load_session
    result = load_comparison_bundle(work / "b2-session-regenerated")
    state = load_session(work / "api-session.json", result=result)
    records = {}
    for suffix in ("svg", "pdf"):
        path = export_query_figure(result, query_id="M01", candidate_id="P01", layer_id="b1-observed",
                                   output=work / ("api-figure." + suffix), color="condition",
                                   group="condition", h=1, omission=True)
        records["api-" + suffix] = check_figure(path)
        records["cli-" + suffix] = check_figure(work / ("cli-figure." + suffix))
    path = export_query_figure(result, query_id="M01", candidate_id="P01", layer_id="b1-observed",
                               output=work / "decision-figure.svg", session=state, decision_id="initial-investigate")
    records["decision-svg"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
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
    elif mode == "session":
        result = session(Path(args[0]))
    elif mode == "figures":
        result = figures(Path(args[0]))
    elif mode == "legacy":
        result = legacy()
    else:
        raise ValueError("unknown smoke mode: " + mode)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
