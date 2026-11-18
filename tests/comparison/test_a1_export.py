"""Detached adapters, safe input bundles, and no-compute import boundaries."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_a1_contracts import descriptor, table_descriptor, prefix_descriptor, FIXTURE
from test_import_isolation import SubprocessCase, IMPORT_GUARD, IMPORT_ASSERTIONS
from valpas.comparison import (
    ComparisonSettings, ComparisonValidationError, build_pools,
    export_comparison_inputs, from_association_result, load_comparison_input,
    load_input_bundle, load_manifest, rank_output,
)


class Matrix:
    """Minimal labeled matrix protocol, no pandas/torch needed."""
    def __init__(self, rows, columns, values):
        self.index, self.columns = list(rows), list(columns)
        self.cells = {(r, c): values[i][j] for i, r in enumerate(rows) for j, c in enumerate(columns)}
        self.at = self
        self.axis_names = ["original row name", "original column name"]

    def __getitem__(self, key):
        return self.cells[key]


class ExportCase(unittest.TestCase):
    def test_structural_adapter_detached_no_mutating_methods(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("mutating legacy method called")
        result = SimpleNamespace(
            values=Matrix(["unused", "q", "all-missing"], ["c", "a", "b"], [[1, 2, 3], [0.1, -0.9123456789123456, 0.8], [None, None, None]]),
            counts=Matrix(["q", "unused", "all-missing"], ["a", "b", "c"], [[6, 5, 4], [1, 1, 1], [0, 0, 0]]),
            omic_x={"type": "original", "features": ["q"]}, omic_y=None,
            analysis_results={"nested": [1, 2]}, annotationlist={"source": "local"}, edgelist=["untouched"],
            save=forbidden, as_list=forbidden,
        )
        before = copy.deepcopy(result)
        d = descriptor()
        d["count_semantics"] = "joint observed sample count"
        out = from_association_result(result, d, query_axis="index", query_ids=["q"], candidate_ids=["a", "b", "c"])
        self.assertEqual(out.pair("q", "a").score, -0.9123456789123456)
        self.assertEqual(out.pair("q", "a").count, 6)
        for name in ("values", "counts"):
            left, right = getattr(result, name), getattr(before, name)
            self.assertEqual(left.cells, right.cells)
            self.assertEqual(left.index, right.index)
            self.assertEqual(left.columns, right.columns)
            self.assertEqual(left.axis_names, right.axis_names)
        for name in ("omic_x", "omic_y", "analysis_results", "annotationlist", "edgelist"):
            self.assertEqual(getattr(result, name), getattr(before, name))
        result.values.cells["q", "a"] = 999
        d["identity"]["context"] = "changed"
        self.assertEqual(out.pair("q", "a").score, -0.9123456789123456)
        self.assertNotEqual(out.descriptor["identity"]["context"], "changed")

    def test_structural_transpose_and_missing_axes(self):
        result = SimpleNamespace(values=Matrix(["a", "b", "c"], ["q"], [[-0.9], [0.8], [None]]), counts=None)
        d = descriptor()
        d["orientation"] = "candidate_rows_query_columns"
        out = from_association_result(result, d, query_axis="columns", query_ids=["q"], candidate_ids=["a", "b", "c"])
        self.assertEqual(rank_output(out, "q").order, ("a", "b"))
        result.values.index.append("a")
        with self.assertRaises(ComparisonValidationError):
            from_association_result(result, d, query_axis="columns", query_ids=["q"], candidate_ids=["a", "b", "c"])

    def test_all_representations_full_precision_roundtrip(self):
        score = descriptor("../../not-a-filename", scores=[-0.9123456789123456, -0.0, None])
        ordered = table_descriptor(oid="ordered")
        prefix = prefix_descriptor("prefix")
        filtered = table_descriptor("filtered_list", "filtered")
        filtered["completeness"] = {"kind": "inspection_only", "filter": "threshold"}
        filtered["missing_policy"]["absent"] = "unreported"
        filtered["data"]["inline"]["records"] = [{"query_id": "q", "candidate_id": "b", "score": 1}]
        permutation = descriptor("permutation")
        permutation["representation"] = "rank_permutation"
        permutation["data"] = {"format": "json", "index_base": 0, "inline": {"query_ids": ["q"], "permutations": [[2, 0, 1]]}}
        long = table_descriptor("long_scores", "long")
        long["data"]["inline"]["records"] = [{"query_id": "q", "candidate_id": c, "score": s} for c, s in zip(["a", "b", "c"], [1, 2, 3])]
        legacy = descriptor("legacy")
        legacy["representation"] = "legacy_score_count"
        legacy["count_semantics"] = "joint observations"
        legacy["data"]["inline"]["values"] = [["0.12345:6", "-0.98765:5", "0.0:4"]]
        outputs = [load_comparison_input(d) for d in (score, ordered, prefix, filtered, permutation, long, legacy)]
        with tempfile.TemporaryDirectory() as tmp:
            destination = export_comparison_inputs(outputs, Path(tmp) / "bundle", settings=ComparisonSettings(pool_policy="native_inspection"))
            loaded = load_input_bundle(destination)
            self.assertEqual(len(loaded.outputs), len(outputs))
            for before, after in zip(outputs, loaded.outputs):
                self.assertEqual(before.pairs, after.pairs)
                self.assertEqual(before.warnings, after.warnings)
                self.assertEqual(rank_output(before, "q"), rank_output(after, "q"))
                for candidate in before.candidate_ids:
                    self.assertEqual(before.pair("q", candidate), after.pair("q", candidate))
            self.assertEqual(math.copysign(1, loaded.outputs[0].pair("q", "b").score), -1)
            self.assertEqual(loaded.outputs[0].pair("q", "a").score, -0.9123456789123456)
            with self.assertRaises(ComparisonValidationError):
                export_comparison_inputs(outputs, destination)
            member = destination / "input-0000.json"
            member.write_text(member.read_text() + " ")
            with self.assertRaises(ComparisonValidationError):
                load_input_bundle(destination)

    def test_reload_is_independent_of_original_files(self):
        manifest = load_manifest(FIXTURE / "manifest.json")
        with tempfile.TemporaryDirectory() as tmp:
            bundle = export_comparison_inputs(manifest.outputs, Path(tmp) / "bundle", dataset=manifest.dataset)
            with patch("valpas.comparison.adapters._local_path", wraps=__import__("valpas.comparison.adapters", fromlist=["_local_path"])._local_path) as paths:
                loaded = load_input_bundle(bundle)
                self.assertTrue(all(Path(call.args[1]).resolve() == bundle for call in paths.call_args_list))
            self.assertEqual(build_pools(manifest.outputs).queries, build_pools(loaded.outputs).queries)

    def test_safe_destination_existing_symlinks_and_failure_cleanup(self):
        out = load_comparison_input(descriptor())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "unrelated"
            existing.mkdir()
            (existing / "keep.txt").write_text("keep")
            with self.assertRaises(ComparisonValidationError):
                export_comparison_inputs([out], existing)
            self.assertEqual((existing / "keep.txt").read_text(), "keep")
            (root / "link").symlink_to(existing, target_is_directory=True)
            (root / "dangling").symlink_to(root / "absent", target_is_directory=True)
            for dest in (root / "link", root / "dangling", root / "link" / "nested", root / ".." / "escape", root / "absent" / "nested"):
                with self.subTest(dest=dest), self.assertRaises(ComparisonValidationError):
                    export_comparison_inputs([out], dest)
            with patch("valpas.comparison.bundles._write_json", side_effect=OSError("injected failure")):
                with self.assertRaises(ComparisonValidationError):
                    export_comparison_inputs([out], root / "failed")
            self.assertFalse((root / "failed").exists())
            self.assertFalse(list(root.glob(".failed.partial-*")))
            with patch("valpas.comparison.bundles.os.replace", side_effect=OSError("publication failure")):
                with self.assertRaises(ComparisonValidationError):
                    export_comparison_inputs([out], root / "failed-publish")
            self.assertFalse((root / "failed-publish").exists())
            self.assertFalse(list(root.glob(".failed-publish.partial-*")))


class NoComputeCase(SubprocessCase):
    def test_loading_ranking_export_reload_block_all_heavy_modules(self):
        self.run_python(IMPORT_GUARD + f'''
from pathlib import Path
import tempfile
from valpas.comparison import *
import valpas.cli
m = load_manifest({str((FIXTURE / 'manifest.json').resolve())!r})
p = build_pools(m.outputs, ComparisonSettings(pool_policy="common"))
assert p.queries["M02"].active_orders["ae-seed-42"] == ("P03", "P01")
with tempfile.TemporaryDirectory() as tmp:
    bundle = export_comparison_inputs(m.outputs, Path(tmp) / "bundle", dataset=m.dataset)
    reloaded = load_input_bundle(bundle)
    assert reloaded.outputs[0].pair("M01", "P01").score == -0.9
''' + IMPORT_ASSERTIONS)


if __name__ == "__main__":
    unittest.main()
