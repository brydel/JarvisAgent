// Capture rapide d'une page (inspection visuelle pendant le développement).
// node scripts/capture.mjs <url> <sortie.png> [largeur] [hauteur]
import { chromium } from "@playwright/test";

const [url, sortie, l = "1672", h = "941"] = process.argv.slice(2);
const navigateur = await chromium.launch();
const page = await navigateur.newPage({ viewport: { width: Number(l), height: Number(h) }, deviceScaleFactor: 1, reducedMotion: "reduce" });
const erreurs = [];
page.on("console", (m) => m.type() === "error" && erreurs.push(m.text()));
page.on("pageerror", (e) => erreurs.push(String(e)));
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(800);
if (process.env.CLIC) {
  await page.locator(process.env.CLIC).first().click({ position: { x: 60, y: 60 } });
  await page.mouse.move(5, 5);
  await page.waitForTimeout(700);
}
await page.screenshot({ path: sortie });
if (erreurs.length) console.log("ERREURS CONSOLE:\n" + erreurs.join("\n"));
console.log("capture", sortie);
await navigateur.close();
