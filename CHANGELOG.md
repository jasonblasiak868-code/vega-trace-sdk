# Changelog

## 2026-10-21: fixes found by a line-by-line source read

Found by reading the six modules against the README and SPEC, then reproducing each suspected defect before fixing it. Each fix has a regression test in `tests/test_findings_20261021.py` that failed before the fix, and each fix was checked by undoing it and confirming a test fails.

### Fixed
- **A stamp could be made after the run and still be graded.** `grade()` only checked that the stamp matched its own hash, so a forged stamp with a recomputed hash was graded as a HIT. `grade()` now takes `dag`; with it, the stamp must be on the chain (found by run id and hash) or the grade is refused. Without it the result says `stamp_on_chain: false` and that the chain was not checked.
- **A run could be stamped twice**, so expectations could be rewritten after the results were seen. A second stamp for the same run id is refused. (The check covers one process; another process writing the same chain at the same moment is not prevented by it.)
- **A large vector gave an infinite norm** in the record (a vector holding 1e200), and large timings gave `inf` and `nan` statistics. Norms now use `math.hypot`; a vector whose true length is not a finite number is refused; a timing above 1e18 ns is refused.
- **`melody` crashed with `OverflowError`** on an extreme ratio between norms (for example 5e-324 against 1.0). The ratio is now a difference of logs and is clamped as before.
- **The signature and `calibrate` crashed with `OverflowError`** on very large numbers, and a very large value made the running spread infinite. Telemetry numbers above 1e100 are refused.
- **`compare` said "identical" when the layers' inputs differed** but the outputs matched. It now also reports `differ_in` and is identical only when both match. It refuses echo records and records it cannot read, where it raised `KeyError` before.
- **`score`, `render_wav`, `cue`, `grade` and `commit_trace` raised `KeyError`, `ValueError`, `AttributeError` or `TypeError` on malformed input.** Each now refuses with its own refusal type. `render_wav` also checks the frequency and writes the file beside the target and moves it into place, so a failure never leaves half a file.
- **The observe ledger had no memory cap.** Five observations of 4,000 heads kept all 20,000 in memory forever. It now holds at most 2,000,000 head magnitudes and refuses an observation past that before anything is written to the chain.
- A region text in a stamp had no length limit; it is now at most 2,000 characters.

### Changed
- `grade()` has a new optional argument `dag` and its result has two new fields, `stamp_on_chain` and `stamp_note`.
- `compare()` for metamorphosis records has a new field `differ_in`, and `identical` now also requires no input differences.
- `commit_trace` refuses a trace that is not strict canonical JSON (for example one holding a set or `nan`) with `NnrRefused`.
- The reference signature now holds a lock. A race was suspected and not reproduced (24,000 concurrent additions came out exact), so this is defence in depth and not a fix for an observed fault.

### Not changed
- `echo.echo` lets an exception raised by the caller's `run` or `judge` function propagate; that is the caller's code.
- A cosine similarity of 0.0 is returned both for orthogonal profiles and for an all-zero profile.
