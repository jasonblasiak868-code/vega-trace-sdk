"""harmonic.py - the harmonic echo: make a trace audible, so a clean pass sounds clear and a drifting or stuck one sounds dissonant.

SOURCE OF THE IDEA: the owner's words of 2026-09-30 (quoted in COMBINED_PROVISIONAL_20261003.md): tracers on the tokens whose harmonic echoes let you HEAR the parameters hitting; a model tuned
correctly sounds clear and melodic, one that drifts or breaks constraints produces dissonance or a 'stuck noise'; the same tracers can be rendered in 3D.
WHAT THIS FILE DOES: turns a metamorphosis record (digests and norms per layer, see trace.py) into a melody and scores it.
  - pitch: each layer's tone is its change in state size relative to the layer before: a semitone offset of 12 * log2(norm_out / norm_in), clamped to +/- 24, above a base of 220 Hz
  - stuck: a layer whose output digest equals its input digest changed nothing; a run of such layers is the 'stuck noise'
  - dissonance: the share of consecutive intervals that are not consonant (unison, minor and major third, fourth, fifth, minor and major sixth, octave count as consonant)
  - clarity: 1 - 0.6 * dissonance - 0.4 * stuck_share, and a verdict STUCK (half or more of the layers changed nothing), CLEAR (>= 0.7), MUDDY, or DISSONANT (< 0.4)
HONEST LIMITS: the mapping from numbers to notes is a CONVENTION chosen here, not a discovered law. That a clear sound goes with a correct answer is the owner's hypothesis, not a finding:
`compare_clarity` exists to test it on recorded passes (clarity of passes later judged right against passes judged wrong) and reports the difference with the counts, nothing more.
A rendered WAV is deterministic, capped in length, and made only from the record: no raw activations are ever needed or stored."""
import math
import os
import struct
import wave

from vega_trace import trace as T

BASE_HZ = 220.0
CONSONANT = frozenset({0, 3, 4, 5, 7, 8, 9, 12})
MAX_LAYERS_RENDERED = 512
SAMPLE_RATE = 22050
NOTE_SECONDS = 0.15


class HarmonicRefused(ValueError):
    pass


def melody(record):
    """record: a metamorphosis record from trace.metamorphosis_record. Returns [{"layer", "semitones", "hz", "stuck"}] in layer order."""
    if not isinstance(record, dict) or record.get("trace") != "metamorphosis" or not isinstance(record.get("layers"), list):
        raise HarmonicRefused("melody takes a metamorphosis record")
    notes = []
    for row in record["layers"][:MAX_LAYERS_RENDERED]:
        try:
            nin, nout = float(row["norm_in"]), float(row["norm_out"])
            changed = row["changed"]
            layer = row["layer"]
        except (KeyError, TypeError, ValueError):
            raise HarmonicRefused("a layer row needs layer, norm_in, norm_out and changed")
        if isinstance(layer, bool) or not isinstance(layer, int):
            raise HarmonicRefused("a layer row's layer is an integer")
        if changed is not True and changed is not False or not math.isfinite(nin) or not math.isfinite(nout) or nin < 0 or nout < 0:
            raise HarmonicRefused("a layer row holds finite non-negative norms and a boolean changed")
        if nin == 0 or nout == 0:
            semis = 0 if nin == nout else (24 if nout > nin else -24)
        else:
            semis = max(-24, min(24, round(12 * (math.log2(nout) - math.log2(nin)))))      # a difference of logs, so an extreme ratio cannot overflow
        notes.append({"layer": layer, "semitones": semis, "hz": round(BASE_HZ * 2 ** (semis / 12), 3), "stuck": not changed})
    if not notes:
        raise HarmonicRefused("a record with no layers has no sound")
    return notes


def _check_notes(notes, need_hz):
    for n in notes:
        if not isinstance(n, dict) or not isinstance(n.get("stuck"), bool):
            raise HarmonicRefused("a note is a dict from melody() with a boolean stuck")
        if need_hz:
            hz = n.get("hz")
            if isinstance(hz, bool) or not isinstance(hz, (int, float)) or not math.isfinite(hz) or not 20 <= hz <= 20000:
                raise HarmonicRefused("a note's hz is a finite number from 20 to 20000")
        else:
            s = n.get("semitones")
            if isinstance(s, bool) or not isinstance(s, int):
                raise HarmonicRefused("a note's semitones is an integer")


def score(notes):
    if not isinstance(notes, list) or not notes:
        raise HarmonicRefused("score takes the notes from melody()")
    _check_notes(notes, need_hz=False)
    pairs = list(zip(notes, notes[1:]))
    if pairs:
        dissonant = sum(1 for a, b in pairs if abs(a["semitones"] - b["semitones"]) % 12 not in CONSONANT)        # an octave (12, 24) is the same pitch class as a unison
        dissonance = dissonant / len(pairs)
    else:
        dissonance = 0.0
    stuck_share = sum(1 for n in notes if n["stuck"]) / len(notes)
    clarity = max(0.0, min(1.0, 1 - 0.6 * dissonance - 0.4 * stuck_share))
    verdict = "STUCK" if stuck_share >= 0.5 else "CLEAR" if clarity >= 0.7 else "DISSONANT" if clarity < 0.4 else "MUDDY"        # half the layers changing nothing is the 'stuck noise', however consonant
    return {"layers": len(notes), "dissonance": round(dissonance, 4), "stuck_share": round(stuck_share, 4), "clarity": round(clarity, 4), "verdict": verdict}


def render_wav(notes, path):
    """Deterministic sine tones, one per layer, 0.15 s each, 16-bit mono. Refuses more than MAX_LAYERS_RENDERED notes. Returns the number of samples written."""
    if not isinstance(notes, list) or not notes or len(notes) > MAX_LAYERS_RENDERED:
        raise HarmonicRefused("render_wav takes 1..%d notes" % MAX_LAYERS_RENDERED)
    _check_notes(notes, need_hz=True)
    frames = bytearray()
    n_per = int(SAMPLE_RATE * NOTE_SECONDS)
    for n in notes:
        amp = 0.05 if n["stuck"] else 0.4                                       # a stuck layer is a faint flat tone: present, but not music
        hz = float(n["hz"])
        for i in range(n_per):
            env = min(1.0, i / 200, (n_per - i) / 200)
            frames += struct.pack("<h", int(32767 * amp * env * math.sin(2 * math.pi * hz * i / SAMPLE_RATE)))
    part = str(path) + ".part"                                                  # written beside the target and moved into place, so a failure never leaves half a file there
    try:
        with wave.open(part, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(frames))
        os.replace(part, str(path))
    finally:
        if os.path.exists(part):
            os.remove(part)
    return len(frames) // 2


def compare_clarity(good, bad):
    """good, bad: lists of clarity scores (0..1) for passes later judged right and wrong. Reports the means, the difference and the counts. No significance is claimed: with few passes it
    says so."""
    for name, xs in (("good", good), ("bad", bad)):
        if not isinstance(xs, (list, tuple)) or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 <= x <= 1 for x in xs):
            raise HarmonicRefused("%s is a list of clarity scores in 0..1" % name)
    if not good or not bad:
        return {"n_good": len(good), "n_bad": len(bad), "difference": None, "note": "both groups need at least one pass"}
    mg, mb = sum(good) / len(good), sum(bad) / len(bad)
    note = "small samples: this is not evidence either way" if min(len(good), len(bad)) < 20 else "a difference in means only; it does not show clear sound causes or predicts a right answer"
    return {"n_good": len(good), "n_bad": len(bad), "mean_good": round(mg, 4), "mean_bad": round(mb, 4), "difference": round(mg - mb, 4), "note": note}


def echo_record(step_id, notes):
    """The record for the chain: the verdict and counts, plus a digest of the melody, never the activations."""
    import hashlib
    import json
    T._id(step_id, "step_id")
    s = score(notes)
    return {"trace": "echo", "step": step_id, "kind": "harmonic", "n": len(notes), "clarity": s["clarity"], "verdict": s["verdict"], "dissonance": s["dissonance"], "stuck_share": s["stuck_share"],
            "melody_sha256": hashlib.sha256(json.dumps([(n["semitones"], n["stuck"]) for n in notes]).encode()).hexdigest()}
