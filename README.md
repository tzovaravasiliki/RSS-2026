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
