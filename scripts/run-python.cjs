const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function resolvePythonExecutable() {
  const candidates = process.platform === "win32"
    ? [
        path.resolve(".venv", "Scripts", "python.exe"),
        path.resolve(".venv", "Scripts", "python"),
      ]
    : [
        path.resolve(".venv", "bin", "python"),
        path.resolve(".venv", "bin", "python3"),
      ];

  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

const pythonExecutable = resolvePythonExecutable();

if (!pythonExecutable) {
  console.error("Unable to find the project virtualenv Python executable in .venv.");
  process.exit(1);
}

const child = spawn(pythonExecutable, process.argv.slice(2), {
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Unable to start ${pythonExecutable}: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
