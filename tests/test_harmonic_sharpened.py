"""Tests added after the mutation check found harmonic fixes no earlier test noticed."""
import pathlib
import struct
import tempfile
import unittest
import wave

from vega_trace import harmonic as H
from vega_trace import trace as T


def by_offsets(offsets):
    return T.metamorphosis_record("s1", [{"layer": i, "in": [1.0, 0.0], "out": [2 ** (o / 12), 0.5]} for i, o in enumerate(offsets)])


class Sharpened(unittest.TestCase):
    def test_a_huge_change_in_size_is_clamped_to_two_octaves(self):
        rec = T.metamorphosis_record("s", [{"layer": 0, "in": [1.0], "out": [2.0 ** 40]}, {"layer": 1, "in": [2.0 ** 40], "out": [1.0]}])
        self.assertEqual([n["semitones"] for n in H.melody(rec)], [24, -24])

    def test_a_flat_run_is_called_stuck(self):
        flat = T.metamorphosis_record("s", [{"layer": i, "in": [1.0, 2.0], "out": [1.0, 2.0]} for i in range(8)])
        self.assertEqual(H.score(H.melody(flat))["verdict"], "STUCK")

    def test_jumps_of_two_octaves_are_the_same_pitch_class_not_dissonance(self):
        s = H.score(H.melody(by_offsets([-12, 12, -12, 12, -12, 12])))               # intervals of 24 semitones
        self.assertEqual(s["dissonance"], 0.0)

    def test_only_metamorphosis_records_make_a_melody(self):
        mapping_like = {"trace": "mapping", "step": "s", "layers": [{"layer": 0, "norm_in": 1.0, "norm_out": 2.0, "changed": True}]}
        with self.assertRaises(H.HarmonicRefused):
            H.melody(mapping_like)

    def test_a_stuck_layer_is_a_faint_tone(self):
        d = pathlib.Path(tempfile.mkdtemp())
        loud, faint = d / "loud.wav", d / "faint.wav"
        H.render_wav([{"hz": 440.0, "stuck": False}], loud)
        H.render_wav([{"hz": 440.0, "stuck": True}], faint)

        def peak(p):
            with wave.open(str(p)) as w:
                raw = w.readframes(w.getnframes())
            return max(abs(x) for x in struct.unpack("<%dh" % (len(raw) // 2), raw))
        self.assertGreater(peak(loud), 4 * peak(faint))


if __name__ == "__main__":
    unittest.main()
