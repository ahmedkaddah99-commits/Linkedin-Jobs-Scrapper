# Project instructions

## Python environment

All Python commands in this repository must use the project virtual environment:

```powershell
.venv\Scripts\python.exe
```

Never use the global Python interpreter or global `pip` for this project.

Before running tests, scripts, or installing packages, verify the interpreter:

```powershell
.venv\Scripts\python.exe --version
```

The required Python version is **3.12.7**. If `.venv\Scripts\python.exe` does not exist or reports a different version, stop and report the issue. Do not fall back to global Python.

Use these command forms:

- Install packages: `.venv\Scripts\python.exe -m pip install <package>`
- Run scripts: `.venv\Scripts\python.exe <script.py>`
- Run tests: `.venv\Scripts\python.exe -m pytest`
