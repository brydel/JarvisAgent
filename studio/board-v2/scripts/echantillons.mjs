// Mesure de la maquette : couleur moyenne (3×3) à des points nommés. Sert à fonder design/board-v2/tokens.json.
import fs from "node:fs";
import { PNG } from "pngjs";

const png = PNG.sync.read(fs.readFileSync(process.argv[2]));
const points = {
  barre_haut: [700, 12], onglet_board_actif: [262, 28], sous_barre: [700, 112], canevas: [560, 430],
  canevas_2: [990, 445], canevas_point: [0, 0], carte_fond: [700, 450], carte_note_fond: [300, 640],
  carte_bord: [146, 600], panneau_droit: [1480, 600], panneau_bord: [1305, 600], texte_titre: [0, 0],
  accent_bouton: [1600, 90], accent_bouton_2: [1500, 82], progression: [700, 579], progression_vide: [860, 579],
  case_cochee: [630, 612], cyan_lien: [960, 230], violet_lien: [540, 430], vert_alimente: [520, 577],
  vert_badge: [1235, 488], p1_badge: [596, 168], p2_badge: [163, 179], p3_badge: [1010, 179],
  mission_bord: [600, 600], mission_glow: [596, 470], pastille_tag: [650, 407], approuver: [1505, 822],
  refuser: [1600, 822], toolbar: [50, 400], toolbar_ajouter: [50, 166], minimap: [150, 880],
  barre_recherche: [1300, 28], texte_secondaire: [0, 0],
};
const out = {};
for (const [nom, [x, y]] of Object.entries(points)) {
  if (!x && !y) continue;
  let r = 0, g = 0, b = 0, n = 0;
  for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
    const i = ((y + dy) * png.width + (x + dx)) * 4;
    r += png.data[i]; g += png.data[i + 1]; b += png.data[i + 2]; n++;
  }
  const h = (v) => Math.round(v / n).toString(16).padStart(2, "0");
  out[nom] = `#${h(r)}${h(g)}${h(b)}`;
}
console.log(JSON.stringify(out, null, 1));
