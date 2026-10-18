"""nnr.py - the staged neural-network-reader pieces that need no model: the prompt battery and observe ledger (NNR-007), the stamped-prediction calibration (NNR-008) and the salted keyed trace
commitment (NNR-010). From the staging package NNR_ENABLEMENT_PACKAGE.md (2026-09-20); keyword probes found NNR-007 and NNR-010 text in none of the 21 filed provisionals, so treat this file as UNFILED matter.

  Battery / ObserveLedger   head profiles {(layer, head): magnitude} per prompt class (computational, cache, novel); cumulative pathway frequency across sessions; a determinism check (identical
                            repeated prompts should give identical profiles, variance 0.0); similarity between class mean profiles. Every observation is recorded with a SHA-256 body digest and a pointer
                            to the head of the capsule chain, so interpretability evidence is custody-controlled.
  stamp / grade             expectations of where change will land are stamped (hashed and recorded) BEFORE a run; after it each is graded HIT or MISS against the observed change. Misses are kept.
  commit_trace / open       a keyed, salted commitment to a trace record; the opening is checked in constant time. A zero-knowledge PROOF that a trace derives from a committed model and exceeds a
                            baseline without revealing it is NOT built: prove_derivation raises ProofUnavailable until a real backend is registered (fail closed)."""
import hashlib
import hmac
import json
import math

from vega_custody.dag.dag import RecordRefused
from vega_trace import trace as T

CLASSES = ("computational", "cache", "novel")
MAX_HEADS = 4096


class NnrRefused(ValueError):
    pass


class ProofUnavailable(NotImplementedError):
    pass


def _profile(p):
    if not isinstance(p, dict) or not 1 <= len(p) <= MAX_HEADS:
        raise NnrRefused("a profile is a dict of 1..%d (layer, head) magnitudes" % MAX_HEADS)
    out = {}
    for k, v in p.items():
        if not (isinstance(k, tuple) and len(k) == 2 and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < 100000 for i in k)):
            raise NnrRefused("a key is a (layer, head) pair of small non-negative integers")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise NnrRefused("a magnitude is a finite non-negative number")
        out[k] = float(v)
    return out


def _digest(p):
    return hashlib.sha256(json.dumps(sorted([k[0], k[1], round(v, 6)] for k, v in p.items())).encode()).hexdigest()


def cosine(a, b):
    keys = sorted(set(a) | set(b))
    va, vb = [a.get(k, 0.0) for k in keys], [b.get(k, 0.0) for k in keys]
    na, nb = math.sqrt(sum(x * x for x in va)), math.sqrt(sum(x * x for x in vb))
    return round(sum(x * y for x, y in zip(va, vb)) / (na * nb), 6) if na and nb else 0.0


class ObserveLedger:
    def __init__(self, dag):
        self.dag = dag
        self.cum = {}
        self.runs = {}

    def observe(self, step_id, prompt_class, prompt_sha256, profile, capsule_head):
        T._id(step_id, "step_id")
        if prompt_class not in CLASSES:
            raise NnrRefused("prompt class is one of %s" % (CLASSES,))
        for h, w in ((prompt_sha256, "prompt_sha256"), (capsule_head, "capsule_head")):
            if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
                raise NnrRefused("%s is a sha256 hex digest" % w)
        p = _profile(profile)
        top = sorted(p.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        rec = {"trace": "mapping", "kind": "nnr007_observation", "step": step_id, "class": prompt_class, "prompt_sha256": prompt_sha256, "body_sha256": _digest(p), "capsule_head": capsule_head,
               "heads": len(p), "top": [[k[0], k[1], round(v, 4)] for k, v in top]}
        try:
            e = self.dag.record("TRACE_NNR007", rec)
        except RecordRefused as exc:
            raise NnrRefused(str(exc))
        for k, v in p.items():
            self.cum[k] = self.cum.get(k, 0.0) + v
        self.runs.setdefault((prompt_class, prompt_sha256), []).append(p)
        return e

    def determinism(self, prompt_class, prompt_sha256):
        """Largest per-head variance across repeated identical prompts (0.0 means the same pathway every time). None with fewer than two runs."""
        rs = self.runs.get((prompt_class, prompt_sha256), [])
        if len(rs) < 2:
            return None
        keys = sorted(set().union(*rs))
        worst = 0.0
        for k in keys:
            xs = [r.get(k, 0.0) for r in rs]
            m = sum(xs) / len(xs)
            worst = max(worst, sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
        return round(worst, 9)

    def class_similarity(self):
        means = {}
        for (cls, _), rs in self.runs.items():
            for r in rs:
                acc = means.setdefault(cls, [{}, 0])
                for k, v in r.items():
                    acc[0][k] = acc[0].get(k, 0.0) + v
                acc[1] += 1
        prof = {c: {k: v / n for k, v in a.items()} for c, (a, n) in means.items()}
        names = sorted(prof)
        return {"%s|%s" % (a, b): cosine(prof[a], prof[b]) for i, a in enumerate(names) for b in names[i + 1:]}

    def brightest(self, n=5):
        return [[k[0], k[1], round(v, 4)] for k, v in sorted(self.cum.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def stamp(dag, run_id, expectations):
    """expectations: [{"region": text, "direction": 'up'|'down'|'none'}]. Recorded BEFORE the run; returns the stamp (its hash is what grade() later requires)."""
    T._id(run_id, "run_id")
    if not isinstance(expectations, (list, tuple)) or not 1 <= len(expectations) <= 500:
        raise NnrRefused("expectations is a list of 1..500")
    seen = set()
    for e in expectations:
        if not isinstance(e, dict) or set(e) != {"region", "direction"} or e["direction"] not in ("up", "down", "none") or not isinstance(e["region"], str) or not e["region"].strip() or e["region"] in seen:
            raise NnrRefused("each expectation is {region (new text), direction up|down|none}")
        seen.add(e["region"])
    h = hashlib.sha256(json.dumps(sorted((e["region"], e["direction"]) for e in expectations)).encode()).hexdigest()
    try:
        dag.record("TRACE_STAMP", {"run": run_id, "stamp_sha256": h, "n": len(expectations)})
    except RecordRefused as exc:
        raise NnrRefused(str(exc))
    return {"run": run_id, "stamp_sha256": h, "expectations": [dict(e) for e in expectations]}


def grade(stamp_obj, observed, tolerance=0.0):
    """observed: {region: signed change}. A region expected 'up' is a HIT if its change exceeds +tolerance, 'down' below -tolerance, 'none' within +/- tolerance. A region not observed is a MISS."""
    if not isinstance(stamp_obj, dict) or not isinstance(stamp_obj.get("expectations"), list):
        raise NnrRefused("grade takes the stamp from stamp()")
    h = hashlib.sha256(json.dumps(sorted((e["region"], e["direction"]) for e in stamp_obj["expectations"])).encode()).hexdigest()
    if h != stamp_obj.get("stamp_sha256"):
        raise NnrRefused("the stamp was altered after it was recorded")
    if not isinstance(observed, dict) or isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
        raise NnrRefused("observed is a dict of region to change; tolerance is non-negative")
    rows = []
    for e in stamp_obj["expectations"]:
        v = observed.get(e["region"])
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and ((e["direction"] == "up" and v > tolerance) or (e["direction"] == "down" and v < -tolerance) or (e["direction"] == "none" and abs(v) <= tolerance))
        rows.append({"region": e["region"], "expected": e["direction"], "result": "HIT" if ok else "MISS"})
    hits = sum(1 for r in rows if r["result"] == "HIT")
    return {"rows": rows, "hits": hits, "misses": len(rows) - hits, "rate": round(hits / len(rows), 4), "note": "misses are kept: a calibration that hides its misses is not one"}


def _canon(rec):
    return json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()


def commit_trace(trace_record, salt, key):
    """HMAC-SHA256 over the canonical trace with a salt, under a key the holder keeps. Returns the hex commitment; reveal (trace, salt) and the verifier with the key can check it."""
    if not isinstance(trace_record, dict) or not isinstance(salt, (bytes, bytearray)) or len(salt) < 16 or not isinstance(key, (bytes, bytearray)) or len(key) < 16:
        raise NnrRefused("a trace is a dict; the salt and the key are at least 16 bytes each")
    return hmac.new(bytes(key), bytes(salt) + b"\x00" + _canon(trace_record), hashlib.sha256).hexdigest()


def open_commitment(commitment, trace_record, salt, key):
    try:
        return hmac.compare_digest(commitment, commit_trace(trace_record, salt, key))
    except (NnrRefused, TypeError):
        return False


def prove_derivation(*args, **kwargs):
    raise ProofUnavailable("no zero-knowledge backend is registered: a proof that a trace derives from the committed model without revealing it is not built (fail closed)")
