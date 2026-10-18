"""Tests for the harmonic echo (the audible trace) and its attacks."""
import math
import os
import pathlib
import tempfile
import unittest
import wave

from vega_custody.dag.dag import Dag
from vega_trace import harmonic as H
from vega_trace import trace as T


def rec(rows):
    return T.metamorphosis_record("s1", [{"layer": i, "in": a, "out": b} for i, (a, b) in enumerate(rows)])


def by_offsets(offsets):
    """A record whose layer i has pitch offset offsets[i] semitones (each layer starts from size 1)."""
    return rec([([1.0, 0.0], [2 ** (o / 12), 0.5]) for o in offsets])


def clean():
    return by_offsets([0, 4, 7, 12, 7, 4, 0, 5])             # steps of a third, a fourth, a fifth: consonant


class Melody(unittest.TestCase):
    def test_pitch_follows_the_change_in_size(self):
        n = H.melody(rec([([1.0], [2.0]), ([2.0], [1.0])]))
        self.assertEqual([x["semitones"] for x in n], [12, -12])
        self.assertAlmostEqual(n[0]["hz"], 440.0, places=2)

    def test_an_unchanged_layer_is_stuck(self):
        n = H.melody(rec([([1.0, 2.0], [1.0, 2.0])]))
        self.assertTrue(n[0]["stuck"])

    def test_a_clean_run_is_clear_and_a_flat_run_is_stuck(self):
        self.assertEqual(H.score(H.melody(clean()))["verdict"], "CLEAR")
        flat = rec([([1.0, 2.0], [1.0, 2.0])] * 8)
        s = H.score(H.melody(flat))
        self.assertEqual(s["stuck_share"], 1.0)
        self.assertNotEqual(s["verdict"], "CLEAR")

    def test_jumps_by_seconds_and_tritones_are_dissonant(self):
        s = H.score(H.melody(by_offsets([0, 1, 0, 6, 0, 1, 0, 6])))                  # intervals of 1 and 6 semitones
        self.assertGreater(s["dissonance"], 0.5)
        self.assertNotEqual(s["verdict"], "CLEAR")


class Wav(unittest.TestCase):
    def test_wav_is_valid_deterministic_and_the_right_length(self):
        d = pathlib.Path(tempfile.mkdtemp())
        n = H.melody(clean())
        a, b = d / "a.wav", d / "b.wav"
        H.render_wav(n, a)
        H.render_wav(n, b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with wave.open(str(a)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, H.SAMPLE_RATE))
            self.assertEqual(w.getnframes(), len(n) * int(H.SAMPLE_RATE * H.NOTE_SECONDS))


class Hypothesis(unittest.TestCase):
    def test_comparison_reports_counts_and_refuses_to_overclaim(self):
        r = H.compare_clarity([0.9, 0.8], [0.4, 0.3])
        self.assertAlmostEqual(r["difference"], 0.5)
        self.assertIn("not evidence", r["note"])
        self.assertIsNone(H.compare_clarity([], [0.5])["difference"])

    def test_the_chain_record_holds_the_verdict_and_a_melody_digest_only(self):
        t = pathlib.Path(tempfile.mkdtemp())
        dag = Dag([t / "c.jsonl"], [t / "l.jsonl"])
        T.record(dag, H.echo_record("s1", H.melody(clean())))
        raw = (t / "c.jsonl").read_text(encoding="utf-8")
        self.assertIn("melody_sha256", raw)
        self.assertNotIn("440", raw)


class Attacks(unittest.TestCase):
    def test_bad_records_are_refused(self):
        good = {"trace": "metamorphosis", "step": "s", "layers": [{"layer": 0, "norm_in": 1.0, "norm_out": 2.0, "changed": True}]}
        for bad in (None, {}, [], "x", {"trace": "mapping", "layers": []}, {"trace": "metamorphosis", "layers": "x"}, {"trace": "metamorphosis", "layers": []},
                    {"trace": "metamorphosis", "layers": [{"layer": 0}]}, {"trace": "metamorphosis", "layers": [{"layer": 0, "norm_in": float("nan"), "norm_out": 1.0, "changed": True}]},
                    {"trace": "metamorphosis", "layers": [{"layer": 0, "norm_in": -1.0, "norm_out": 1.0, "changed": True}]}, {"trace": "metamorphosis", "layers": [{"layer": 0, "norm_in": 1.0, "norm_out": 1.0, "changed": 1}]},
                    {"trace": "metamorphosis", "layers": [{"layer": 0, "norm_in": float("inf"), "norm_out": 1.0, "changed": True}]}):
            with self.assertRaises(H.HarmonicRefused, msg=repr(bad)):
                H.melody(bad)
        self.assertEqual(len(H.melody(good)), 1)

    def test_zero_norms_do_not_crash_or_make_infinite_pitch(self):
        n = H.melody({"trace": "metamorphosis", "step": "s", "layers": [{"layer": 0, "norm_in": 0.0, "norm_out": 5.0, "changed": True}, {"layer": 1, "norm_in": 5.0, "norm_out": 0.0, "changed": True},
                                                                         {"layer": 2, "norm_in": 0.0, "norm_out": 0.0, "changed": False}]})
        self.assertEqual([x["semitones"] for x in n], [24, -24, 0])

    def test_extreme_ratios_are_clamped(self):
        n = H.melody(rec([([1e-9], [1e9]), ([1e9], [1e-9])]))
        self.assertEqual([x["semitones"] for x in n], [24, -24])

    def test_too_many_layers_cannot_be_rendered_and_scoring_needs_notes(self):
        with self.assertRaises(H.HarmonicRefused):
            H.render_wav([{"hz": 220.0, "stuck": False}] * (H.MAX_LAYERS_RENDERED + 1), os.path.join(tempfile.mkdtemp(), "x.wav"))
        for bad in (None, [], "x"):
            with self.assertRaises(H.HarmonicRefused):
                H.score(bad)
            with self.assertRaises(H.HarmonicRefused):
                H.render_wav(bad, os.path.join(tempfile.mkdtemp(), "y.wav"))

    def test_bad_clarity_lists_are_refused(self):
        for good, bad in (([2.0], [0.1]), ([True], [0.1]), (["0.5"], [0.1]), (None, [0.1]), ([0.5], [float("nan")])):
            with self.assertRaises(H.HarmonicRefused, msg=repr((good, bad))):
                H.compare_clarity(good, bad)

    def test_scores_are_bounded(self):
        s = H.score([{"layer": 0, "semitones": 0, "hz": 220.0, "stuck": True}])
        self.assertTrue(0.0 <= s["clarity"] <= 1.0)

    def test_a_step_id_in_the_record_must_be_plain(self):
        with self.assertRaises(T.TraceRefused):
            H.echo_record("not plain!", H.melody(clean()))


if __name__ == "__main__":
    unittest.main()
