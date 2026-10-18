# STATUS 

## BUILT and tested

- trace
- harmonic
- echo

Tests: 78 tests in 6 files, all passing.

## DESIGNED ONLY (not built)

- Reading real activations out of a model is the caller's job; no model hook is included.
- A semantic (embedding or entailment) judge for echoes is a plug-in point; the built-in comparison is word overlap.

## Release

Source-available under the LICENSE in this folder. Patent pending (U.S. provisional application 64/178,949 and others). The licence text is a draft that has not been reviewed by an attorney.
