"""Integrity checks for hand-calculated A0 data, not a comparison engine."""

import csv
import json
import math
from pathlib import Path
import unittest


FIXTURE = Path(__file__).parent / "fixtures" / "demo-01"


class TestSavedScoreFixture(unittest.TestCase):
    def setUp(self):
        self.metadata = json.loads((FIXTURE / "metadata.json").read_text(encoding="utf-8"))
        self.expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
        self.scores = {}
        for output in self.metadata["outputs"]:
            with (FIXTURE / output["score_file"]).open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                self.assertEqual(next(reader), ["query_id", *self.metadata["dataset"]["candidate_ids"]])
                rows = list(reader)
            self.assertEqual([row[0] for row in rows], self.metadata["dataset"]["query_ids"])
            self.assertTrue(all(len(row) == 4 for row in rows))
            self.scores[output["output_id"]] = {
                row[0]: {candidate: None if cell == "" else float(cell)
                         for candidate, cell in zip(self.metadata["dataset"]["candidate_ids"], row[1:])}
                for row in rows
            }

    def test_inventory_and_explicit_identity(self):
        outputs = self.metadata["outputs"]
        configurations = self.metadata["configurations"]
        self.assertEqual(self.expected["inventory"], {"methods": 2, "configurations": 2, "outputs": 3})
        self.assertEqual(len({o["method_id"] for o in outputs}), 2)
        self.assertEqual(len(configurations), 2)
        self.assertEqual(len(outputs), 3)
        self.assertEqual(len({o["output_id"] for o in outputs}), 3)
        self.assertEqual(len({o["run_id"] for o in outputs}), 3)
        dataset = self.metadata["dataset"]
        self.assertEqual(dataset["observation_ids"], [f"S{i:02d}" for i in range(1, 7)])
        self.assertEqual(dataset["query_ids"], ["M01", "M02"])
        self.assertEqual(dataset["candidate_ids"], ["P01", "P02", "P03"])
        self.assertNotEqual(dataset["query_namespace"], dataset["candidate_namespace"])
        for output in outputs:
            for key in ("dataset_id", "source_identity", "observation_ids"):
                self.assertEqual(output[key], dataset[key])
            self.assertEqual(output["method_id"], configurations[output["configuration_id"]]["method_id"])
        ae = [o for o in outputs if o["method_id"] == "autoencoder"]
        self.assertEqual([o["seed"] for o in ae], [42, 123])
        self.assertEqual({o["configuration_id"] for o in ae}, {"ae-base"})
        self.assertNotIn("seed", configurations["ae-base"]["parameters"])
        self.assertFalse(self.metadata["provenance"]["training_performed"])

    def test_signed_scores_and_exactly_one_explicit_missing_cell(self):
        self.assertEqual(list(self.scores["pearson-run"]["M01"].values()), [-0.9, 0.8, 0.1])
        missing = []
        for output, queries in self.scores.items():
            for query, values in queries.items():
                for candidate, value in values.items():
                    if value is None:
                        missing.append((output, query, candidate))
                    else:
                        self.assertTrue(math.isfinite(value))
        self.assertEqual(missing, [("pearson-run", "M02", "P02")])
        self.assertEqual(self.metadata["matrix_contract"]["blank_cell_status"], "unscored")

    def test_hand_calculated_native_orders(self):
        for output in self.metadata["outputs"]:
            policy = self.metadata["configurations"][output["configuration_id"]]["ranking_policy"]
            self.assertIn(policy, ("absolute_descending", "native_descending"))
            for query, values in self.scores[output["output_id"]].items():
                finite = [candidate for candidate, value in values.items() if value is not None]
                order = sorted(finite, key=lambda c: (
                    -abs(values[c]) if policy == "absolute_descending" else -values[c], c))
                self.assertEqual(order, self.expected["native_order"][query][output["output_id"]])

    def test_common_pools_exclusions_and_strict_status(self):
        exclusions = []
        for query in self.metadata["dataset"]["query_ids"]:
            pools = []
            for output, queries in self.scores.items():
                pools.append({c for c, v in queries[query].items() if v is not None})
                for candidate, value in queries[query].items():
                    if value is None:
                        exclusions.append({"query_id": query, "candidate_id": candidate,
                                           "output_id": output, "status": "unscored",
                                           "reason": "synthetic_missing_score"})
            common = set.intersection(*pools)
            self.assertEqual(sorted(common), self.expected["common_candidates"][query])
            available = all(pool == pools[0] for pool in pools)
            self.assertEqual(self.expected["strict_query_status"][query], {
                "status": "available" if available else "unavailable",
                "reason": None if available else "scorable_candidate_sets_differ",
            })
            for output, native_order in self.expected["native_order"][query].items():
                self.assertEqual([c for c in native_order if c in common],
                                 self.expected["common_order"][query][output])
        self.assertEqual(exclusions, self.expected["common_exclusions"])

    def test_hand_calculated_overlap_and_unavailable_values(self):
        for record in self.expected["agreements"]:
            with self.subTest(record=record):
                query = record["query_id"]
                if record["status"] == "unavailable":
                    self.assertEqual(record["pool"], "strict")
                    self.assertEqual(record["reason"], self.expected["strict_query_status"][query]["reason"])
                    for key in ("effective_depth", "shared_count", "overlap_fraction", "jaccard"):
                        self.assertIsNone(record[key])
                    continue
                if record["pool"] == "strict":
                    self.assertEqual(self.expected["strict_query_status"][query]["status"], "available")
                orders = self.expected["common_order" if record["pool"] == "common" else "native_order"][query]
                left, right = [orders[output] for output in record["outputs"]]
                self.assertEqual(set(left), set(right))
                depth = min(record["requested_depth"], len(left))
                a, b = set(left[:depth]), set(right[:depth])
                shared = len(a & b)
                self.assertEqual(record["effective_depth"], depth)
                self.assertEqual(record["shared_count"], shared)
                self.assertEqual(record["overlap_fraction"], shared / depth)
                self.assertEqual(record["jaccard"], shared / len(a | b))


if __name__ == "__main__":
    unittest.main()
