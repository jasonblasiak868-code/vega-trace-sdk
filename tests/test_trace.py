"""Functional tests: the three traces and the harmonic echo."""
import pathlib
import tempfile
import unittest

from vega_custody.dag.dag import Dag
from vega_trace import echo as E
from vega_trace import trace as T


def dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl"], [t / "l.jsonl"])


class Traces(unittest.TestCase):
    def test_mapping_is_canonical(self):
        a = T.mapping_record("s1", [{"layer": 2, "positions": [5, 1, 3]}, {"layer": 1, "positions": [0]}])
        b = T.mapping_record("s1", [{"layer": 1, "positions": [0]}, {"layer": 2, "positions": [3, 5, 1, 1]}])
        self.assertEqual(a, b)
        self.assertTrue(T.compare(a, b)["identical"])

    def test_metamorphosis_keeps_digests_not_vectors(self):
        r = T.metamorphosis_record("s1", [{"layer": 0, "in": [1.0, 2.0], "out": [1.0, 2.5]}, {"layer": 1, "in": [1.0, 1.0], "out": [1.0, 1.0]}])
        self.assertTrue(r["layers"][0]["changed"])
        self.assertFalse(r["layers"][1]["changed"])
        self.assertNotIn("2.5", str(r))

    def test_vector_digest_survives_float_noise_below_the_precision(self):
        self.assertEqual(T.digest_vector([1.0, 2.0])[0], T.digest_vector([1.0000000001, 1.9999999999])[0])
        self.assertNotEqual(T.digest_vector([1.0, 2.0])[0], T.digest_vector([1.0, 2.001])[0])

    def test_breathing_statistics(self):
        r = T.breathing_record("s1", [100, 110, 90, 105, 95])
        self.assertEqual(r["n"], 5)
        self.assertAlmostEqual(r["mean_ns"], 100.0)
        self.assertEqual(r["min_ns"], 90)

    def test_records_land_on_the_chain(self):
        d = dag()
        T.record(d, T.breathing_record("s1", [1, 2, 3]))
        T.record(d, T.mapping_record("s1", [{"layer": 0, "positions": [1]}]))
        self.assertEqual([e["kind"] for e in d.content.entries()], ["TRACE_BREATHING", "TRACE_MAPPING"])
        self.assertTrue(d.verify())

    def test_compare_finds_the_layer_that_changed(self):
        a = T.metamorphosis_record("s", [{"layer": 0, "in": [1], "out": [2]}, {"layer": 1, "in": [2], "out": [3]}])
        b = T.metamorphosis_record("s", [{"layer": 0, "in": [1], "out": [2]}, {"layer": 1, "in": [2], "out": [9]}])
        self.assertEqual(T.compare(a, b)["differ"], [1])


class Echoes(unittest.TestCase):
    def test_identical_echoes_are_stable(self):
        h = E.harmonics(["the cache must be cleared before deploy", "the cache must be cleared before deploy"])
        self.assertEqual(h["resonance"], 1.0)
        self.assertEqual(h["verdict"], "STABLE")

    def test_unrelated_echoes_are_unstable(self):
        h = E.harmonics(["delete the old database tonight", "photosynthesis converts sunlight into sugar"])
        self.assertEqual(h["verdict"], "UNSTABLE")

    def test_an_outlier_is_named(self):
        same = "restart the worker pool after changing the queue limit"
        h = E.harmonics([same, same + " carefully", same, "bananas ripen faster near apples in warm rooms"])
        self.assertEqual(h["outlier"], 3)

    def test_echo_runs_the_function_once_per_variation_and_records_hashes_only(self):
        d = dag()
        calls = []

        def run(v):
            calls.append(v)
            return "answer one two three " + ("extra" if v == 2 else "")
        h = E.echo(run, "step-1", [1, 2, 3], dag=d)
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(len(h["record"]["echo_sha256"]), 3)
        with open(d.content.paths[0] if hasattr(d.content, "paths") else d.content._paths[0], encoding="utf-8") as fh:
            self.assertNotIn("answer one two", fh.read())

    def test_a_contradiction_forces_unstable(self):
        h = E.echo(lambda v: "deploy now" if v else "deploy now", "s", [0, 1], judge=lambda a, b: True)
        self.assertEqual(h["verdict"], "UNSTABLE")


if __name__ == "__main__":
    unittest.main()
