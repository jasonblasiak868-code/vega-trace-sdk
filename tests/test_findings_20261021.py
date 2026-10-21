"""Findings from a line-by-line source read, 2026-10-21. Each test failed before its fix."""
import hashlib
import json
import math
import pathlib
import tempfile
import unittest

from vega_custody.dag.dag import Dag
from vega_trace import harmonic as H
from vega_trace import nnr
from vega_trace import signature as SG
from vega_trace import tiers as TI
from vega_trace import trace as T


def new_dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl"], [t / "l.jsonl"])


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


class A_NumbersThatOverflow(unittest.TestCase):
    def test_a_large_vector_has_a_finite_norm_in_a_record_that_is_strict_json(self):
        rec = T.metamorphosis_record("s1", [{"layer": 0, "in": [1e200], "out": [1.0]}])
        self.assertEqual(rec["layers"][0]["norm_in"], 1e200)
        json.dumps(rec, allow_nan=False)

    def test_a_vector_whose_length_cannot_be_held_is_refused(self):
        with self.assertRaises(T.TraceRefused):
            T.digest_vector([1.7e308, 1.7e308])

    def test_timings_that_would_overflow_the_statistics_are_refused(self):
        with self.assertRaises(T.TraceRefused):
            T.breathing_record("s1", [1e308, 1e308])
        rec = T.breathing_record("s1", [1e18, 1e18])
        json.dumps(rec, allow_nan=False)

    def test_melody_survives_an_extreme_ratio_between_norms(self):
        for nin, nout, want in ((5e-324, 1.0, 24), (1e-300, 1e300, 24), (1e300, 1e-300, -24)):
            rec = {"trace": "metamorphosis", "layers": [{"layer": 0, "norm_in": nin, "norm_out": nout, "changed": True}]}
            self.assertEqual(H.melody(rec)[0]["semitones"], want, (nin, nout))

    def test_the_signature_refuses_numbers_it_cannot_square(self):
        s = SG.ReferenceSignature("m1")
        with self.assertRaises(SG.SignatureRefused):
            s.add_verified([1e200, 1.0], "FACT", True)
        for i in range(12):
            s.add_verified([float(i % 3), 1.0], "FACT", True)
        with self.assertRaises(SG.SignatureRefused):
            s.asserted_value([1e200, 1.0])
        with self.assertRaises(SG.SignatureRefused):
            SG.calibrate([1e200, 1.0], [2.0, 3.0])

    def test_features_refuses_a_non_numeric_entropy_record(self):
        with self.assertRaises(SG.SignatureRefused):
            SG.features({"kind": "entropy", "mean_bits": "x", "sd_bits": 1, "max_bits": 1, "p90_bits": 1, "high_share": 1})


class B_Compare(unittest.TestCase):
    def test_an_echo_record_is_not_comparable(self):
        e = {"trace": "echo", "step": "s1"}
        with self.assertRaises(T.TraceRefused):
            T.compare(e, e)

    def test_a_malformed_record_is_refused_not_a_crash(self):
        a = {"trace": "mapping", "step": "s1"}
        with self.assertRaises(T.TraceRefused):
            T.compare(a, a)

    def test_different_inputs_with_the_same_output_are_not_identical(self):
        m1 = T.metamorphosis_record("s1", [{"layer": 0, "in": [1.0, 2.0], "out": [3.0]}])
        m2 = T.metamorphosis_record("s1", [{"layer": 0, "in": [9.0, 9.0], "out": [3.0]}])
        got = T.compare(m1, m2)
        self.assertFalse(got["identical"])
        self.assertEqual(got["differ_in"], [0])
        self.assertEqual(got["differ"], [])
        self.assertTrue(T.compare(m1, m1)["identical"])


class B2_RecordAndCompareGuards(unittest.TestCase):
    def test_compare_refuses_a_kind_it_does_not_know_even_when_it_looks_like_a_layer_record(self):
        r = {"trace": "other", "step": "s1", "layers": [{"layer": 0, "in_sha256": "a", "out_sha256": "b"}]}
        with self.assertRaises(T.TraceRefused):
            T.compare(r, r)

    def test_record_refuses_a_credential_shaped_record_before_it_reaches_the_chain(self):
        class Stub:
            def record(self, *a, **k):
                raise AssertionError("the chain must not be reached")
        with self.assertRaises(T.TraceRefused):
            T.record(Stub(), {"trace": "mapping", "step": "s1", "note": "sk-" + "a" * 30})


class C_InputsFromOutside(unittest.TestCase):
    def test_score_refuses_notes_that_are_not_melody_notes(self):
        for bad in ([{"x": 1}], [{"semitones": "a", "stuck": False}], [{"semitones": 1, "stuck": "no"}], ["a"]):
            with self.assertRaises(H.HarmonicRefused, msg=repr(bad)):
                H.score(bad)

    def test_render_wav_refuses_bad_notes_and_leaves_no_file(self):
        d = pathlib.Path(tempfile.mkdtemp())
        for i, bad in enumerate(([{"hz": 220.0}], [{"hz": float("nan"), "stuck": False}], [{"hz": 0, "stuck": False}], [{"hz": float("inf"), "stuck": False}],
                                  [{"hz": 220.0, "stuck": "no"}], ["a"])):
            p = d / ("a%d.wav" % i)
            with self.assertRaises(H.HarmonicRefused, msg=repr(bad)):
                H.render_wav(bad, p)
            self.assertFalse(p.exists())

    def test_cue_refuses_what_is_not_a_telemetry_record(self):
        for bad in (None, "x", [1]):
            with self.assertRaises(TI.TierRefused):
                TI.cue(bad)
        with self.assertRaises(TI.TierRefused):
            TI.cue({"entropy": {"high_share": "x"}})
        self.assertTrue(TI.cue({"entropy": {"high_share": 0.9}})["cue"])


class D_StampsAndCommitments(unittest.TestCase):
    EXP = [{"region": "layer 3 heads", "direction": "up"}]

    def test_a_run_can_be_stamped_once(self):
        d = new_dag()
        nnr.stamp(d, "run1", self.EXP)
        with self.assertRaises(nnr.NnrRefused):
            nnr.stamp(d, "run1", [{"region": "layer 3 heads", "direction": "down"}])
        nnr.stamp(d, "run2", self.EXP)

    def test_grade_refuses_a_malformed_stamp(self):
        for bad in ({"expectations": [{"nope": 1}], "stamp_sha256": "x"}, {"expectations": ["a"], "stamp_sha256": "x"}, {"expectations": [], "stamp_sha256": "x"},
                    {"expectations": [{"region": "r", "direction": "sideways"}], "stamp_sha256": "x"}):
            with self.assertRaises(nnr.NnrRefused, msg=repr(bad)):
                nnr.grade(bad, {})

    def test_a_forged_stamp_with_a_recomputed_hash_is_caught_by_the_chain(self):
        d = new_dag()
        real = nnr.stamp(d, "run1", self.EXP)
        forged = dict(real)
        forged["expectations"] = [{"region": "layer 3 heads", "direction": "down"}]
        forged["stamp_sha256"] = hashlib.sha256(json.dumps(sorted((e["region"], e["direction"]) for e in forged["expectations"])).encode()).hexdigest()
        with self.assertRaises(nnr.NnrRefused):
            nnr.grade(forged, {"layer 3 heads": -1.0}, dag=d)
        good = nnr.grade(real, {"layer 3 heads": 1.0}, dag=d)
        self.assertIs(good["stamp_on_chain"], True)
        self.assertEqual(good["hits"], 1)

    def test_without_a_chain_the_grade_says_it_did_not_check(self):
        d = new_dag()
        real = nnr.stamp(d, "run1", self.EXP)
        got = nnr.grade(real, {"layer 3 heads": 1.0})
        self.assertIs(got["stamp_on_chain"], False)
        self.assertIn("not checked against the chain", got["stamp_note"])

    def test_a_region_is_bounded(self):
        with self.assertRaises(nnr.NnrRefused):
            nnr.stamp(new_dag(), "run3", [{"region": "x" * 5000, "direction": "up"}])

    def test_commit_trace_refuses_what_it_cannot_canonicalise(self):
        for bad in ({"a": {1, 2}}, {"a": float("nan")}):
            with self.assertRaises(nnr.NnrRefused):
                nnr.commit_trace(bad, b"s" * 16, b"k" * 16)
            self.assertFalse(nnr.open_commitment("0" * 64, bad, b"s" * 16, b"k" * 16))
        c = nnr.commit_trace({"a": 1}, b"s" * 16, b"k" * 16)
        self.assertTrue(nnr.open_commitment(c, {"a": 1}, b"s" * 16, b"k" * 16))

    def test_the_observe_ledger_is_bounded_and_records_nothing_when_full(self):
        d = new_dag()
        led = nnr.ObserveLedger(d)
        old = nnr.MAX_STORED_HEADS
        nnr.MAX_STORED_HEADS = 50
        try:
            prof = {(i, 0): 1.0 for i in range(30)}
            led.observe("s1", "novel", sha("p"), prof, sha("h"))
            before = len(d.content)
            with self.assertRaises(nnr.NnrRefused):
                led.observe("s2", "novel", sha("p"), prof, sha("h"))
            self.assertEqual(len(d.content), before)               # nothing was written to the chain for the refused observation
        finally:
            nnr.MAX_STORED_HEADS = old


if __name__ == "__main__":
    unittest.main()
