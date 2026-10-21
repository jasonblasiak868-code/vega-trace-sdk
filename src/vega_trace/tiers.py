"""tiers.py - trace telemetry by access tier (provisional 64/168,948, section IV.20.3).

What can be captured depends on what the architecture can see of the model:
  tier 1  weights accessible:        per-token traces through the layers (see trace.py: mapping and metamorphosis), which may be rendered as audio (harmonic.py)
  tier 2  only output probabilities: the per-token ENTROPY of the output distribution; low and high entropy are distinguishable to a listener
  tier 3  text only:                 NO internal trace; only external observation (timing and resource use)
A lower tier is never padded with what only a higher tier could know: a tier-3 request that carries layer data is refused, not quietly accepted.
A telemetry signal may CUE a hard stop; it never grants or withdraws authority (cue() returns advice only)."""
import math

from vega_trace import trace as T

ACCESS = ("weights", "probabilities", "text")
MAX_TOKENS = 100000
MAX_VOCAB = 1000000


class TierRefused(ValueError):
    pass


def entropy_bits(probs):
    """Shannon entropy, in bits, of one next-token distribution. The values must be finite, non-negative and sum to 1 within 1e-3 (a model's printed probabilities are rounded)."""
    if isinstance(probs, (str, bytes)) or not hasattr(probs, "__iter__"):
        raise TierRefused("a distribution is a list of probabilities")
    ps = []
    for p in probs:
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 or p > 1:
            raise TierRefused("a probability is a finite number in 0..1")
        ps.append(float(p))
        if len(ps) > MAX_VOCAB:
            raise TierRefused("distribution too long")
    if not ps or abs(sum(ps) - 1.0) > 1e-3:
        raise TierRefused("a distribution is non-empty and sums to 1")
    return -sum(p * math.log2(p) for p in ps if p > 0)


def tier2_record(step_id, per_token_probs):
    T._id(step_id, "step_id")
    if not isinstance(per_token_probs, (list, tuple)) or not 1 <= len(per_token_probs) <= MAX_TOKENS:
        raise TierRefused("per_token_probs is a list of 1..%d distributions" % MAX_TOKENS)
    ent = [entropy_bits(p) for p in per_token_probs]
    n = len(ent)
    mean = sum(ent) / n
    sd = math.sqrt(sum((e - mean) ** 2 for e in ent) / (n - 1)) if n > 1 else 0.0
    srt = sorted(ent)
    return {"trace": "echo", "kind": "entropy", "tier": 2, "step": step_id, "n": n, "mean_bits": round(mean, 6), "sd_bits": round(sd, 6), "max_bits": round(srt[-1], 6), "p90_bits": round(srt[min(n - 1, int(0.9 * n))], 6),
            "high_share": round(sum(1 for e in ent if e > 3.0) / n, 6)}


def telemetry(access, step_id, **data):
    """The record the architecture can honestly produce for the access it has.
    weights:       layers=[{"layer","in","out"}] (metamorphosis) and optionally consulted=[{"layer","positions"}] (mapping) -> a dict with those records
    probabilities: per_token_probs=[[...], ...] -> a tier-2 entropy record
    text:          timings_ns=[...] -> a tier-3 breathing record; any layer or probability data is refused."""
    if access not in ACCESS:
        raise TierRefused("access is one of %s" % (ACCESS,))
    if access == "weights":
        if "layers" not in data:
            raise TierRefused("weights access needs layers")
        out = {"tier": 1, "metamorphosis": T.metamorphosis_record(step_id, data["layers"])}
        if "consulted" in data:
            out["mapping"] = T.mapping_record(step_id, data["consulted"])
        extra = set(data) - {"layers", "consulted", "timings_ns"}
        if extra:
            raise TierRefused("unexpected data for weights access: %s" % sorted(extra))
        if "timings_ns" in data:
            out["breathing"] = T.breathing_record(step_id, data["timings_ns"])
        return out
    if access == "probabilities":
        if set(data) - {"per_token_probs", "timings_ns"} or "per_token_probs" not in data:
            raise TierRefused("probability access takes per_token_probs (and optionally timings_ns), nothing from the layers")
        out = {"tier": 2, "entropy": tier2_record(step_id, data["per_token_probs"])}
        if "timings_ns" in data:
            out["breathing"] = T.breathing_record(step_id, data["timings_ns"])
        return out
    if set(data) - {"timings_ns"} or "timings_ns" not in data:
        raise TierRefused("text-only access has no internal trace: only timings_ns (external observation) is accepted")
    return {"tier": 3, "breathing": T.breathing_record(step_id, data["timings_ns"])}


def cue(record, high_share=0.5, cv=1.0):
    """Advice only. True when the telemetry looks like something worth a person's attention (a large share of high-entropy tokens, or very uneven timing). It does not stop anything."""
    if not isinstance(record, dict):
        raise TierRefused("cue takes a telemetry record (a dict from telemetry())")
    for name, v in (("high_share", high_share), ("cv", cv)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise TierRefused("%s threshold is a non-negative number" % name)

    def number(d, key):
        x = d.get(key, 0)
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TierRefused("%s in the record is a number" % key)
        return x
    flags = []
    ent = record.get("entropy")
    if isinstance(ent, dict) and number(ent, "high_share") >= high_share:
        flags.append("many high-entropy tokens")
    br = record.get("breathing")
    if isinstance(br, dict) and number(br, "cv") >= cv:
        flags.append("uneven timing")
    return {"advice_only": True, "cue": bool(flags), "why": flags, "grants_authority": False}
