"""RED TEAM 2 - trace SDK: the harmonic echo against a lying, crashing or hostile run function."""
import pathlib
import tempfile
import unittest

from vega_custody.dag.dag import Dag
from vega_trace import echo as E


def dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl"], [t / "l.jsonl"])


class A_Contract(unittest.TestCase):
    def test_bad_arguments_are_refused(self):
        for run, vs in ((None, [1, 2]), (lambda v: "x", [1]), (lambda v: "x", []), (lambda v: "x", "ab"), (lambda v: "x", list(range(E.MAX_ECHOES + 1))), (lambda v: 5, [1, 2]), (lambda v: None, [1, 2])):
            with self.assertRaises(E.EchoRefused, msg=repr(vs)):
                E.echo(run, "s", vs)

    def test_a_crashing_run_propagates_and_records_nothing(self):
        d = dag()

        def run(v):
            if v == 2:
                raise RuntimeError("model died")
            return "text"
        with self.assertRaises(RuntimeError):
            E.echo(run, "s", [1, 2, 3], dag=d)
        self.assertEqual(d.content.entries(), [])

    def test_a_crashing_judge_propagates_and_records_nothing(self):
        d = dag()

        def judge(a, b):
            raise ValueError("judge down")
        with self.assertRaises(ValueError):
            E.echo(lambda v: "deploy now", "s", [1, 2], dag=d, judge=judge)
        self.assertEqual(d.content.entries(), [])

    def test_a_judge_answer_other_than_exactly_true_is_not_a_contradiction(self):
        h = E.echo(lambda v: "deploy now", "s", [1, 2], judge=lambda a, b: "yes")
        self.assertEqual(h["record"]["contradictions"], [])
        self.assertEqual(h["verdict"], "STABLE")

    def test_oversized_text_is_refused(self):
        with self.assertRaises(E.EchoRefused):
            E.harmonics(["a" * (E.MAX_CHARS + 1), "b"])


class B_Scoring(unittest.TestCase):
    def test_empty_and_stopword_only_echoes_do_not_look_stable(self):
        h = E.harmonics(["", ""])
        self.assertEqual(h["resonance"], 0.0)
        self.assertNotEqual(h["verdict"], "STABLE")
        self.assertNotEqual(E.harmonics(["the and of", "the and of"])["verdict"], "STABLE")

    def test_padding_cannot_fake_stability(self):
        core = "the migration drops the user table and loses every row permanently"
        pad = " ".join("filler%d" % i for i in range(60))
        h = E.harmonics([core + " " + pad.replace("filler", "alpha"), core + " " + pad.replace("filler", "beta")])
        self.assertLess(h["resonance"], 0.3)
        self.assertEqual(h["verdict"], "UNSTABLE")

    def test_case_and_punctuation_do_not_change_the_result(self):
        self.assertEqual(E.harmonics(["Restart the Pool!", "restart the pool"])["resonance"], 1.0)

    def test_one_dissenting_echo_pulls_resonance_down(self):
        same = "rotate the signing key after the incident review"
        all_same = E.harmonics([same, same, same])["resonance"]
        with_dissent = E.harmonics([same, same, "keep the signing key forever and never rotate"])["resonance"]
        self.assertGreater(all_same, with_dissent)

    def test_pair_keys_cover_every_pair_once(self):
        h = E.harmonics(["a1 b1", "a1 b1", "a1 c1", "d1 e1"])
        self.assertEqual(sorted(h["pairs"]), ["0-1", "0-2", "0-3", "1-2", "1-3", "2-3"])


class C_Record(unittest.TestCase):
    def test_the_record_never_holds_the_echo_text(self):
        d = dag()
        E.echo(lambda v: "secret plan alpha %d" % v, "s", [1, 2], dag=d)
        raw = open(d.content.paths[0], encoding="utf-8").read()
        self.assertNotIn("secret plan", raw)
        self.assertIn("echo_sha256", raw)

    def test_a_credential_in_an_echo_is_hashed_not_stored_and_does_not_break_recording(self):
        d = dag()
        key = "nvapi-" + "A1b2C3d4E5" * 3
        E.echo(lambda v: "the key is " + key, "s", [1, 2], dag=d)
        self.assertNotIn(key, open(d.content.paths[0], encoding="utf-8").read())

    def test_a_tampered_chain_refuses_the_next_echo_record(self):
        d = dag()
        E.echo(lambda v: "same words here", "s", [1, 2], dag=d)
        with open(d.content.paths[0], "a", encoding="utf-8") as fh:
            fh.write('{"garbage": 1}\n')
        with self.assertRaises(Exception):
            E.echo(lambda v: "same words here", "s", [1, 2], dag=d)


if __name__ == "__main__":
    unittest.main()
