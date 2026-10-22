// Comparaison avec la maquette de référence (direction artistique, PAS un instantané binaire obligatoire) :
// diff pixel (pixelmatch), superposition 50 %, écart moyen de couleur par zone et global.
// node scripts/compare.mjs <capture.png> <dossier-sortie>
import fs from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const REF = path.resolve(import.meta.dirname, "../../../design/references/JARVIS_BOARD_V2_REFERENCE.png");
const [capture, sortie = "."] = process.argv.slice(2);
const a = PNG.sync.read(fs.readFileSync(REF));
const b = PNG.sync.read(fs.readFileSync(capture));
if (a.width !== b.width || a.height !== b.height) throw new Error(`tailles différentes : ${a.width}×${a.height} contre ${b.width}×${b.height}`);
const { width: w, height: h } = a;
fs.mkdirSync(sortie, { recursive: true });

const diff = new PNG({ width: w, height: h });
const differents = pixelmatch(a.data, b.data, diff.data, w, h, { threshold: 0.15, includeAA: false, alpha: 0.25 });
fs.writeFileSync(path.join(sortie, "diff.png"), PNG.sync.write(diff));

const sup = new PNG({ width: w, height: h });
for (let i = 0; i < a.data.length; i += 4) {
  for (let c = 0; c < 3; c++) sup.data[i + c] = Math.round(a.data[i + c] * 0.5 + b.data[i + c] * 0.5);
  sup.data[i + 3] = 255;
}
fs.writeFileSync(path.join(sortie, "overlay.png"), PNG.sync.write(sup));

// écart de couleur moyen (0–255) par zone du contrat visuel
const zones = {
  barre_haut: [0, 0, 1672, 56], seconde_rangee: [0, 60, 1672, 60], outils: [16, 136, 68, 724], panneau: [1305, 120, 367, 821],
  image: [135, 163, 393, 247], lien: [566, 148, 347, 285], pdf: [981, 155, 278, 254], note: [146, 455, 326, 313],
  mission: [598, 475, 362, 290], agents: [1016, 466, 265, 274], audio: [246, 789, 370, 142], video: [636, 789, 302, 142],
  dossier: [964, 808, 302, 122], global: [0, 0, w, h],
};
const ecarts = {};
for (const [nom, [x0, y0, zw, zh]] of Object.entries(zones)) {
  let s = 0, n = 0;
  for (let y = y0; y < Math.min(h, y0 + zh); y++) for (let x = x0; x < Math.min(w, x0 + zw); x++) {
    const i = (y * w + x) * 4;
    s += (Math.abs(a.data[i] - b.data[i]) + Math.abs(a.data[i + 1] - b.data[i + 1]) + Math.abs(a.data[i + 2] - b.data[i + 2])) / 3;
    n++;
  }
  ecarts[nom] = Math.round((s / n) * 10) / 10;
}
const rapport = { capture: path.basename(capture), pixels_differents_pct: Math.round((differents / (w * h)) * 1000) / 10, ecart_couleur_moyen: ecarts };
fs.writeFileSync(path.join(sortie, "comparaison.json"), JSON.stringify(rapport, null, 1));
console.log(JSON.stringify(rapport, null, 1));
