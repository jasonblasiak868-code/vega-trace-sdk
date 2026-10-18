"""echo.py - REPEAT-RUN STABILITY: ask the same governed step several times and read what stays and what moves.

NOT the owner's 'harmonic echo'. That term (owner's words, 2026-09-30) means making tracers AUDIBLE so a clean pass sounds clear and a drifting or stuck one sounds dissonant: see harmonic.py.
This file is a separate, complementary test that this repo added: a step is run N times under controlled variation. Each run is an echo of the others. Across the echoes:
  fundamental   the words every echo contains (the part that does not move: the common stasis)
  overtones     words only some echoes contain (the part that varies)
  resonance     fundamental / all words seen, 0..1: how much of what was said is shared by every echo
  pairs         each pair's word overlap, so one outlier echo is visible
  verdict       STABLE (resonance >= 0.6), MIXED, or UNSTABLE (< 0.3)
A step that echoes UNSTABLE is one the reasoning is not settled on, however confident any single run sounded.
The SDK never calls a model: the caller passes a function (run(variation) -> text). It records scores and hashes, not the echoes' text."""
import hashlib
import itertools
import re

from vega_trace import trace as T

_WORD = re.compile(r"[a-z0-9']+")
MAX_ECHOES = 64
MAX_CHARS = 1 << 20
STOP = frozenset("a an the and or of to in is it that this for on with as be are was were by at from".split())


class EchoRefused(ValueError):
    pass


def words(text):
    return {w for w in _WORD.findall(text.casefold()) if w not in STOP and len(w) > 1}


def harmonics(texts):
    if not isinstance(texts, (list, tuple)) or not 2 <= len(texts) <= MAX_ECHOES or any(not isinstance(t, str) or len(t) > MAX_CHARS for t in texts):
        raise EchoRefused("harmonics needs 2..%d texts of text, each under %d characters" % (MAX_ECHOES, MAX_CHARS))
    sets = [words(t) for t in texts]
    union = set().union(*sets)
    core = set.intersection(*sets)
    resonance = (len(core) / len(union)) if union else 0.0
    pairs = {}
    for i, j in itertools.combinations(range(len(sets)), 2):
        u = sets[i] | sets[j]
        pairs["%d-%d" % (i, j)] = round(len(sets[i] & sets[j]) / len(u), 4) if u else 0.0
    outlier = None
    if len(sets) >= 3:
        mean_by = {i: sum(v for k, v in pairs.items() if str(i) in k.split("-")) / (len(sets) - 1) for i in range(len(sets))}
        worst = min(mean_by, key=mean_by.get)
        if mean_by[worst] < 0.8 * (sum(mean_by.values()) / len(mean_by)):
            outlier = worst
    verdict = "STABLE" if resonance >= 0.6 else "UNSTABLE" if resonance < 0.3 else "MIXED"
    return {"n": len(texts), "fundamental": sorted(core), "overtones": sorted(union - core), "resonance": round(resonance, 4), "pairs": pairs, "outlier": outlier, "verdict": verdict}


def echo(run, step_id, variations, dag=None, judge=None):
    """run(variation) -> text, called once per variation (the caller decides what a variation is: a seed, a paraphrase, a temperature). judge(text_a, text_b) -> True if they
    CONTRADICT (optional; any contradiction turns the verdict UNSTABLE). Returns the harmonics plus the echo hashes; records them on the chain when dag is given."""
    T._id(step_id, "step_id")
    if not callable(run):
        raise EchoRefused("run must be a function")
    if not isinstance(variations, (list, tuple)) or not 2 <= len(variations) <= MAX_ECHOES:
        raise EchoRefused("variations is a list of 2..%d" % MAX_ECHOES)
    texts = []
    for v in variations:
        t = run(v)
        if not isinstance(t, str):
            raise EchoRefused("run must return text")
        texts.append(t)
    h = harmonics(texts)
    contradictions = []
    if judge is not None:
        for i, j in itertools.combinations(range(len(texts)), 2):
            if judge(texts[i], texts[j]) is True:
                contradictions.append([i, j])
        if contradictions:
            h["verdict"] = "UNSTABLE"
    rec = {"trace": "echo", "step": step_id, "n": h["n"], "resonance": h["resonance"], "verdict": h["verdict"], "fundamental_n": len(h["fundamental"]), "overtones_n": len(h["overtones"]),
           "outlier": h["outlier"], "contradictions": contradictions, "echo_sha256": [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]}
    if dag is not None:
        T.record(dag, rec)
    h["record"] = rec
    return h
