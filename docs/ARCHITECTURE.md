# Architecture and operating boundaries

Python 3.10+, standard library, local HTTP UI. No package installation is required for users.

| Component | Responsibility |
|---|---|
| app.py | Loopback-only HTTP service, static UI, JSON endpoints and exports |
| web/ | Greek UI, experiment forms, trace replay and scenario editor |
| catalog.py | Dataset structure/provenance checks and simulator construction |
| contracts.py | Public-input allowlist, common prompt/schema, extraction validation, scripted dialogue transitions |
| engine.py | Frozen randomized plans, policies/ablations, bounded resumable episodes and pre-gate scoring |
| providers.py | Fixed HTTPS provider endpoints, local keys, one HTTP attempt, normalized/native usage |
| manager.py | One background worker, batches, pause/resume and request checkpoints |
| storage.py | Atomic JSON persistence and OS workspace process lock |
| analysis.py | Coverage/error tables, matched scenario-level descriptive contrasts, CSV/HTML/LaTeX |
| run_experiment.py | CLI alternative using the same engine and workspace |

Public observations consist of task subject/aliases, time/deadline, source priors/availability/cost, previous attempted sources and public dialogue. Gold evidence, conflict annotation, true verification and actual source access are restricted to the simulator/evaluator. Offline fixtures deliberately use gold as a software double and must not be interpreted as a language-model experiment.

At every live step, intent and cumulative call count are persisted before transport. A completed response is validated before an action is applied. Saved transitions are deterministically replayed on resume. A request with no saved response is classified interrupted_unknown and never automatically retried. A saved terminal transition is finalized without another request. This is at-most-one automatic attempt per recorded step, not an exactly-once billing guarantee.

The server binds to 127.0.0.1. Host validation, same-origin POST checks and an unpredictable per-process request token protect local mutation endpoints. Provider keys are never returned to the browser or exported. They are read from process environment, with a Windows User-registry fallback. Persistent User variables are not an encrypted credential vault. Provider redirects are disabled. No arbitrary API endpoint URL is accepted.

One workspace can be used by one UI/CLI process at a time. Atomic writes protect session checkpoints from partial JSON files. For backup, pause work and copy the entire workspace with the exact code release. Do not edit frozen session JSON manually.

Provider requests are opt-in. Opening the UI, refreshing key availability, editing scenarios, creating a plan and running offline fixtures do not make AI API calls. Only starting/resuming an experiment whose frozen mode is live can request model inference. There is no scheduled/background inference and no automatic retry or model fallback.

Official primary specifications inspected for implementation, 2026-10-23:

- OpenAI Responses structured output: https://developers.openai.com/api/docs/guides/structured-outputs
- Anthropic Messages structured output: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Gemini generation API and generation config: https://ai.google.dev/api/generate-content
- Gemini structured-output semantics: https://ai.google.dev/gemini-api/docs/structured-output

Adapter verification in this release uses mock transports and representative response shapes. Account/model availability and real schema acceptance require a small live integration test on each selected provider. Provider defaults and reasoning settings are not assumed equivalent.


## Addendum 1.1

evidence_guard.py reads only public message text/IDs/cart aliases. engine.py stores raw and admitted claims/checks separately. evidence_mode is frozen in the config; the guard implementation is included in the code fingerprint. The raw LLM decision is never replaced for the llm policy. replay_audit.py only evaluates saved histories; regression labels are offline-only and never passed to the online filter. The new CHECK_OFFLINE_WINDOWS.bat runs tests and a zero-network saved-input audit.
