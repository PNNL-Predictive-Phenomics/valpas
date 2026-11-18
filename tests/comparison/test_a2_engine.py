"""Hand-calculated A2 scientific contracts, using saved values only."""
import copy
import json
import unittest

from test_a1_contracts import descriptor, table_descriptor, prefix_descriptor, FIXTURE
from valpas.comparison import (ComparisonSettings, ComparisonValidationError,
    compare_results, load_manifest, load_comparison_input)


def compare(descriptors, policy="strict", depths=(1, 2, 5)):
    return compare_results([load_comparison_input(d) for d in descriptors],
                           ComparisonSettings(pool_policy=policy, depths=depths))


class EngineCase(unittest.TestCase):
    def test_requires_two_and_allows_one_configuration_two_runs(self):
        with self.assertRaisesRegex(ComparisonValidationError, "at least two"):
            compare([descriptor()])
        r = compare([descriptor("a"), descriptor("b")])
        overview = r.materialize_table("dataset_summary")[0]
        self.assertEqual((overview["methods"], overview["configurations"], overview["outputs"]), (1, 1, 2))
        self.assertEqual(r.materialize_table("agreement")[0]["overlap_fraction"], 1)
        self.assertEqual(r.materialize_table("agreement")[0]["pair_class"], "same_configuration_different_run")

    def test_every_a0_hand_calculated_metric(self):
        m = load_manifest(FIXTURE / "manifest.json")
        expected = json.loads((FIXTURE / "expected.json").read_text())["agreements"]
        results = {policy: compare_results(m, ComparisonSettings(pool_policy=policy, depths=(1, 2, 5))) for policy in ("strict", "common")}
        for e in expected:
            with self.subTest(expected=e):
                rows = results[e["pool"]].materialize_table("agreement")
                r = next(r for r in rows if r["query_id"] == e["query_id"] and r["requested_depth"] == e["requested_depth"] and
                         {r["left_output_id"], r["right_output_id"]} == set(e["outputs"]))
                for name in ("effective_depth", "shared_count", "overlap_fraction", "jaccard", "status"):
                    self.assertEqual(r[name], e[name])
                if "reason" in e:
                    self.assertEqual(r["reason"], e["reason"])

    def test_partial_disjoint_identical_lists_and_denominators(self):
        r = compare([descriptor("a", [3, 2, 1]), descriptor("b", [1, 3, 2])])
        one, two, five = r.materialize_table("agreement")
        self.assertEqual((one["shared_count"], one["union_size"], one["overlap_fraction"], one["jaccard"]), (0, 2, 0, 0))
        self.assertEqual((two["shared_count"], two["union_size"], two["overlap_fraction"], two["jaccard"]), (1, 3, .5, 1/3))
        self.assertEqual((five["requested_depth"], five["effective_depth"], five["overlap_fraction"]), (5, 3, 1))

    def test_all_pair_classifications_no_method_collapsing(self):
        a, b, c, d = [descriptor(x) for x in "abcd"]
        c["configuration_id"] = "other-config"
        c["configuration"]["preprocessing"] = {"transform": "other"}
        d["configuration_id"], d["method_id"] = "other-method-config", "other-method"
        r = compare([a, b, c, d], depths=(1,))
        rows = r.materialize_table("agreement")
        self.assertEqual(len(rows), 6)
        self.assertEqual({x["pair_class"] for x in rows}, {"same_configuration_different_run", "same_method_different_configuration", "different_method"})
        self.assertTrue(any("not an isolated method" in w.reason for w in r.warnings))
        self.assertTrue(r.materialize_table("configuration_differences"))

    def test_strict_is_cohort_wide_not_pair_specific(self):
        m = load_manifest(FIXTURE / "manifest.json")
        r = compare_results(m, ComparisonSettings(depths=(1,)))
        missing = [x for x in r.materialize_table("agreement") if x["query_id"] == "M02"]
        self.assertEqual(len(missing), 3)
        self.assertTrue(all(x["status"] == "unavailable" and x["shared_count"] is None for x in missing))
        rec = [x for x in r.materialize_table("run_recurrence") if x["query_id"] == "M02" and x["configuration_id"] == "ae-base"]
        self.assertTrue(all(x["expected_runs"] == 2 and x["recurrence_fraction"] is None for x in rec))
        self.assertTrue(all(x["reason"] == "scorable_candidate_sets_differ" for x in rec))

    def test_common_native_ranks_exclusions_and_full_rank_export(self):
        r = compare_results(load_manifest(FIXTURE / "manifest.json"), ComparisonSettings(pool_policy="common", depths=(1,)))
        ranks = r.materialize_table("candidate_ranks")
        self.assertEqual(len(ranks), 18)  # complete data, not just 6 top-one rows
        row = next(x for x in ranks if (x["query_id"], x["candidate_id"], x["output_id"]) == ("M02", "P03", "ae-seed-42"))
        self.assertEqual((row["native_rank"], row["active_rank"]), (2, 1))
        self.assertEqual(len([x for x in r.materialize_table("exclusions") if x["candidate_id"] == "P02"]), 3)
        score = next(x for x in ranks if (x["query_id"], x["candidate_id"], x["output_id"]) == ("M01", "P01", "pearson-run"))
        self.assertEqual(score["score"], -.9)

    def test_native_unequal_lengths_no_false_common_denominator(self):
        r = compare([descriptor("a", [3, None, 1]), descriptor("b", [3, 2, 1])], "native_inspection", (5,))
        row = r.materialize_table("agreement")[0]
        self.assertEqual((row["left_list_size"], row["right_list_size"], row["shared_count"], row["union_size"]), (2, 3, 2, 3))
        self.assertEqual((row["left_shared_fraction"], row["right_shared_fraction"], row["jaccard"]), (1, 2/3, 2/3))
        self.assertIsNone(row["overlap_fraction"])
        self.assertIsNone(row["effective_depth"])
        self.assertEqual(row["status"], "descriptive")
        summary = r.materialize_table("agreement_summary")[0]
        self.assertEqual((summary["evaluable_queries"], summary["descriptive_queries"]), (0, 1))
        self.assertIsNone(summary["median"])
        self.assertTrue(all(x["recurrence_fraction"] is None for x in r.materialize_table("run_recurrence")))

    def test_prefix_depths_independent_and_strict_certificates(self):
        r = compare([prefix_descriptor("a", 2), prefix_descriptor("b", 2)])
        rows = r.materialize_table("agreement")
        self.assertEqual([x["status"] for x in rows], ["available", "available", "unavailable"])
        self.assertEqual(rows[-1]["reason"], "insufficient_certified_depth")
        self.assertEqual(len(r.materialize_table("candidate_ranks")), 4)
        a, b = prefix_descriptor("a"), prefix_descriptor("b")
        b["completeness"]["queries"]["q"]["pool_id"] = "other"
        self.assertEqual(compare([a, b]).materialize_table("agreement")[0]["reason"], "certified_native_pools_differ")
        with self.assertRaisesRegex(ComparisonValidationError, "complete representations"):
            compare([a, b], "common")

    def test_unequal_certified_exhausted_prefixes(self):
        a, b = prefix_descriptor("a", 3), prefix_descriptor("b", 2)
        b["candidate_ids"] = ["b", "c"]
        b["completeness"]["queries"]["q"].update(pool_size=2, exhausted=True, pool_id="bc")
        row = compare([a, b], "native_inspection", (20,)).materialize_table("agreement")[0]
        self.assertEqual((row["left_list_size"], row["right_list_size"], row["left_shared_fraction"], row["right_shared_fraction"]), (3, 2, 2/3, 1))
        self.assertEqual(row["status"], "descriptive")
        self.assertIsNone(row["overlap_fraction"])

    def test_filtered_inspection_rank_only_and_permutation(self):
        d = table_descriptor("filtered_list", "a")
        d["completeness"] = {"kind": "inspection_only", "filter": "manual"}
        d["missing_policy"]["absent"] = "unreported"
        d["data"]["inline"]["records"] = [{"query_id": "q", "candidate_id": "b", "rank": 7}]
        r = compare([d, descriptor("b")], "native_inspection", (1,))
        self.assertEqual(r.materialize_table("agreement")[0]["status"], "unavailable")
        row = next(x for x in r.materialize_table("candidate_ranks") if x["output_id"] == "a")
        self.assertEqual(row["saved_rank"], 7)
        self.assertIsNone(row["native_rank"])
        a, b = table_descriptor(oid="a"), descriptor("b")
        b["representation"] = "rank_permutation"
        b["data"] = {"format": "json", "index_base": 0, "inline": {"query_ids": ["q"], "permutations": [[1, 2, 0]]}}
        r = compare([a, b])
        self.assertTrue(all(x["overlap_fraction"] == 1 for x in r.materialize_table("agreement")))
        self.assertTrue(all(x["score"] is None for x in r.materialize_table("candidate_ranks")))

    def test_missing_run_retains_expected_denominator(self):
        a, b, c = descriptor("a"), descriptor("b"), table_descriptor(oid="c")
        c["missing_queries"] = ["q"]
        c["data"]["inline"]["records"] = []
        r = compare([a, b, c], depths=(1,))
        rows = r.materialize_table("run_recurrence")
        arow = next(x for x in rows if x["candidate_id"] == "a")
        self.assertEqual((arow["nominations"], arow["evaluable_runs"], arow["expected_runs"]), (2, 2, 3))
        self.assertEqual(arow["status"], "unavailable")
        self.assertIsNone(arow["recurrence_fraction"])

    def test_recurrence_hand_calculation_and_single_run_not_assessed(self):
        r = compare_results(load_manifest(FIXTURE / "manifest.json"), ComparisonSettings(pool_policy="common", depths=(1, 2)))
        rows = r.materialize_table("run_recurrence")
        for row in rows:
            if row["configuration_id"] == "pearson-base":
                self.assertEqual(row["status"], "not_assessed")
                self.assertIsNone(row["recurrence_fraction"])
        row = next(x for x in rows if (x["query_id"], x["candidate_id"], x["configuration_id"], x["requested_depth"]) == ("M02", "P03", "ae-base", 1))
        self.assertEqual((row["nominations"], row["expected_runs"], row["evaluable_runs"], row["recurrence_fraction"]), (1, 2, 2, .5))

    def test_empty_unavailable_and_empty_common_error(self):
        ds = [descriptor(x, [None, None, None]) for x in "ab"]
        r = compare(ds)
        self.assertTrue(all(x["status"] == "unavailable" and x["overlap_fraction"] is None for x in r.materialize_table("agreement")))
        self.assertTrue(all(x["candidate_id"] is None for x in r.materialize_table("run_recurrence")))
        self.assertIsNone(r.materialize_table("agreement_summary")[0]["median"])
        with self.assertRaisesRegex(ComparisonValidationError, "empty common scorable pool"):
            compare(ds, "common")

    def test_query_exclusions_overview_and_distribution_denominators(self):
        a, b = descriptor("a"), descriptor("b")
        a["query_ids"].append("extra")
        a["data"]["inline"]["row_ids"].append("extra")
        a["data"]["inline"]["values"].append([1, 2, 3])
        r = compare([a, b], "common", (1,))
        summary = r.materialize_table("agreement_summary")[0]
        self.assertEqual((summary["declared_queries"], summary["eligible_queries"], summary["evaluable_queries"], summary["excluded_queries"]), (2, 1, 1, 1))
        self.assertEqual(summary["median"], 1)
        self.assertEqual(r.materialize_table("query_summary")[0]["status"], "excluded")
        self.assertEqual(len([x for x in r.materialize_table("exclusions") if x["candidate_id"] is None]), 2)

    def test_summary_quartiles_and_no_run_pair_averaging(self):
        r = compare_results(load_manifest(FIXTURE / "manifest.json"), ComparisonSettings(pool_policy="common", depths=(1,)))
        rows = r.materialize_table("agreement_summary")
        self.assertEqual(len(rows), 3)
        row = next(x for x in rows if {x["left_output_id"], x["right_output_id"]} == {"pearson-run", "ae-seed-123"})
        self.assertEqual((row["minimum"], row["q1"], row["median"], row["q3"], row["maximum"]), (0, .25, .5, .75, 1))

    def test_bounded_materialization_and_detachment(self):
        ds = [descriptor("a"), descriptor("b")]
        r = compare(ds)
        ds[0]["data"]["inline"]["values"][0][0] = 100
        self.assertEqual(r.outputs[0].pair("q", "a").score, -.9)
        with self.assertRaisesRegex(ComparisonValidationError, "materialization limit"):
            r.materialize_table("candidate_ranks", max_rows=1)
        with self.assertRaises(ComparisonValidationError):
            list(r.iter_table("unknown"))
        self.assertEqual(len(list(r.iter_table("candidate_ranks"))), 6)
        self.assertNotIn("candidate_ranks", r.summaries)
        with self.assertRaises(TypeError):
            r.summaries["query_summary"][0]["query_id"] = "mutated"


if __name__ == "__main__":
    unittest.main()
