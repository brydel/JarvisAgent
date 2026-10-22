// Capture « avant » : l'ancien Board (Studio V1, /) sur le serveur de test isolé, avec quelques objets réels.
// node scripts/avant.mjs <port> <fichier-jeton> <sortie.png>
import fs from "node:fs";
import { chromium } from "@playwright/test";

const [port = "7720", fichierJeton = "/tmp/jarvis-board-v2-jeton", sortie = "../../reports/board-v2/before.png"] = process.argv.slice(2);
const jeton = fs.readFileSync(fichierJeton, "utf8").trim();
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1672, height: 941 }, reducedMotion: "reduce" });
await p.goto(`http://localhost:${port}/connexion#${jeton}`);
await p.waitForTimeout(800);
await p.evaluate(async () => {
  const h = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };
  const existants = (await (await fetch("/api/board?espace=accueil")).json()).objets.length;
  if (existants) return;
  for (const [i, contenu] of ["Inspiration — paysage montagne (image non affichable en V1)", "https://claude.ai — lien collé comme texte",
    "Note de recherche : plateforme unifiée IA + projets + connaissances"].entries()) {
    await fetch("/api/board", { method: "POST", headers: h, body: JSON.stringify({ espace: "accueil", type: "note", contenu, x: 40 + i * 330, y: 40 + (i % 2) * 60 }) });
  }
});
await p.goto(`http://localhost:${port}/`);
await p.waitForTimeout(1200);
await p.screenshot({ path: sortie });
console.log("capture", sortie);
await b.close();
