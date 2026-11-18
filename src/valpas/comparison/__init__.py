"""A1 saved-output contracts, adapters, compatibility and ranks.

Standard library only. No fitting/scoring, checkpoints, metric engine, report
or CLI orchestration. Existing root lazy exports remain unchanged.
"""
from .models import (
    SCHEMA_VERSION, TIE_POLICY, ComparisonInput, ComparisonManifest,
    ComparisonSettings, ComparisonValidationError, CompatibilityReport,
    Exclusion, Issue, PairStatus, PairValue, PoolPolicy, PoolResult, QueryPool,
    RankingPolicy, RankView,
)
from .adapters import load_comparison_input, load_manifest, from_association_result
from .compatibility import validate_compatibility, build_pools
from .ranking import rank_output, top_list
from .bundles import export_comparison_inputs, load_input_bundle

__all__ = [
    "SCHEMA_VERSION", "TIE_POLICY", "ComparisonInput", "ComparisonManifest",
    "ComparisonSettings", "ComparisonValidationError", "CompatibilityReport",
    "Exclusion", "Issue", "PairStatus", "PairValue", "PoolPolicy", "PoolResult",
    "QueryPool", "RankingPolicy", "RankView", "load_comparison_input",
    "load_manifest", "from_association_result", "validate_compatibility",
    "build_pools", "rank_output", "top_list", "export_comparison_inputs",
    "load_input_bundle",
]
