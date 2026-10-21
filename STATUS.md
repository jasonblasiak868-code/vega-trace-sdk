# STATUS 

## BUILT and tested

- trace
- harmonic
- echo

Tests: 99 tests in 7 files, all passing. Every fix in `tests/mutations.py` was checked by undoing it and confirming a test fails; two mutants survive and are equivalent (the echo `run must return text` check, which `harmonics` also makes, and the constant-time compare, which is a timing property no unit test can see).

## DESIGNED ONLY (not built)

- Reading real activations out of a model is the caller's job; no model hook is included.
- A semantic (embedding or entailment) judge for echoes is a plug-in point; the built-in comparison is word overlap.

## Release

Source-available under the LICENSE in this folder. Patent pending (U.S. provisional application 64/178,949 and others). The licence text is a draft that has not been reviewed by an attorney.
