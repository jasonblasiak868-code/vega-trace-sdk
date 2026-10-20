# vega-trace-sdk — Capabilities

## At a glance

| Capability | Why policy/prompt cannot provide it | Where enforced in code | Test demonstrating it | Honest limit |
|------------|-------------------------------------|------------------------|----------------------|--------------|
| **Trace records contain only hashes/scalars, never raw vectors** | Policy cannot prevent a model from embedding secrets in its output; a prompt "don't store raw activations" is unenforceable | `trace.py`: `digest_vector`, `mapping_record`, `metamorphosis_record`, `breathing_record` — all drop raw data, keep only digests/norms/counts | `test_trace.py::test_metamorphosis_keeps_digests_not_vectors` | Caller must supply layer data; no model hook included |
| **Mapping canonicalizes layer order and position sets** | A prompt "sort your layers" cannot be verified; model may claim canonicalization while doing nothing | `trace.py`: `mapping_record` sorts layers and deduplicates/sorts positions before hashing | `test_trace.py::test_mapping_is_canonical` | Only works on caller-supplied data |
| **Vector digests stable under float noise below precision** | Prompt-level "round your numbers" is unreliable; different runs produce different rounding | `trace.py`: `digest_vector` rounds to 6 decimal places before hashing | `test_trace.py::test_vector_digest_survives_float_noise_below_the_precision` | Precision is a convention (6 places), not a discovered law |
| **Chain refuses credential-shaped content in trace records** | Policy "don't log API keys" fails when a model hallucinates or is prompted to leak; grep-based scanning misses obfuscated credentials | `trace.py`: `record` calls custody's `contains_credential` which detects patterns like `ghp_`, `sk-`, `nvapi-` | `test_trace.py::test_a_credential_cannot_ride_in_a_record_field` | Pattern-based; novel credential formats may pass |
| **Harmonic WAV is deterministic** | Prompt "generate the same audio each time" cannot be enforced; model outputs are non-deterministic | `harmonic.py`: `render_wav` uses fixed sample rate, note duration, sine synthesis; no randomness | `test_harmonic.py::test_wav_is_valid_deterministic_and_the_right_length` | WAV parameters are conventions (22050 Hz, 0.15s/note) |
| **Harmonic verdict rules (STUCK/CLEAR/MUDDY/DISSONANT) from measurable properties** | A prompt "rate your confidence" yields uncalibrated self-report; no ground truth for "how settled" | `harmonic.py`: `score` computes dissonance (interval consonance), stuck_share (unchanged layers), clarity = 1 - 0.6*dissonance - 0.4*stuck_share | `test_harmonic.py::test_a_clean_run_is_clear_and_a_flat_run_is_stuck` | Clarity→correctness is a hypothesis tested by `compare_clarity`, not a finding |
| **Echo never stores text on chain, only hashes** | Policy "don't log the output" is invisible; a compromised model or prompt injection bypasses it | `echo.py`: `echo` records `echo_sha256` list; `harmonics` operates on texts in memory only | `redteam_2_echo.py::test_the_record_never_holds_the_echo_text` | Caller's `run` function could log externally; SDK only controls chain |
| **Echo judge requires exactly `True` for contradiction** | Prompt "detect contradictions" yields false positives/negatives; LLM judges are unreliable | `echo.py`: `echo` checks `judge(a,b) is True` (identity, not truthiness) | `redteam_2_echo.py::test_a_judge_answer_other_than_exactly_true_is_not_a_contradiction` | Judge is caller-supplied; SDK only enforces the `is True` gate |
| **Tier boundary enforced: text tier refuses layer/probability data** | Prompt "you only have text access" is ignored by a model that hallucinates internals | `tiers.py`: `telemetry` validates `access` string and refuses extra keys for each tier | `test_filed_telemetry.py::test_text_only_access_never_accepts_internal_data` | Enforcement only works if caller uses `telemetry()`; direct module calls bypass |
| **Cue never grants authority** | A prompt "alert a human if unsure" can be ignored or manipulated; model controls its own output | `tiers.py`: `cue` returns `grants_authority: False` hardcoded; no code path sets it true | `test_filed_telemetry.py::test_a_cue_is_advice_only` | Cue is advisory; caller decides whether to act |
| **Reference signature requires FACT + committed=True** | Policy "only verified facts enter the signature" is unenforceable at prompt level | `signature.py`: `ReferenceSignature.add_verified` checks `grade == "FACT" and committed is True` | `test_filed_telemetry.py::test_only_committed_fact_enters_the_signature` | FACT grade source is outside this SDK (metacog evidence) |
| **Asserted value returns None until 10 verified** | Prompt "don't guess with little data" cannot prevent hallucinated confidence | `signature.py`: `asserted_value` returns `None` if `n < MIN_FOR_SIGNATURE (10)` | `test_filed_telemetry.py::test_no_value_without_a_basis` | Threshold (10) is a convention, not statistically derived |
| **ObserveLedger records body digest + capsule head** | Prompt "record your reasoning path" produces text, not verifiable custody-controlled digests | `nnr.py`: `ObserveLedger.observe` records `body_sha256` and `capsule_head` to `TRACE_NNR007` | `test_filed_telemetry.py::test_observation_is_recorded_with_a_digest_and_the_capsule_head` | Head profiles are caller-supplied; no model hook |
| **Stamp tamper detected** | Prompt "don't change your plan after seeing results" is unenforceable | `nnr.py`: `stamp` hashes expectations; `grade` re-hashes and compares; mismatch raises `NnrRefused` | `test_filed_telemetry.py::test_stamped_expectations_are_graded_and_misses_are_kept` | Only detects tamper if `grade` is called with original stamp object |
| **Commitment constant-time verify** | Prompt "verify this trace matches the commitment" leaks timing side-channels | `nnr.py`: `open_commitment` uses `hmac.compare_digest` | `test_filed_telemetry.py::test_commitment_opens_only_with_the_right_trace_salt_and_key` | Salt/key management is caller's responsibility |
| **prove_derivation fails closed (ProofUnavailable)** | Prompt "prove this trace came from the committed model" cannot be satisfied without ZK backend | `nnr.py`: `prove_derivation` unconditionally raises `ProofUnavailable` | `test_filed_telemetry.py::test_the_zero_knowledge_proof_is_not_built_and_says_so` | Explicitly not built; zero-knowledge backend is a separate concern |

## The predictive loop: this repo's part

The Vega family runs a **predictive loop**:

```
records → lessons → knowledge graph → lattice foresight → human decision
```

**vega-trace-sdk sits at the *records* and *foresight* steps:**

1. **Records (observe):** This SDK produces the telemetry that lands in the custody chain — mapping, metamorphosis, breathing traces; harmonic echo verdicts; repeat-run echo stability; tier-constrained entropy records; reference signature asserted values; NNR head profiles with capsule-head pointers. Every record is a hash-chained, credential-free fact about what happened.

2. **Lessons (librarian):** `vega-librarian-sdk` (layer 5) consumes these trace records, distills patterns (e.g., "layer 7 drift correlates with STUCK verdict"), and writes lesson capsules back to the chain.

3. **Knowledge graph (dkg-lattice):** `vega-dkg-lattice-sdk` (layer 7) ingests lessons, builds a graph where every fact has origin and licence, and makes it queryable.

4. **Lattice foresight (reasoning/galaxy):** `vega-reasoning-sdk` (layer 11) runs `predict.py` and `galaxy` on the knowledge graph, forecasting fidelity/convergence/futures. `vega-galaxy-sdk` (layer 14) visualizes the lattice levels above the present.

5. **Human decision:** The human (layer 15) sees the feed (layer 13), the galaxy view, the council deliberation (layer 14), and decides the next commitment.

**This SDK's specific contributions to the loop:**

- **Trace records** are the raw material: without them, the graph has no telemetry of reasoning.
- **Harmonic echo verdicts** (CLEAR/MUDDY/DISSONANT/STUCK) give a fast, auditable signal of step quality that feeds the lattice.
- **Repeat-run echo resonance** quantifies stability across variations — a measure of reasoning settlement.
- **Tier-enforced telemetry** ensures the graph knows *what the architecture could see* (weights/probabilities/text), preventing hallucinated "insight" from higher tiers.
- **Reference signature asserted values** let the lattice flag assertions that drift from the verified-fact baseline.
- **NNR ObserveLedger** provides head-profile determinism and class similarity — structural evidence of model behavior, not just output text.
- **Stamp/grade** creates a calibration loop: expectations → observation → HIT/MISS → kept misses → lattice learns where predictions fail.

**A category of its own**

vega-trace-sdk is the **only** kit in the family that:

- **Governance-first telemetry:** Authority stays outside the model (human commitment → jacket gates). This SDK never holds a key, never grants authority, never calls a model. It only records what happened.
- **Deterministic trace records:** Every record is a pure function of caller input → digests/scalars. No model in the loop, no stochasticity in the recording.
- **Pre-registered predicted paths (via NNR stamp):** Expectations are hashed and committed *before* a run. The lattice learns from HIT/MISS, not post-hoc rationalization.
- **Single-use human commitments:** The trace chain is anchored to human-signed commitments (via custody). One commitment → one action → one trace family. Replay is detected by the chain.
- **Chain-of-custody by default:** Every trace record lands in the hash-chained DAG. Tampering breaks the chain; anyone can verify without trusting the model, vendor, or project.
- **Lattice-informed foresight:** The trace telemetry this SDK produces is the *input* to the reasoning/galaxy lattice. The lattice forecasts from what was actually recorded, not from what a model claims it did.

Every differentiation claim above is what **this design does**. It does not claim "competitors cannot" — it claims that authority held outside the model (governance-first) cannot be replicated by prompt-level policy, because the thing being checked (the model) is the thing doing the checking. That argument comes from the WHITEPAPER.md Section 1.