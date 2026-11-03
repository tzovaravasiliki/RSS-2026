# RSS2027 Research Workbench

A local Python workbench for uncertainty-aware information seeking in simulated human–robot teams. Version 1.1 studies when to request confirmation and which human information source to ask.

## Run on Windows

Requires Python 3.10 or newer. No third-party Python packages are required.

1. Download or clone this repository.
2. Open **START_WINDOWS.bat**, or run `py app.py` from the project folder.
3. Keep the terminal open. Use the local address printed by the application, usually http://127.0.0.1:8765.

Starting the application does not call an AI provider. Offline experiments use scripted fixtures and are not LLM evaluations.

## Offline checks

Run **CHECK_OFFLINE_WINDOWS.bat**, or:

```powershell
py -m unittest -v
py replay_audit.py
```

## Optional live experiments

Use `SETUP_KEY.ps1` to enter an API key locally. It saves a Windows user environment variable, not an encrypted credential vault. Never place API keys in source files. Select an explicit call cap before starting a live experiment; provider charges apply.

## Compared policies

- `cost_aware`: selective reverification with interruption-cost-aware source selection.
- `always_reverify`: mandatory fresh confirmation with the same source selector.
- `cost_blind`: selective reverification without interruption costs in source selection.
- `llm`: the model selects the action directly.

Additional ablations and the bounded explicit-support filter are documented in [README_GR.md](README_GR.md) and [docs/EXPLICIT_SUPPORT_GR.md](docs/EXPLICIT_SUPPORT_GR.md).

## Scope

Research development prototype with simulated human replies and equipment tasks. It does not control a physical robot or implement speech recognition, and has no clinical validation. The explicit-support filter uses a limited hand-written Greek/English grammar. The hidden-truth simulator dispatch gate is an evaluation mechanism, not a deployable robot safety system. Repeated development episodes are not independent benchmark evidence.

Local experiments under `workspace/`, generated audit outputs, caches, and credential files are excluded from Git. Synthetic regression fixtures are included for software checks.

The original version 1.1 release documents describe the state at packaging time; later experimental runs do not change that release snapshot.

The research target is RSS 2027; the repository name does not change the experiment protocol.

## Interactive training lab and recorded playback

Open **Διαδραστικό εργαστήριο** to choose a scenario, click a human source, ask, wait, dispatch or escalate. Source costs can be changed for an explicitly labelled training variant. Compare the three scripted policies from the same initial state. The lab runs entirely in the browser, uses structured initial annotations and programmed replies, makes no provider calls, and does not save or score research experiments.

Inside a saved experiment, **Προσομοίωση ομάδας** provides Play/Pause, speed, and before/after frames. It displays only the recorded public information available at the chosen phase. Replay makes no new inference calls and does not change the saved session. A frozen scenario can be copied into a separate training attempt.

The isometric room, figures, signals and delivery movement are symbolic. They do not model physical robot navigation or real team behaviour. See [interactive simulation notes](docs/SIMULATION_UI_GR.md).

Offline validation: `node test_frontend_smoke.cjs` and `py -m unittest test_interactive_parity -v`. The parity test checks the browser training adapter against the Python simulator using synthetic policy rollouts and manual paths. Node is optional and used only for tests.
