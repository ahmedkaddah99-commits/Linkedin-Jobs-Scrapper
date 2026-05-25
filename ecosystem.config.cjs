module.exports = {
  apps: [
    {
      name: "runr-api",
      script: "scripts/run-python.cjs",
      args: "workspace_runner.py serve-api",
      watch: false,
      autorestart: true,
      restart_delay: 5000,
      env: { NODE_ENV: "development" },
      env_production: { NODE_ENV: "production" }
    },
    {
      name: "runr-worker",
      script: "scripts/run-python.cjs",
      args: "workspace_runner.py run-worker --worker-id local_worker",
      watch: false,
      autorestart: true,
      restart_delay: 5000
    },
    {
      name: "runr-frontend",
      script: "scripts/run-python.cjs",
      args: "backend/static_server.py",
      watch: false,
      autorestart: true,
      env: { PORT: "3000" }
    }
  ]
}
