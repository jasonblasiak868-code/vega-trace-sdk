# vega-trace-sdk

![vega-trace-sdk](assets/tile.svg)

Mapping, metamorphosis and breathing traces kept as hashes on a custody chain, and the harmonic echo test of how settled a reasoning step is.

> **Licensing.** Source-available, not open source. Free for personal use; free for registered small businesses (under US$1M revenue and valuation); everyone else needs a commercial license (see LICENSE; for a commercial license write to jasonblasiak.ai.mail@gmail.com). Patent pending. Draft licence text, not yet reviewed by an attorney.

Package: `vega_trace` (src layout). Depends on: vega-custody-sdk.

## Modules

| Module | What it does |
|---|---|
| `trace` | Three per-step traces as digests and scalars only: where a step went, what it became layer by layer, and how it breathed (timing seen from outside). Raw vectors are refused. |
| `harmonic` | The harmonic echo, from the owner's own description (2026-09-30): turn a trace into a melody so a clean pass sounds clear and a drifting or stuck pass sounds dissonant; scored CLEAR, MUDDY, DISSONANT or STUCK, with a deterministic WAV. The note mapping is a convention and the idea that clarity tracks correctness is a hypothesis, tested by compare_clarity, not a finding. |
| `echo` | A separate repeat-run stability test this repo added (NOT the owner's harmonic echo): run the same step several times, report what never moves, what varies, a resonance score and an outlier. |

## What it does NOT do (read this)

- A stable echo is not a correct answer: all echoes can agree and be wrong.
- Breathing traces show timing, not content, and are sensitive to the machine's load.

## Status

See STATUS.md. Tests: 78 tests in 6 files, all passing.  See SECURITY.md for the threat model.

## Run the tests

Put `src` of this repo and of the repos it depends on on PYTHONPATH, then run each file in `tests/`.
