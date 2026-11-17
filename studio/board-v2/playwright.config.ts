import { defineConfig } from "@playwright/test";

// Serveur Studio ISOLE : aucune donnee de test ne touche l'installation reelle.
// Port et fichier du jeton réglables (JARVIS_E2E_PORT, JARVIS_E2E_JETON) : deux suites peuvent tourner sur le même poste.
const PORT = process.env.JARVIS_E2E_PORT || "7721";
const JETON = process.env.JARVIS_E2E_JETON || "/tmp/jarvis-e2e-jeton";
// Chemins relatifs à cette configuration, séparables pour conserver les preuves de chaque lot CI.
const SORTIES = process.env.JARVIS_E2E_SORTIES || "../../reports/board-v2/playwright-sorties";
const RESULTATS = process.env.JARVIS_E2E_RESULTATS || "../../reports/board-v2/playwright-resultats.json";
process.env.JARVIS_E2E_JETON = JETON;
// présent = l'exécutant factice du serveur de test ne prend aucune tâche (tests/e2e/intelligence.spec.ts)
const PAUSE = `${JETON}.pause-executant`;
process.env.JARVIS_E2E_PAUSE = PAUSE;
export default defineConfig({
  testDir: "tests/e2e",
  outputDir: SORTIES,
  snapshotPathTemplate: "tests/e2e/__captures__/{testFilePath}/{arg}{ext}",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000, toHaveScreenshot: { maxDiffPixelRatio: 0.012, animations: "disabled", caret: "hide" } },
  reporter: [["list"], ["json", { outputFile: RESULTATS }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: process.env.JARVIS_TEST_BROWSER_CHANNEL === "chrome" ? "chrome" : undefined,
    launchOptions: { executablePath: process.env.JARVIS_TEST_BROWSER_EXECUTABLE || undefined },
    viewport: { width: 1672, height: 941 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
    locale: "fr-FR",
    timezoneId: "America/Toronto",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 scripts/serveur_test.py",
    url: `http://localhost:${PORT}/v2/`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: { JARVIS_TEST_PORT: PORT, JARVIS_TEST_EXECUTANT: "1", JARVIS_TEST_RUNTIME: "1", JARVIS_TEST_JETON_FICHIER: JETON, JARVIS_TEST_PAUSE_FICHIER: PAUSE },
  },
});
