"""Release A overview-first saved-output comparison; no target feature or training.

From a source checkout:
    PYTHONPATH=src python3 examples/compare_saved_results.py
Optionally supply a NEW output directory to retain the offline HTML and tables.
Without a destination, a temporary bundle is written/reloaded and cleaned up.
The source-checkout fixture is not claimed as an installed B3 package asset.
"""
import argparse
from pathlib import Path
import tempfile

from valpas.comparison import (
    ComparisonSettings, compare_results, load_comparison_bundle, load_manifest,
    write_comparison,
)


def demonstrate(destination, policy):
    fixture = Path(__file__).resolve().parents[1] / "tests/comparison/fixtures/demo-01/manifest.json"
    manifest = load_manifest(fixture)
    result = compare_results(manifest, ComparisonSettings(pool_policy=policy, depths=(1, 2, 5)))
    print("Synthetic saved scores only; no fitting, models, or observed profiles.")
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
    path = write_comparison(result, destination)
    restored = load_comparison_bundle(path)
    assert restored.comparison_id == result.comparison_id
    for name in result.table_names:
        assert list(restored.iter_table(name)) == list(result.iter_table(name)), name
    print("All ten scientific tables reproduce from normalized saved values:", path)
    print("CSV data cells are JSON encoded; large detail tables are gzip compressed.")
    print("Open directly from disk:", path / "report.html")
    print("This example has no profiles. B1/B2 diagnostics, references, sessions and figures remain unfinished.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", nargs="?", type=Path)
    parser.add_argument("--pool", choices=("strict", "common", "native_inspection"), default="common")
    args = parser.parse_args()
    if args.outdir is not None:
        demonstrate(args.outdir, args.pool)
    else:
        with tempfile.TemporaryDirectory(prefix="valpas-a2-example-") as directory:
            demonstrate(Path(directory) / "comparison", args.pool)
        print("Temporary example bundle removed; supply outdir to retain it.")


if __name__ == "__main__":
    main()
