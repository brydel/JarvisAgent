import { defineConfig } from "@playwright/test";

// Serveur Studio ISOLE : aucune donnee de test ne touche l'installation reelle.
export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "../../reports/board-v2/playwright-sorties",
  snapshotPathTemplate: "tests/e2e/__captures__/{testFilePath}/{arg}{ext}",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000, toHaveScreenshot: { maxDiffPixelRatio: 0.012, animations: "disabled", caret: "hide" } },
  reporter: [["list"], ["json", { outputFile: "../../reports/board-v2/playwright-resultats.json" }]],
  use: {
    baseURL: "http://localhost:7721",
    channel: process.env.JARVIS_TEST_BROWSER_CHANNEL === "chrome" ? "chrome" : undefined,
    viewport: { width: 1672, height: 941 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
    locale: "fr-FR",
    timezoneId: "America/Toronto",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 scripts/serveur_test.py",
    url: "http://localhost:7721/v2/",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { JARVIS_TEST_PORT: "7721", JARVIS_TEST_EXECUTANT: "1", JARVIS_TEST_JETON_FICHIER: "/tmp/jarvis-e2e-jeton" },
  },
});
