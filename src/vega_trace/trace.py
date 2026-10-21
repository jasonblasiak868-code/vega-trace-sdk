"""trace.py - the three per-step traces, kept as hashes and small numbers, never as raw activations.

  mapping      WHERE a step went: which layers and positions it consulted (the attention route)
  metamorphosis WHAT it became: per layer, a digest of the state going in and coming out, and their sizes (the digestion record)
  breathing    the OUTSIDE view: timing of the step as seen from outside the model (no access to the model at all)
Inside-complete, inside-deep, outside-only: together a trace family from full access to zero access.

Rules: a record holds digests, counts and scalars only. A raw vector, a long list, or anything credential-shaped is refused, so a trace can be stored, shared and compared without
carrying the data that made it. Every record is appended to a custody chain (hash-chained, replica-checked)."""
import hashlib
import json
import math
import re

from vega_custody.dag.dag import RecordRefused, contains_credential

MAX_LAYERS = 512
MAX_POSITIONS = 4096
MAX_TIMINGS = 100000
MAX_TIMING_NS = 1e18                  # about 31 years in nanoseconds: far past any real step, and small enough that the statistics below cannot overflow
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class TraceRefused(ValueError):
    pass


def _id(x, what):
    if not isinstance(x, str) or not _ID.fullmatch(x):
        raise TraceRefused("%s must be a plain id (letters, digits, . _ : -)" % what)
    return x


def _int(x, what, lo=0, hi=10 ** 9):
    if isinstance(x, bool) or not isinstance(x, int) or not lo <= x <= hi:
        raise TraceRefused("%s must be an integer in %d..%d" % (what, lo, hi))
    return x


def _num(x, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise TraceRefused("%s must be a finite number" % what)
    return float(x)


def digest_vector(values, places=6):
    """Canonical digest of a vector: values rounded to `places` decimals, so two machines that agree to that precision get the same hash. Refuses NaN, infinity and non-numbers."""
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise TraceRefused("a vector is a list of numbers")
    out = []
    for v in values:
        v = _num(v, "vector element")
        out.append(0.0 if v == 0 else round(v, places))
        if len(out) > 10 ** 6:
            raise TraceRefused("vector too long")
    norm = math.hypot(*out) if out else 0.0                       # hypot does not overflow on the squares; only a true length beyond a float is refused
    if not math.isfinite(norm):
        raise TraceRefused("the vector is too large to record: its length is not a finite number")
    return hashlib.sha256(json.dumps(out, separators=(",", ":")).encode()).hexdigest(), len(out), norm


def mapping_record(step_id, consulted):
    """consulted: list of {"layer": int, "positions": [int,...]} -> a record with, per layer, the number of positions and a digest of the sorted positions."""
    _id(step_id, "step_id")
    if not isinstance(consulted, (list, tuple)) or len(consulted) > MAX_LAYERS:
        raise TraceRefused("consulted is a list of at most %d layers" % MAX_LAYERS)
    rows, seen = [], set()
    for c in consulted:
        if not isinstance(c, dict) or set(c) - {"layer", "positions"}:
            raise TraceRefused("each consulted entry is {layer, positions}")
        layer = _int(c.get("layer"), "layer", 0, 100000)
        if layer in seen:
            raise TraceRefused("layer %d listed twice" % layer)
        seen.add(layer)
        pos = c.get("positions")
        if not isinstance(pos, (list, tuple)) or len(pos) > MAX_POSITIONS:
            raise TraceRefused("positions is a list of at most %d integers" % MAX_POSITIONS)
        ps = sorted({_int(p, "position", 0, 10 ** 9) for p in pos})
        rows.append({"layer": layer, "n_positions": len(ps), "positions_sha256": hashlib.sha256(json.dumps(ps).encode()).hexdigest()})
    rows.sort(key=lambda r: r["layer"])
    return {"trace": "mapping", "step": step_id, "layers": rows}


def metamorphosis_record(step_id, layers):
    """layers: list of {"layer": int, "in": vector, "out": vector} -> per layer digests and norms (the vectors themselves are dropped)."""
    _id(step_id, "step_id")
    if not isinstance(layers, (list, tuple)) or len(layers) > MAX_LAYERS:
        raise TraceRefused("layers is a list of at most %d" % MAX_LAYERS)
    rows, seen = [], set()
    for l in layers:
        if not isinstance(l, dict) or set(l) - {"layer", "in", "out"}:
            raise TraceRefused("each layer entry is {layer, in, out}")
        n = _int(l.get("layer"), "layer", 0, 100000)
        if n in seen:
            raise TraceRefused("layer %d listed twice" % n)
        seen.add(n)
        din, lin, nin = digest_vector(l.get("in"))
        dout, lout, nout = digest_vector(l.get("out"))
        rows.append({"layer": n, "in_sha256": din, "out_sha256": dout, "dim_in": lin, "dim_out": lout, "norm_in": round(nin, 6), "norm_out": round(nout, 6),
                     "changed": din != dout})
    rows.sort(key=lambda r: r["layer"])
    return {"trace": "metamorphosis", "step": step_id, "layers": rows}


def breathing_record(step_id, timings_ns):
    """timings_ns: how long the same step took each time it was observed from outside. Records count, mean, spread and the 95th percentile, not the samples."""
    _id(step_id, "step_id")
    if not isinstance(timings_ns, (list, tuple)) or not 2 <= len(timings_ns) <= MAX_TIMINGS:
        raise TraceRefused("timings_ns is a list of 2..%d numbers" % MAX_TIMINGS)
    xs = sorted(_num(t, "timing") for t in timings_ns)
    if xs[0] < 0:
        raise TraceRefused("a timing cannot be negative")
    if xs[-1] > MAX_TIMING_NS:
        raise TraceRefused("a timing is at most %g nanoseconds" % MAX_TIMING_NS)
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    p95 = xs[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
    return {"trace": "breathing", "step": step_id, "n": n, "mean_ns": round(mean, 3), "sd_ns": round(sd, 3), "cv": round(sd / mean, 6) if mean else 0.0, "p95_ns": p95, "min_ns": xs[0], "max_ns": xs[-1]}


def record(dag, rec):
    """Append a trace record to the custody chain (kind TRACE_<NAME>). Credential-shaped content is refused by the chain itself."""
    if not isinstance(rec, dict) or rec.get("trace") not in ("mapping", "metamorphosis", "breathing", "echo"):
        raise TraceRefused("not a trace record")
    if contains_credential(rec):
        raise TraceRefused("a trace record may not hold anything credential-shaped")
    try:
        return dag.record("TRACE_" + rec["trace"].upper(), rec)
    except RecordRefused as exc:
        raise TraceRefused(str(exc))


def compare(a, b):
    """Compare two records of the same kind for the same step. Mapping: which layers' consulted positions differ. Metamorphosis: which layers' outputs differ (`differ`) and which layers' inputs differ
    (`differ_in`); the pair is identical only when neither does and both cover the same layers. Breathing: ratio of means. Returns a plain dict. Echo records and malformed records are refused."""
    if not isinstance(a, dict) or not isinstance(b, dict) or a.get("trace") != b.get("trace") or a.get("step") != b.get("step"):
        raise TraceRefused("only the same kind of trace for the same step can be compared")
    kind = a["trace"]
    if kind not in ("mapping", "metamorphosis", "breathing"):
        raise TraceRefused("only mapping, metamorphosis and breathing records can be compared")
    try:
        if kind == "breathing":
            return {"mean_ratio": round(b["mean_ns"] / a["mean_ns"], 6) if a["mean_ns"] else None, "same_spread": abs(a["cv"] - b["cv"]) < 0.05}
        la = {r["layer"]: r for r in a["layers"]}
        lb = {r["layer"]: r for r in b["layers"]}
        key = "positions_sha256" if kind == "mapping" else "out_sha256"
        shared = la.keys() & lb.keys()
        differ = sorted(n for n in shared if la[n][key] != lb[n][key])
        differ_in = sorted(n for n in shared if la[n]["in_sha256"] != lb[n]["in_sha256"]) if kind == "metamorphosis" else []
    except (KeyError, TypeError, AttributeError) as exc:
        raise TraceRefused("a record is malformed: %s" % exc)
    return {"only_in_a": sorted(la.keys() - lb.keys()), "only_in_b": sorted(lb.keys() - la.keys()), "differ": differ, "differ_in": differ_in,
            "identical": not differ and not differ_in and la.keys() == lb.keys()}
