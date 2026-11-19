"""Safe local saved-data readers and detached structural adaptation."""
import csv
import io
import json
import hashlib
import math
from collections.abc import Mapping
from pathlib import Path

from .models import (ComparisonInput, ComparisonManifest, ComparisonSettings,
                     ComparisonValidationError, Issue, PairValue, TIE_POLICY,
                     fail, ids, integer, keys, text, thaw, validate_descriptor,
                     validate_identity)


def _json(text_data, field, oid=None):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                fail(field, "duplicate JSON key: " + k, oid)
            result[k] = v
        return result
    def constant(value):
        fail(field, "nonstandard JSON constant: " + value, oid)
    try:
        return json.loads(text_data, object_pairs_hook=unique, parse_constant=constant)
    except (ValueError, TypeError) as exc:
        if isinstance(exc, ComparisonValidationError):
            raise
        fail(field, "invalid JSON: " + str(exc), oid)


def _local_path(value, base, field, oid=None):
    text(value, field, oid)
    if ":" in value or "\\" in value or "\x00" in value:
        fail(field, "only local relative paths are accepted", oid)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        fail(field, "absolute paths and parent traversal are prohibited", oid)
    root = Path(base).resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        fail(field, "symlink escapes manifest directory", oid)
    if not resolved.is_file():
        fail(field, "input is not a regular local file", oid)
    return resolved


def _read(path, oid=None):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail("data.path", "cannot read UTF-8 file: " + str(exc), oid)


def _number(value, policy, field, oid, *, count=False):
    if value is None or value == "":
        if count or policy["blank"] == "unscored":
            return None
        fail(field, "blank value forbidden by declared policy", oid)
    if type(value) is bool or not isinstance(value, (int, float, str)):
        fail(field, "expected numeric value", oid)
    try:
        number = float(value)
    except (ValueError, OverflowError):
        fail(field, "invalid number", oid)
    if math.isnan(number):
        if policy["nan"] == "unscored":
            return None
        fail(field, "NaN forbidden by declared policy", oid)
    if not math.isfinite(number):
        fail(field, "infinity is invalid", oid)
    if count and number < 0:
        fail(field, "negative count", oid)
    return number


def _rank(value, oid):
    if isinstance(value, str):
        if not value.isascii() or not value.isdecimal():
            fail("data.rank", "expected a one-based integer rank", oid)
        value = int(value)
    return integer(value, "data.rank", oid, minimum=1)


def _data_contract(d):
    data, oid = d["data"], d["output_id"]
    keys(data, ("format",), ("path", "inline", "index_base", "symmetric"), "data", oid)
    if ("path" in data) == ("inline" in data):
        fail("data", "supply exactly one of path and inline", oid)
    if data["format"] not in ("json", "csv", "tsv", "normalized"):
        fail("data.format", "only JSON/CSV/TSV or normalized JSON is supported; no pickle/checkpoints/NumPy", oid)
    if "inline" in data and data["format"] not in ("json", "normalized"):
        fail("data.format", "inline data must be JSON objects", oid)
    if "index_base" in data:
        if d["representation"] != "rank_permutation" or type(data["index_base"]) is not int or data["index_base"] not in (0, 1):
            fail("data.index_base", "only permutations accept explicit base 0 or 1", oid)
    elif d["representation"] == "rank_permutation":
        fail("data.index_base", "permutations require explicit index base", oid)
    if "symmetric" in data:
        if type(data["symmetric"]) is not bool or d["representation"] not in ("legacy_score_count", "long_scores"):
            fail("data.symmetric", "symmetry only applies to legacy matrices or long scores", oid)
        if data["symmetric"]:
            ident = d["identity"]
            if ident["query_namespace"] != ident["candidate_namespace"] or set(d["query_ids"]) != set(d["candidate_ids"]):
                fail("data.symmetric", "symmetric expansion needs identical entity namespaces and axis sets", oid)


def _read_fingerprinted(path, role, oid=None):
    """Hash precisely the bytes parsed, not a later reopening of the source."""
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        fail("data.path", "cannot read UTF-8 file: " + str(exc), oid)
    return content, {"path": str(path.resolve()), "role": role,
                     "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _payload(d, base):
    data, oid = d["data"], d["output_id"]
    _data_contract(d)
    if "inline" in data:
        return data["inline"], (), ()
    path = _local_path(data["path"], base, "data.path", oid)
    fmt = data["format"]
    suffix = ".json" if fmt in ("json", "normalized") else "." + fmt
    if path.suffix.lower() != suffix:
        fail("data.path", "file extension must match declared safe format", oid)
    content, fingerprint = _read_fingerprinted(path, "output_data", oid)
    if fmt in ("json", "normalized"):
        return _json(content, "data", oid), (str(path),), (fingerprint,)
    try:
        rows = list(csv.reader(io.StringIO(content, newline=""), delimiter="," if fmt == "csv" else "\t", strict=True))
    except csv.Error as exc:
        fail("data", "invalid delimited file: " + str(exc), oid)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        fail("data", "empty or ragged delimited data", oid)
    if len(set(rows[0])) != len(rows[0]):
        fail("data", "duplicate header IDs/columns", oid)
    if d["representation"] in ("score_matrix", "legacy_score_count"):
        return {"row_ids": [r[0] for r in rows[1:]], "column_ids": rows[0][1:],
                "values": [r[1:] for r in rows[1:]]}, (str(path),), (fingerprint,)
    if d["representation"] == "rank_permutation":
        fail("data.format", "permutations require JSON integer arrays", oid)
    return {"records": [dict(zip(rows[0], r)) for r in rows[1:]]}, (str(path),), (fingerprint,)


def _insert(pairs, pair, value, oid):
    if pair in pairs:
        fail("data", "duplicate pair (even equal duplicates are rejected): " + repr(pair), oid)
    pairs[pair] = value


def _matrix(d, payload):
    oid, policy = d["output_id"], d["missing_policy"]
    keys(payload, ("row_ids", "column_ids", "values"), ("counts",), "data.matrix", oid)
    rows = ids(payload["row_ids"], "data.row_ids", oid)
    cols = ids(payload["column_ids"], "data.column_ids", oid)
    transposed = d["orientation"] == "candidate_rows_query_columns"
    expected_rows = d["candidate_ids"] if transposed else d["query_ids"]
    expected_cols = d["query_ids"] if transposed else d["candidate_ids"]
    if set(rows) != set(expected_rows) or set(cols) != set(expected_cols):
        fail("data.axes", "labeled matrix axes must match declared IDs; no shape inference", oid)
    for name in ("values", "counts"):
        if name in payload:
            array = payload[name]
            if not isinstance(array, (list, tuple)) or len(array) != len(rows) or any(not isinstance(r, (list, tuple)) or len(r) != len(cols) for r in array):
                fail("data." + name, "matrix shape does not match labeled axes", oid)
    legacy = d["representation"] == "legacy_score_count"
    if legacy and "counts" in payload:
        fail("data.counts", "legacy counts must be in score:count cells", oid)
    pairs = {}
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            raw, count = payload["values"][i][j], None
            if legacy and raw not in (None, ""):
                if not isinstance(raw, str) or raw.count(":") != 1:
                    fail("data.values", "legacy cell must be score:count or declared blank", oid)
                raw, count = raw.split(":")
                count = _number(count, policy, "data.count", oid, count=True)
            elif "counts" in payload:
                count = _number(payload["counts"][i][j], policy, "data.count", oid, count=True)
            score = _number(raw, policy, "data.score", oid)
            pair = (c, r) if transposed else (r, c)
            pairs[pair] = PairValue("scorable" if score is not None else "unscored", score=score,
                                    count=count, reason=None if score is not None else "declared_missing_score")
    return pairs


def _records(d, payload, normalized=False):
    oid, policy = d["output_id"], d["missing_policy"]
    keys(payload, ("records",), field="data", output_id=oid)
    if not isinstance(payload["records"], (list, tuple)):
        fail("data.records", "expected list", oid)
    pairs = {}
    rep = d["representation"]
    for row in payload["records"]:
        keys(row, ("query_id", "candidate_id", "status") if normalized else ("query_id", "candidate_id"),
             ("score", "rank", "count", "reason") if normalized else ("score", "rank", "count", "status", "reason"), "data.records", oid)
        q, c = row["query_id"], row["candidate_id"]
        text(q, "data.query_id", oid)
        text(c, "data.candidate_id", oid)
        score = _number(row["score"], policy, "data.score", oid) if row.get("score") not in (None, "") else None
        if "score" in row and row["score"] in (None, "") and not normalized:
            _number(row["score"], policy, "data.score", oid)
        rank = _rank(row["rank"], oid) if row.get("rank") not in (None, "") else None
        count = _number(row["count"], policy, "data.count", oid, count=True) if "count" in row else None
        status = row.get("status", "scorable" if score is not None or rank is not None else "unscored")
        reason = row.get("reason") or None
        if not normalized and "status" not in row and status == "unscored":
            reason = reason or "declared_missing_score"
        if not normalized and rep == "long_scores" and "score" not in row and ("status" not in row or status == "scorable"):
            fail("data.score", "long scores require a score column or explicit non-scorable status", oid)
        try:
            value = PairValue(status, score, rank, count, reason)
        except ComparisonValidationError as exc:
            fail(exc.issue.field, exc.issue.reason, oid)
        _insert(pairs, (q, c), value, oid)
    return pairs


def _permutations(d, payload):
    oid = d["output_id"]
    keys(payload, ("query_ids", "permutations"), field="data", output_id=oid)
    qs = ids(payload["query_ids"], "data.query_ids", oid)
    if set(qs) != set(d["query_ids"]):
        fail("data.query_ids", "one permutation required for every declared query", oid)
    arrays = payload["permutations"]
    if not isinstance(arrays, (list, tuple)) or len(arrays) != len(qs):
        fail("data.permutations", "one permutation required per query", oid)
    n, base, pairs = len(d["candidate_ids"]), d["data"]["index_base"], {}
    for q, perm in zip(qs, arrays):
        if not isinstance(perm, (list, tuple)) or any(type(i) is not int for i in perm) or sorted(perm) != list(range(base, n + base)):
            fail("data.permutations", "row is not an exact candidate permutation", oid)
        for rank, position in enumerate(perm, 1):
            pairs[q, d["candidate_ids"][position - base]] = PairValue("scorable", rank=rank)
    return pairs


def _expand_symmetric(d, pairs):
    if not d["data"].get("symmetric", False):
        return pairs
    for (q, c), value in list(pairs.items()):
        reverse = pairs.get((c, q))
        if value.status == "scorable":
            if reverse is not None and reverse.status == "scorable" and (value.score, value.count) != (reverse.score, reverse.count):
                fail("data.symmetric", "conflicting reciprocal scores/counts", d["output_id"])
            if reverse is None or reverse.status == "unscored":
                pairs[c, q] = value
    return pairs


def _validate_pairs(output):
    """Validate normalized data, including direct dataclass construction."""
    d, oid, pairs = output.descriptor, output.output_id, output.pairs
    _data_contract(d)
    qs, cs = set(output.query_ids), set(output.candidate_ids)
    rep = d["representation"]
    for pair, value in pairs.items():
        if not isinstance(pair, tuple) or len(pair) != 2 or pair[0] not in qs or pair[1] not in cs:
            fail("data", "pair outside declared axes", oid)
        if not isinstance(value, PairValue):
            fail("data", "normalized entries must be PairValue objects", oid)
        if value.count is not None and "count_semantics" not in d:
            fail("count_semantics", "counts require their original meaning", oid)
        if value.status == "missing_query" and pair[0] not in d.get("missing_queries", ()):
            fail("data.status", "missing_query requires query-level declaration", oid)
        if pair[0] in d.get("missing_queries", ()) and value.status != "missing_query":
            fail("missing_queries", "missing query has reported pair values", oid)
        if output.complete and value.status in ("truncated", "unreported"):
            fail("data.status", "complete input contains unknown omissions", oid)
        if value.status != "scorable" and not value.reason:
            fail("data.reason", "explicit non-scorable records require a reason", oid)
        for rule in d.get("eligibility", ()):
            if (rule["query_id"], rule["candidate_id"]) == pair:
                if rule["eligible"] and value.status == "ineligible":
                    fail("eligibility", "eligible override contradicts ineligible pair status", oid)
                if not rule["eligible"] and value.rank is not None:
                    fail("eligibility", "ineligible pair has a supplied rank", oid)
    if rep == "certified_prefix" and d.get("missing_queries"):
        fail("missing_queries", "a prefix certificate cannot certify a missing query", oid)
    if rep == "rank_permutation":
        if d.get("eligibility") or d.get("missing_queries"):
            fail("representation", "full permutations require every declared candidate/query", oid)
        for q in output.query_ids:
            row = [pairs.get((q, c)) for c in output.candidate_ids]
            if any(v is None or v.status != "scorable" or v.rank is None for v in row) or sorted(v.rank for v in row) != list(range(1, len(cs) + 1)):
                fail("data.rank", "normalized permutation must cover every candidate exactly once", oid)
    for q in output.query_ids:
        if q in d.get("missing_queries", ()):
            continue
        known = []
        for c in output.candidate_ids:
            if rep == "ordered_ranks" and (q, c) not in pairs:
                # A declared eligibility override is complete status metadata.
                if not any(r["query_id"] == q and r["candidate_id"] == c and not r["eligible"] for r in d.get("eligibility", ())):
                    fail("data.status", "complete ordered ranks require status for every pair", oid)
            v = output.pair(q, c)
            if v.status == "scorable":
                known.append((c, v))
            if rep in ("score_matrix", "long_scores", "legacy_score_count") and v.status == "scorable" and v.score is None:
                fail("data.score", "scored representation has rank-only pair", oid)
        ranks = [v.rank for _, v in known]
        if rep == "filtered_list":
            supplied = [r for r in ranks if r is not None]
            if len(set(supplied)) != len(supplied):
                fail("data.rank", "duplicate saved ranks in filtered list", oid)
        elif rep in ("ordered_ranks", "certified_prefix") or any(r is not None for r in ranks):
            if any(r is None for r in ranks) or sorted(ranks) != list(range(1, len(ranks) + 1)):
                fail("data.rank", "ranks must be unique consecutive one-based ranks of all scorable eligible pairs", oid)
        scored = [(c, v) for c, v in known if v.score is not None]
        if any(v.rank is not None for _, v in known) and scored:
            if len(scored) != len(known) or any(v.rank is None for _, v in known):
                fail("data.score", "scores accompanying ranks must cover all reported scorable pairs, with ranks", oid)
            from .ranking import score_order
            expected = score_order({c: v.score for c, v in known}, d["ranking_policy"])
            actual = tuple(c for c, v in sorted(known, key=lambda item: item[1].rank))
            if expected != actual:
                fail("data.rank", "scores and ranks contradict declared policy/Unicode tie rule", oid)
            if d["tie_policy"] != TIE_POLICY:
                fail("tie_policy", "score/rank consistency requires canonical Unicode ties", oid)
        if rep == "certified_prefix":
            cert = d["completeness"]["queries"][q]
            if len(known) != cert["depth"]:
                fail("completeness.depth", "saved row count differs from certified depth", oid)
            native_size = sum(output.pair(q, c).status not in ("ineligible", "missing_query", "unscored")
                              and not (cert["self_excluded"] and d["identity"]["query_namespace"] == d["identity"]["candidate_namespace"] and q == c)
                              for c in output.candidate_ids)
            if native_size != cert["pool_size"]:
                fail("completeness.pool_size", "certificate contradicts declared native universe/statuses", oid)
            if cert["self_excluded"] and d["identity"]["query_namespace"] == d["identity"]["candidate_namespace"] and any(c == q for c, _ in known):
                fail("completeness.self_excluded", "certified prefix contains an excluded self edge", oid)


def load_comparison_input(descriptor, *, base_dir="."):
    """Load a v1 output descriptor; paths are contained within base_dir."""
    validate_descriptor(descriptor)
    payload, sources, fingerprints = _payload(descriptor, base_dir)
    rep = descriptor["representation"]
    if descriptor["data"]["format"] == "normalized":
        pairs = _records(descriptor, payload, normalized=True)
    elif rep in ("score_matrix", "legacy_score_count"):
        pairs = _matrix(descriptor, payload)
    elif rep == "rank_permutation":
        pairs = _permutations(descriptor, payload)
    else:
        pairs = _records(descriptor, payload)
    pairs = _expand_symmetric(descriptor, pairs)
    warnings = ()
    if rep == "legacy_score_count":
        warnings = (Issue("data", "legacy scores may be rounded to five decimals; ranks use available precision",
                          "Re-export full-precision source matrices for exact original ordering.", descriptor["output_id"]),)
    return ComparisonInput(descriptor, pairs, warnings, sources, fingerprints)


def load_manifest(path):
    """Read and validate identity/configuration without building metrics or reports."""
    path = Path(path)
    if path.suffix.lower() != ".json" or not path.is_file():
        fail("manifest", "expected a local JSON manifest file")
    content, fingerprint = _read_fingerprinted(path, "manifest")
    data = _json(content, "manifest")
    keys(data, ("schema_version", "dataset", "outputs", "settings"),
         ("profiles", "report", "sample_metadata", "diagnostic_requests"), field="manifest")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        fail("schema_version", "unsupported version")
    validate_identity(data["dataset"])
    settings = ComparisonSettings.from_dict(data["settings"])
    if not isinstance(data["outputs"], list) or not data["outputs"]:
        fail("outputs", "at least one saved output is required")
    outputs = tuple(load_comparison_input(d, base_dir=path.parent) for d in data["outputs"])
    from .compatibility import validate_compatibility
    report = validate_compatibility(outputs, settings, dataset=data["dataset"])
    from .models import freeze
    from .profiles import load_profile_data
    from .browser import ReportSettings
    profiles = load_profile_data(data["profiles"], base_dir=path.parent) if "profiles" in data else None
    if profiles is not None:
        profiles.validate_binding(data["dataset"], outputs)
    report_settings = ReportSettings.from_dict(data.get("report", {}))
    from .diagnostics import load_sample_metadata, DiagnosticRequest
    metadata = load_sample_metadata(data["sample_metadata"], base_dir=path.parent) if "sample_metadata" in data else None
    requests = data.get("diagnostic_requests", [])
    if not isinstance(requests, list):
        fail("diagnostic_requests", "expected an explicit request list")
    requests = tuple(DiagnosticRequest.from_dict(r) for r in requests)
    return ComparisonManifest(freeze(data["dataset"]), outputs, settings, report,
                              freeze((fingerprint,)), profiles, report_settings, metadata, requests)


def from_association_result(result, descriptor, *, query_axis, query_ids, candidate_ids):
    """Copy explicit labeled selections from .values/.counts, never save/as_list.

    query_axis is 'index' or 'columns'. Source may be a structural test double;
    no import or isinstance check against the legacy result class is performed.
    """
    d = thaw(descriptor)
    validate_descriptor(d)
    if query_axis not in ("index", "columns"):
        fail("query_axis", "select index or columns explicitly", d["output_id"])
    qs, cs = ids(query_ids, "query_ids"), ids(candidate_ids, "candidate_ids")
    if tuple(d["query_ids"]) != qs or tuple(d["candidate_ids"]) != cs:
        fail("axes", "selected IDs must equal descriptor axes in order", d["output_id"])
    expected_orientation = "query_rows_candidate_columns" if query_axis == "index" else "candidate_rows_query_columns"
    if d["orientation"] != expected_orientation or d["representation"] != "score_matrix":
        fail("orientation", "descriptor must describe the selected score matrix orientation", d["output_id"])
    try:
        values, counts = result.values, result.counts
        for matrix in (values, counts):
            if matrix is None:
                continue
            rows = ids(list(matrix.index), "source.index", d["output_id"])
            cols = ids(list(matrix.columns), "source.columns", d["output_id"])
            rq, rc = (rows, cols) if query_axis == "index" else (cols, rows)
            if not set(qs) <= set(rq) or not set(cs) <= set(rc):
                fail("source.axes", "selected IDs absent from source matrix", d["output_id"])
        selected_rows, selected_cols = (qs, cs) if query_axis == "index" else (cs, qs)
        def copy_cells(matrix, count=False):
            return [[_number(matrix.at[r, c].item() if hasattr(matrix.at[r, c], "item") else matrix.at[r, c],
                             d["missing_policy"], "source.count" if count else "source.score", d["output_id"], count=count)
                     for c in selected_cols] for r in selected_rows]
        payload = {"row_ids": list(selected_rows), "column_ids": list(selected_cols), "values": copy_cells(values)}
        if counts is not None:
            payload["counts"] = copy_cells(counts, True)
    except (AttributeError, KeyError, TypeError) as exc:
        fail("source", "expected labeled .values/.counts with .index/.columns/.at: " + str(exc), d["output_id"])
    d["data"] = {"format": "json", "inline": payload}
    return load_comparison_input(d)
