"""B1 scientific contracts and hand-calculated browser/Python parity fixtures."""
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from valpas.comparison.diagnostics import (SampleMetadata, DiagnosticRequest,
    load_sample_metadata, group_summary, covariance_diagnostic)
from valpas.comparison.models import ComparisonValidationError, thaw
from valpas.comparison.profiles import ProfileData

FIXTURE = Path(__file__).parent / "fixtures" / "b1-diagnostics.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


def dataset(obs):
    return {"dataset_id": "synthetic", "dataset_evidence": {
        "type": "fingerprint", "source": "hand-calculated", "value": "b1",
        "limitations": "Synthetic descriptive data, not model attribution"},
        "observation_ids": list(obs), "query_namespace": {"id": "q", "modality": "query"},
        "candidate_namespace": {"id": "c", "modality": "candidate"}, "context": "synthetic"}


def raw_layer(case=None):
    case = case or DATA["cases"][0]
    ds = dataset(case["observation_ids"])
    layer = {"layer_id": "raw", "dataset": ds,
        "orientation": "feature_rows_observation_columns", "observation_ids": list(case["observation_ids"]),
        "units": "synthetic", "transform": "none", "provenance": "hand-calculated",
        "raw_unimputed": True, "mask_source": "raw_finite", "subset_extra_observations": False,
        "algorithm_layers": {}, "features": [
            {"namespace": ds["query_namespace"], "feature_id": "Q", "values": list(case["x"]), "observed": None},
            {"namespace": ds["candidate_namespace"], "feature_id": "C", "values": list(case["y"]), "observed": None}]}
    return layer


def layer_for(case=None):
    return ProfileData([raw_layer(case)]).layers[0]


def metadata_doc(ds=None):
    ds = ds or dataset(DATA["cases"][0]["observation_ids"])
    return {"schema_version": 1, "dataset": copy.deepcopy(ds),
            "fields": {"condition": "categorical", "age": "continuous"},
            "records": [{"observation_id": sid, "values": {"condition": group, "age": i}}
                        for i, (sid, group) in enumerate(zip(ds["observation_ids"], DATA["group_case"]["values"]))]}


class MetadataCase(unittest.TestCase):
    def test_roundtrip_detached_immutable(self):
        doc = metadata_doc()
        metadata = SampleMetadata.from_dict(doc)
        expected = metadata.to_dict()
        doc["records"][0]["values"]["condition"] = "changed"
        doc["dataset"]["observation_ids"].reverse()
        doc["fields"]["age"] = "categorical"
        self.assertEqual(metadata.to_dict(), expected)
        with self.assertRaises(FrozenInstanceError):
            metadata.records = ()
        with self.assertRaises(TypeError):
            metadata.records[0]["values"]["condition"] = "changed"
        with self.assertRaises(TypeError):
            metadata.dataset["observation_ids"][0] = "changed"
        exported = metadata.to_dict()
        exported["records"].clear()
        self.assertEqual(SampleMetadata.from_dict(expected).to_dict(), expected)
        self.assertEqual(len(metadata.records), 5)

    def test_exact_ids_no_normalization_and_duplicate_rejection(self):
        doc = metadata_doc(dataset(["01", "1", " A", "A", "a"]))
        m = SampleMetadata.from_dict(doc)
        self.assertEqual([r["observation_id"] for r in m.records], doc["dataset"]["observation_ids"])
        doc["records"].append(copy.deepcopy(doc["records"][0]))
        with self.assertRaisesRegex(ComparisonValidationError, "duplicate"):
            SampleMetadata.from_dict(doc)

    def test_invalid_types_keys_versions(self):
        mutations = [lambda d: d.update(schema_version=True), lambda d: d.update(schema_version=2),
            lambda d: d.update(unknown=1), lambda d: d.update(subset_extra_observations=1),
            lambda d: d.update(fields=[]), lambda d: d["fields"].update(condition="ordinal"),
            lambda d: d["fields"].update({1: "categorical"}), lambda d: d.update(records=None),
            lambda d: d["records"][0].update(observation_id=1),
            lambda d: d["records"][0].update(observation_id=""),
            lambda d: d["records"][0].update(extra="unknown"),
            lambda d: d["records"][0]["values"].update(other=1),
            lambda d: d["records"][0]["values"].update(condition=1),
            lambda d: d["records"][0]["values"].update(age=True),
            lambda d: d["records"][0]["values"].update(age="1"),
            lambda d: d["records"][0]["values"].update(age=float("nan")),
            lambda d: d["records"][0]["values"].update(age=float("inf")),
            lambda d: d["records"][0]["values"].update(age=10 ** 1000),
            lambda d: d.pop("records"), lambda d: d.pop("fields")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                doc = metadata_doc(); mutation(doc)
                with self.assertRaises(ComparisonValidationError):
                    SampleMetadata.from_dict(doc)

    def test_missing_records_fields_nulls_and_extra_export(self):
        doc = metadata_doc(); ds = doc["dataset"]
        doc["records"] = [{"observation_id": "s01", "values": {"condition": "", "age": None}},
                          {"observation_id": "extra", "values": {"condition": "E", "age": 1.5}}]
        m = SampleMetadata.from_dict(doc)
        with self.assertRaisesRegex(ComparisonValidationError, "extra observations"):
            m.validate_binding(ds)
        m = replace(m, subset_extra_observations=True)
        rows = list(m.iter_table(ds))
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r["status"] == "missing" for r in rows), 9)
        self.assertEqual(sum(not r["in_required_cohort"] for r in rows), 2)
        self.assertEqual(rows[1]["value"], "")
        self.assertEqual(rows[1]["status"], "available")
        empty = SampleMetadata(ds, {}, [])
        self.assertEqual(list(empty.iter_table(ds)), [])
        self.assertEqual(len(list(SampleMetadata(ds, {"x": "continuous"}, []).iter_table(ds))), 5)

    def test_binding_matches_profile_identity_semantics(self):
        m = SampleMetadata.from_dict(metadata_doc()); ds = thaw(m.dataset)
        ds["observation_ids"].reverse()
        m.validate_binding(ds, outputs=())
        for name, value in [("dataset_id", "other"), ("context", None), ("context", "other"),
                            ("observation_ids", ["other"]), ("dataset_evidence", None),
                            ("query_namespace", {"id": "different", "modality": "query"})]:
            changed = thaw(m.dataset); changed[name] = value
            with self.subTest(name=name), self.assertRaises(ComparisonValidationError):
                m.validate_binding(changed)
        changed = thaw(m.dataset); changed["dataset_evidence"]["value"] = "other"
        with self.assertRaises(ComparisonValidationError):
            m.validate_binding(changed)

    def test_local_loader_fingerprint_and_strict_json(self):
        doc = metadata_doc()
        self.assertEqual(load_sample_metadata(doc).source_fingerprints, ())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            raw = json.dumps(doc).encode("utf-8"); path.write_bytes(raw)
            m = load_sample_metadata({"path": "metadata.json"}, base_dir=tmp)
            self.assertEqual(m.source_fingerprints[0]["role"], "sample_metadata")
            self.assertEqual(m.source_fingerprints[0]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertNotIn("source_fingerprints", m.to_dict())
            for descriptor in ({"path": "../outside.json"}, {"path": "https://example.com/x.json"},
                               {"path": "metadata.csv"}, {"path": "metadata.json", "extra": True}):
                with self.subTest(descriptor=descriptor), self.assertRaises(ComparisonValidationError):
                    load_sample_metadata(descriptor, base_dir=tmp)
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(ComparisonValidationError):
                load_sample_metadata({"path": "metadata.json"}, base_dir=tmp)

    def test_requests_defaults_roundtrip_and_strict_types(self):
        r = DiagnosticRequest.from_dict({"query_id": "01", "candidate_id": "1", "layer_id": "raw"})
        self.assertEqual((r.h, r.omission, r.group_field, r.include_fraction), (5, False, None, True))
        self.assertEqual(DiagnosticRequest.from_dict(r.to_dict()), r)
        with self.assertRaises(FrozenInstanceError):
            r.h = 1
        for name, values in {"h": [True, 0, -1, 1.5, "5"], "omission": [1, None, "false"],
                             "include_fraction": [0, None], "group_field": [1, ""],
                             "query_id": [1, ""], "candidate_id": [None], "layer_id": [False]}.items():
            for value in values:
                d = r.to_dict(); d[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ComparisonValidationError):
                    DiagnosticRequest.from_dict(d)
        d = r.to_dict(); d["extra"] = 1
        with self.assertRaises(ComparisonValidationError):
            DiagnosticRequest.from_dict(d)


class ScientificCase(unittest.TestCase):
    def assertSubset(self, expected, actual):
        if isinstance(expected, dict):
            for key, value in expected.items():
                self.assertIn(key, actual)
                self.assertSubset(value, actual[key])
        elif isinstance(expected, list):
            self.assertEqual(len(expected), len(actual))
            for a, b in zip(expected, actual):
                self.assertSubset(a, b)
        elif type(expected) in (int, float):
            self.assertAlmostEqual(expected, actual, places=12)
        else:
            self.assertEqual(expected, actual)

    def summarize(self, layer=None, metadata=None, **kwargs):
        layer = layer or layer_for()
        metadata = metadata or SampleMetadata.from_dict(metadata_doc(thaw(layer["dataset"])))
        return group_summary(layer, layer["dataset"], metadata, layer["dataset"]["query_namespace"],
                             "Q", kwargs.pop("field", "condition"), **kwargs)

    def diagnose(self, layer=None, **kwargs):
        layer = layer or layer_for()
        return covariance_diagnostic(layer, layer["dataset"], "Q", "C", **kwargs)

    def test_shared_hand_calculated_fixture(self):
        for case in DATA["cases"]:
            with self.subTest(case=case["name"]):
                result = self.diagnose(layer_for(case), h=case["h"], omission=case["omission"])
                expected = copy.deepcopy(case["expected"])
                self.assertSubset(expected.pop("products"), [p["product"] for p in result["products"]])
                self.assertSubset(expected.pop("absolute_shares"), [p["absolute_share"] for p in result["products"]])
                self.assertSubset(expected, result)
                json.dumps(result, allow_nan=False)
        self.assertSubset(DATA["group_case"]["expected"], self.summarize())

    def test_masks_joint_centering_missing_values_and_disjoint_group_exclusions(self):
        layer = raw_layer(); layer.update(raw_unimputed=False, mask_source="explicit_original")
        layer["features"][0].update(values=[0, 1, 999, 3, 9], observed=[True, True, False, True, True])
        layer["features"][1].update(values=[0, None, 2, 3, 9], observed=[True] * 5)
        layer = ProfileData([layer]).layers[0]
        r = self.diagnose(layer)
        self.assertEqual(r["joint_observation_ids"], ["s01", "s04", "s05"])
        self.assertEqual(r["excluded_observation_ids"], ["s02", "s03"])
        self.assertEqual(r["original"]["mean_x"], 4)
        self.assertEqual([p["product"] for p in r["products"]], [16, 1, 25])
        self.assertEqual(r["mask_source"], "explicit_original")
        doc = metadata_doc(); doc["records"][0]["values"].clear()
        # Missing group AND unavailable feature are counted only as missing_group.
        doc["records"][2]["values"]["condition"] = None
        doc["records"].pop()
        s = self.summarize(layer, SampleMetadata.from_dict(doc))
        self.assertEqual(s["included_observation_ids"], ["s02", "s04"])
        self.assertEqual(s["exclusions"]["missing_group"]["observation_ids"], ["s01", "s03", "s05"])
        self.assertEqual(s["exclusions"]["not_observed_finite"]["count"], 0)
        doc["records"][2]["values"]["condition"] = "B"
        s = self.summarize(layer, SampleMetadata.from_dict(doc))
        self.assertEqual(s["exclusions"]["not_observed_finite"]["observation_ids"], ["s03"])
        self.assertEqual(s["included_count"] + sum(e["count"] for e in s["exclusions"].values()), 5)

    def test_reordered_axes_and_explicit_extras(self):
        layer = raw_layer()
        layer["observation_ids"].reverse()
        for f in layer["features"]:
            f["values"].reverse()
        reordered = ProfileData([layer]).layers[0]
        self.assertEqual(self.diagnose(), self.diagnose(reordered))
        self.assertEqual(self.summarize(), self.summarize(reordered))
        layer["observation_ids"].append("extra")
        for f in layer["features"]:
            f["values"].append(1e100)
        with self.assertRaises(ComparisonValidationError):
            self.diagnose(ProfileData([layer]).layers[0])
        layer["subset_extra_observations"] = True
        r = self.diagnose(ProfileData([layer]).layers[0])
        self.assertEqual(r["excluded_profile_observation_ids"], ["extra"])
        self.assertEqual(r["joint_observed_count"], 5)
        self.assertEqual(r["original"], self.diagnose()["original"])

    def test_missing_feature_observation_unknown_mask_disable(self):
        for reason in ("missing_feature", "missing_required_observations", "original_mask_unavailable"):
            layer = raw_layer()
            if reason == "missing_feature":
                layer["features"].pop(0)
            elif reason == "missing_required_observations":
                layer["observation_ids"].pop()
                for f in layer["features"]:
                    f["values"].pop()
            else:
                layer.update(raw_unimputed=False, mask_source="unavailable")
            layer = ProfileData([layer]).layers[0]
            with self.subTest(reason=reason):
                for result in (self.diagnose(layer, omission=True), self.summarize(layer)):
                    self.assertEqual(result["status"], "unavailable")
                    self.assertEqual(result["reason"], reason)
                    json.dumps(result, allow_nan=False)

    def test_group_zero_variation_no_groups_continuous_and_optional_fraction(self):
        layer = raw_layer(); layer["features"][0]["values"] = [7] * 5
        s = self.summarize(ProfileData([layer]).layers[0])
        self.assertEqual(s["status"], "available")
        self.assertEqual(s["fraction_reason"], "zero_total_variation")
        self.assertIsNone(s["between_group_fraction"])
        s = self.summarize(include_fraction=False)
        self.assertEqual(s["fraction_status"], "not_requested")
        self.assertIsNone(s["total_ss"])
        self.assertEqual(self.summarize(field="age")["reason"], "categorical_field_required")
        self.assertEqual(self.summarize(field="absent")["reason"], "missing_group_field")
        m = SampleMetadata(layer["dataset"], {"condition": "categorical"}, [])
        s = self.summarize(metadata=m)
        self.assertEqual(s["reason"], "no_known_group_observed_finite_values")
        self.assertEqual(s["exclusions"]["missing_group"]["count"], 5)
        with self.assertRaises(ComparisonValidationError):
            self.summarize(include_fraction=1)

    def test_small_cohorts_h_bounds_and_omission_explicit(self):
        r = self.diagnose()
        self.assertEqual(r["effective_h"], 5)
        self.assertAlmostEqual(r["largest_h_share"], 1)
        self.assertEqual(r["remaining"]["reason"], "not_requested")
        self.assertEqual(r["omitted_observation_ids"], [])
        r = self.diagnose(h=99, omission=True)
        self.assertEqual(r["effective_h"], 5)
        self.assertEqual(r["remaining"]["count"], 0)
        self.assertEqual(r["remaining"]["reason"], "insufficient_observations")
        for count in (0, 1, 2):
            layer = raw_layer()
            for f in layer["features"]:
                f["values"] = f["values"][:count] + [None] * (5 - count)
            r = self.diagnose(ProfileData([layer]).layers[0], omission=True)
            self.assertEqual(r["joint_observed_count"], count)
            self.assertEqual(r["status"], "unavailable")
            self.assertEqual(r["effective_h"], 0)
            self.assertIsNone(r["largest_h_share"])
        for kwargs in ({"h": True}, {"h": 0}, {"omission": 1}):
            with self.assertRaises(ComparisonValidationError):
                self.diagnose(**kwargs)

    def test_numeric_range_is_unavailable_not_nan_or_infinity(self):
        for xs, ys in [([1e308, -1e308, 1e308, -1e308, 0], [1e308] * 4 + [-1e308]),
                       ([1e200, -1e200, 0, 1, 2], [1e200, -1e200, 0, 1, 2])]:
            layer = raw_layer()
            layer["features"][0]["values"] = xs
            layer["features"][1]["values"] = ys
            layer = ProfileData([layer]).layers[0]
            r = self.diagnose(layer, omission=True)
            self.assertEqual(r["reason"], "numeric_range")
            self.assertEqual(r["original"]["reason"], "numeric_range")
            self.assertEqual(r["remaining"]["reason"], "numeric_range")
            self.assertEqual(r["selected_observation_ids"], [])
            json.dumps(r, allow_nan=False)
            s = self.summarize(layer)
            self.assertEqual(s["status"], "available")
            self.assertEqual(s["fraction_reason"], "numeric_range")
            self.assertIsNone(s["between_group_fraction"])
            json.dumps(s, allow_nan=False)

    def test_large_finite_correlation_avoids_denominator_overflow(self):
        layer = raw_layer()
        for f in layer["features"]:
            f["values"] = [-1e150, -5e149, 0, 5e149, 1e150]
        r = self.diagnose(ProfileData([layer]).layers[0], h=1)
        self.assertEqual(r["status"], "available")
        self.assertAlmostEqual(r["original"]["correlation"], 1)
        json.dumps(r, allow_nan=False)

    def test_omission_retained_constant_has_covariance_but_no_correlation(self):
        layer = raw_layer()
        layer["features"][0]["values"] = [1, 1, 1, 1, 9]
        result = self.diagnose(ProfileData([layer]).layers[0], h=1, omission=True)
        self.assertEqual(result["selected_observation_ids"], ["s05"])
        self.assertEqual(result["remaining"]["count"], 4)
        self.assertEqual(result["remaining"]["mean_x"], 1)
        self.assertEqual(result["remaining"]["mean_y"], 1.5)
        self.assertEqual(result["remaining"]["covariance"], 0)
        self.assertEqual(result["remaining"]["covariance_status"], "available")
        self.assertIsNone(result["remaining"]["correlation"])
        self.assertEqual(result["remaining"]["correlation_reason"], "zero_variance")

    def test_absolute_sum_overflow_preserves_finite_original_stats(self):
        layer = raw_layer()
        for feature in layer["features"]:
            feature["values"] = [1e154, -1e154, 1e154, -1e154, 0]
        result = self.diagnose(ProfileData([layer]).layers[0], omission=True)
        self.assertEqual(result["reason"], "numeric_range")
        self.assertEqual(result["original"]["status"], "available")
        self.assertAlmostEqual(result["original"]["covariance"] / 1e308, 1)
        self.assertAlmostEqual(result["original"]["correlation"], 1)
        self.assertEqual(result["products"], [])
        json.dumps(result, allow_nan=False)

    def test_metadata_extra_and_null_transformed_observed_value(self):
        layer = raw_layer()
        layer.update(raw_unimputed=False, mask_source="explicit_original")
        for feature in layer["features"]:
            feature["observed"] = [True] * 5
        layer["features"][0]["values"][0] = None
        layer = ProfileData([layer]).layers[0]
        doc = metadata_doc()
        doc["records"].append({"observation_id": "extra", "values": {"condition": "X"}})
        with self.assertRaises(ComparisonValidationError):
            self.summarize(layer, SampleMetadata.from_dict(doc))
        doc["subset_extra_observations"] = True
        summary = self.summarize(layer, SampleMetadata.from_dict(doc))
        self.assertEqual(summary["excluded_metadata_observation_ids"], ["extra"])
        self.assertEqual(summary["known_group_count"], 5)
        self.assertEqual(summary["observed_finite_count"], 4)
        self.assertEqual(summary["included_count"], 4)
        self.assertEqual(summary["exclusions"]["not_observed_finite"]["observation_ids"], ["s01"])
        self.assertEqual(self.diagnose(layer)["excluded_observation_ids"], ["s01"])
        self.assertNotIn("X", [g["group"] for g in summary["groups"]])

    def test_wrong_dataset_rejected_and_sources_never_mutated(self):
        layer = layer_for(); ds = thaw(layer["dataset"]); ds["dataset_id"] = "wrong"
        with self.assertRaises(ComparisonValidationError):
            covariance_diagnostic(layer, ds, "Q", "C")
        metadata = SampleMetadata.from_dict(metadata_doc())
        before = thaw(layer), metadata.to_dict()
        result = self.diagnose(layer, h=1, omission=True)
        summary = self.summarize(layer, metadata)
        result["products"].clear(); result["required_observation_ids"].clear()
        summary["groups"].clear(); summary["namespace"].clear()
        self.assertEqual((thaw(layer), metadata.to_dict()), before)
        bad_metadata = replace(metadata, dataset=ds)
        with self.assertRaises(ComparisonValidationError):
            self.summarize(layer, bad_metadata)


if __name__ == "__main__":
    unittest.main()
