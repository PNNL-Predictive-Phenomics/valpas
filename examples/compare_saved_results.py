"""Overview-first saved-output comparison with optional B1 descriptions, no training.

From a source checkout:
    PYTHONPATH=src python3 examples/compare_saved_results.py
Optionally supply a NEW output directory to retain the offline HTML and tables.
Without a destination, a temporary bundle is written/reloaded and cleaned up.
The example and fixtures ship in the source distribution, not as wheel data.
The separate B1 manifest requests one diagnostic pair; it does not limit the
all-query comparison. Browser diagnostics are on demand, independent of exports.
"""
import argparse
from pathlib import Path
import tempfile
from math import isclose

from valpas.comparison import (
    ComparisonSettings, compare_results, load_comparison_bundle, load_manifest,
    write_comparison,
)


def demonstrate(destination, policy):
    fixture = Path(__file__).resolve().parents[1] / "tests/comparison/fixtures/demo-01/manifest-with-b1.json"
    manifest = load_manifest(fixture)
    result = compare_results(manifest, ComparisonSettings(pool_policy=policy, depths=(1, 2, 5)))
    print("Synthetic saved scores plus separate illustrative profiles and metadata.")
    print("Profiles did not generate the saved scores; no fitting or model attribution.")
    print("All declared queries under policy; no target metabolite/protein required.")
    print("Comparison:", result.comparison_id)
    print("Dataset overview:", result.materialize_table("dataset_summary")[0])
    print("Query overview:")
    for row in result.iter_table("query_summary"):
        print(" ", row)
    print("Agreement distributions (each output pair stays separate):")
    for row in result.iter_table("agreement_summary"):
        print(" ", row)
    print("Run recurrence is separate; seeds are not biological replicates.")
    print("Agreement is not correctness or a best-method recommendation.")
    for issue in result.warnings:
        print("Warning:", issue.output_id, issue.reason)
    # Optional requested exports do not select the comparison's query universe.
    diagnostic = result.materialize_table("diagnostics")[0]["result"]
    assert diagnostic["joint_observed_count"] == 6
    assert [row["product"] for row in diagnostic["products"]] == [16, 9, 4, 1, 0, 100]
    assert diagnostic["selected_observation_ids"] == ["S06"]
    assert isclose(diagnostic["largest_h_share"], 10 / 13)
    assert diagnostic["original"]["mean_x"] == 4
    assert diagnostic["original"]["covariance"] == 26
    assert diagnostic["remaining"]["mean_x"] == 2
    assert diagnostic["remaining"]["covariance"] == 2.5
    assert isclose(diagnostic["remaining"]["correlation"], 1)
    print("Requested M01/P01 diagnostic only:", diagnostic)
    groups = result.materialize_table("group_summaries")
    assert len(groups) == 2
    for row in groups:
        summary = row["result"]
        assert summary["included_count"] == 4
        assert summary["exclusions"]["missing_group"]["observation_ids"] == ["S05", "S06"]
        assert summary["total_ss"] == 5
        assert summary["between_group_ss"] == 4
        assert summary["between_group_fraction"] == 0.8
        print("Marginal condition summary:", row)
    metadata_rows = result.materialize_table("sample_metadata")
    assert len(metadata_rows) == 24
    assert sum(row["status"] == "missing" for row in metadata_rows) == 7
    # Clearing requests keeps metadata/profiles and all ten scientific tables.
    unrequested = compare_results(manifest, result.settings, diagnostic_requests=[])
    assert unrequested.comparison_id == result.comparison_id
    assert "diagnostics" not in unrequested.table_names
    assert "group_summaries" not in unrequested.table_names
    baseline = compare_results(load_manifest(fixture.with_name("manifest.json")), result.settings)
    assert baseline.comparison_id == result.comparison_id
    for name in baseline.table_names:
        assert list(baseline.iter_table(name)) == list(result.iter_table(name)), name
    path = write_comparison(result, destination)
    restored = load_comparison_bundle(path)
    assert restored.comparison_id == result.comparison_id
    for name in result.table_names:
        assert list(restored.iter_table(name)) == list(result.iter_table(name)), name
    print("All ten scientific tables, two profile tables and three B1 tables reproduce:", path)
    print("CSV data cells are JSON encoded; large detail tables are gzip compressed.")
    print("Open directly from disk:", path / "report.html")
    print("Browser: select M01/P01, set largest h to 1, explicitly preview omission, group by condition.")
    print("Color/order are display-only. No causality, retraining, scoring or rank changes.")
    print("B2/B3 references, sessions, figures and final integration remain unfinished.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", nargs="?", type=Path)
    parser.add_argument("--pool", choices=("strict", "common", "native_inspection"), default="common")
    args = parser.parse_args()
    if args.outdir is not None:
        demonstrate(args.outdir, args.pool)
    else:
        with tempfile.TemporaryDirectory(prefix="valpas-b1-example-") as directory:
            demonstrate(Path(directory) / "comparison", args.pool)
        print("Temporary example bundle removed; supply outdir to retain it.")


if __name__ == "__main__":
    main()
