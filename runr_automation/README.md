# Runr Local Automation

Runr Local Automation is the single-folder, laptop-only controller for turning bounded Linear tickets into durable engineering jobs. The detailed operator guide is under `docs/` and is completed with the runtime phases.

Install from the repository virtual environment:

```powershell
.venv\Scripts\python.exe -m pip install -e .\runr_automation
.venv\Scripts\runr-auto.exe doctor
```

Tracked source, tests, skills, scripts, configuration examples, and documentation live in this folder. Mutable state lives together under `%LOCALAPPDATA%\RunrAutomation` so it cannot accidentally be committed.
