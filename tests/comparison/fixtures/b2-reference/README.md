# B2 reference evidence: known-math fixture

The [manifest](manifest.json) has two complete saved-score outputs, six query features and six output candidates (a–f). A ranks a,b,c,d,e,f; B ranks b,a,c,d,e,f for every query. Analysis depths are 1, 2 and 10. These are synthetic descriptions, not biological truth or evidence of method quality.

The [reference document](references.json) declares five independent endpoints: curated/v1 direct reaction, curated/v1 inferred reaction, curated/v1 pathway co-membership, other/v1 direct reaction, and curated/v2 direct reaction. All assess q0, q1, q2, q6 and qU; qN is explicitly unassessed. Their candidate universes include a–f and an annotated candidate named outside, which is absent from both output axes.

## Direct endpoint at depth 1, output A

| Query | Known support | Total | Reachable | Supported nominations | Hit | Supported fraction | Recovery | Reachability | Stratum |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| q0 | none | 0 | 0 | 0 | 0 | 0 | undefined | undefined | 0 |
| q1 | a | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| q2 | a, b, outside | 3 | 2 | 1 | 1 | 1 | 1/2 | 2/3 | 2–5 |
| q6 | a–f | 6 | 6 | 1 | 1 | 1 | 1/6 | 1 | 6+ |
| qU | outside | 1 | 0 | 0 | 0 | 0 | undefined | 0 | 0 |
| qN | unassessed | undefined | undefined | undefined | undefined | undefined | undefined | undefined | undefined |

The q1/a pair has two distinct evidence records plus an exact duplicate of one. Normalization retains two records, but support counts the pair once. Empty assessed q0 is not unassessed qN; known-unreachable qU is neither. Undefined metrics are exported as null with reasons, not zero.

Default equal-feature means:

- All-assessed hit and supported fraction: 3/5, with five evaluable queries.
- Reachable-cohort hit: 3/3 = 1.
- Recovery: (1 + 1/2 + 1/6) / 3 = **5/9**, three evaluable queries.
- Reachability: (1 + 2/3 + 1 + 0) / 4 = **2/3**, four evaluable queries.
- B's all-assessed depth-1 hit: 2/5, since b does not support q1 in this endpoint.
- At depth 10 the exhausted nomination list has six candidates, not ten. A's q1 supported fraction is 1/6 and recovery is 1.

The [query groups](query-groups.json) map q0/q1/q2 to G1, q6 to G2, and qU/qN to G3. Switching the reference weighting to group explicitly gives:

- All-assessed hit: ((0+1+1)/3 + 1 + 0) / 3 = **5/9**.
- Recovery: ((1+1/2)/2 + 1/6) / 2 = **11/24**. G3 has zero evaluable recovery features and is excluded, not assigned zero.

Each group reports total size, evaluable feature count, included IDs, exclusions and within-group mean. Runs/outputs are never pooled.

The other endpoints support only q1: inferred supports b, pathway supports c, other source supports d, and other version supports e. These exercise independent endpoint selection, not a union. The default fixture produces 180 per-query recovery rows and 1,200 metric-summary rows (including empty strata).

## Validation and boundaries

[Contract/math tests](../../test_b2_reference.py), [persistence tests](../../test_b2_reference_persistence.py) and [real Chrome tests](../../test_b2_reference_browser.py) cover these calculations plus unavailable/limited inputs, native/common pools, missing groups, source hashes, provenance, exact reload, payload limits, omission and display-only evidence filtering. Chrome opens generated reports directly from disk with external resolution disabled.

This fixture covers only B2 reference evidence. It does not implement or certify sessions, notes, figures, target-scale performance or a final release.
