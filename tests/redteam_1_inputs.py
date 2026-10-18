"""RED TEAM 1 - trace SDK: hostile and malformed input must be refused, never stored, never crash the caller."""
import math
import pathlib
import tempfile
import unittest

from vega_custody.dag.dag import Dag
from vega_trace import trace as T


def dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl", ], [t / "l.jsonl"])


class A_Vectors(unittest.TestCase):
    def test_non_finite_and_non_numeric_elements_are_refused(self):
        for bad in ([float("nan")], [float("inf")], [-math.inf], ["1"], [None], [True], [[1]], [{"a": 1}], "123", b"123", 5, None):
            with self.assertRaises(T.TraceRefused, msg=repr(bad)):
                T.digest_vector(bad)

    def test_negative_zero_and_zero_hash_the_same(self):
        self.assertEqual(T.digest_vector([0.0, 1.0])[0], T.digest_vector([-0.0, 1.0])[0])

    def test_a_huge_generator_is_cut_off_not_consumed(self):
        def gen():
            for _ in range(1500000):
                yield 1.0
        with self.assertRaises(T.TraceRefused):
            T.digest_vector(gen())


class B_Shapes(unittest.TestCase):
    def test_step_ids_must_be_plain(self):
        for bad in ("", " ", "a b", "a/b", "../x", "x" * 200, "аbc", "a\nb", None, 5, "sk-" + "a" * 30 + "x y"):
            with self.assertRaises(T.TraceRefused, msg=repr(bad)):
                T.mapping_record(bad, [])

    def test_extra_keys_duplicates_and_wrong_types_are_refused(self):
        for bad in ([{"layer": 1, "positions": [1], "extra": 1}], [{"layer": 1}], [{"positions": [1]}], [{"layer": -1, "positions": []}], [{"layer": True, "positions": []}],
                    [{"layer": 1.5, "positions": []}], [{"layer": 1, "positions": "12"}], [{"layer": 1, "positions": [1.5]}], [{"layer": 1, "positions": [-1]}],
                    [{"layer": 1, "positions": []}, {"layer": 1, "positions": []}], "x", 5, [5]):
            with self.assertRaises(T.TraceRefused, msg=repr(bad)):
                T.mapping_record("s", bad)

    def test_size_limits(self):
        with self.assertRaises(T.TraceRefused):
            T.mapping_record("s", [{"layer": i, "positions": []} for i in range(T.MAX_LAYERS + 1)])
        with self.assertRaises(T.TraceRefused):
            T.mapping_record("s", [{"layer": 0, "positions": list(range(T.MAX_POSITIONS + 1))}])
        with self.assertRaises(T.TraceRefused):
            T.breathing_record("s", [1.0] * (T.MAX_TIMINGS + 1))

    def test_timings_must_be_sane(self):
        for bad in ([1], [], [-1, 2], [float("nan"), 1], ["1", "2"], [True, False], None, "12"):
            with self.assertRaises(T.TraceRefused, msg=repr(bad)):
                T.breathing_record("s", bad)

    def test_constant_timings_have_zero_spread(self):
        r = T.breathing_record("s", [5, 5, 5])
        self.assertEqual((r["sd_ns"], r["cv"]), (0.0, 0.0))
        self.assertEqual(T.breathing_record("s", [0, 0])["cv"], 0.0)


class C_Recording(unittest.TestCase):
    def test_only_trace_records_are_recorded(self):
        d = dag()
        for bad in (None, {}, {"trace": "other"}, "x", {"trace": "mapping", "note": "sk-" + "A1b2C3d4" * 4}):
            with self.assertRaises(T.TraceRefused, msg=repr(bad)):
                T.record(d, bad)
        self.assertEqual(d.content.entries(), [])

    def test_a_credential_cannot_ride_in_a_record_field(self):
        rec = T.mapping_record("s", [])
        rec["layers"] = [{"layer": 0, "n_positions": 0, "positions_sha256": "ghp_" + "a" * 36}]
        with self.assertRaises(T.TraceRefused):
            T.record(dag(), rec)

    def test_compare_refuses_mixed_kinds_and_steps(self):
        a, b = T.mapping_record("s", []), T.mapping_record("t", [])
        with self.assertRaises(T.TraceRefused):
            T.compare(a, b)
        with self.assertRaises(T.TraceRefused):
            T.compare(a, T.breathing_record("s", [1, 2]))

    def test_compare_reports_layers_present_on_one_side_only(self):
        a = T.mapping_record("s", [{"layer": 0, "positions": [1]}, {"layer": 1, "positions": [1]}])
        b = T.mapping_record("s", [{"layer": 0, "positions": [1]}])
        c = T.compare(a, b)
        self.assertEqual(c["only_in_a"], [1])
        self.assertFalse(c["identical"])


if __name__ == "__main__":
    unittest.main()
