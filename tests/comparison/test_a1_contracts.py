"""A1 contracts/adapters/ranking tests, compatible with unittest and pytest."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from valpas.comparison import (
    ComparisonInput, ComparisonSettings, ComparisonValidationError, PairValue,
    build_pools, load_comparison_input, load_manifest, rank_output, top_list,
    validate_compatibility,
)

FIXTURE = Path(__file__).parent / "fixtures" / "demo-01"


def descriptor(oid="one", scores=None):
    d = json.loads((FIXTURE / "manifest.json").read_text())["outputs"][0]
    d.update(output_id=oid, run_id=oid, configuration_id="config", query_ids=["q"],
             candidate_ids=["a", "b", "c"])
    d["data"] = {"format": "json", "inline": {"row_ids": ["q"], "column_ids": ["a", "b", "c"],
                                                   "values": [scores if scores is not None else [-0.9, 0.8, 0.1]]}}
    return d


def table_descriptor(rep="ordered_ranks", oid="one"):
    d = descriptor(oid)
    d["representation"] = rep
    d["data"] = {"format": "json", "inline": {"records": [
        {"query_id": "q", "candidate_id": c, "rank": i}
        for i, c in enumerate(("b", "c", "a"), 1)]}}
    return d


def prefix_descriptor(oid="one", depth=2):
    d = table_descriptor("certified_prefix", oid)
    d["data"]["inline"]["records"] = d["data"]["inline"]["records"][:depth]
    d["missing_policy"]["absent"] = "truncated"
    d["completeness"] = {"kind": "prefix", "queries": {"q": {
        "depth": depth, "pool_id": "native-q-abc", "pool_size": 3,
        "exhausted": depth == 3, "complete_prefix": True, "self_excluded": True}}}
    return d


class ContractCase(unittest.TestCase):
    def reject(self, d, field=None):
        with self.assertRaises(ComparisonValidationError) as caught:
            load_comparison_input(d)
        issue = caught.exception.issue
        self.assertTrue(issue.field)
        self.assertTrue(issue.reason)
        self.assertTrue(issue.remediation)
        if field:
            self.assertIn(field, issue.field)
        return issue

    def test_demo_matches_a0_reference_without_metrics(self):
        manifest = load_manifest(FIXTURE / "manifest.json")
        expected = json.loads((FIXTURE / "expected.json").read_text())
        self.assertEqual(len(manifest.outputs), 3)
        self.assertEqual(len(manifest.compatibility.run_groups), 2)
        self.assertEqual(manifest.compatibility.identity_status, "user_attested")
        for policy in ("strict", "common"):
            pools = build_pools(manifest.outputs, ComparisonSettings(pool_policy=policy))
            for q, pool in pools.queries.items():
                for oid, view in pool.native.items():
                    self.assertEqual(list(view.order), expected["native_order"][q][oid])
                    if policy == "common":
                        self.assertEqual(list(pool.active_orders[oid]), expected["common_order"][q][oid])
                if policy == "strict":
                    self.assertEqual(pool.reason, expected["strict_query_status"][q]["reason"])
        self.assertEqual(manifest.outputs[0].pair("M01", "P01").score, -0.9)

    def test_unknown_keys_versions_types_and_nested_settings(self):
        mutations = [
            lambda d: d.update(schema_version=True), lambda d: d.update(schema_version=2),
            lambda d: d.update(surprise=1), lambda d: d["identity"].update(typo=1),
            lambda d: d["identity"]["query_namespace"].update(modailty="x"),
            lambda d: d["configuration"].update(preprocesing={}),
            lambda d: d["completeness"].update(complet=True),
            lambda d: d["missing_policy"].update(nann="unscored"),
            lambda d: d["data"].update(allow_pickle=True),
            lambda d: d["data"]["inline"].update(transpose=True),
            lambda d: d["provenance"].update(checkpoint="model.pt"),
            lambda d: d["configuration"]["parameters"].update(seed=42),
            lambda d: d.update(ranking_policy="descending"),
            lambda d: d.update(orientation="guess"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                d = descriptor()
                mutate(d)
                self.reject(d)
        for settings in ({"pool_polcy": "common"}, {"depths": [True]}, {"exclude_self": 1},
                         {"attestations": [{"output_id": "one", "field": "context", "claimed_value": "x", "statement": "test", "force": True}]}):
            with self.subTest(settings=settings), self.assertRaises(ComparisonValidationError):
                ComparisonSettings.from_dict(settings)

    def test_exact_ids_and_reordered_matrix_axes(self):
        d = descriptor()
        d["query_ids"] = ["001", " q "]
        d["candidate_ids"] = ["01", " 01", "Ω"]
        d["data"]["inline"] = {"row_ids": [" q ", "001"], "column_ids": ["Ω", "01", " 01"],
                                  "values": [[2, 1, 3], [4, 6, 5]]}
        o = load_comparison_input(d)
        self.assertEqual(o.pair("001", "01").score, 6)
        self.assertEqual(rank_output(o, " q ").order, (" 01", "Ω", "01"))
        d["candidate_ids"] = ["01", "01", "Ω"]
        self.reject(d, "candidate_ids")
        d = descriptor()
        d["query_ids"] = [1]
        self.reject(d, "query_ids")

    def test_explicit_transposed_rectangular_and_square(self):
        d = descriptor()
        d["orientation"] = "candidate_rows_query_columns"
        d["data"]["inline"] = {"row_ids": ["c", "a", "b"], "column_ids": ["q"], "values": [[0.1], [-0.9], [0.8]]}
        self.assertEqual(rank_output(load_comparison_input(d), "q").order, ("a", "b", "c"))
        d["orientation"] = "query_rows_candidate_columns"
        self.reject(d, "axes")

    def test_all_score_policies_signed_values_and_unicode_ties(self):
        expected = {"native_descending": ("b", "c", "a"), "native_ascending": ("a", "c", "b"),
                    "absolute_descending": ("a", "b", "c"), "absolute_ascending": ("c", "b", "a")}
        for policy, order in expected.items():
            d = descriptor()
            d["ranking_policy"] = policy
            o = load_comparison_input(d)
            self.assertEqual(rank_output(o, "q").order, order)
            self.assertEqual(o.pair("q", "a").score, -0.9)
        d = descriptor(scores=[-0.0, 0.0, 0.0])
        d["candidate_ids"] = ["é", "Z", "a"]
        d["data"]["inline"]["column_ids"] = d["candidate_ids"]
        self.assertEqual(rank_output(load_comparison_input(d), "q").order, ("Z", "a", "é"))
        d = descriptor(scores=[-0.1, 0.10000000000000002, 0.0])
        self.assertEqual(rank_output(load_comparison_input(d), "q").order, ("b", "a", "c"))

    def test_nan_infinity_and_unscored_not_worst_rank(self):
        d = descriptor(scores=[None, 0, "NaN"])
        self.reject(d)
        d["missing_policy"]["nan"] = "unscored"
        o = load_comparison_input(d)
        self.assertEqual(rank_output(o, "q").order, ("b",))
        self.assertEqual(o.pair("q", "a").status, "unscored")
        for bad in ("inf", "-inf", True, "not a number"):
            d["data"]["inline"]["values"][0][0] = bad
            self.reject(d)

    def test_namespace_aware_self_edges(self):
        d = descriptor()
        d["query_ids"] = ["a"]
        d["data"]["inline"]["row_ids"] = ["a"]
        self.assertIn("a", rank_output(load_comparison_input(d), "a").order)
        d["identity"]["query_namespace"] = d["identity"]["candidate_namespace"]
        o = load_comparison_input(d)
        self.assertEqual(rank_output(o, "a").order, ("b", "c"))
        self.assertEqual(rank_output(o, "a").statuses["a"], ("ineligible", "self_edge"))
        self.assertEqual(rank_output(o, "a", exclude_self=False).order[0], "a")

    def test_long_scores_missing_eligibility_and_duplicate_pairs(self):
        d = table_descriptor("long_scores")
        d["data"]["inline"]["records"] = [{"query_id": "q", "candidate_id": "b", "score": -0.3}]
        d["missing_policy"]["absent"] = "unscored"
        o = load_comparison_input(d)
        self.assertEqual(o.pair("q", "a").status, "unscored")
        self.assertEqual(rank_output(o, "q").order, ("b",))
        d["eligibility"] = [{"query_id": "q", "candidate_id": "b", "eligible": False, "reason": "excluded_by_design"}]
        o = load_comparison_input(d)
        self.assertEqual(o.pair("q", "b").score, -0.3)
        self.assertEqual(o.pair("q", "b").status, "ineligible")
        self.assertFalse(rank_output(o, "q").order)
        d["data"]["inline"]["records"] *= 2
        self.reject(d)

    def test_full_permutation_not_inverse_ranks_both_bases(self):
        for base, permutation in ((0, [2, 0, 1]), (1, [3, 1, 2])):
            d = descriptor()
            d["representation"] = "rank_permutation"
            d["data"] = {"format": "json", "index_base": base, "inline": {"query_ids": ["q"], "permutations": [permutation]}}
            o = load_comparison_input(d)
            self.assertEqual(rank_output(o, "q").order, ("c", "a", "b"))
            self.assertEqual(dict(rank_output(o, "q").ranks), {"c": 1, "a": 2, "b": 3})
            for bad in ([0, 0, 1], [1, 2], [1, 2, 4], [True, 1, 2], [0.0, 1, 2]):
                d["data"]["inline"]["permutations"] = [bad]
                self.reject(d)

    def test_complete_ordered_ranks_statuses_and_missing_query(self):
        d = table_descriptor()
        d["query_ids"].append("missing")
        d["missing_queries"] = ["missing"]
        rows = d["data"]["inline"]["records"]
        rows[:] = [{"query_id": "q", "candidate_id": "a", "rank": 1},
                   {"query_id": "q", "candidate_id": "b", "status": "unscored", "reason": "no_observations"},
                   {"query_id": "q", "candidate_id": "c", "status": "ineligible", "reason": "design"}]
        o = load_comparison_input(d)
        self.assertEqual(rank_output(o, "q").order, ("a",))
        self.assertEqual(o.pair("missing", "a").status, "missing_query")
        self.assertFalse(rank_output(o, "missing").certified)
        rows.pop()
        self.reject(d, "status")
        d["eligibility"] = [{"query_id": "q", "candidate_id": "c", "eligible": False, "reason": "design"}]
        load_comparison_input(d)
        rows[0]["rank"] = 2
        self.reject(d, "rank")

    def test_contradictory_scores_ranks_statuses(self):
        d = table_descriptor()
        for row, score in zip(d["data"]["inline"]["records"], [0.1, 0.8, -0.9]):
            row["score"] = score
        self.reject(d, "rank")
        d = table_descriptor()
        d["data"]["inline"]["records"][0].update(status="unscored", reason="missing")
        self.reject(d)
        d = descriptor()
        d["data"]["inline"]["values"] = [[1, 2]]
        self.reject(d)

    def test_certified_prefix_depth_exhaustion_and_common_rejection(self):
        o = load_comparison_input(prefix_descriptor())
        self.assertEqual(top_list(o, "q", 2), ("b", "c"))
        self.assertEqual(o.pair("q", "a").status, "truncated")
        with self.assertRaises(ComparisonValidationError):
            top_list(o, "q", 3)
        with self.assertRaises(ComparisonValidationError):
            build_pools([o], ComparisonSettings(pool_policy="common"))
        full = load_comparison_input(prefix_descriptor(depth=3))
        self.assertEqual(len(top_list(full, "q", 20)), 3)
        with self.assertRaises(ComparisonValidationError):
            build_pools([full], ComparisonSettings(pool_policy="common"))
        for field, value in (("complete_prefix", False), ("pool_size", 4), ("depth", 1), ("exhausted", True)):
            d = prefix_descriptor()
            d["completeness"]["queries"]["q"][field] = value
            self.reject(d)
        with self.assertRaises(ComparisonValidationError):
            rank_output(o, "q", exclude_self=False)

    def test_filtered_lists_inspection_only(self):
        d = table_descriptor("filtered_list")
        d["completeness"] = {"kind": "inspection_only", "filter": "score threshold; omissions unknown"}
        d["missing_policy"]["absent"] = "unreported"
        d["data"]["inline"]["records"] = [{"query_id": "q", "candidate_id": "b", "score": 0.8}]
        o = load_comparison_input(d)
        self.assertEqual(o.pair("q", "a").status, "unreported")
        self.assertFalse(rank_output(o, "q").ranks)
        with self.assertRaises(ComparisonValidationError):
            top_list(o, "q", 1)
        pool = build_pools([o]).queries["q"]
        self.assertFalse(pool.controlled_available)
        self.assertEqual(pool.coverage["one"]["native_scorable"], 1)
        self.assertEqual(pool.coverage["one"]["native_ranked"], 0)

    def test_csv_tsv_json_paths_and_exact_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for fmt, sep in (("csv", ","), ("tsv", "\t")):
                d = descriptor()
                d["query_ids"] = ["001 "]
                d["candidate_ids"] = ["01", " a", "Ω"]
                path = root / ("scores." + fmt)
                path.write_text(sep.join(["query_id", "Ω", "01", " a"]) + "\n" + sep.join(["001 ", "0.1", "-0.9", "0.8"]) + "\n")
                d["data"] = {"format": fmt, "path": path.name}
                o = load_comparison_input(d, base_dir=root)
                self.assertEqual(rank_output(o, "001 ").order, ("01", " a", "Ω"))
            for path in ("../escape.csv", "/tmp/file.csv", "https://host/data.csv", "file:///tmp/data.csv", "model.pt", "objects.npy"):
                d["data"] = {"format": "csv", "path": path}
                with self.subTest(path=path), self.assertRaises(ComparisonValidationError):
                    load_comparison_input(d, base_dir=root)
            (root / "bad.json").write_text('{"records": [], "records": []}')
            d["data"] = {"format": "json", "path": "bad.json"}
            with self.assertRaises(ComparisonValidationError):
                load_comparison_input(d, base_dir=root)
            (root / "outside.csv").symlink_to(FIXTURE.resolve() / "pearson-run.csv")
            d["data"] = {"format": "csv", "path": "outside.csv"}
            with self.assertRaises(ComparisonValidationError):
                load_comparison_input(d, base_dir=root)

    def test_legacy_score_count_precision_and_symmetry(self):
        d = descriptor()
        d["representation"] = "legacy_score_count"
        d["count_semantics"] = "pairwise observed sample count, not masks"
        d["data"]["inline"]["values"] = [["-0.90000:6", "0.80000:5", ""]]
        o = load_comparison_input(d)
        self.assertEqual(o.pair("q", "a").score, -0.9)
        self.assertEqual(o.pair("q", "a").count, 6)
        self.assertIn("precision", o.warnings[0].reason)
        d["query_ids"] = ["a", "b", "c"]
        d["identity"]["query_namespace"] = d["identity"]["candidate_namespace"]
        d["data"]["inline"] = {"row_ids": ["a", "b", "c"], "column_ids": ["a", "b", "c"],
                                  "values": [["", "-0.9:6", "0.8:6"], ["", "", "0.1:5"], ["", "", ""]]}
        o = load_comparison_input(d)
        self.assertIsNone(o.pair("b", "a").score)
        d["data"]["symmetric"] = True
        o = load_comparison_input(d)
        self.assertEqual(o.pair("b", "a").score, -0.9)
        self.assertEqual(rank_output(o, "a").order, ("b", "c"))
        self.assertEqual(rank_output(o, "b").order, ("a", "c"))
        d["data"]["inline"]["values"][1][0] = "0.9:6"
        self.reject(d, "symmetric")

    def test_long_table_delimited_blanks_statuses_and_malformed_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            d = table_descriptor("long_scores")
            d["missing_policy"]["absent"] = "unscored"
            d["data"] = {"format": "tsv", "path": "scores.tsv"}
            path = root / "scores.tsv"
            path.write_text("query_id\tcandidate_id\tscore\nq\ta\t-0.9\nq\tb\t\n")
            o = load_comparison_input(d, base_dir=root)
            self.assertEqual(o.pair("q", "b").reason, "declared_missing_score")
            self.assertEqual(rank_output(o, "q").order, ("a",))
            for content in ("query_id\tcandidate_id\nq\ta\n", "query_id\tcandidate_id\tscore\nq\ta\n",
                            "query_id\tcandidate_id\tscore\tscore\nq\ta\t1\t2\n",
                            "query_id\tcandidate_id\tscore\nq\ta\t1\nq\ta\t1\n"):
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ComparisonValidationError):
                    load_comparison_input(d, base_dir=root)

    def test_filtered_saved_rank_gaps_remain_inspection_only(self):
        d = table_descriptor("filtered_list")
        d["completeness"] = {"kind": "inspection_only", "filter": "manual selection"}
        d["missing_policy"]["absent"] = "unreported"
        rows = d["data"]["inline"]["records"]
        for row, rank, score in zip(rows, [2, 7, 12], [3, 2, 1]):
            row.update(rank=rank, score=score)
        o = load_comparison_input(d)
        self.assertEqual(o.pair("q", "c").rank, 7)
        self.assertFalse(rank_output(o, "q").ranks)
        rows[1]["rank"] = 2
        self.reject(d, "rank")

    def test_eligibility_status_conflicts_and_invalid_prefix_nested_keys(self):
        d = table_descriptor()
        d["eligibility"] = [{"query_id": "q", "candidate_id": "b", "eligible": False, "reason": "design"}]
        self.reject(d, "eligibility")
        d = table_descriptor()
        d["data"]["inline"]["records"][0] = {"query_id": "q", "candidate_id": "b", "status": "ineligible", "reason": "design"}
        d["eligibility"] = [{"query_id": "q", "candidate_id": "b", "eligible": True, "reason": "design"}]
        self.reject(d, "eligibility")
        d = prefix_descriptor()
        d["completeness"]["queries"]["q"]["tie_polcy"] = "wrong"
        self.reject(d, "completeness")
        d = prefix_descriptor()
        d["missing_queries"] = ["q"]
        self.reject(d)

    def test_direct_contract_cannot_bypass_normalized_validation(self):
        d = descriptor()
        with self.assertRaises(ComparisonValidationError):
            ComparisonInput(d, {("alien", "a"): PairValue("scorable", 1)})
        with self.assertRaises(ComparisonValidationError):
            PairValue("unscored", score=1)
        o = load_comparison_input(d)
        with self.assertRaises(TypeError):
            o.descriptor["identity"]["context"] = "mutated"
        d["identity"]["context"] = "changed caller"
        self.assertNotEqual(o.descriptor["identity"]["context"], d["identity"]["context"])


class IdentityPoolCase(unittest.TestCase):
    def pair(self):
        return descriptor("one"), descriptor("two")

    def test_known_identity_conflicts_never_overridden(self):
        for field, value in (("dataset_id", "other"), ("observation_ids", ["different"]),
                             ("context", "different experiment"), ("query_namespace", {"id": "other", "modality": "metabolomics"})):
            a, b = self.pair()
            b["identity"][field] = value
            with self.subTest(field=field), self.assertRaises(ComparisonValidationError):
                validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        a, b = self.pair()
        a["identity"]["dataset_evidence"].update(type="fingerprint", value="sha256:a")
        b["identity"]["dataset_evidence"].update(type="fingerprint", value="sha256:b")
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)])

    def test_source_evidence_and_context_attestations_preserve_unknowns(self):
        a, b = self.pair()
        evidence, context = copy.deepcopy(a["identity"]["dataset_evidence"]), a["identity"]["context"]
        b["identity"]["dataset_evidence"] = None
        b["identity"]["context"] = None
        outputs = [load_comparison_input(a), load_comparison_input(b)]
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility(outputs)
        claims = [{"output_id": "two", "field": field, "claimed_value": value, "statement": "Specific legacy log assertion."}
                  for field, value in (("dataset_evidence", evidence), ("context", context))]
        report = validate_compatibility(outputs, ComparisonSettings(attestations=claims))
        self.assertEqual(report.identity_status, "user_attested")
        self.assertIsNone(outputs[1].descriptor["identity"]["dataset_evidence"])
        claims[0]["claimed_value"]["source"] = "another-source"
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility(outputs, ComparisonSettings(attestations=claims))

    def test_observation_reordering_and_field_specific_attestation(self):
        a, b = self.pair()
        b["identity"]["observation_ids"].reverse()
        validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        observations = b["identity"]["observation_ids"]
        b["identity"]["observation_ids"] = None
        outputs = [load_comparison_input(a), load_comparison_input(b)]
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility(outputs)
        claim = {"output_id": "two", "field": "observation_ids", "claimed_value": observations, "statement": "Legacy log confirms exact observation set."}
        report = validate_compatibility(outputs, ComparisonSettings(attestations=[claim]))
        self.assertEqual(report.identity_status, "user_attested")
        claim["claimed_value"] = ["wrong"]
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility(outputs, ComparisonSettings(attestations=[claim]))
        b["identity"]["observation_ids"] = observations
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)], ComparisonSettings(attestations=[claim]))

    def test_configurations_runs_differences_and_unknowns(self):
        a, b = self.pair()
        b["seed"] = 123
        report = validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        self.assertEqual(report.run_groups["config"], ("one", "two"))
        b["configuration"]["parameters"]["minimum_joint_observations"] = 4
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        b["configuration_id"] = "other-config"
        report = validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        self.assertTrue(any(r["field"].endswith("minimum_joint_observations") for r in report.configuration_differences))
        a, b = self.pair()
        b["run_id"] = "one"
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        a, b = self.pair()
        original = copy.deepcopy(b["configuration"])
        b["configuration"]["preprocessing"] = None
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)])
        claim = {"output_id": "two", "field": "configuration", "claimed_value": original,
                 "statement": "The saved run log confirms the complete non-seed configuration."}
        validate_compatibility([load_comparison_input(a), load_comparison_input(b)], ComparisonSettings(attestations=[claim]))
        claim["claimed_value"]["parameters"] = {"different": True}
        with self.assertRaises(ComparisonValidationError):
            validate_compatibility([load_comparison_input(a), load_comparison_input(b)], ComparisonSettings(attestations=[claim]))

    def test_strict_common_native_coverage_and_exclusions(self):
        a, b = self.pair()
        b["data"]["inline"]["values"] = [[0.5, None, 0.9]]
        outputs = [load_comparison_input(a), load_comparison_input(b)]
        strict = build_pools(outputs)
        self.assertEqual(strict.queries["q"].reason, "scorable_candidate_sets_differ")
        common = build_pools(outputs, ComparisonSettings(pool_policy="common"))
        q = common.queries["q"]
        self.assertEqual(q.active_orders["one"], ("a", "c"))
        self.assertEqual(q.active_orders["two"], ("c", "a"))
        self.assertEqual(q.native["one"].ranks["c"], 3)
        self.assertEqual(q.active_ranks["one"]["c"], 2)
        self.assertEqual(q.coverage["one"]["excluded_scorable"], 1)
        self.assertEqual(len([e for e in common.exclusions if e.candidate_id == "b"]), 2)
        self.assertFalse(build_pools(outputs, ComparisonSettings(pool_policy="native_inspection")).queries["q"].controlled_available)
        b["eligibility"] = [{"query_id": "q", "candidate_id": "b", "eligible": False, "reason": "design"}]
        with self.assertRaises(ComparisonValidationError):
            build_pools([load_comparison_input(a), load_comparison_input(b)])

    def test_common_query_exclusions_empty_and_strict_prefix_certificates(self):
        a, b = self.pair()
        b["query_ids"].append("extra")
        b["data"]["inline"]["row_ids"].append("extra")
        b["data"]["inline"]["values"].append([1, 2, 3])
        outputs = [load_comparison_input(a), load_comparison_input(b)]
        with self.assertRaises(ComparisonValidationError):
            build_pools(outputs)
        common = build_pools(outputs, ComparisonSettings(pool_policy="common"))
        self.assertEqual(len([e for e in common.exclusions if e.query_id == "extra"]), 2)
        a["data"]["inline"]["values"] = [[None, None, None]]
        with self.assertRaises(ComparisonValidationError):
            build_pools([load_comparison_input(a)], ComparisonSettings(pool_policy="common"))
        a, b = prefix_descriptor("one"), prefix_descriptor("two")
        outputs = [load_comparison_input(a), load_comparison_input(b)]
        self.assertTrue(build_pools(outputs, ComparisonSettings(depths=[1, 2])).queries["q"].controlled_available)
        self.assertEqual(build_pools(outputs).queries["q"].reason, "insufficient_certified_depth")
        b["completeness"]["queries"]["q"]["pool_id"] = "different"
        self.assertEqual(build_pools([load_comparison_input(a), load_comparison_input(b)], ComparisonSettings(depths=[1])).queries["q"].reason, "certified_native_pools_differ")
        # Equal claimed IDs/sizes cannot override a known membership mismatch.
        a, b = prefix_descriptor("one", 1), prefix_descriptor("two", 1)
        for d, unavailable in ((a, "a"), (b, "c")):
            d["completeness"]["queries"]["q"]["pool_size"] = 2
            d["data"]["inline"]["records"].append({"query_id": "q", "candidate_id": unavailable,
                                                        "status": "unscored", "reason": "no_finite_score"})
        pool = build_pools([load_comparison_input(a), load_comparison_input(b)], ComparisonSettings(depths=[1]))
        self.assertEqual(pool.queries["q"].reason, "certified_native_pools_differ")


if __name__ == "__main__":
    unittest.main()
