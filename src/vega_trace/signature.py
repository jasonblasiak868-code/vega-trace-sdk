"""signature.py - the verified-fact reference signature and the asserted value (provisional 64/168,948, sections IV.20.4 to IV.20.6).

  Telemetry of assertions that were verified by two independent sources (evidence grade FACT, see vega_metacog.evidence) forms a REFERENCE SIGNATURE for a model (optionally per subject domain).
  Every other assertion gets an ASSERTED VALUE: the measured distance of its telemetry from that signature, so a listener or reader can perceive each unverified assertion relative to the 'sound of
  verified fact'. The signature changes only by COMMITTED additions of newly verified assertions. The asserted value informs; verification decides.
  calibrate() compares the asserted values of assertions later verified with those that failed, and reports the difference with its counts: an indicator, not a verdict.
  atlas() aggregates frozen computations by KNOWN epistemic status (definitional fact; derived; empirical; circumstantial; disputed; known falsehood) to show how telemetry differs by status.
Telemetry here is a small numeric feature vector (features() builds one from a tier-2 entropy record). No raw activations are held."""
import math
import threading

from vega_trace import trace as T

MIN_FOR_SIGNATURE = 10
MAX_TELEMETRY = 1e100                 # larger numbers cannot be squared safely in the statistics below
STATUSES = ("definitional", "derived", "empirical", "circumstantial", "disputed", "falsehood")
FEATURES = ("mean_bits", "sd_bits", "max_bits", "p90_bits", "high_share")


class SignatureRefused(ValueError):
    pass


def features(entropy_record):
    if not isinstance(entropy_record, dict) or entropy_record.get("kind") != "entropy" or any(k not in entropy_record for k in FEATURES):
        raise SignatureRefused("features takes a tier-2 entropy record")
    return _vec([entropy_record[k] for k in FEATURES])


def _vec(v, dim=None):
    if isinstance(v, (str, bytes)) or not hasattr(v, "__iter__"):
        raise SignatureRefused("a telemetry vector is a list of numbers")
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > MAX_TELEMETRY:
            raise SignatureRefused("a telemetry vector holds finite numbers no larger than %g" % MAX_TELEMETRY)
        out.append(float(x))
    if not 1 <= len(out) <= 64 or (dim is not None and len(out) != dim):
        raise SignatureRefused("a telemetry vector has 1..64 numbers and the signature's own length")
    return out


class ReferenceSignature:
    def __init__(self, model_id, domain="general"):
        T._id(model_id, "model_id")
        T._id(domain, "domain")
        self.model_id, self.domain = model_id, domain
        self.n, self.mean, self.m2 = 0, None, None
        self._lock = threading.RLock()

    def add_verified(self, vector, grade, committed):
        """Add one assertion's telemetry. grade must be exactly 'FACT' (two independent sources or a commit) and committed must be exactly True (the addition itself is a committed act)."""
        if grade != "FACT":
            raise SignatureRefused("only an assertion graded FACT can enter the reference signature")
        if committed is not True:
            raise SignatureRefused("the signature changes only by a committed addition")
        with self._lock:
            v = _vec(vector, None if self.mean is None else len(self.mean))
            if self.mean is None:
                self.mean, self.m2 = [0.0] * len(v), [0.0] * len(v)
            self.n += 1
            for i, x in enumerate(v):                              # Welford: running mean and sum of squares
                d = x - self.mean[i]
                self.mean[i] += d / self.n
                self.m2[i] += d * (x - self.mean[i])

    def sd(self):
        return [math.sqrt(m / (self.n - 1)) if self.n > 1 else 0.0 for m in self.m2]

    def asserted_value(self, vector):
        """RMS z-distance of the vector from the signature. None when there are too few verified assertions to mean anything (no basis, not zero)."""
        with self._lock:
            if self.n < MIN_FOR_SIGNATURE:
                return None
            v = _vec(vector, len(self.mean))
            sd = self.sd()
            mean = list(self.mean)
        scale = max(max(sd), 1e-9)
        return round(math.sqrt(sum(((x - m) / max(s, 0.05 * scale)) ** 2 for x, m, s in zip(v, mean, sd)) / len(v)), 6)


def calibrate(verified_values, failed_values):
    """The asserted values of assertions later verified vs. those that failed verification."""
    for name, xs in (("verified", verified_values), ("failed", failed_values)):
        if not isinstance(xs, (list, tuple)) or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 or x > MAX_TELEMETRY for x in xs):
            raise SignatureRefused("%s is a list of non-negative asserted values no larger than %g" % (name, MAX_TELEMETRY))
    nv, nf = len(verified_values), len(failed_values)
    if nv < 2 or nf < 2:
        return {"n_verified": nv, "n_failed": nf, "difference": None, "note": "at least two of each are needed"}
    mv, mf = sum(verified_values) / nv, sum(failed_values) / nf
    vv = sum((x - mv) ** 2 for x in verified_values) / (nv - 1)
    vf = sum((x - mf) ** 2 for x in failed_values) / (nf - 1)
    se = math.sqrt(vv / nv + vf / nf)
    d = mf - mv
    return {"n_verified": nv, "n_failed": nf, "mean_verified": round(mv, 4), "mean_failed": round(mf, 4), "difference": round(d, 4), "half_width": round(1.96 * se, 4), "separated": bool(se > 0 and abs(d) > 1.96 * se),
            "note": "an indicator presented beside the verification, which stays the authority; small samples prove nothing" if min(nv, nf) < 20 else "an indicator presented beside the verification, which stays the authority"}


def atlas(records):
    """records: [{"status": one of STATUSES, "vector": [...], "model_weight_sha256": hex, "temperature": number, "seed": int, "depth": int, "output_sha256": hex}] - one frozen computation each.
    Returns per status: count, centroid, and the distances between centroids."""
    if not isinstance(records, (list, tuple)) or not records:
        raise SignatureRefused("atlas takes a non-empty list of frozen computations")
    by, dim = {}, None
    for r in records:
        if not isinstance(r, dict) or r.get("status") not in STATUSES:
            raise SignatureRefused("each record has a status in %s" % (STATUSES,))
        for k in ("model_weight_sha256", "output_sha256"):
            if not isinstance(r.get(k), str) or len(r[k]) != 64 or any(c not in "0123456789abcdef" for c in r[k]):
                raise SignatureRefused("%s is a sha256 hex digest" % k)
        if isinstance(r.get("temperature"), bool) or not isinstance(r.get("temperature"), (int, float)) or r["temperature"] < 0 or not isinstance(r.get("seed"), int) or isinstance(r.get("seed"), bool) \
                or not isinstance(r.get("depth"), int) or isinstance(r.get("depth"), bool) or r["depth"] < 0:
            raise SignatureRefused("a frozen computation records its temperature, seed and depth")
        v = _vec(r.get("vector"), dim)
        dim = len(v)
        by.setdefault(r["status"], []).append(v)
    cent = {s: [sum(col) / len(vs) for col in zip(*vs)] for s, vs in by.items()}
    names = sorted(cent)
    dist = {"%s|%s" % (a, b): round(math.sqrt(sum((x - y) ** 2 for x, y in zip(cent[a], cent[b]))), 4) for i, a in enumerate(names) for b in names[i + 1:]}
    return {"counts": {s: len(vs) for s, vs in by.items()}, "centroids": {s: [round(x, 4) for x in c] for s, c in cent.items()}, "centroid_distances": dist,
            "missing_statuses": [s for s in STATUSES if s not in by]}
