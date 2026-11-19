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
from .figures import export_query_figure
from .profiles import ProfileData, load_profile_data
from .diagnostics import (SampleMetadata, DiagnosticRequest, load_sample_metadata,
                          group_summary, covariance_diagnostic)

from .reference import (ReferenceData, QueryGroups, load_reference_data, load_query_groups,
                        reference_provenance_hash)

from .session import Session, Shortlist, load_session, load_shortlist, session_content_id

__all__ = [
    "export_query_figure",
    "Session", "Shortlist", "load_session", "load_shortlist", "session_content_id",
    "SCHEMA_VERSION", "TIE_POLICY", "ComparisonInput", "ComparisonManifest",
    "ComparisonSettings", "ComparisonValidationError", "CompatibilityReport",
    "Exclusion", "Issue", "PairStatus", "PairValue", "PoolPolicy", "PoolResult",
    "QueryPool", "RankingPolicy", "RankView", "load_comparison_input",
    "load_manifest", "from_association_result", "validate_compatibility",
    "build_pools", "rank_output", "top_list", "export_comparison_inputs",
    "load_input_bundle", "ComparisonResult", "compare_results",
    "write_comparison", "load_comparison_bundle", "ReportSettings", "ProfileData", "load_profile_data",
    "SampleMetadata", "DiagnosticRequest", "load_sample_metadata", "group_summary", "covariance_diagnostic",
    "ReferenceData", "QueryGroups", "load_reference_data", "load_query_groups", "reference_provenance_hash",
]
