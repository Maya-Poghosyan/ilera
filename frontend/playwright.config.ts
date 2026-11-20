import { defineConfig, devices } from "@playwright/test";

// End-to-end: real Next app → real FastAPI backend (local test Postgres) → local stand-in for
// the Azure document model. Needs TEST_DATABASE_URL (see backend/tests/conftest.py).
const WEB = 3517, API = 8517, MODEL = 4517;
const DATABASE_URL = process.env.TEST_DATABASE_URL;
if (!DATABASE_URL) throw new Error("TEST_DATABASE_URL is required (see backend/tests/conftest.py)");
// Specs read captured email and fixtures straight from the test API (see backend/tests/e2e_api.py).
process.env.E2E_API_URL = `http://127.0.0.1:${API}`;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  // The dev server compiles each route on first visit.
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB}`, trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: [
    { command: "node e2e/fake-azure-openai.mjs", port: MODEL, env: { FAKE_OPENAI_PORT: String(MODEL) }, reuseExistingServer: false },
    {
      command: `.venv/bin/python tests/e2e_api.py ${API} ${MODEL}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API}/healthz`,
      reuseExistingServer: false,
      env: { DATABASE_URL, OPENAI_API_KEY: "", EMAIL_OPENAI_ENDPOINT: "" },
    },
    {
      command: `npx next dev --port ${WEB} --hostname 127.0.0.1`,
      url: `http://127.0.0.1:${WEB}/intake`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { API_URL: `http://127.0.0.1:${API}`, NEXT_DIST_DIR: ".next-e2e" },
    },
  ],
});
