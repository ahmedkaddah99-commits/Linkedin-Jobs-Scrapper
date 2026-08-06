import { spawn, spawnSync } from "node:child_process";
import { dirname, join } from "node:path";

const npmCli = process.env.npm_execpath || join(dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js");
const env = {
  ...process.env,
  VITE_E2E_AUTH: "1",
  VITE_PERSONALIZED_JOBS_EXPERIENCE: "1",
  VITE_PERSONALIZED_JOBS_DATA_MODE: "real",
};
const build = spawnSync(process.execPath, [npmCli, "run", "build"], { env, shell: false, stdio: "inherit" });
if (build.error) throw build.error;
if (build.status !== 0) process.exit(build.status ?? 1);

const preview = spawn(process.execPath, [npmCli, "run", "preview", "--", "--host", "127.0.0.1", "--port", "4173"], {
  env,
  shell: false,
  stdio: "inherit",
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => preview.kill(signal));
}
preview.on("exit", (code) => process.exit(code ?? 0));
