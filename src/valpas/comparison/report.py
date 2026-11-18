"""A2 tables-only comparison bundles. No HTML, figures, or model execution."""
from contextlib import ExitStack
from dataclasses import asdict, replace
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from valpas import __version__
from .adapters import _json, _read
from .bundles import _write_json
from .engine import (ComparisonResult, POLICY_VERSIONS, TABLE_COLUMNS,
                     canonical_json, compare_results, normalized_descriptor)
from .models import (ComparisonInput, ComparisonSettings, Issue, PairValue,
                     fail, freeze, keys, thaw)

KIND = "valpas-comparison-result"
MARKER = "comparison.json"
TABLE_SCHEMA = {name: {"columns": cols, "cell_encoding": "json",
    "null": "JSON null means unavailable/not applicable; consult status and reason",
    "units": "ordinal ranks/counts; unitless fractions; native scores/counts retain descriptor semantics"}
    for name, cols in TABLE_COLUMNS.items()}
from .profiles import ProfileData, PROFILE_COLUMNS
from .browser import ReportSettings, render_report, safe_json


def table_schema(columns):
    return {name: {**TABLE_SCHEMA["coverage"], "columns": cols} for name, cols in columns.items()}


LONG_TABLES = {"candidate_ranks", "run_recurrence", "exclusions", "profile_values"}
README = """# Saved-output comparison (Release A)

Start with dataset_summary.csv, query_summary.csv and agreement_summary.csv;
then inspect agreement.csv, coverage.csv and the compressed detailed tables.
Every CSV cell is a JSON value (strings remain exact; null is not zero).
comparison.json records table schemas, resolved settings, normalized inputs,
source fingerprints, software/policy versions, warnings and completion inventory.

Use valpas.comparison.load_comparison_bundle to regenerate scientific tables
without original paths or models. This is a comparison-result bundle, NOT an
A1 input bundle. Open report.html directly from disk when present; no server or
network needed. Optional profiles are saved once in profiles.json and complete
profile tables. Report subsets never change full scientific tables. No B1/B2
reference analysis, diagnostics or session state. Agreement is not correctness;
seed runs are not biological replicates. Native inspection is descriptive only.
All declared queries are compared under the explicit pool policy. No target
metabolite/protein is required. Canonical exports retain sensitive IDs/metadata
and are not spreadsheet-escaped or privacy-filtered.
"""


def _digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _table_name(name):
    return name + (".csv.gz" if name in LONG_TABLES else ".csv")


def _open_table(path, mode):
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8", newline="")
    return path.open(mode, encoding="utf-8", newline="")


def _write_tables(result, directory):
    records = {}
    with ExitStack() as stack:
        writers = {}
        for name, columns in result.table_columns.items():
            filename = _table_name(name)
            handle = stack.enter_context(_open_table(directory / filename, "x"))
            writer = csv.writer(handle)
            writer.writerow(columns)
            writers[name] = writer
            records[name] = {"path": filename, "rows": 0}
        def emit(name, row):
            if set(row) != set(result.table_columns[name]):
                fail("table." + name, "internal row/schema mismatch")
            writers[name].writerow([canonical_json(row[c]) for c in result.table_columns[name]])
            records[name]["rows"] += 1
        for name in result.summaries:
            for row in result.iter_table(name):
                emit(name, row)
        for name, row in result.iter_detail_tables(set(TABLE_COLUMNS) - result.summaries.keys()):
            emit(name, row)
        for name in set(result.table_columns) - set(TABLE_COLUMNS):
            for row in result.iter_table(name):
                emit(name, row)
    return records


def _write_payload(result, staging, tables_only=False, report_settings=None):
    settings = report_settings or result.report_settings or ReportSettings()
    report = {"settings": settings.to_dict(), "profiles": result.profiles is not None, "payload": None}
    if not tables_only:
        html, payload, record = render_report(result, settings)
        (staging / "report.html").write_text(html, encoding="utf-8")
        (staging / "report_payload.json").write_text(safe_json(payload), encoding="utf-8")
        report["payload"] = record
    if result.profiles is not None:
        _write_json(staging / "profiles.json", result.profiles.to_dict())
    normalized = []
    for i, output in enumerate(result.outputs):
        filename = f"normalized-{i:04d}.jsonl.gz"
        with gzip.open(staging / filename, "xt", encoding="utf-8", newline="\n") as handle:
            for (q, c), value in sorted(output.pairs.items()):
                handle.write(canonical_json({"query_id": q, "candidate_id": c, **asdict(value)}) + "\n")
        normalized.append({"descriptor": normalized_descriptor(output), "path": filename,
                           "warnings": [asdict(w) for w in output.warnings]})
    tables = _write_tables(result, staging)
    with (staging / "README.md").open("x", encoding="utf-8") as handle:
        handle.write(README)
    inventory = {p.name: {"sha256": _digest(p), "size_bytes": p.stat().st_size} for p in sorted(staging.iterdir())}
    _write_json(staging / MARKER, {"schema_version": 2, "kind": KIND, "complete": True,
        "comparison_id": result.comparison_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "software_version": __version__, "policy_versions": POLICY_VERSIONS,
        "settings": result.settings.to_dict(), "dataset": thaw(result.dataset),
        "scope": {"analysis": "all_declared_queries_under_pool_policy", "tables_only": tables_only, "html": not tables_only},
        "report": report,
        "normalized_inputs": normalized, "input_fingerprints": thaw(result.input_fingerprints),
        "source_fingerprints": thaw(result.source_fingerprints),
        "warnings": [asdict(w) for w in result.warnings], "table_schema": table_schema(result.table_columns),
        "tables": tables, "inventory": inventory})


def _checked_metadata(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        fail("bundle", "expected a regular comparison bundle directory")
    marker = directory / MARKER
    if marker.is_symlink() or not marker.is_file():
        fail("bundle", "missing regular comparison.json completion record")
    m = _json(_read(marker), "bundle")
    keys(m, ("schema_version", "kind", "complete", "comparison_id", "created_at", "software_version",
             "policy_versions", "settings", "dataset", "scope", "normalized_inputs", "input_fingerprints",
             "source_fingerprints", "warnings", "table_schema", "tables", "inventory"),
         ("report",) if m.get("schema_version") == 2 else (), field="bundle")
    if type(m["schema_version"]) is not int or m["schema_version"] not in (1, 2) or m["kind"] != KIND or m["complete"] is not True:
        fail("bundle", "not a completed supported comparison-result bundle", remediation="Use load_input_bundle for A1 input bundles; regenerate incomplete comparison bundles.")
    columns = dict(TABLE_COLUMNS)
    if m["schema_version"] == 2:
        keys(m.get("report"), ("settings", "profiles", "payload"), field="bundle.report")
        ReportSettings.from_dict(m["report"]["settings"])
        if type(m["report"]["profiles"]) is not bool:
            fail("bundle.report", "profiles must be boolean")
        if m["report"]["profiles"]:
            columns.update(PROFILE_COLUMNS)
    if m["software_version"] != __version__ or m["policy_versions"] != POLICY_VERSIONS or m["table_schema"] != table_schema(columns):
        fail("bundle.schema", "unsupported policy versions or table schema")
    scope = m["scope"]
    keys(scope, ("analysis", "tables_only", "html"), field="bundle.scope")
    if scope["analysis"] != "all_declared_queries_under_pool_policy" or type(scope["html"]) is not bool or type(scope["tables_only"]) is not bool or scope["html"] == scope["tables_only"] or (m["schema_version"] == 1 and scope["html"]):
        fail("bundle.scope", "unsupported analysis/report scope")
    if m["schema_version"] == 2 and (m["report"]["payload"] is not None) != scope["html"]:
        fail("bundle.report", "payload presence differs from scope")
    if not isinstance(m["normalized_inputs"], list) or len(m["normalized_inputs"]) < 2:
        fail("bundle.normalized_inputs", "at least two normalized outputs required")
    named = {"README.md"}
    if m["schema_version"] == 2:
        if m["report"]["profiles"]:
            named.add("profiles.json")
        if scope["html"]:
            named.update(("report.html", "report_payload.json"))
    for i, item in enumerate(m["normalized_inputs"]):
        keys(item, ("descriptor", "path", "warnings"), field="bundle.normalized_inputs")
        if item["path"] != f"normalized-{i:04d}.jsonl.gz":
            fail("bundle.inventory", "unexpected normalized member name")
        named.add(item["path"])
    keys(m["tables"], columns, field="bundle.tables")
    for name, record in m["tables"].items():
        keys(record, ("path", "rows"), field="bundle.tables." + name)
        if record["path"] != _table_name(name) or type(record["rows"]) is not int or record["rows"] < 0:
            fail("bundle.tables", "invalid table path or row count")
        named.add(record["path"])
    if not isinstance(m["inventory"], dict) or set(m["inventory"]) != named:
        fail("bundle.inventory", "inventory differs from required normalized/table members")
    if {p.name for p in directory.iterdir()} != named | {MARKER}:
        fail("bundle.inventory", "missing or foreign files; refusing to treat directory as an owned bundle")
    for name, record in m["inventory"].items():
        keys(record, ("sha256", "size_bytes"), field="bundle.inventory")
        path = directory / name
        if path.is_symlink() or not path.is_file():
            fail("bundle.inventory", "nonregular or symlink member: " + name)
        if path.stat().st_size != record["size_bytes"] or _digest(path) != record["sha256"]:
            fail("bundle.inventory", "content checksum/size mismatch: " + name)
    return m


def _validate_tables(result, directory, metadata):
    """Check CSV schema, row counts AND parity with normalized saved values."""
    with ExitStack() as stack:
        readers, counts = {}, {}
        for name, columns in result.table_columns.items():
            reader = csv.reader(stack.enter_context(_open_table(directory / _table_name(name), "r")))
            if next(reader, None) != columns:
                fail("bundle.table", "column schema mismatch: " + name)
            readers[name] = reader
        def check(name, expected):
            actual = next(readers[name], None)
            if actual != [canonical_json(expected[c]) for c in result.table_columns[name]]:
                fail("bundle.table", "table differs from normalized saved values: " + name)
            counts[name] = counts.get(name, 0) + 1
        for name in result.summaries:
            for row in result.iter_table(name):
                check(name, row)
        for name, row in result.iter_detail_tables(set(TABLE_COLUMNS) - result.summaries.keys()):
            check(name, row)
        for name in set(result.table_columns) - set(TABLE_COLUMNS):
            for row in result.iter_table(name):
                check(name, row)
        for name, reader in readers.items():
            if next(reader, None) is not None or counts.get(name, 0) != metadata["tables"][name]["rows"]:
                fail("bundle.table", "row inventory mismatch: " + name)


def load_comparison_bundle(directory):
    """Reload normalized v1/v2 results with completion/inventory/schema/parity checks.

    Original source paths are provenance only and are never opened. Reading the
    normalized values recomputes saved-value ranks/metrics, not associations.
    """
    directory = Path(directory)
    try:
        m = _checked_metadata(directory)
        outputs = []
        for item in m["normalized_inputs"]:
            d = item["descriptor"]
            if not isinstance(d, dict) or not isinstance(d.get("data"), dict) or d["data"].get("format") != "normalized" or d["data"].get("inline") != {"records": []} or "path" in d["data"]:
                fail("bundle.normalized_inputs", "expected self-contained normalized descriptor")
            pairs = {}
            with gzip.open(directory / item["path"], "rt", encoding="utf-8") as handle:
                for line in handle:
                    row = _json(line, "bundle.normalized_record")
                    keys(row, ("query_id", "candidate_id", "status", "score", "rank", "count", "reason"), field="bundle.normalized_record")
                    pair = (row.pop("query_id"), row.pop("candidate_id"))
                    if pair in pairs:
                        fail("bundle.normalized_record", "duplicate pair")
                    pairs[pair] = PairValue(**row)
            outputs.append(ComparisonInput(d, pairs, tuple(Issue(**w) for w in item["warnings"])))
        profiles = None
        report_settings = None
        if m["schema_version"] == 2:
            report_settings = ReportSettings.from_dict(m["report"]["settings"])
            if m["report"]["profiles"]:
                profiles = ProfileData.from_dict(_json(_read(directory / "profiles.json"), "bundle.profiles"))
        result = compare_results(outputs, ComparisonSettings.from_dict(m["settings"]), dataset=m["dataset"], profiles=profiles)
        result = replace(result, report_settings=report_settings)
        if result.comparison_id != m["comparison_id"] or thaw(result.input_fingerprints) != m["input_fingerprints"]:
            fail("bundle.comparison_id", "normalized content/settings identity mismatch (including software/policy version)")
        if canonical_json([asdict(w) for w in result.warnings]) != canonical_json(m["warnings"]):
            fail("bundle.warnings", "warnings differ from normalized metadata")
        _validate_tables(result, directory, m)
        if m["scope"]["html"]:
            html, payload, record = render_report(result, report_settings)
            if record != m["report"]["payload"] or (directory / "report_payload.json").read_text(encoding="utf-8") != safe_json(payload) or (directory / "report.html").read_text(encoding="utf-8") != html:
                fail("bundle.report", "report differs from normalized saved values/settings")
        # Prevent overwrite of a bundle actively supplying this result, even
        # though the original pre-export paths are not needed for reproduction.
        protected = tuple(str(p.resolve()) for p in directory.iterdir())
        return replace(result, source_fingerprints=freeze(m["source_fingerprints"]), protected_sources=protected)
    except (OSError, ValueError, TypeError, KeyError, EOFError) as exc:
        if hasattr(exc, "issue"):
            raise
        fail("bundle", "cannot reload comparison bundle: " + str(exc), remediation="Use an intact completed comparison bundle or regenerate from saved inputs.")


def write_comparison(result, destination, *, tables_only=False, overwrite=False, report_settings=None):
    """Stage complete tables and an optional offline HTML report; publish atomically.

    Default refusal includes empty destinations. Explicit overwrite accepts only
    intact owned comparison bundles with exactly the expected inventory, never a source
    or unrelated directory. Replacement uses a backup rename and rollback on
    publication failure; no partial bundle is visible as the new destination.
    Not a transaction against hostile concurrent filesystem modification.
    """
    if not isinstance(result, ComparisonResult):
        fail("result", "expected compare_results or load_comparison_bundle result")
    if type(tables_only) is not bool or type(overwrite) is not bool:
        fail("tables_only", "tables_only and overwrite must be boolean")
    if report_settings is not None and not isinstance(report_settings, ReportSettings):
        fail("report_settings", "expected ReportSettings")
    destination = Path(destination)
    if ".." in destination.parts or destination.is_symlink():
        fail("destination", "parent traversal and destination symlinks prohibited")
    destination = destination.absolute()
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        fail("destination", "parent must exist and must not be a symlink")
    destination = destination.parent.resolve() / destination.name
    protected = set(result.protected_sources) | {f["path"] for f in result.source_fingerprints}
    for source in protected:
        if Path(source).resolve().is_relative_to(destination):
            fail("destination", "destination contains a consumed source; overwrite prohibited", remediation="Choose a separate new output directory.")
    exists = destination.exists()
    if exists:
        if not overwrite:
            fail("destination", "existing destination refused", remediation="Choose a new directory or explicitly overwrite an intact owned comparison bundle that contains no inputs.")
        load_comparison_bundle(destination)
    staging = Path(tempfile.mkdtemp(prefix="." + destination.name + ".partial-", dir=destination.parent))
    backup, reserved = None, False
    try:
        _write_payload(result, staging, tables_only, report_settings)
        if exists:
            # Recheck just before mutation, so newly added unrelated files are
            # not deleted by a long-running export.
            load_comparison_bundle(destination)
            backup = Path(tempfile.mkdtemp(prefix="." + destination.name + ".previous-", dir=destination.parent))
            backup.rmdir()
            os.replace(destination, backup)
        else:
            destination.mkdir()  # exclusive reservation; never clobber a racer
            reserved = True
        try:
            os.replace(staging, destination)
            reserved = False
        except BaseException:
            if backup is not None and backup.exists():
                os.replace(backup, destination)
            raise
        if backup is not None:
            shutil.rmtree(backup)
    except (OSError, ValueError) as exc:
        if hasattr(exc, "issue"):
            raise
        fail("destination", "comparison write failed: " + str(exc), remediation="Check permissions/disk space; any .previous directory contains the prior completed bundle.")
    finally:
        if reserved:
            destination.rmdir()
        if staging.exists():
            shutil.rmtree(staging)
    return destination
