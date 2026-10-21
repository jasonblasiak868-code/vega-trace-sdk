# vega-trace-sdk — Specification

Spec v1.0 — 2026-10-19 — describes the published reference implementation as tested; where this document and the source disagree, the source wins.

## At a glance

| Item | Value |
|------|-------|
| Version | 0.1.0 |
| Status | Reference implementation; not independently security-reviewed; crypto not expert-reviewed |
| Tests | 99 tests in 7 files, all passing |
| Layer | 10 — observe |
| Dependencies | vega-custody-sdk |

## Table of contents

- [Purpose and scope](#1-purpose-and-scope)
- [Vocabulary](#2-vocabulary)
- [Components](#3-components)
  - [trace.py — the three traces](#31-tracepy--the-three-traces)
  - [harmonic.py — the harmonic echo](#32-harmonicpy--the-harmonic-echo)
  - [echo.py — repeat-run stability echo](#33-echopy--repeat-run-stability-echo)
  - [tiers.py — telemetry by access tier](#34-tierspy--telemetry-by-access-tier)
  - [signature.py — reference signature & calibration](#35-signaturepy--reference-signature--calibration)
  - [nnr.py — staged NNR pieces](#36-nnrpy--staged-nnr-pieces)
- [Guarantees and non-guarantees](#4-guarantees-and-non-guarantees)
- [Failure modes](#5-failure-modes)
- [Dependencies and layer rules](#6-dependencies-and-layer-rules)
- [Conformance](#7-conformance)

## 1. Purpose and scope

This specification covers the vega-trace-sdk package (layer 10, **observe**). It defines the three per-step trace types (mapping, metamorphosis, breathing), the **harmonic echo** scoring, the **repeat-run echo** stability test, telemetry by **access tier**, the **reference signature** with **asserted-value** calibration, and the staged **NNR** pieces (ObserveLedger, stamp/grade, salted commitment). It does not cover: model internals, any model hook, semantic judges for echoes, zero-knowledge proof backends, production hardening, or the Vega umbrella registry wiring.

## 2. Vocabulary

| Term | Definition |
|------|------------|
| **commitment** | A human-signed, single-use note authorizing one exact action; the model never holds the signing key. |
| **gate** | A check that refuses when a valid commitment for the exact action is absent, expired, or already used; fails closed. |
| **trace record** | A dict containing only digests, counts, and scalars; never raw vectors or credential-shaped content. |
| **custody chain** | Append-only, hash-chained ledger (vega-custody-sdk) where every trace record lands as `TRACE_<KIND>`. |
| **mapping trace** | WHERE a step went: per layer, the number of positions consulted and a digest of sorted positions. |
| **metamorphosis trace** | WHAT it became: per layer, input/output digests, dimensions, norms, and a `changed` boolean. |
| **breathing trace** | External timing statistics: n, mean, sd, cv, p95, min, max (no samples stored). |
| **harmonic echo** | The owner's idea (2026-09-30): map metamorphosis norm changes to semitones, score dissonance/stuck/clarity, render deterministic WAV. |
| **repeat-run echo** | This repo's separate stability test: run N times, compute fundamental/overtones/resonance/verdict. |
| **access tier** | What the architecture can see: weights (tier 1), probabilities (tier 2), text only (tier 3). |
| **reference signature** | Running mean of FACT-grade committed telemetry vectors; changes only by committed additions. |
| **asserted value** | RMS z-distance of a new vector from the reference signature (None until 10 verified). |
| **ObserveLedger** | Records head profiles per prompt class with capsule-head pointers and body digests. |
| **stamp/grade** | Expectations hashed and recorded before a run; graded HIT/MISS after; misses are kept. |
| **salted commitment** | HMAC-SHA256 of canonical trace with salt under a key; constant-time verify; fresh salt hides repetition. |

## 3. Components

### 3.1 `trace.py` — the three traces

**Role:** Produce and validate the three trace record types; append them to the custody chain.

**Public interface:**

```python
digest_vector(values, places=6) → (sha256, length, norm)
mapping_record(step_id, consulted) → record dict
metamorphosis_record(step_id, layers) → record dict
breathing_record(step_id, timings_ns) → record dict
record(dag, rec) → custody entry
compare(a, b) → dict with identical, differ, differ_in, only_in_a, only_in_b
TraceRefused exception
```

**Behavior:** Validates every input strictly. `mapping_record` canonicalizes layer order and position sets (sorted unique). `metamorphosis_record` digests in/out vectors, drops them, keeps digests/norms/changed. `breathing_record` computes statistics, drops samples. `record` refuses non-trace kinds and credential-shaped content via custody's `contains_credential`. `compare` refuses mixed kinds or different steps.

**Failure modes:** All invalid inputs raise `TraceRefused`. Chain refusal bubbles up as `TraceRefused`. Fail-closed: nothing is written on validation failure.

**Invariants:**

- Records contain only hashes, counts, scalars — never raw vectors.
- Layer order is canonical (sorted).
- Position lists are deduplicated and sorted.
- Step ids match `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`.
- Digests are stable under float noise below the rounding precision (6 places).

### 3.2 `harmonic.py` — the harmonic echo

**Role:** Convert a metamorphosis record to a melody, score it, render a WAV, and compare clarity groups.

**Public interface:**

```python
melody(record) → list of notes {layer, semitones, hz, stuck}
score(notes) → {layers, dissonance, stuck_share, clarity, verdict}
render_wav(notes, path) → samples written
compare_clarity(good, bad) → {n_good, n_bad, mean_good, mean_bad, difference, note}
echo_record(step_id, notes) → chain record with verdict, clarity, melody_sha256
HarmonicRefused exception
```

**Behavior:** `melody` computes semitones = clamp(12 * (log2(norm_out) - log2(norm_in)), -24, +24); zero norms map to ±24 or 0. `score` computes dissonance as share of non-consonant consecutive intervals (CONSONANT = {0,3,4,5,7,8,9,12}); stuck_share = fraction of `stuck` layers; clarity = 1 - 0.6*dissonance - 0.4*stuck_share; verdict rules as above. `render_wav` writes 16-bit mono sine tones, 0.15s each, faint amplitude (0.05) for stuck layers. `compare_clarity` reports means, difference, and small-sample warning.

**Failure modes:** Non-metamorphosis records, missing fields, non-boolean `changed`, non-finite/negative norms, >512 layers → `HarmonicRefused`. WAV render refuses >512 notes. `compare_clarity` refuses non-lists, values outside [0,1].

**Invariants:**

- Pitch mapping is a convention, not a discovered law.
- Clarity tracking correctness is a hypothesis; `compare_clarity` tests it, does not prove it.
- WAV is deterministic: same notes → identical bytes.
- Chain record holds verdict and melody digest only; no raw activations.

### 3.3 `echo.py` — repeat-run stability echo

**Role:** Run a caller-provided function N times under variations, compute word-overlap stability.

**Public interface:**

```python
words(text) → set of filtered words
harmonics(texts) → {n, fundamental, overtones, resonance, pairs, outlier, verdict}
echo(run, step_id, variations, dag=None, judge=None) → harmonics + record
EchoRefused exception
```

**Behavior:** `words` lowercases, regex extracts `[a-z0-9']+`, drops stopwords and len≤1. `harmonics` computes union/core/resonance, all pair overlaps, outlier detection (≥3 echoes). `echo` calls `run(v)` for each variation, hashes outputs, optional `judge(a,b)` returning exactly `True` forces UNSTABLE. Records only hashes, never text.

**Failure modes:** Bad callable, wrong variation count (2..64), oversized text (>1MiB), non-string returns, crashing `run` or `judge` → `EchoRefused` or propagates exception; chain records nothing on crash.

**Invariants:**

- Never stores echo text on chain — only sha256 hashes.
- Case/punctuation invariant.
- Padding with stopwords cannot fake stability (resonance uses union/core).
- Judge must return exactly `True` for contradiction; truthy is not enough.

### 3.4 `tiers.py` — telemetry by access tier

**Role:** Enforce what each access tier can honestly produce; refuse data the tier cannot see.

**Public interface:**

```python
entropy_bits(probs) → float
tier2_record(step_id, per_token_probs) → entropy record
telemetry(access, step_id, **data) → tier record dict
cue(record, high_share=0.5, cv=1.0) → {advice_only: True, cue: bool, why: list, grants_authority: False}
TierRefused exception
```

**Behavior:** `telemetry("weights", ...)` requires `layers`, optionally `consulted`, `timings_ns`; returns tier-1 with metamorphosis (+mapping, +breathing). `telemetry("probabilities", ...)` requires `per_token_probs`, optionally `timings_ns`; returns tier-2 entropy (+breathing); refuses any layer data. `telemetry("text", ...)` requires only `timings_ns`; refuses any layer or probability data. `cue` flags high entropy share or uneven timing; `grants_authority` is always `False`.

**Failure modes:** Wrong access string, missing required data, extra data for the tier, bad distributions (non-finite, negative, sum≠1), bad step ids → `TierRefused`. `entropy_bits` refuses empty, non-sum-to-1, non-finite, non-numeric.

**Invariants:**

- A lower tier is never padded with what only a higher tier could know.
- Tier-3 requests carrying layer/probability data are refused, not quietly accepted.
- Cue is advice only; never grants or withdraws authority.

### 3.5 `signature.py` — reference signature & calibration

**Role:** Maintain a running reference signature of FACT-grade verified assertions; compute asserted values; calibrate; atlas by epistemic status.

**Public interface:**

```python
features(entropy_record) → 5-element feature vector
ReferenceSignature(model_id, domain) with add_verified(vector, grade, committed), sd(), asserted_value(vector)
calibrate(verified_values, failed_values) → {n_verified, n_failed, mean_verified, mean_failed, difference, half_width, separated, note}
atlas(records) → {counts, centroids, centroid_distances, missing_statuses}
SignatureRefused exception
```

**Behavior:** `add_verified` requires grade exactly `"FACT"` and committed exactly `True`; running Welford mean/m2. `asserted_value` returns None if `n < 10` (not zero). RMS z-distance uses per-dimension sd with floor 0.05*max_sd. `calibrate` reports mean difference, standard error, 1.96*SE half-width, separation flag; small-sample note. `atlas` aggregates frozen computations by status, computes centroid distances.

**Failure modes:** Non-FACT grade, non-True committed, wrong vector length, non-finite values, unknown statuses, bad sha256 digests, negative temperature/depth, boolean seeds → `SignatureRefused`.

**Invariants:**

- Signature changes only by committed FACT additions.
- Asserted value is None (no basis), not zero, until 10 verified.
- Calibration is an indicator; verification stays the authority.
- Atlas statuses fixed: definitional, derived, empirical, circumstantial, disputed, falsehood.

### 3.6 `nnr.py` — staged NNR pieces

**Role:** Observe head profiles with custody, stamp expectations before runs, grade after, salted trace commitments.

**Public interface:**

```python
ObserveLedger(dag) with observe(step_id, prompt_class, prompt_sha256, profile, capsule_head), determinism(prompt_class, prompt_sha256), class_similarity(), brightest(n)
stamp(dag, run_id, expectations) → {run, stamp_sha256, expectations}
grade(stamp_obj, observed, tolerance=0.0, dag=None) → {rows, hits, misses, rate, note, stamp_on_chain, stamp_note}
(a run id can be stamped once; grade proves the stamp predates the run only when `dag` is passed and the stamp is found on its chain)
commit_trace(trace_record, salt, key) → hex commitment
open_commitment(commitment, trace_record, salt, key) → bool (constant-time)
prove_derivation(*args, **kwargs) → raises ProofUnavailable
NnrRefused, ProofUnavailable exceptions
```

**Behavior:** `observe` validates class ∈ {computational, cache, novel}, sha256 digests, finite non-negative magnitudes; records `TRACE_NNR007` with body_sha256 and capsule_head; updates cumulative and per-run profiles. `determinism` returns max per-head variance (0.0 = identical pathways). `stamp` hashes expectations before run; `grade` verifies stamp integrity, scores HIT/MISS per direction/tolerance; misses kept. `commit_trace` HMAC-SHA256(salt + nul + canonical_json) under key; `open_commitment` uses `hmac.compare_digest`. `prove_derivation` always raises `ProofUnavailable` (fail closed).

**Failure modes:** Unknown class, bad digests, negative/NaN magnitudes, duplicate regions, tampered stamp, short salt/key (<16 bytes), bad types → `NnrRefused`. `prove_derivation` always fails closed.

**Invariants:**

- Every observation carries a body digest and capsule-head pointer (custody-controlled).
- Identical repeated prompts → determinism 0.0.
- Misses are kept; a calibration that hides misses is not one.
- Constant-time commitment verify; fresh salt hides repeated trace.
- Zero-knowledge proof not built; explicitly fails closed.

## 4. Guarantees and non-guarantees

### Guarantees

| Guarantee | Module | Test |
|-----------|--------|------|
| Trace records contain only hashes/counts/scalars, never raw vectors | trace.py | test_trace.py::test_metamorphosis_keeps_digests_not_vectors |
| Mapping canonicalizes layer order and position sets | trace.py | test_trace.py::test_mapping_is_canonical |
| Vector digests stable under float noise below precision | trace.py | test_trace.py::test_vector_digest_survives_float_noise_below_the_precision |
| Chain refuses credential-shaped content in trace records | trace.py | test_trace.py::test_a_credential_cannot_ride_in_a_record_field |
| Harmonic WAV deterministic | harmonic.py | test_harmonic.py::test_wav_is_valid_deterministic_and_the_right_length |
| Harmonic verdict rules (STUCK/CLEAR/MUDDY/DISSONANT) | harmonic.py | test_harmonic.py::test_a_clean_run_is_clear_and_a_flat_run_is_stuck |
| Echo never stores text on chain, only hashes | echo.py | redteam_2_echo.py::test_the_record_never_holds_the_echo_text |
| Echo judge requires exactly True for contradiction | echo.py | redteam_2_echo.py::test_a_judge_answer_other_than_exactly_true_is_not_a_contradiction |
| Tier boundary enforced: text tier refuses layer/probability data | tiers.py | test_filed_telemetry.py::test_text_only_access_never_accepts_internal_data |
| Cue never grants authority | tiers.py | test_filed_telemetry.py::test_a_cue_is_advice_only |
| Reference signature requires FACT + committed=True | signature.py | test_filed_telemetry.py::test_only_committed_fact_enters_the_signature |
| Asserted value None until 10 verified | signature.py | test_filed_telemetry.py::test_no_value_without_a_basis |
| ObserveLedger records body digest + capsule head | nnr.py | test_filed_telemetry.py::test_observation_is_recorded_with_a_digest_and_the_capsule_head |
| Stamp tamper detected | nnr.py | test_filed_telemetry.py::test_stamped_expectations_are_graded_and_misses_are_kept |
| Commitment constant-time verify | nnr.py | test_filed_telemetry.py::test_commitment_opens_only_with_the_right_trace_salt_and_key |
| prove_derivation fails closed | nnr.py | test_filed_telemetry.py::test_the_zero_knowledge_proof_is_not_built_and_says_so |

### Non-guarantees

| Non-guarantee | Explanation |
|---------------|-------------|
| A stable echo means a correct answer | All echoes can agree and be wrong (echo.py docstring) |
| Harmonic clarity predicts correctness | Convention + hypothesis; `compare_clarity` tests, does not prove |
| Breathing traces reveal content | External timing only; sensitive to machine load |
| Semantic (embedding/entailment) judge for echoes | Plug-in point only; built-in is word overlap |
| Zero-knowledge proof of trace derivation | Not built; `prove_derivation` raises `ProofUnavailable` |
| Production hardening | Reference implementation; not independently security-reviewed |
| Expert-reviewed cryptography | Plain software written for clarity; do not protect real secrets |

## 5. Failure modes

| Failure | What happens | Test file |
|---------|--------------|-----------|
| Tampered trace record (credential-shaped) | `trace.record` refuses via `contains_credential` | test_trace.py::test_a_credential_cannot_ride_in_a_record_field |
| Missing commitment / wrong kind / wrong step | `trace.compare`, `trace.record` raise `TraceRefused` | test_trace.py::test_compare_refuses_mixed_kinds_and_steps |
| Expired/replayed commitment | Custody chain detects (append-only, hash-chained) | vega-custody-sdk tests |
| Corrupt chain | Next `record` call raises (chain verify fails) | redteam_2_echo.py::test_a_tampered_chain_refuses_the_next_echo_record |
| Malformed input to any function | Typed `*Refused` exception; nothing written | All redteam tests |
| Tier boundary violation | `tiers.telemetry` refuses extra data for declared tier | test_filed_telemetry.py::test_text_only_access_never_accepts_internal_data |
| Non-FACT grade or non-committed addition to signature | `ReferenceSignature.add_verified` raises `SignatureRefused` | test_filed_telemetry.py::test_only_committed_fact_enters_the_signature |
| Tampered stamp | `nnr.grade` raises `NnrRefused` | test_filed_telemetry.py::test_stamped_expectations_are_graded_and_misses_are_kept |
| Short salt/key for commitment | `commit_trace` raises `NnrRefused` | test_filed_telemetry.py::test_commitment_opens_only_with_the_right_trace_salt_and_key |
| Crashing run/judge in echo | Exception propagates; chain records nothing | redteam_2_echo.py::test_a_crashing_run_propagates_and_records_nothing |

## 6. Dependencies and layer rules

Registry entry verbatim:

```text
vega-trace-sdk | 10 observe | custody
```

Dependencies point down layers only, never up or sideways. This kit imports only `vega_custody.dag.dag` (layer 0). No other family SDKs are imported.

## 7. Conformance

Run the test suite:

```bash
PYTHONPATH=src:../vega-custody-sdk/src python -m pytest tests/
# or
python -m unittest discover tests
```

99 tests in 7 files must pass.

Passing means: the published reference implementation behaves as specified — validation refuses bad inputs, records contain only hashes/scalars, tier boundaries are enforced, fail-closed points hold.

Passing does NOT mean: production ready, independently security-reviewed, crypto expert-reviewed, correct answers from stable echoes, or that harmonic clarity predicts correctness.