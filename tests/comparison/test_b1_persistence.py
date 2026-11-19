"""B1 API, requested-only exports, durability, and genuine legacy-shape migration."""
import csv
from dataclasses import FrozenInstanceError, asdict, replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_a1_contracts import FIXTURE
from test_a3_report import fixture_result, profile_layer, profiled_result
from valpas import __version__
from valpas.comparison import (
    SampleMetadata, DiagnosticRequest, ComparisonValidationError, ProfileData,
    ReportSettings, compare_results, load_manifest, load_sample_metadata,
    load_comparison_bundle, write_comparison, covariance_diagnostic, group_summary,
)
from valpas.comparison import diagnostics
from valpas.comparison.browser import build_report_payload, render_report, safe_json
from valpas.comparison.engine import TABLE_COLUMNS, canonical_json, normalized_descriptor, POLICY_VERSIONS
from valpas.comparison.models import thaw


def metadata_doc(result=None):
    result = result or fixture_result()
    return {"schema_version": 1, "dataset": thaw(result.dataset),
            "fields": {"condition": "categorical", "age": "continuous"},
            "records": [{"observation_id": sid, "values": {"condition": "A" if i < 3 else "B", "age": i}}
                        for i, sid in enumerate(result.dataset["observation_ids"])]}


def request(**changes):
    return DiagnosticRequest(**({"query_id": "M01", "candidate_id": "P01", "layer_id": "measured",
                                 "h": 1, "omission": True, "group_field": "condition"} | changes))


def b1_result(requests=None, metadata=None, profiles=True):
    base = fixture_result()
    return compare_results(base.outputs, base.settings, dataset=base.dataset,
                           profiles=ProfileData([profile_layer(base)]) if profiles else None,
                           sample_metadata=metadata or SampleMetadata.from_dict(metadata_doc(base)),
                           diagnostic_requests=[request()] if requests is None else requests)


def digest_record(path):
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def legacy_bundle(result, path, version, *, html=False, omit_metadata=False):
    """Construct historical schemas directly, NOT a relabeled v3 writer output.

    Fixed representative legacy HTML deliberately differs from current assets;
    the A3 payload projection, tables, normalized records and inventory are real.
    No B1 key/artifact exists. This fixture needs no Git history or source files.
    """
    path.mkdir()
    normalized = []
    for i, output in enumerate(result.outputs):
        name = f"normalized-{i:04d}.jsonl.gz"
        with gzip.open(path / name, "wt", encoding="utf-8") as handle:
            for (q, c), value in sorted(output.pairs.items()):
                handle.write(canonical_json({"query_id": q, "candidate_id": c, **asdict(value)}) + "\n")
        normalized.append({"descriptor": normalized_descriptor(output), "path": name,
                           "warnings": [asdict(w) for w in output.warnings]})
    tables, schemas = {}, {}
    for name, columns in result.table_columns.items():
        compressed = name in {"candidate_ranks", "run_recurrence", "exclusions", "profile_values"}
        filename = name + (".csv.gz" if compressed else ".csv")
        opener = gzip.open if compressed else open
        with opener(path / filename, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            rows = list(result.iter_table(name))
            writer.writerows([[canonical_json(row[c]) for c in columns] for row in rows])
        tables[name] = {"path": filename, "rows": len(rows)}
        schemas[name] = {"columns": columns, "cell_encoding": "json",
                         "null": "JSON null means unavailable/not applicable; consult status and reason",
                         "units": "ordinal ranks/counts; unitless fractions; native scores/counts retain descriptor semantics"}
    (path / "README.md").write_text("Historical saved-output bundle\n", encoding="utf-8")
    marker = {"schema_version": version, "kind": "valpas-comparison-result", "complete": True,
              "comparison_id": result.comparison_id, "created_at": "2026-01-01T00:00:00+00:00",
              "software_version": __version__, "policy_versions": POLICY_VERSIONS,
              "settings": result.settings.to_dict(), "dataset": thaw(result.dataset),
              "scope": {"analysis": "all_declared_queries_under_pool_policy", "tables_only": not html, "html": html},
              "normalized_inputs": normalized, "input_fingerprints": thaw(result.input_fingerprints),
              "source_fingerprints": thaw(result.source_fingerprints), "warnings": [asdict(w) for w in result.warnings],
              "table_schema": schemas, "tables": tables}
    if version == 2:
        settings = ReportSettings(max_interactive_depth=2, omit_metadata=omit_metadata)
        report = {"settings": settings.to_dict(), "profiles": result.profiles is not None, "payload": None}
        if result.profiles is not None:
            (path / "profiles.json").write_text(json.dumps(result.profiles.to_dict()), encoding="utf-8")
        if html:
            payload = build_report_payload(result, settings)
            del payload["sample_metadata"]
            payload["omissions"] = [s.replace("; sample metadata;", ";") for s in payload["omissions"]]
            raw = safe_json(payload)
            (path / "report_payload.json").write_text(raw, encoding="utf-8")
            (path / "report.html").write_text(
                '<!doctype html><html><body><h1>Legacy A3 renderer</h1>'
                '<script id="comparison-data" type="application/json">' + raw +
                '</script><script>document.body.dataset.legacy="true";</script></body></html>', encoding="utf-8")
            report["payload"] = {"payload_bytes": len(raw.encode("utf-8")),
                                 "payload_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
        marker["report"] = report
    marker["inventory"] = {p.name: digest_record(p) for p in path.iterdir()}
    (path / "comparison.json").write_text(json.dumps(marker), encoding="utf-8")
    return path


class B1PersistenceCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def marker(self, path):
        return json.loads((path / "comparison.json").read_text())

    def edit_marker(self, path, mutate):
        marker = self.marker(path)
        mutate(marker)
        (path / "comparison.json").write_text(json.dumps(marker))

    def refresh(self, path, name):
        self.edit_marker(path, lambda m: m["inventory"].__setitem__(name, digest_record(path / name)))

    def assert_tables(self, left, right):
        self.assertEqual(left.comparison_id, right.comparison_id)
        self.assertEqual(left.table_names, right.table_names)
        for name in left.table_names:
            self.assertEqual(list(left.iter_table(name)), list(right.iter_table(name)), name)

    def test_public_api_immutability_identity_and_ten_scientific_tables(self):
        base = fixture_result()
        doc = metadata_doc(base)
        meta = SampleMetadata.from_dict(doc)
        requests = [request().to_dict()]
        result = b1_result(requests, meta)
        requests[0]["query_id"] = "changed"
        doc["records"][0]["values"]["condition"] = "changed"
        self.assertEqual(result.diagnostic_requests, (request(),))
        self.assertEqual(result.sample_metadata.records[0]["values"]["condition"], "A")
        with self.assertRaises(FrozenInstanceError):
            result.sample_metadata = None
        with self.assertRaises(FrozenInstanceError):
            result.diagnostic_requests[0].h = 9
        with self.assertRaises(TypeError):
            result.sample_metadata.fields["age"] = "categorical"
        detached = list(result.iter_table("diagnostics"))
        detached[0]["result"]["products"].clear()
        self.assertTrue(next(result.iter_table("diagnostics"))["result"]["products"])
        self.assertEqual(base.comparison_id, result.comparison_id)
        self.assertEqual(base.input_fingerprints, result.input_fingerprints)
        self.assertEqual(len(TABLE_COLUMNS), 10)
        for name in TABLE_COLUMNS:
            self.assertEqual(list(base.iter_table(name)), list(result.iter_table(name)))
        changed = b1_result([request(h=3, omission=False)], replace(meta, records=()))
        self.assertEqual(result.comparison_id, changed.comparison_id)

    def test_no_eager_or_all_pair_diagnostics_and_optional_tables(self):
        with patch.object(diagnostics, "covariance_diagnostic", side_effect=AssertionError("eager")), \
             patch.object(diagnostics, "group_summary", side_effect=AssertionError("eager")):
            result = b1_result([])
            self.assertNotIn("diagnostics", result.table_names)
            self.assertNotIn("group_summaries", result.table_names)
            build_report_payload(result, ReportSettings(max_interactive_depth=1))
            write_comparison(result, self.root / "no-requests")
            requested = b1_result([request(group_field=None)])
            build_report_payload(requested, ReportSettings(max_interactive_depth=1))
        with patch.object(diagnostics, "covariance_diagnostic", wraps=covariance_diagnostic) as called:
            rows = list(requested.iter_table("diagnostics"))
            self.assertEqual(called.call_count, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["query_id"], rows[0]["candidate_id"]), ("M01", "P01"))
        self.assertNotIn("group_summaries", requested.table_names)
        self.assertEqual(rows[0]["result"], covariance_diagnostic(requested.profiles.layers[0], requested.dataset,
                                                                 "M01", "P01", h=1, omission=True))

    def test_group_deduplication_includes_namespace_layer_field_fraction(self):
        requests = [request(), request(candidate_id="P02"), request(h=2),
                    request(include_fraction=False), request(group_field="other"), request(layer_id="second")]
        meta = SampleMetadata.from_dict(metadata_doc())
        meta = replace(meta, fields={**meta.fields, "other": "categorical"})
        base = b1_result([], meta)
        layer = profile_layer(); layer["layer_id"] = "second"
        result = compare_results(base.outputs, base.settings, profiles=ProfileData([profile_layer(), layer]),
                                 sample_metadata=meta, diagnostic_requests=requests)
        with patch.object(diagnostics, "group_summary", wraps=group_summary) as called:
            rows = list(result.iter_table("group_summaries"))
            self.assertEqual(called.call_count, 9)  # 3 base + 2 fraction + 2 field + 2 layer
        keys = [(r["layer_id"], canonical_json(r["namespace"]), r["feature_id"], r["field"], r["include_fraction"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(list(result.iter_table("diagnostics"))), len(requests))
        row = rows[0]
        self.assertEqual(row["result"], group_summary(result.profiles.layers[0], result.dataset, meta,
                                                     row["namespace"], row["feature_id"], row["field"]))
        self.assertEqual(len(list(result.iter_table("profile_values"))), 60)

    def test_metadata_without_profiles_and_missing_rows_once(self):
        doc = metadata_doc(); doc["records"] = doc["records"][:1]
        result = b1_result([], SampleMetadata.from_dict(doc), profiles=False)
        rows = list(result.iter_table("sample_metadata"))
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r["status"] == "missing" for r in rows), 10)
        self.assertNotIn("profile_values", result.table_names)
        self.assertEqual(build_report_payload(result)["sample_metadata"], result.sample_metadata.to_dict())
        out = write_comparison(result, self.root / "metadata-only")
        self.assert_tables(result, load_comparison_bundle(out))
        self.assertFalse((out / "profiles.json").exists())

    def test_invalid_request_scope_types_and_binding(self):
        base = b1_result([])
        cases = [request(query_id="missing"), request(candidate_id="M01"), request(layer_id="missing"),
                 request(group_field="age"), request(group_field="missing")]
        for req in cases:
            with self.subTest(req=req), self.assertRaises(ComparisonValidationError):
                compare_results(base.outputs, profiles=base.profiles, sample_metadata=base.sample_metadata,
                                diagnostic_requests=[req])
        for requests in (None, "all", {}, [None], [{"query_id": "M01"}]):
            with self.subTest(requests=requests), self.assertRaises(ComparisonValidationError):
                b1_result(requests if requests is not None else "invalid")
        with self.assertRaisesRegex(ComparisonValidationError, "require profiles"):
            b1_result(profiles=False)
        with self.assertRaisesRegex(ComparisonValidationError, "categorical"):
            compare_results(base.outputs, profiles=base.profiles, diagnostic_requests=[request()])
        with self.assertRaisesRegex(ComparisonValidationError, "SampleMetadata"):
            compare_results(base.outputs, sample_metadata=metadata_doc())
        wrong = thaw(base.dataset); wrong["context"] = "wrong"
        with self.assertRaisesRegex(ComparisonValidationError, "binding"):
            b1_result([], replace(base.sample_metadata, dataset=wrong))
        with self.assertRaises(ComparisonValidationError):
            replace(base, diagnostic_requests=[request(query_id="missing")])

    def test_namespace_maps_and_identical_feature_ids_remain_distinct(self):
        from test_a1_contracts import descriptor
        from valpas.comparison import load_comparison_input
        outputs = []
        for oid in ("a", "b"):
            d = descriptor(oid)
            d["query_ids"] = ["a"]
            d["data"]["inline"]["row_ids"] = ["a"]
            outputs.append(load_comparison_input(d))
        base = compare_results(outputs)
        layer = profile_layer(base)
        for feature in layer["features"]:
            feature["values"] = list(range(len(base.dataset["observation_ids"])))
            feature["observed"] = [True] * len(base.dataset["observation_ids"])
        meta = SampleMetadata.from_dict(metadata_doc(base))
        req = DiagnosticRequest("a", "a", "measured", group_field="condition")
        result = compare_results(outputs, profiles=ProfileData([layer]), sample_metadata=meta,
                                 diagnostic_requests=[req, req])
        rows = list(result.iter_table("group_summaries"))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["feature_id"] for r in rows], ["a", "a"])
        self.assertNotEqual(rows[0]["namespace"], rows[1]["namespace"])
        self.assertEqual(len(list(result.iter_table("diagnostics"))), 2)
        # Duplicate requests preserve explicit list semantics, while groups deduplicate.
        self.assert_tables(result, load_comparison_bundle(write_comparison(result, self.root / "namespaces")))

    def test_missing_profile_feature_is_unavailable_not_invalid_id(self):
        base = b1_result([])
        layer = profile_layer()
        layer["features"] = [f for f in layer["features"] if f["feature_id"] != "P01"]
        result = compare_results(base.outputs, profiles=ProfileData([layer]), sample_metadata=base.sample_metadata,
                                 diagnostic_requests=[request()])
        self.assertEqual(next(result.iter_table("diagnostics"))["result"]["reason"], "missing_feature")
        self.assertEqual(list(result.iter_table("group_summaries"))[1]["result"]["reason"], "missing_feature")
        with self.assertRaisesRegex(ComparisonValidationError, "materialization limit"):
            result.materialize_table("group_summaries", max_rows=1)

    def make_source(self, *, inline=False):
        source = self.root / "source"
        shutil.copytree(FIXTURE, source)
        manifest = json.loads((source / "manifest-with-profiles.json").read_text())
        doc = metadata_doc()
        (source / "samples.json").write_text(json.dumps(doc))
        manifest["sample_metadata"] = doc if inline else {"path": "samples.json"}
        manifest["diagnostic_requests"] = [{"query_id": "M01", "candidate_id": "P01", "layer_id": "measured",
                                             "group_field": "condition"}]
        # Fixture's profile transport may use another layer name; use our explicit fixture.
        (source / "profiles.json").write_text(json.dumps({"schema_version": 1, "layers": [profile_layer()]}))
        manifest["profiles"] = {"path": "profiles.json"}
        (source / "manifest.json").write_text(json.dumps(manifest))
        return source

    def test_manifest_inline_and_normalized_defaults_and_override(self):
        source = self.make_source(inline=True)
        manifest = load_manifest(source / "manifest.json")
        result = compare_results(manifest)
        self.assertIsInstance(manifest.sample_metadata, SampleMetadata)
        self.assertEqual(result.diagnostic_requests[0].h, 5)
        self.assertFalse(result.diagnostic_requests[0].omission)
        self.assertEqual(compare_results(manifest, diagnostic_requests=[]).diagnostic_requests, ())
        self.assertEqual(compare_results(manifest, diagnostic_requests=[request()]).diagnostic_requests, (request(),))
        self.assertFalse(any(f["role"] == "sample_metadata" for f in result.source_fingerprints))
        doc = json.loads((source / "manifest.json").read_text())
        for invalid in (None, {}, "all", [{"query_id": "bad", "candidate_id": "P01", "layer_id": "measured"}]):
            doc["diagnostic_requests"] = invalid
            (source / "manifest.json").write_text(json.dumps(doc))
            with self.assertRaises(ComparisonValidationError):
                load_manifest(source / "manifest.json")

    def test_fingerprints_consumed_bytes_source_protection_and_delete_roundtrip(self):
        source = self.make_source()
        manifest = load_manifest(source / "manifest.json")
        result = compare_results(manifest)
        fingerprint = next(f for f in result.source_fingerprints if f["role"] == "sample_metadata")
        self.assertEqual(dict(fingerprint), {"role": "sample_metadata", "path": str((source / "samples.json").resolve()),
                                             **digest_record(source / "samples.json")})
        self.assertIn(fingerprint["path"], result.protected_sources)
        (source / "samples.json").write_text("changed after consumption")
        with self.assertRaisesRegex(ComparisonValidationError, "consumed source"):
            write_comparison(result, source, overwrite=True)
        out = write_comparison(result, self.root / "out")
        shutil.rmtree(source)
        loaded = load_comparison_bundle(out)
        self.assert_tables(result, loaded)
        self.assertEqual(loaded.sample_metadata.to_dict(), result.sample_metadata.to_dict())
        self.assertEqual(loaded.diagnostic_requests, result.diagnostic_requests)
        self.assertEqual(loaded.source_fingerprints, result.source_fingerprints)
        again = write_comparison(loaded, self.root / "again")
        self.assertEqual((out / "report.html").read_bytes(), (again / "report.html").read_bytes())
        with self.assertRaisesRegex(ComparisonValidationError, "consumed source"):
            write_comparison(loaded, out, overwrite=True)

    def test_metadata_inside_owned_bundle_cannot_be_overwritten(self):
        out = write_comparison(b1_result([]), self.root / "owned")
        meta = load_sample_metadata({"path": "sample_metadata.json"}, base_dir=out)
        result = b1_result([], meta)
        before = (out / "sample_metadata.json").read_bytes()
        with self.assertRaisesRegex(ComparisonValidationError, "consumed source"):
            write_comparison(result, out, overwrite=True)
        self.assertEqual((out / "sample_metadata.json").read_bytes(), before)

    def test_v3_inventory_normalized_scope_and_descriptive_schemas(self):
        result = b1_result()
        for tables_only in (False, True):
            out = write_comparison(result, self.root / str(tables_only), tables_only=tables_only)
            marker = self.marker(out)
            self.assertEqual(marker["schema_version"], 3)
            self.assertEqual(marker["b1"], {"sample_metadata": True, "diagnostic_requests": [request().to_dict()]})
            self.assertEqual(set(marker["inventory"]) | {"comparison.json"}, {p.name for p in out.iterdir()})
            for table in ("sample_metadata", "diagnostics", "group_summaries"):
                schema = marker["table_schema"][table]
                self.assertIn("descriptive", schema["units"])
                self.assertIn("status", schema)
                self.assertNotEqual(schema["units"], marker["table_schema"]["coverage"]["units"])
                with (out / marker["tables"][table]["path"]).open(newline="") as handle:
                    rows = [{k: json.loads(v) for k, v in row.items()} for row in csv.DictReader(handle)]
                self.assertEqual(rows, list(result.iter_table(table)))
            self.assert_tables(result, load_comparison_bundle(out))

    def test_privacy_safe_payload_and_budget_include_metadata(self):
        doc = metadata_doc()
        secret = "private-sample-value-" + "x" * 10000 + "</script>\u2028"
        doc["records"][0]["values"]["condition"] = secret
        result = b1_result(metadata=SampleMetadata.from_dict(doc))
        settings = ReportSettings(max_interactive_depth=1)
        html, payload, record = render_report(result, settings)
        self.assertEqual(payload["sample_metadata"], result.sample_metadata.to_dict())
        self.assertNotIn(secret, html)
        self.assertNotIn("diagnostics", payload)
        self.assertNotIn("group_summaries", payload)
        _, _, baseline = render_report(replace(result, sample_metadata=None, diagnostic_requests=()), settings)
        self.assertGreater(record["payload_bytes"], baseline["payload_bytes"] + 10000)
        with self.assertRaisesRegex(ComparisonValidationError, "before HTML wrapping"):
            write_comparison(result, self.root / "too-big", report_settings=replace(settings, max_payload_bytes=baseline["payload_bytes"]))
        self.assertFalse((self.root / "too-big").exists())
        private = replace(settings, omit_metadata=True)
        html, payload, _ = render_report(result, private)
        self.assertIsNone(payload["sample_metadata"])
        self.assertEqual(payload["layers"], [])
        self.assertNotIn(secret[:20], html)
        self.assertNotIn("condition", safe_json(payload))
        out = write_comparison(result, self.root / "private", report_settings=private)
        self.assert_tables(result, load_comparison_bundle(out))

    def test_b1_corruption_and_schema_inventory_checked(self):
        mutations = [lambda m: m.pop("b1"), lambda m: m["b1"].update(sample_metadata=False),
                     lambda m: m["b1"]["diagnostic_requests"][0].pop("h"),
                     lambda m: m["b1"]["diagnostic_requests"][0].update(candidate_id="unknown"),
                     lambda m: m["table_schema"]["diagnostics"].update(units="scientific score"),
                     lambda m: m["tables"]["group_summaries"].update(rows=100)]
        for i, mutate in enumerate(mutations):
            out = write_comparison(b1_result(), self.root / str(i), tables_only=True)
            self.edit_marker(out, mutate)
            with self.subTest(i=i), self.assertRaises(ComparisonValidationError):
                load_comparison_bundle(out)
        out = write_comparison(b1_result(), self.root / "metadata", tables_only=True)
        file = out / "sample_metadata.json"
        data = json.loads(file.read_text()); data["records"][0]["values"]["age"] = 123
        file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ComparisonValidationError, "checksum"):
            load_comparison_bundle(out)
        self.refresh(out, file.name)
        with self.assertRaisesRegex(ComparisonValidationError, "table differs"):
            load_comparison_bundle(out)
        for table in ("diagnostics", "group_summaries"):
            out = write_comparison(b1_result(), self.root / table, tables_only=True)
            file = out / (table + ".csv")
            with file.open(newline="") as handle:
                rows = list(csv.reader(handle))
            nested = json.loads(rows[1][-1]); nested["reason"] = "forged"
            rows[1][-1] = canonical_json(nested)
            with file.open("w", newline="") as handle:
                csv.writer(handle).writerows(rows)
            self.refresh(out, file.name)
            with self.assertRaisesRegex(ComparisonValidationError, "table differs"):
                load_comparison_bundle(out)

    def test_true_v1_v2_migrations_without_b1_keys_and_new_asset_regeneration(self):
        cases = [(1, False, False, False), (2, False, False, False), (2, True, True, False),
                 (2, False, True, False), (2, True, True, True)]
        for i, (version, profiles, html, private) in enumerate(cases):
            result = profiled_result() if profiles else fixture_result()
            out = legacy_bundle(result, self.root / str(i), version, html=html, omit_metadata=private)
            self.assertNotIn("b1", self.marker(out))
            self.assertFalse((out / "sample_metadata.json").exists())
            loaded = load_comparison_bundle(out)
            self.assert_tables(result, loaded)
            self.assertIsNone(loaded.sample_metadata)
            self.assertEqual(loaded.diagnostic_requests, ())
            again = write_comparison(loaded, self.root / (str(i) + "-v3"))
            self.assertEqual(self.marker(again)["schema_version"], 3)
            self.assert_tables(result, load_comparison_bundle(again))
            if html:
                self.assertNotEqual((out / "report.html").read_bytes(), (again / "report.html").read_bytes())
                self.assertIn("sample_metadata", json.loads((again / "report_payload.json").read_text()))

    def test_legacy_payload_at_original_budget_loads_without_new_byte_requirement(self):
        out = legacy_bundle(fixture_result(), self.root / "budget", 2, html=True)
        file = out / "report_payload.json"
        payload = json.loads(file.read_text())
        # Find the fixed point: the budget itself contributes its digits to size.
        for _ in range(10):
            size = len(safe_json(payload).encode("utf-8"))
            if payload["report_settings"]["max_payload_bytes"] == size:
                break
            payload["report_settings"]["max_payload_bytes"] = size
        raw = safe_json(payload)
        self.assertEqual(len(raw.encode("utf-8")), size)
        html = out / "report.html"
        html.write_text(html.read_text().replace(file.read_text(), raw))
        file.write_text(raw)
        for name in (file.name, html.name):
            self.refresh(out, name)
        def update(marker):
            marker["report"]["settings"]["max_payload_bytes"] = size
            marker["report"]["payload"] = {"payload_bytes": size, "payload_sha256": hashlib.sha256(raw.encode()).hexdigest()}
        self.edit_marker(out, update)
        loaded = load_comparison_bundle(out)
        with self.assertRaisesRegex(ComparisonValidationError, "before HTML wrapping"):
            write_comparison(loaded, self.root / "needs-larger-budget")
        write_comparison(loaded, self.root / "new-budget", report_settings=ReportSettings(max_interactive_depth=2))

    def test_legacy_checksum_payload_science_and_schema_remain_checked(self):
        for i, name in enumerate(("report.html", "report_payload.json", "agreement.csv")):
            out = legacy_bundle(profiled_result(), self.root / str(i), 2, html=True)
            with (out / name).open("a") as handle:
                handle.write("corruption")
            with self.assertRaisesRegex(ComparisonValidationError, "checksum"):
                load_comparison_bundle(out)
        out = legacy_bundle(profiled_result(), self.root / "parity", 2, html=True)
        file = out / "report_payload.json"
        payload = json.loads(file.read_text()); payload["agreement"][0]["shared_count"] = 999
        old = file.read_text(); raw = safe_json(payload); file.write_text(raw)
        html = out / "report.html"; html.write_text(html.read_text().replace(old, raw))
        for name in (file.name, html.name):
            self.refresh(out, name)
        self.edit_marker(out, lambda m: m["report"].update(payload={"payload_bytes": len(raw.encode()),
                                                                  "payload_sha256": hashlib.sha256(raw.encode()).hexdigest()}))
        with self.assertRaisesRegex(ComparisonValidationError, "report differs"):
            load_comparison_bundle(out)
        for version in (1, 2):
            for kind in ("schema", "table", "software"):
                out = legacy_bundle(fixture_result(), self.root / f"{version}-{kind}", version)
                if kind == "schema":
                    self.edit_marker(out, lambda m: m["table_schema"]["agreement"].update(columns=["wrong"]))
                elif kind == "software":
                    self.edit_marker(out, lambda m: m.update(software_version="unsupported"))
                else:
                    with (out / "agreement.csv").open("a") as handle:
                        handle.write("corruption\n")
                    self.refresh(out, "agreement.csv")
                with self.subTest(version=version, kind=kind), self.assertRaises(ComparisonValidationError):
                    load_comparison_bundle(out)

    def test_cli_manifest_b1_configuration_and_source_free_regeneration(self):
        source = self.make_source()
        env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}
        out = self.root / "cli"
        args = ["--manifest", str(source / "manifest.json"), "--outdir", str(out)]
        completed = subprocess.run([sys.executable, "-m", "valpas.cli", "compare", *args], env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.marker(out)["tables"]["diagnostics"]["rows"], 1)
        shutil.rmtree(source)
        again = self.root / "cli-again"
        completed = subprocess.run([sys.executable, "-m", "valpas.cli", "compare", "--bundle", str(out),
                                    "--outdir", str(again)], env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_tables(load_comparison_bundle(out), load_comparison_bundle(again))


if __name__ == "__main__":
    unittest.main()
