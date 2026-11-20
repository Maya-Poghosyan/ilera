import { defineConfig, devices } from "@playwright/test";

// End-to-end: real Next app → real FastAPI backend → local stand-in for the Azure model.
// No database (in-memory store) and no general LLM key, so nothing reaches shared services.
const WEB = 3517, API = 8517, MODEL = 4517;

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
      command: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${API}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API}/healthz`,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: "", OPENAI_API_KEY: "", EMAIL_OPENAI_ENDPOINT: "",
        DOCUMENT_OPENAI_ENDPOINT: `http://127.0.0.1:${MODEL}`,
        DOCUMENT_OPENAI_DEPLOYMENT: "e2e-documents",
        DOCUMENT_OPENAI_API_KEY: "e2e-only",
      },
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
