import { defineConfig } from "@playwright/test";

const testPort = Number(process.env.E2E_PORT ?? "3032");
if (!Number.isInteger(testPort) || testPort < 1 || testPort > 65535)
  throw new Error("Invalid E2E_PORT");

export default defineConfig({
  testDir: "./tests/browser",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${testPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { browserName: "chromium", viewport: { width: 1280, height: 900 } },
    },
    {
      name: "narrow",
      use: { browserName: "chromium", viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: "uv run --locked python tests/e2e_server.py",
    env: { PYTHONPATH: ".", OPENAI_API_KEY: "", E2E_PORT: String(testPort) },
    url: `http://127.0.0.1:${testPort}/api/health`,
    reuseExistingServer: false,
    timeout: 20_000,
  },
});
