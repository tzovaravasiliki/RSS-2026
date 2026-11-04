# Validation record — Workbench 1.1

Date: 2026-10-31. No new model API calls were performed while building or checking this release.

Verified in the build environment:

- 47 automated tests pass, including the prior 34 checks and 13 new evidence-support/locking regression tests. The optional Node test exercises six startup routes plus the guarded experiment overview and dialogue, with DOM stubs and browser-like globals.
- All 20 built-in cases × 7 policies run both with raw and filtered fixture extraction (280 software episodes). When extraction is annotation-backed and correct, all saved actions and transitions are preserved; no gold fixture claim is rejected. This is software verification, not LLM evaluation.
- The original 140-condition bounded offline test remains enabled. A 36-episode CLI development suite completes with zero real API calls and valid exports.
- The 12 recorded development turns from session d64dd3c32bdd4c77a1351ff65afbb875 replay locally: 4 raw extraction-error turns remain recorded; 4 unsupported claims are rejected; admitted extraction has 0 errors on this known sample; 1 controller action changes on a saved input. No new future dialogue or full counterfactual outcome is inferred.
- Input immutability, no influence from gold/private fields, cart binding, preservation of source/time/TTL, polarity, ambiguity, questions, unknown statements, participation and alias-only statements are checked.
- The unfiltered raw mode retains the prior failure path and metrics. The llm policy retains its model-selected action. Guard mode and its code are frozen per experiment.
- The Windows byte-lock regression is tested with a simulated msvcrt handle that raises on read, and duplicate-lock failures close the handle cleanly. Real POSIX lock acquisition/release remains tested.

Limits:

- The support filter is a small hand-written Greek/English lexical grammar. It is not general semantic validation and may reject correct paraphrases or miss complex linguistic context. Independent text coverage and false-rejection evaluation are still required.
- These development examples informed the change. The recorded replay is not independent evidence of generalization or improved new LLM outputs.
- No live provider/model evaluation, Windows execution or full browser visual QA was performed for 1.1 here. Windows launchers were inspected; the user's first step is CHECK_OFFLINE_WINDOWS.bat. Node is optional and its one test can be skipped on a machine without Node.
- Original baseline results and workspaces must be retained separately. A new code fingerprint prevents continuation of 1.0 experiments in 1.1.


## Research workflow 1.2

Added contract tests for frozen source copies, isolated cost variants, stale-plan/source rejection, no implicit provider start, JSON/CSV/report exports, one-step audit independence from private truth, conservative conflict handling and explicit technical/limit/pending counts. Added UI regression coverage for sandbox-to-study transfer, preview invalidation, create-only flow and escaped read-only research reports. Live provider calls were mocked; these checks do not evaluate LLM accuracy. A full browser/Windows launch was not available in the current executor.
