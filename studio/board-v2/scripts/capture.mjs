// Capture rapide d'une page (inspection visuelle pendant le développement).
// node scripts/capture.mjs <url> <sortie.png> [largeur] [hauteur]
// Variables : THEME=jour|nuit (préférence posée avant le chargement), CLIC=<sélecteur> (clic avant la capture),
// JETON=<fichier> (session du serveur de test : ouvre /v2/connexion#jeton avant l'adresse demandée).
import fs from "node:fs";
import { chromium } from "@playwright/test";

const [url, sortie, l = "1672", h = "941"] = process.argv.slice(2);
const navigateur = await chromium.launch();
const page = await navigateur.newPage({ viewport: { width: Number(l), height: Number(h) }, deviceScaleFactor: 1, reducedMotion: "reduce" });
const erreurs = [];
page.on("console", (m) => m.type() === "error" && erreurs.push(m.text()));
page.on("pageerror", (e) => erreurs.push(String(e)));
if (process.env.THEME) {
  await page.addInitScript((theme) => {
    const cle = "jarvis.board.preferences.v1";
    let p = {};
    try { p = JSON.parse(localStorage.getItem(cle) ?? "{}"); } catch { /* préférences illisibles : repart de zéro */ }
    localStorage.setItem(cle, JSON.stringify({ ...p, theme }));
  }, process.env.THEME);
}
if (process.env.JETON) {
  await page.goto(new URL(`/v2/connexion#${fs.readFileSync(process.env.JETON, "utf8").trim()}`, url).href);
  await page.locator(".react-flow, .product-app").first().waitFor({ state: "visible", timeout: 15000 });
}
await page.goto(url, { waitUntil: process.env.JETON ? "domcontentloaded" : "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(800);
if (process.env.CLIC) {
  // une carte se clique dans son coin (hors de ses boutons) ; tout autre élément en son centre
  await page.locator(process.env.CLIC).first().click(process.env.CLIC.includes("react-flow__node") ? { position: { x: 60, y: 60 } } : {});
  await page.mouse.move(5, 5);
  await page.waitForTimeout(700);
}
await page.screenshot({ path: sortie });
if (erreurs.length) console.log("ERREURS CONSOLE:\n" + erreurs.join("\n"));
console.log("capture", sortie);
await navigateur.close();
