"""Version-one contracts for saved outputs. No analysis dependencies."""
from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType
from collections.abc import Mapping

SCHEMA_VERSION = 1
TIE_POLICY = "canonical_candidate_id_unicode_ascending"


@dataclass(frozen=True)
class Issue:
    field: str
    reason: str
    remediation: str
    output_id: str | None = None
    examples: tuple = ()
    count: int = 1


class ComparisonValidationError(ValueError):
    """Machine-readable issue, also usable as an actionable ValueError."""
    def __init__(self, field, reason, remediation="Correct the descriptor or re-export complete saved data.",
                 output_id=None, examples=(), count=1):
        self.issue = Issue(field, reason, remediation, output_id, tuple(examples), count)
        super().__init__(f"{output_id or 'manifest'}: {field}: {reason}. {remediation}")


def fail(field, reason, output_id=None, remediation="Correct the descriptor or re-export complete saved data."):
    raise ComparisonValidationError(field, reason, remediation, output_id)


class RankingPolicy(str, Enum):
    NATIVE_DESCENDING = "native_descending"
    NATIVE_ASCENDING = "native_ascending"
    ABSOLUTE_DESCENDING = "absolute_descending"
    ABSOLUTE_ASCENDING = "absolute_ascending"


class PoolPolicy(str, Enum):
    STRICT = "strict"
    COMMON = "common"
    NATIVE_INSPECTION = "native_inspection"


class PairStatus(str, Enum):
    SCORABLE = "scorable"
    UNSCORED = "unscored"
    INELIGIBLE = "ineligible"
    MISSING_QUERY = "missing_query"
    UNREPORTED = "unreported"
    TRUNCATED = "truncated"


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(v) for v in value]
    return value


def keys(value, required, optional=(), field="", output_id=None):
    if not isinstance(value, Mapping):
        fail(field, "expected an object", output_id)
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        fail(field, f"missing keys {sorted(missing, key=repr)}; unknown keys {sorted(unknown, key=repr)}", output_id)


def text(value, field, output_id=None):
    if not isinstance(value, str) or not value:
        fail(field, "expected a nonempty exact string (no ID coercion)", output_id)
    return value


def ids(value, field, output_id=None, allow_empty=False):
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        fail(field, "expected an explicit ID list", output_id)
    for item in value:
        text(item, field, output_id)
    if len(set(value)) != len(value):
        fail(field, "duplicate canonical IDs", output_id)
    return tuple(value)


def integer(value, field, output_id=None, minimum=0):
    if type(value) is not int or value < minimum:
        fail(field, f"expected integer >= {minimum}", output_id)
    return value


def json_value(value, field, output_id=None):
    """Open scientific metadata maps are JSON data, never executable settings."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            text(k, field, output_id)
            json_value(v, f"{field}.{k}", output_id)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            json_value(v, field, output_id)
        return
    fail(field, "expected finite JSON metadata", output_id)


def namespace(value, field, output_id=None):
    keys(value, ("id", "modality"), field=field, output_id=output_id)
    for k, v in value.items():
        text(v, f"{field}.{k}", output_id)


def validate_identity(value, field="dataset", output_id=None):
    keys(value, ("dataset_id", "dataset_evidence", "observation_ids", "query_namespace",
                 "candidate_namespace", "context"), field=field, output_id=output_id)
    text(value["dataset_id"], field + ".dataset_id", output_id)
    for k in ("query_namespace", "candidate_namespace"):
        namespace(value[k], field + "." + k, output_id)
    if value["context"] is not None:
        text(value["context"], field + ".context", output_id)
    if value["observation_ids"] is not None:
        ids(value["observation_ids"], field + ".observation_ids", output_id)
    evidence = value["dataset_evidence"]
    if evidence is not None:
        keys(evidence, ("type", "source", "value", "limitations"),
             field=field + ".dataset_evidence", output_id=output_id)
        if evidence["type"] not in ("fingerprint", "attestation"):
            fail(field + ".dataset_evidence.type", "expected fingerprint or attestation", output_id)
        for k in ("source", "value", "limitations"):
            text(evidence[k], field + ".dataset_evidence." + k, output_id)


CONFIG_FIELDS = ("parameters", "preprocessing", "score_semantics", "supervision",
                 "training_features", "observation_selection")


def validate_descriptor(d):
    oid = d.get("output_id") if isinstance(d, Mapping) else None
    keys(d, ("schema_version", "output_id", "label", "method_id", "configuration_id", "run_id",
             "seed", "identity", "configuration", "provenance", "query_ids", "candidate_ids",
             "orientation", "representation", "ranking_policy", "tie_policy", "completeness",
             "missing_policy", "data"), ("eligibility", "missing_queries", "count_semantics"),
         "output", oid)
    if type(d["schema_version"]) is not int or d["schema_version"] != SCHEMA_VERSION:
        fail("schema_version", "unsupported version", oid)
    for k in ("output_id", "label", "method_id", "configuration_id", "run_id", "tie_policy"):
        text(d[k], k, oid)
    if d["seed"] is not None:
        integer(d["seed"], "seed", oid)
    validate_identity(d["identity"], "identity", oid)
    config = d["configuration"]
    keys(config, CONFIG_FIELDS, field="configuration", output_id=oid)
    for k in ("parameters", "preprocessing"):
        if config[k] is not None:
            if not isinstance(config[k], Mapping):
                fail("configuration." + k, "expected metadata object or explicit null", oid)
            json_value(config[k], "configuration." + k, oid)
    def no_seed(v):
        if isinstance(v, Mapping):
            for k, child in v.items():
                if k.lower() in ("seed", "random_seed", "random_state"):
                    fail("configuration.parameters", "seed belongs on the run, not in non-seed configuration", oid)
                no_seed(child)
        elif isinstance(v, (list, tuple)):
            for child in v:
                no_seed(child)
    no_seed(config)
    for k in ("score_semantics", "supervision", "observation_selection"):
        if config[k] is not None:
            text(config[k], "configuration." + k, oid)
    if config["training_features"] is not None:
        keys(config["training_features"], ("namespace", "ids"), field="configuration.training_features", output_id=oid)
        namespace(config["training_features"]["namespace"], "configuration.training_features.namespace", oid)
        ids(config["training_features"]["ids"], "configuration.training_features.ids", oid)
    keys(d["provenance"], ("software", "source", "limitations"), field="provenance", output_id=oid)
    for k, v in d["provenance"].items():
        if v is not None:
            text(v, "provenance." + k, oid)
    qs, cs = ids(d["query_ids"], "query_ids", oid), ids(d["candidate_ids"], "candidate_ids", oid)
    if d["orientation"] not in ("query_rows_candidate_columns", "candidate_rows_query_columns"):
        fail("orientation", "explicit axis semantics required", oid)
    if d["ranking_policy"] not in tuple(p.value for p in RankingPolicy):
        fail("ranking_policy", "unknown ranking policy", oid)
    reps = ("score_matrix", "long_scores", "rank_permutation", "ordered_ranks", "certified_prefix", "filtered_list", "legacy_score_count")
    if d["representation"] not in reps:
        fail("representation", "unsupported representation", oid)
    if d["representation"] not in ("score_matrix", "legacy_score_count") and d["orientation"] != "query_rows_candidate_columns":
        fail("orientation", "tables/permutations use canonical query orientation", oid)
    if d["representation"] in ("score_matrix", "long_scores", "legacy_score_count") and d["tie_policy"] != TIE_POLICY:
        fail("tie_policy", "scored inputs require canonical Unicode ID ties", oid)
    keys(d["missing_policy"], ("blank", "nan", "absent"), field="missing_policy", output_id=oid)
    for k, allowed in {"blank": ("reject", "unscored"), "nan": ("reject", "unscored"),
                       "absent": ("reject", "unscored", "unreported", "truncated")}.items():
        if d["missing_policy"][k] not in allowed:
            fail("missing_policy." + k, "unsupported missing policy", oid)
    comp = d["completeness"]
    rep = d["representation"]
    if rep == "certified_prefix":
        keys(comp, ("kind", "queries"), field="completeness", output_id=oid)
        if comp["kind"] != "prefix":
            fail("completeness.kind", "prefix required", oid)
        keys(comp["queries"], qs, field="completeness.queries", output_id=oid)
        for q, cert in comp["queries"].items():
            keys(cert, ("depth", "pool_id", "pool_size", "exhausted", "complete_prefix", "self_excluded"), field="completeness.queries." + q, output_id=oid)
            integer(cert["depth"], "completeness.depth", oid)
            integer(cert["pool_size"], "completeness.pool_size", oid)
            text(cert["pool_id"], "completeness.pool_id", oid)
            if cert["complete_prefix"] is not True or type(cert["exhausted"]) is not bool or type(cert["self_excluded"]) is not bool:
                fail("completeness", "explicit prefix, exhaustion and self-edge certificates required", oid)
            if cert["depth"] > cert["pool_size"] or cert["exhausted"] != (cert["depth"] == cert["pool_size"]):
                fail("completeness", "depth/exhaustion contradict pool size", oid)
        if d["missing_policy"]["absent"] != "truncated":
            fail("missing_policy.absent", "prefix omissions must be truncated", oid)
    elif rep == "filtered_list":
        keys(comp, ("kind", "filter"), field="completeness", output_id=oid)
        if comp["kind"] != "inspection_only":
            fail("completeness.kind", "filtered lists are inspection_only", oid)
        text(comp["filter"], "completeness.filter", oid)
        if d["missing_policy"]["absent"] != "unreported":
            fail("missing_policy.absent", "filtered omissions must be unreported", oid)
    else:
        keys(comp, ("kind",), field="completeness", output_id=oid)
        if comp["kind"] != "complete" or d["missing_policy"]["absent"] not in ("reject", "unscored"):
            fail("completeness", "complete representation requires known omissions", oid)
    missing = ids(d.get("missing_queries", ()), "missing_queries", oid, allow_empty=True)
    if not set(missing) <= set(qs):
        fail("missing_queries", "unknown query ID", oid)
    eligibility = d.get("eligibility", ())
    if not isinstance(eligibility, (list, tuple)):
        fail("eligibility", "expected a list of pair overrides", oid)
    seen = set()
    for row in eligibility:
        keys(row, ("query_id", "candidate_id", "eligible", "reason"), field="eligibility", output_id=oid)
        text(row["query_id"], "eligibility.query_id", oid)
        text(row["candidate_id"], "eligibility.candidate_id", oid)
        pair = (row["query_id"], row["candidate_id"])
        if pair[0] not in qs or pair[1] not in cs or pair in seen:
            fail("eligibility", "unknown or duplicate pair", oid)
        seen.add(pair)
        if type(row["eligible"]) is not bool:
            fail("eligibility.eligible", "expected boolean", oid)
        text(row["reason"], "eligibility.reason", oid)
    if "count_semantics" in d:
        text(d["count_semantics"], "count_semantics", oid)
    # Data shape is checked before reading by the adapter (including nested keys).
    return d


@dataclass(frozen=True)
class ComparisonSettings:
    pool_policy: str = "strict"
    exclude_self: bool = True
    depths: tuple = (5, 10, 20)
    attestations: tuple = ()

    def __post_init__(self):
        if self.pool_policy not in tuple(p.value for p in PoolPolicy):
            fail("settings.pool_policy", "unknown pool policy")
        if type(self.exclude_self) is not bool:
            fail("settings.exclude_self", "expected boolean")
        if not isinstance(self.depths, (list, tuple)) or not self.depths:
            fail("settings.depths", "expected nonempty integer list")
        for k in self.depths:
            integer(k, "settings.depths", minimum=1)
        if len(set(self.depths)) != len(self.depths):
            fail("settings.depths", "duplicate depths")
        if not isinstance(self.attestations, (list, tuple)):
            fail("settings.attestations", "expected list")
        seen = set()
        for a in self.attestations:
            keys(a, ("output_id", "field", "claimed_value", "statement"), field="settings.attestations")
            for k in ("output_id", "field", "statement"):
                text(a[k], "settings.attestations." + k)
            if a["field"] not in ("dataset_evidence", "observation_ids", "context", "configuration"):
                fail("settings.attestations.field", "not an attestable field")
            key = (a["output_id"], a["field"])
            if key in seen:
                fail("settings.attestations", "duplicate attestation")
            seen.add(key)
            if a["claimed_value"] is None:
                fail("settings.attestations.claimed_value", "a specific claim is required")
            json_value(a["claimed_value"], "settings.attestations.claimed_value")
        object.__setattr__(self, "depths", tuple(self.depths))
        object.__setattr__(self, "attestations", freeze(self.attestations))

    @classmethod
    def from_dict(cls, value):
        keys(value, (), ("pool_policy", "exclude_self", "depths", "attestations"), "settings")
        return cls(**value)

    def to_dict(self):
        return {"pool_policy": self.pool_policy, "exclude_self": self.exclude_self,
                "depths": list(self.depths), "attestations": thaw(self.attestations)}


@dataclass(frozen=True)
class PairValue:
    status: str
    score: float | None = None
    rank: int | None = None
    count: float | None = None
    reason: str | None = None

    def __post_init__(self):
        if self.status not in tuple(s.value for s in PairStatus):
            fail("pair.status", "unknown status")
        for name in ("score", "count"):
            v = getattr(self, name)
            if v is not None and (type(v) not in (float, int) or not math.isfinite(v)):
                fail("pair." + name, "expected finite number or null")
        if self.count is not None and self.count < 0:
            fail("pair.count", "negative count")
        if self.rank is not None:
            integer(self.rank, "pair.rank", minimum=1)
        if self.status != "scorable" and self.rank is not None:
            fail("pair.rank", "non-scorable pairs cannot have ranks")
        if self.status in ("unscored", "missing_query", "unreported", "truncated") and self.score is not None:
            fail("pair.score", "status contradicts finite score")
        if self.status == "scorable" and self.score is None and self.rank is None:
            fail("pair", "scorable pair needs a score or rank")
        if self.reason is not None:
            text(self.reason, "pair.reason")


@dataclass(frozen=True)
class ComparisonInput:
    """Detached normalized output; sparse omissions have explicit status semantics."""
    descriptor: Mapping
    pairs: Mapping
    warnings: tuple = ()
    source_files: tuple = ()

    source_fingerprints: tuple = ()

    def __post_init__(self):
        validate_descriptor(self.descriptor)
        object.__setattr__(self, "descriptor", freeze(self.descriptor))
        object.__setattr__(self, "pairs", freeze(self.pairs))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "source_files", tuple(self.source_files))
        object.__setattr__(self, "source_fingerprints", freeze(self.source_fingerprints))
        # One validator for direct construction, file and structural adapters.
        from .adapters import _validate_pairs
        _validate_pairs(self)

    @property
    def output_id(self):
        return self.descriptor["output_id"]

    @property
    def query_ids(self):
        return self.descriptor["query_ids"]

    @property
    def candidate_ids(self):
        return self.descriptor["candidate_ids"]

    @property
    def complete(self):
        return self.descriptor["completeness"]["kind"] == "complete"

    def pair(self, query_id, candidate_id):
        if query_id not in self.query_ids:
            return PairValue("missing_query", reason="query_not_in_output")
        if candidate_id not in self.candidate_ids:
            return PairValue("ineligible", reason="candidate_not_in_output")
        if query_id in self.descriptor.get("missing_queries", ()):
            return PairValue("missing_query", reason="declared_missing_query")
        for row in self.descriptor.get("eligibility", ()):
            if row["query_id"] == query_id and row["candidate_id"] == candidate_id and not row["eligible"]:
                saved = self.pairs.get((query_id, candidate_id))
                return PairValue("ineligible", score=saved.score if saved else None,
                                 count=saved.count if saved else None, reason=row["reason"])
        saved = self.pairs.get((query_id, candidate_id))
        if saved is not None:
            return saved
        status = self.descriptor["missing_policy"]["absent"]
        if status == "reject":
            fail("data", "missing required pair", self.output_id)
        return PairValue(status, reason="declared_absent_" + status)


@dataclass(frozen=True)
class ComparisonManifest:
    dataset: Mapping
    outputs: tuple
    settings: ComparisonSettings
    compatibility: object
    source_fingerprints: tuple = ()


@dataclass(frozen=True)
class CompatibilityReport:
    configuration_differences: tuple
    run_groups: Mapping
    warnings: tuple
    identity_status: str


@dataclass(frozen=True)
class RankView:
    output_id: str
    query_id: str
    order: tuple
    ranks: Mapping
    statuses: Mapping
    certified: bool
    exhausted: bool


@dataclass(frozen=True)
class Exclusion:
    output_id: str
    query_id: str
    candidate_id: str | None
    status: str
    reason: str


@dataclass(frozen=True)
class QueryPool:
    query_id: str
    native: Mapping
    active_orders: Mapping
    active_ranks: Mapping
    candidates: Mapping
    controlled_available: bool
    reason: str | None
    coverage: Mapping


@dataclass(frozen=True)
class PoolResult:
    policy: str
    queries: Mapping
    exclusions: tuple
    compatibility: CompatibilityReport
