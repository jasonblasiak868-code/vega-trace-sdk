"""Tests for the tiers, the reference signature and the staged NNR pieces, with their attacks."""
import math
import os
import pathlib
import tempfile
import unittest

from vega_custody.dag.dag import Dag
from vega_trace import nnr, signature as S, tiers as X
from vega_trace import trace as T

H = "ab" * 32


def dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl"], [t / "l.jsonl"]), t


def flat(n):
    return [1.0 / n] * n


class Tiers(unittest.TestCase):
    def test_entropy(self):
        self.assertAlmostEqual(X.entropy_bits([0.5, 0.5]), 1.0)
        self.assertAlmostEqual(X.entropy_bits([1.0]), 0.0)
        self.assertAlmostEqual(X.entropy_bits(flat(8)), 3.0)

    def test_bad_distributions_are_refused(self):
        for bad in ([], [0.5], [0.5, 0.6], [-0.1, 1.1], [float("nan"), 1.0], [True, 0.0], ["0.5", "0.5"], "ab", None, [2.0, -1.0]):
            with self.assertRaises(X.TierRefused, msg=repr(bad)):
                X.entropy_bits(bad)

    def test_text_only_access_never_accepts_internal_data(self):
        self.assertEqual(X.telemetry("text", "s", timings_ns=[1, 2, 3])["tier"], 3)
        for extra in ({"layers": []}, {"per_token_probs": [[1.0]]}, {"consulted": []}):
            with self.assertRaises(X.TierRefused):
                X.telemetry("text", "s", timings_ns=[1, 2], **extra)
        with self.assertRaises(X.TierRefused):
            X.telemetry("text", "s")

    def test_probability_access_takes_no_layer_data(self):
        r = X.telemetry("probabilities", "s", per_token_probs=[flat(4), flat(8)])
        self.assertEqual((r["tier"], r["entropy"]["n"]), (2, 2))
        with self.assertRaises(X.TierRefused):
            X.telemetry("probabilities", "s", per_token_probs=[flat(4)], layers=[])
        with self.assertRaises(X.TierRefused):
            X.telemetry("probabilities", "s")

    def test_weights_access_gives_layer_records(self):
        r = X.telemetry("weights", "s", layers=[{"layer": 0, "in": [1.0], "out": [2.0]}], consulted=[{"layer": 0, "positions": [1, 2]}])
        self.assertEqual((r["tier"], r["metamorphosis"]["trace"], r["mapping"]["trace"]), (1, "metamorphosis", "mapping"))
        with self.assertRaises(X.TierRefused):
            X.telemetry("weights", "s")
        with self.assertRaises(X.TierRefused):
            X.telemetry("weights", "s", layers=[], junk=1)

    def test_unknown_access_and_bad_step_ids(self):
        for a in ("root", "", None, "TEXT"):
            with self.assertRaises(X.TierRefused):
                X.telemetry(a, "s", timings_ns=[1, 2])
        with self.assertRaises(T.TraceRefused):
            X.telemetry("text", "bad id!", timings_ns=[1, 2])

    def test_a_cue_is_advice_only(self):
        r = X.telemetry("probabilities", "s", per_token_probs=[flat(64)] * 4)
        c = X.cue(r)
        self.assertTrue(c["cue"])
        self.assertFalse(c["grants_authority"])
        self.assertFalse(X.cue(X.telemetry("probabilities", "s", per_token_probs=[[1.0]] * 4))["cue"])
        for bad in (dict(high_share=-1), dict(cv=True), dict(high_share="x")):
            with self.assertRaises(X.TierRefused):
                X.cue(r, **bad)

    def test_size_limits(self):
        with self.assertRaises(X.TierRefused):
            X.tier2_record("s", [])
        with self.assertRaises(X.TierRefused):
            X.tier2_record("s", "x")


class Signature(unittest.TestCase):
    def sig(self, n=12):
        s = S.ReferenceSignature("m1")
        for i in range(n):
            s.add_verified([1.0 + 0.01 * (i % 3), 0.2, 2.0, 1.5, 0.1], "FACT", True)
        return s

    def test_only_committed_fact_enters_the_signature(self):
        s = S.ReferenceSignature("m1")
        for grade, committed in (("SINGLE_SOURCE", True), ("FACT", False), ("FACT", 1), ("fact", True), (None, True), ("FACT", None)):
            with self.assertRaises(S.SignatureRefused, msg=repr((grade, committed))):
                s.add_verified([1.0], grade, committed)
        self.assertEqual(s.n, 0)

    def test_no_value_without_a_basis(self):
        s = self.sig(5)
        self.assertIsNone(s.asserted_value([1.0, 0.2, 2.0, 1.5, 0.1]))

    def test_distance_grows_as_telemetry_moves_away(self):
        s = self.sig()
        near = s.asserted_value([1.01, 0.2, 2.0, 1.5, 0.1])
        far = s.asserted_value([5.0, 3.0, 9.0, 8.0, 0.9])
        self.assertLess(near, far)

    def test_vectors_are_checked(self):
        s = self.sig()
        for bad in ([], [1.0], ["1"] * 5, [float("nan")] * 5, [True] * 5, None, "abcde", [1.0] * 100):
            with self.assertRaises(S.SignatureRefused, msg=repr(bad)):
                s.asserted_value(bad)
        with self.assertRaises(S.SignatureRefused):
            s.add_verified([1.0, 2.0], "FACT", True)                     # wrong length for this signature

    def test_calibration_reports_counts_and_does_not_overclaim(self):
        r = S.calibrate([1.0, 1.2, 0.9, 1.1], [3.0, 3.5, 2.8, 3.1])
        self.assertTrue(r["separated"])
        self.assertIn("small samples", r["note"])
        self.assertIsNone(S.calibrate([1.0], [3.0, 4.0])["difference"])
        for bad in (([-1.0, 1.0], [1.0, 2.0]), ([True, 1.0], [1.0, 2.0]), (None, [1.0]), ([float("nan"), 1.0], [1.0, 2.0])):
            with self.assertRaises(S.SignatureRefused):
                S.calibrate(*bad)

    def test_features_need_an_entropy_record(self):
        rec = X.tier2_record("s", [flat(4), flat(8)])
        self.assertEqual(len(S.features(rec)), 5)
        for bad in ({}, None, {"kind": "entropy"}, {"kind": "timing"}):
            with self.assertRaises(S.SignatureRefused):
                S.features(bad)

    def test_atlas(self):
        def rec(status, v):
            return {"status": status, "vector": v, "model_weight_sha256": H, "temperature": 0.0, "seed": 1, "depth": 3, "output_sha256": H}
        a = S.atlas([rec("definitional", [1.0, 1.0]), rec("definitional", [1.2, 1.0]), rec("falsehood", [4.0, 3.0])])
        self.assertEqual(a["counts"], {"definitional": 2, "falsehood": 1})
        self.assertIn("disputed", a["missing_statuses"])
        self.assertGreater(a["centroid_distances"]["definitional|falsehood"], 2.0)
        for bad in ([], None, [rec("rumour", [1.0])], [dict(rec("derived", [1.0]), seed=True)], [dict(rec("derived", [1.0]), model_weight_sha256="zz")], [dict(rec("derived", [1.0]), temperature=-1)],
                    [rec("derived", [1.0]), rec("derived", [1.0, 2.0])]):
            with self.assertRaises(S.SignatureRefused, msg=repr(bad)[:60]):
                S.atlas(bad)


class Nnr(unittest.TestCase):
    def prof(self, **kw):
        base = {(0, 7): 5.0, (3, 3): 2.0, (10, 6): 9.0}
        base.update({(int(k.split("_")[0]), int(k.split("_")[1])): v for k, v in kw.items()})
        return base

    def test_observation_is_recorded_with_a_digest_and_the_capsule_head(self):
        d, t = dag()
        led = nnr.ObserveLedger(d)
        led.observe("s1", "cache", H, self.prof(), "cd" * 32)
        raw = (t / "c.jsonl").read_text(encoding="utf-8")
        self.assertIn("body_sha256", raw)
        self.assertIn("capsule_head", raw)

    def test_identical_repeats_have_zero_variance_and_different_ones_do_not(self):
        d, _ = dag()
        led = nnr.ObserveLedger(d)
        for _ in range(3):
            led.observe("s1", "cache", H, self.prof(), "cd" * 32)
        self.assertEqual(led.determinism("cache", H), 0.0)
        led.observe("s1", "cache", H, self.prof(**{"10_6": 20.0}), "cd" * 32)
        self.assertGreater(led.determinism("cache", H), 0.0)
        self.assertIsNone(led.determinism("novel", H))

    def test_cumulative_brightness_and_class_similarity(self):
        d, _ = dag()
        led = nnr.ObserveLedger(d)
        for _ in range(3):
            led.observe("s1", "computational", "11" * 32, self.prof(), "cd" * 32)
        led.observe("s2", "novel", "22" * 32, {(0, 7): 1.0, (3, 3): 8.0}, "cd" * 32)
        self.assertEqual(led.brightest(1)[0][:2], [10, 6])
        self.assertIn("computational|novel", led.class_similarity())

    def test_bad_observations_are_refused(self):
        d, _ = dag()
        led = nnr.ObserveLedger(d)
        for args in (("s1", "weird", H, self.prof(), H), ("s1", "cache", "x", self.prof(), H), ("s1", "cache", H, self.prof(), "x"), ("s1", "cache", H, {}, H), ("s1", "cache", H, {"a": 1.0}, H),
                     ("s1", "cache", H, {(0, 0): -1.0}, H), ("s1", "cache", H, {(0, 0): float("nan")}, H), ("s1", "cache", H, {(True, 0): 1.0}, H), ("bad id", "cache", H, self.prof(), H), ("s1", "cache", H, None, H)):
            with self.assertRaises((nnr.NnrRefused, T.TraceRefused), msg=repr(args)[:50]):
                led.observe(*args)

    def test_stamped_expectations_are_graded_and_misses_are_kept(self):
        d, _ = dag()
        s = nnr.stamp(d, "run1", [{"region": "L3", "direction": "up"}, {"region": "L0H7", "direction": "up"}, {"region": "L9", "direction": "none"}])
        g = nnr.grade(s, {"L3": 0.02, "L0H7": -0.01}, tolerance=0.005)
        self.assertEqual((g["hits"], g["misses"]), (1, 2))
        s["expectations"][0]["direction"] = "down"                       # altered after stamping
        with self.assertRaises(nnr.NnrRefused):
            nnr.grade(s, {"L3": 0.02})

    def test_bad_stamps_are_refused(self):
        d, _ = dag()
        for bad in ([], None, [{"region": "a"}], [{"region": "a", "direction": "sideways"}], [{"region": "", "direction": "up"}], [{"region": "a", "direction": "up"}, {"region": "a", "direction": "down"}],
                    [{"region": "a", "direction": "up", "extra": 1}], "x"):
            with self.assertRaises(nnr.NnrRefused, msg=repr(bad)):
                nnr.stamp(d, "run1", bad)

    def test_commitment_opens_only_with_the_right_trace_salt_and_key(self):
        rec = {"trace": "mapping", "step": "s", "layers": []}
        salt, key = b"s" * 16, b"k" * 16
        c = nnr.commit_trace(rec, salt, key)
        self.assertTrue(nnr.open_commitment(c, rec, salt, key))
        self.assertFalse(nnr.open_commitment(c, dict(rec, step="t"), salt, key))
        self.assertFalse(nnr.open_commitment(c, rec, b"x" * 16, key))
        self.assertFalse(nnr.open_commitment(c, rec, salt, b"y" * 16))
        self.assertFalse(nnr.open_commitment(None, rec, salt, key))
        self.assertNotEqual(c, nnr.commit_trace(rec, b"t" * 16, key))     # a fresh salt hides a repeated trace
        for bad in (dict(trace_record=None, salt=salt, key=key), dict(trace_record=rec, salt=b"short", key=key), dict(trace_record=rec, salt=salt, key=b"short"), dict(trace_record=rec, salt="text" * 8, key=key)):
            with self.assertRaises(nnr.NnrRefused):
                nnr.commit_trace(**bad)

    def test_the_zero_knowledge_proof_is_not_built_and_says_so(self):
        with self.assertRaises(nnr.ProofUnavailable):
            nnr.prove_derivation({"trace": 1})


if __name__ == "__main__":
    unittest.main()
