"""Offline saved-output comparison. Standard library only; no training/scoring."""
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
from .engine import ComparisonResult, compare_results
from .report import write_comparison, load_comparison_bundle
from .browser import ReportSettings
from .profiles import ProfileData, load_profile_data

__all__ = [
    "SCHEMA_VERSION", "TIE_POLICY", "ComparisonInput", "ComparisonManifest",
    "ComparisonSettings", "ComparisonValidationError", "CompatibilityReport",
    "Exclusion", "Issue", "PairStatus", "PairValue", "PoolPolicy", "PoolResult",
    "QueryPool", "RankingPolicy", "RankView", "load_comparison_input",
    "load_manifest", "from_association_result", "validate_compatibility",
    "build_pools", "rank_output", "top_list", "export_comparison_inputs",
    "load_input_bundle", "ComparisonResult", "compare_results",
    "write_comparison", "load_comparison_bundle", "ReportSettings", "ProfileData", "load_profile_data",
]
