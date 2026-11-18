"""A1 saved-input demo: no fitting, metrics, report or new CLI command.

From the repository: PYTHONPATH=src python3 examples/inspect_comparison_inputs.py
Optionally pass a new destination directory to export/reload an input bundle.
The fixture path is source-checkout-relative; packaged example assets are B3.
"""
from pathlib import Path
import sys

from valpas.comparison import (
    ComparisonSettings, build_pools, export_comparison_inputs,
    load_input_bundle, load_manifest,
)


def main():
    fixture = Path(__file__).resolve().parents[1] / "tests/comparison/fixtures/demo-01/manifest.json"
    manifest = load_manifest(fixture)
    print("Synthetic fixture: two methods, two configurations, three outputs; no training.")
    print("Identity:", manifest.compatibility.identity_status)
    for policy in ("strict", "common"):
        pools = build_pools(manifest.outputs, ComparisonSettings(pool_policy=policy))
        for query, pool in pools.queries.items():
            print(policy, query, "available" if pool.controlled_available else pool.reason)
            for output_id, order in pool.active_orders.items():
                print(" ", output_id, ", ".join(order))
    if len(sys.argv) > 2:
        raise SystemExit("Pass at most one new input-bundle destination directory.")
    if len(sys.argv) == 2:
        destination = export_comparison_inputs(manifest.outputs, sys.argv[1],
                                               dataset=manifest.dataset, settings=manifest.settings)
        reloaded = load_input_bundle(destination)
        assert [o.pairs for o in reloaded.outputs] == [o.pairs for o in manifest.outputs]
        print("Full-precision input bundle reloaded:", destination)
    print("A1 only: agreement metrics, recurrence, report and comparison CLI remain later phases.")


if __name__ == "__main__":
    main()
