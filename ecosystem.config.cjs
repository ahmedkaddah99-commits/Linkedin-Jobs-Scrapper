module.exports = {
  apps: [
    {
      name: "runr-api",
      script: "workspace_runner.py",
      args: "serve-api",
      interpreter: process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
      watch: false,
      autorestart: true,
      restart_delay: 5000,
      env: { NODE_ENV: "development" },
      env_production: { NODE_ENV: "production" }
    },
    {
      name: "runr-worker",
      script: "workspace_runner.py",
      args: "run-worker --worker-id local_worker",
      interpreter: process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
      watch: false,
      autorestart: true,
      restart_delay: 5000
    },
    {
      name: "runr-frontend",
      script: "backend/static_server.py",
      interpreter: process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
      watch: false,
      autorestart: true,
      env: { PORT: "3000" }
    }
  ]
}
