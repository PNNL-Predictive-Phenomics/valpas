"""Saved-output single-modality regressions; no fitting or training imports.

The same independent four-entity fixtures exercise protein abundance and gene
expression. Matrices are synthetic saved association scores, not measurements.
"""
import copy
import csv
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from valpas.comparison import (
    ComparisonSettings, ComparisonValidationError, build_pools, compare_results,
    export_comparison_inputs, from_association_result, load_comparison_bundle,
    load_comparison_input, load_input_bundle, load_manifest, rank_output,
    top_list, write_comparison,
)
from valpas.comparison.models import TIE_POLICY


SCORES_A = (
    (1.0, -.9, .8, .1),
    (-.9, 1.0, -.4, .7),
    (.8, -.4, 1.0, -.6),
    (.1, .7, -.6, 1.0),
)
SCORES_B = (
    (1.0, -.2, .9, -.8),
    (-.2, 1.0, -.85, .3),
    (.9, -.85, 1.0, .2),
    (-.8, .3, .2, 1.0),
)
# Hand-written orders, independent of the implementation's sorting helpers.
ORDERS_A = ((1, 2, 3), (0, 3, 2), (0, 3, 1), (1, 2, 0))
ORDERS_B = ((2, 3, 1), (2, 3, 0), (0, 1, 3), (0, 1, 2))


class SingleModalityChecks:
    """Mixin run as separate unittest cases for each biological modality."""

    def setUp(self):
        self.ids = [self.prefix + str(i).zfill(2) for i in range(1, 5)]
        self.namespace = {"id": self.modality + "-feature-ids-v1", "modality": self.modality}

    def descriptor(self, oid="a", scores=SCORES_A, *, queries=None, candidates=None,
                   transposed=False, reorder=False):
        qs = list(self.ids if queries is None else queries)
        cs = list(self.ids if candidates is None else candidates)
        values = {(q, c): scores[i][j] for i, q in enumerate(self.ids)
                  for j, c in enumerate(self.ids)}
        rows, cols = (cs[:], qs[:]) if transposed else (qs[:], cs[:])
        if reorder:
            rows.reverse()
            cols[:] = cols[1:] + cols[:1]
        return {
            "schema_version": 1, "output_id": oid, "label": "Synthetic saved " + oid,
            "method_id": "saved-method", "configuration_id": "replicates",
            "run_id": oid, "seed": {"a": 11, "b": 22}.get(oid),
            "identity": {
                "dataset_id": "synthetic-" + self.modality,
                "dataset_evidence": {"type": "attestation", "source": "synthetic-fixture-v1",
                                     "value": "Same synthetic measurements for every saved output",
                                     "limitations": "Test data, not measured biological evidence"},
                "observation_ids": ["sample-1", "sample-2", "sample-3"],
                "query_namespace": copy.deepcopy(self.namespace),
                "candidate_namespace": copy.deepcopy(self.namespace),
                "context": "Single modality saved-output regression",
            },
            "configuration": {
                "parameters": {"fixture_version": 1}, "preprocessing": {"transform": "none"},
                "score_semantics": "signed synthetic association score",
                "supervision": "none; saved synthetic outputs",
                "training_features": {"namespace": copy.deepcopy(self.namespace), "ids": self.ids[:]},
                "observation_selection": "all declared observations",
            },
            "provenance": {"software": "test fixture", "source": "literal saved scores",
                           "limitations": "No model execution or real experiment"},
            "query_ids": qs, "candidate_ids": cs,
            "orientation": "candidate_rows_query_columns" if transposed else "query_rows_candidate_columns",
            "representation": "score_matrix", "ranking_policy": "absolute_descending",
            "tie_policy": TIE_POLICY, "completeness": {"kind": "complete"},
            "missing_policy": {"blank": "unscored", "nan": "unscored", "absent": "reject"},
            "data": {"format": "json", "inline": {
                "row_ids": rows, "column_ids": cols,
                "values": [[values[c, r] if transposed else values[r, c] for c in cols] for r in rows],
            }},
        }

    def descriptors(self):
        a, b, c = self.descriptor(), self.descriptor("b", SCORES_B), self.descriptor("c")
        c.update(method_id="other-saved-method", configuration_id="other-method")
        return [a, b, c]

    def compare(self, descriptors=None, *, policy="strict", depths=(1, 2, 9), exclude_self=True):
        return compare_results([load_comparison_input(d) for d in
                                (self.descriptors() if descriptors is None else descriptors)],
                               ComparisonSettings(pool_policy=policy, depths=depths, exclude_self=exclude_self))

    def assert_parity(self, left, right):
        self.assertEqual(left.comparison_id, right.comparison_id)
        for name in left.table_names:
            self.assertEqual(list(left.iter_table(name)), list(right.iter_table(name)), name)

    def test_square_directional_ranks_metrics_and_recurrence(self):
        result = self.compare()
        pools = build_pools(result.outputs)
        for q_index, q in enumerate(self.ids):
            for oid, expected in (("a", ORDERS_A), ("b", ORDERS_B), ("c", ORDERS_A)):
                view = pools.queries[q].native[oid]
                order = tuple(self.ids[i] for i in expected[q_index])
                self.assertEqual(view.order, order)
                self.assertEqual(dict(view.ranks), dict(zip(order, (1, 2, 3))))
                self.assertEqual(view.statuses[q], ("ineligible", "self_edge"))
        ranks = result.materialize_table("candidate_ranks")
        self.assertEqual(len(ranks), 48)  # 3 outputs * 4 queries * 4 candidates
        for oid in "abc":
            active = {(r["query_id"], r["candidate_id"]) for r in ranks
                      if r["output_id"] == oid and r["active_rank"] is not None}
            self.assertEqual(active, {(q, c) for q in self.ids for c in self.ids if q != c})
            self.assertEqual(len(active), 12)  # not six undirected edges
        diagonal = [r for r in ranks if r["query_id"] == r["candidate_id"]]
        self.assertEqual(len(diagonal), 12)
        self.assertTrue(all(r["active_rank"] is None and r["score"] == 1 for r in diagonal))
        self.assertEqual(len(result.materialize_table("exclusions")), 12)
        for coverage in result.iter_table("coverage"):
            self.assertEqual((coverage["declared_candidates"], coverage["native_eligible"],
                              coverage["native_scorable"], coverage["active_pool_size"]), (4, 3, 3, 3))
        agreements = result.materialize_table("agreement")
        self.assertEqual(len(agreements), 36)
        for row in agreements:
            self.assertEqual(row["status"], "available")
            self.assertEqual(row["effective_depth"], min(row["requested_depth"], 3))
        ab = [r for r in agreements if r["query_id"] == self.ids[0]
              and (r["left_output_id"], r["right_output_id"]) == ("a", "b")]
        self.assertEqual([(r["shared_count"], r["union_size"], r["overlap_fraction"], r["jaccard"])
                          for r in ab], [(0, 2, 0, 0), (1, 3, .5, 1 / 3), (3, 3, 1, 1)])
        rec = result.materialize_table("run_recurrence")
        self.assertEqual(len(rec), 72)
        for row in rec:
            self.assertNotEqual(row["query_id"], row["candidate_id"])
            if row["configuration_id"] == "replicates":
                self.assertEqual((row["expected_runs"], row["evaluable_runs"]), (2, 2))
                self.assertEqual(row["recurrence_fraction"], row["nominations"] / 2)
                self.assertEqual(row["effective_depth"], min(row["requested_depth"], 3))
            else:
                self.assertEqual(row["status"], "not_assessed")
                self.assertIsNone(row["recurrence_fraction"])
        first = {r["candidate_id"]: r["nominations"] for r in rec if r["query_id"] == self.ids[0]
                 and r["configuration_id"] == "replicates" and r["requested_depth"] == 1}
        self.assertEqual(first, dict(zip(self.ids[1:], (1, 1, 0))))
        full = [r for r in rec if r["configuration_id"] == "replicates" and r["requested_depth"] == 9]
        self.assertEqual(len(full), 12)
        self.assertTrue(all(r["nominations"] == 2 for r in full))
        self.assertTrue(all(r["evaluable_queries"] == 4 and r["excluded_queries"] == 0
                            for r in result.iter_table("agreement_summary")))
        # Policies have different identities, but complete shared pools have identical orders.
        common = self.compare(policy="common")
        self.assertEqual([r["active_rank"] for r in common.iter_table("candidate_ranks")],
                         [r["active_rank"] for r in ranks])

    def test_signed_policies_and_self_opt_in(self):
        for policy, indices in (("native_descending", (2, 3, 1)), ("native_ascending", (1, 3, 2)),
                                ("absolute_descending", (1, 2, 3)), ("absolute_ascending", (3, 2, 1))):
            with self.subTest(policy=policy):
                d = self.descriptor()
                d["ranking_policy"] = policy
                out = load_comparison_input(d)
                self.assertEqual(top_list(out, self.ids[0], 99), tuple(self.ids[i] for i in indices))
                self.assertEqual(out.pair(self.ids[0], self.ids[1]).score, -.9)
        result = self.compare(exclude_self=False)
        self.assertTrue(all(r["active_rank"] is not None for r in result.iter_table("candidate_ranks")))
        self.assertEqual(list(result.iter_table("exclusions")), [])
        self.assertTrue(all(r["effective_depth"] == 4 for r in result.iter_table("agreement")
                            if r["requested_depth"] == 9))

    def test_namespace_equality_is_exact_id_and_modality(self):
        for field in ("id", "modality"):
            with self.subTest(field=field):
                d = self.descriptor()
                d["identity"]["candidate_namespace"][field] += "-different"
                self.assertIn(self.ids[0], rank_output(load_comparison_input(d), self.ids[0]).order)
                # A matching ID alone, or matching modality alone, is insufficient.
                with self.assertRaises(ComparisonValidationError) as caught:
                    self.compare([self.descriptor("b"), d])
                self.assertEqual(caught.exception.issue.field, "identity.candidate_namespace")
        for extra in ("label", "species", "version"):
            d = self.descriptor()
            d["identity"]["query_namespace"][extra] = "not a namespace field"
            with self.assertRaises(ComparisonValidationError):
                load_comparison_input(d)
        d = self.descriptor()
        d["label"] = "A display label does not change self identity"
        d["provenance"]["source"] = "another saved-file description"
        self.assertNotIn(self.ids[0], rank_output(load_comparison_input(d), self.ids[0]).order)
        for orientation in (None, "square", "auto"):
            d = self.descriptor()
            d["orientation"] = orientation
            with self.assertRaises(ComparisonValidationError):
                load_comparison_input(d)

    def test_reordered_axes_and_explicit_square_transpose(self):
        asymmetric = [list(row) for row in SCORES_A]
        asymmetric[0][1] = -.9123456789123456
        asymmetric[1][0] = .2
        original = [self.descriptor("a", asymmetric), self.descriptor("b", SCORES_B)]
        alternate = [self.descriptor("a", asymmetric, transposed=True, reorder=True),
                     self.descriptor("b", SCORES_B, reorder=True)]
        for d in alternate:
            d["query_ids"].reverse()
            d["candidate_ids"].reverse()
            d["identity"]["observation_ids"].reverse()
        self.assert_parity(self.compare(original), self.compare(alternate))
        out = load_comparison_input(alternate[0])
        self.assertEqual(out.pair(self.ids[0], self.ids[1]).score, -.9123456789123456)
        self.assertEqual(out.pair(self.ids[1], self.ids[0]).score, .2)
        alternate[0]["orientation"] = "query_rows_candidate_columns"
        # Shape cannot reveal a wrong square declaration: the caller owns semantics.
        self.assertNotEqual(self.compare(original).comparison_id, self.compare(alternate).comparison_id)

    def test_same_namespace_rectangular_subsets_and_common_intersection(self):
        qs, cs = self.ids[:2], self.ids[1:]
        ds = [self.descriptor("a", queries=qs, candidates=cs),
              self.descriptor("b", SCORES_B, queries=qs, candidates=cs, transposed=True, reorder=True)]
        result = self.compare(ds, depths=(9,))
        self.assertEqual(len(result.materialize_table("candidate_ranks")), 12)
        self.assertEqual({r["query_id"]: r["effective_depth"] for r in result.iter_table("agreement")},
                         {qs[0]: 3, qs[1]: 2})
        # Same namespace does not require identical query/candidate axis sets.
        self.assertEqual(len(result.materialize_table("exclusions")), 2)
        ds[1] = self.descriptor("b", SCORES_B, queries=self.ids[1:3], candidates=self.ids[:3])
        with self.assertRaises(ComparisonValidationError):
            self.compare(ds)
        common = self.compare(ds, policy="common", depths=(9,))
        row = common.materialize_table("agreement")[0]
        self.assertEqual((row["query_id"], row["effective_depth"], row["shared_count"]), (self.ids[1], 1, 1))
        summary = common.materialize_table("agreement_summary")[0]
        self.assertEqual((summary["declared_queries"], summary["eligible_queries"],
                          summary["evaluable_queries"], summary["excluded_queries"]), (3, 1, 1, 2))
        self.assertEqual(len([r for r in common.iter_table("exclusions") if r["candidate_id"] is None]), 4)

    def test_missing_offdiagonal_strict_common_blank_and_absent(self):
        for missing_kind in ("blank", "absent"):
            with self.subTest(missing_kind=missing_kind):
                ds = self.descriptors()
                if missing_kind == "blank":
                    ds[1]["data"]["inline"]["values"][0][1] = None
                else:
                    ds[1]["representation"] = "long_scores"
                    ds[1]["missing_policy"]["absent"] = "unscored"
                    ds[1]["data"] = {"format": "json", "inline": {"records": [
                        {"query_id": q, "candidate_id": c, "score": SCORES_B[i][j]}
                        for i, q in enumerate(self.ids) for j, c in enumerate(self.ids) if (i, j) != (0, 1)]}}
                strict = self.compare(ds)
                rows = strict.materialize_table("agreement")
                missing = [r for r in rows if r["query_id"] == self.ids[0]]
                self.assertEqual(len(missing), 9)
                self.assertTrue(all(r["status"] == "unavailable" and r["shared_count"] is None
                                    and r["reason"] == "scorable_candidate_sets_differ" for r in missing))
                self.assertTrue(all(r["status"] == "available" for r in rows if r not in missing))
                self.assertTrue(all(r["evaluable_queries"] == 3 and r["excluded_queries"] == 1
                                    for r in strict.iter_table("agreement_summary")))
                rec = [r for r in strict.iter_table("run_recurrence") if r["query_id"] == self.ids[0]
                       and r["configuration_id"] == "replicates"]
                self.assertTrue(all(r["expected_runs"] == 2 and r["recurrence_fraction"] is None for r in rec))
                common = self.compare(ds, policy="common")
                self.assertTrue(all(r["effective_depth"] == (2 if r["query_id"] == self.ids[0] else 3)
                                    for r in common.iter_table("agreement") if r["requested_depth"] == 9))
                ranks = {(r["output_id"], r["query_id"], r["candidate_id"]): r
                         for r in common.iter_table("candidate_ranks")}
                removed = ranks["a", self.ids[0], self.ids[1]]
                self.assertEqual((removed["native_rank"], removed["active_rank"], removed["active_status"]),
                                 (1, None, "excluded_from_common"))
                reranked = ranks["a", self.ids[0], self.ids[2]]
                self.assertEqual((reranked["native_rank"], reranked["active_rank"]), (2, 1))
                self.assertEqual(ranks["b", self.ids[0], self.ids[1]]["status"], "unscored")
                self.assertIsNotNone(ranks["b", self.ids[1], self.ids[0]]["active_rank"])
                self.assertEqual(len(common.materialize_table("exclusions")), 15)

    def test_missing_run_keeps_declared_recurrence_denominator(self):
        ds = self.descriptors()
        ds[2].update(method_id="saved-method", configuration_id="replicates", representation="long_scores")
        ds[2]["missing_queries"] = self.ids[:1]
        ds[2]["data"] = {"format": "json", "inline": {"records": [
            {"query_id": q, "candidate_id": c, "score": SCORES_A[i][j]}
            for i, q in enumerate(self.ids) for j, c in enumerate(self.ids) if i != 0]}}
        result = self.compare(ds, depths=(9,))
        rows = [r for r in result.iter_table("run_recurrence") if r["query_id"] == self.ids[0]]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual((row["expected_runs"], row["evaluable_runs"], row["nominations"]), (3, 2, 2))
            self.assertEqual(row["status"], "unavailable")
            self.assertIsNone(row["recurrence_fraction"])
        self.assertTrue(all(r["recurrence_fraction"] == 1 for r in result.iter_table("run_recurrence")
                            if r["query_id"] != self.ids[0]))

    def test_legacy_triangle_opt_in_preserves_both_directions_and_counts(self):
        ds = []
        for oid in ("a", "b"):
            d = self.descriptor(oid)
            d["representation"] = "legacy_score_count"
            d["count_semantics"] = "joint observed sample count; not an eligibility mask"
            d["data"]["inline"]["values"] = [[f"{score:.5f}:3" if j > i else ""
                                                 for j, score in enumerate(row)] for i, row in enumerate(SCORES_A)]
            ds.append(d)
        unexpanded = load_comparison_input(ds[0])
        self.assertEqual(rank_output(unexpanded, self.ids[-1]).order, ())
        self.assertEqual(unexpanded.pair(self.ids[1], self.ids[0]).status, "unscored")
        for d in ds:
            d["data"]["symmetric"] = True
        result = self.compare(ds, depths=(9,))
        for output in result.outputs:
            self.assertTrue(any("precision" in w.reason for w in output.warnings))
            for i, q in enumerate(self.ids):
                self.assertEqual(rank_output(output, q).order, tuple(self.ids[j] for j in ORDERS_A[i]))
                for j, c in enumerate(self.ids):
                    if q != c:
                        self.assertEqual((output.pair(q, c).score, output.pair(q, c).count), (SCORES_A[i][j], 3))
        self.assertTrue(all(r["effective_depth"] == 3 and r["overlap_fraction"] == 1
                            for r in result.iter_table("agreement")))
        for conflicting in ("0.90000:3", "-0.90000:2"):
            d = copy.deepcopy(ds[0])
            d["data"]["inline"]["values"][1][0] = conflicting
            with self.assertRaisesRegex(ComparisonValidationError, "conflicting reciprocal"):
                load_comparison_input(d)
        d = copy.deepcopy(ds[0])
        d["identity"]["candidate_namespace"]["modality"] += "-different"
        with self.assertRaisesRegex(ComparisonValidationError, "identical entity namespaces"):
            load_comparison_input(d)
        with tempfile.TemporaryDirectory() as tmp:
            bundle = write_comparison(result, Path(tmp) / "legacy")
            self.assert_parity(result, load_comparison_bundle(bundle))

    def test_full_rank_input_and_result_bundle_roundtrips(self):
        for policy in ("strict", "common"):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as tmp:
                ds = self.descriptors()
                ds[1]["data"]["inline"]["values"][0][1] = None
                ds[0]["data"]["inline"]["values"][0][2] = -.8123456789123456
                result = self.compare(ds, policy=policy, depths=(1,))
                root = Path(tmp)
                inputs = export_comparison_inputs(result.outputs, root / "inputs", settings=result.settings)
                self.assert_parity(result, compare_results(load_input_bundle(inputs)))
                bundle = write_comparison(result, root / "result")
                with gzip.open(bundle / "candidate_ranks.csv.gz", "rt", encoding="utf-8", newline="") as handle:
                    exported = [{k: json.loads(v) for k, v in row.items()} for row in csv.DictReader(handle)]
                self.assertEqual(exported, result.materialize_table("candidate_ranks"))
                self.assertEqual(len(exported), 48)  # includes below top-one and diagonals
                self.assertTrue(any(r["active_rank"] == 3 for r in exported))
                self.assertTrue(any(r["score"] == -.8123456789123456 for r in exported))
                self.assert_parity(result, load_comparison_bundle(bundle))

    def test_cli_saved_csv_manifest_end_to_end_without_training_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ds = [self.descriptor(), self.descriptor("b", SCORES_B, transposed=True, reorder=True)]
            for i, d in enumerate(ds):
                payload = d["data"]["inline"]
                name = f"saved-{i}.csv"
                with (root / name).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["feature_id", *payload["column_ids"]])
                    writer.writerows([q, *values] for q, values in zip(payload["row_ids"], payload["values"]))
                d["data"] = {"format": "csv", "path": name}
            path = root / "manifest.json"
            path.write_text(json.dumps({"schema_version": 1, "dataset": ds[0]["identity"],
                                        "outputs": ds, "settings": {"depths": [1, 2, 9]}}), encoding="utf-8")
            api = compare_results(load_manifest(path))
            # Execute the real module entry point, blocking training/plotting imports.
            script = '''import importlib.abc, runpy, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'pandas', 'numpy', 'sklearn', 'matplotlib', 'seaborn'} or fullname.startswith('valpas._core'):
            raise AssertionError('Unexpected analysis dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
runpy.run_module('valpas.cli', run_name='__main__')
'''
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
            completed = subprocess.run([sys.executable, "-c", script, "compare", "--manifest", str(path),
                                        "--outdir", str(root / "cli"), "--tables-only"],
                                       cwd=root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("4/4 queries", completed.stdout)
            self.assertIn("no HTML", completed.stdout)
            self.assertIn(api.comparison_id, completed.stdout)
            self.assertEqual(len(api.materialize_table("candidate_ranks")), 32)
            self.assertEqual(len(api.materialize_table("agreement")), 12)
            self.assert_parity(api, load_comparison_bundle(root / "cli"))
            for source in root.glob("saved-*.csv"):
                source.unlink()
            path.unlink()
            self.assert_parity(api, load_comparison_bundle(root / "cli"))

    @unittest.skipUnless(importlib.util.find_spec("pandas"), "pandas unavailable for structural adapter check")
    def test_pandas_association_shape_square_and_selected_rectangle_detached(self):
        import pandas as pd

        # Matches AssociationResult's stored fields for one omic: square labeled
        # DataFrames, omic_y=None. Do not import its training-dependent module.
        values = pd.DataFrame(SCORES_A, index=self.ids, columns=self.ids)
        values.index.name, values.columns.name = "original index", "original columns"
        counts = pd.DataFrame(3, index=self.ids[::-1], columns=self.ids[1:] + self.ids[:1])
        values.at[self.ids[0], self.ids[1]] = -.9123456789123456
        values.at[self.ids[2], self.ids[3]] = float("nan")
        result = SimpleNamespace(values=values, counts=counts,
                                 omic_x=SimpleNamespace(type=self.modality, features=pd.Index(self.ids)),
                                 omic_y=None, analysis_results={"saved": True}, annotationlist=None, edgelist=None,
                                 save=Mock(side_effect=AssertionError("save must not be called")),
                                 as_list=Mock(side_effect=AssertionError("as_list must not be called")))
        before_values, before_counts = values.copy(deep=True), counts.copy(deep=True)
        adapted = []
        for axis in ("index", "columns"):
            for rectangular in (False, True):
                with self.subTest(axis=axis, rectangular=rectangular):
                    qs = self.ids[:2] if rectangular else self.ids[:]
                    cs = self.ids[1:] if rectangular else self.ids[:]
                    d = self.descriptor(queries=qs, candidates=cs, transposed=axis == "columns")
                    d["count_semantics"] = "joint observed sample count"
                    out = from_association_result(result, d, query_axis=axis, query_ids=qs, candidate_ids=cs)
                    adapted.append(out)
                    for q in qs:
                        for c in cs:
                            score = values.at[q, c] if axis == "index" else values.at[c, q]
                            self.assertEqual(out.pair(q, c).count, 3)
                            if pd.isna(score):
                                self.assertEqual(out.pair(q, c).status, "unscored")
                                self.assertNotIn(c, rank_output(out, q).order)
                            else:
                                self.assertEqual(out.pair(q, c).score, score)
                    pd.testing.assert_frame_equal(values, before_values)
                    pd.testing.assert_frame_equal(counts, before_counts)
        result.save.assert_not_called()
        result.as_list.assert_not_called()
        self.assertIsNone(result.omic_y)
        self.assertEqual(result.omic_x.type, self.modality)
        self.assertTrue(result.omic_x.features.equals(pd.Index(self.ids)))
        self.assertEqual(result.analysis_results, {"saved": True})
        values.at[self.ids[0], self.ids[1]] = 999
        counts.iloc[:, :] = 0
        self.assertEqual(adapted[0].pair(self.ids[0], self.ids[1]).score, -.9123456789123456)
        self.assertEqual(adapted[0].pair(self.ids[0], self.ids[1]).count, 3)


class ProteinAbundanceCase(SingleModalityChecks, unittest.TestCase):
    modality = "proteomics"
    prefix = "P"


class GeneExpressionCase(SingleModalityChecks, unittest.TestCase):
    modality = "transcriptomics"
    prefix = "G"


if __name__ == "__main__":
    unittest.main()
