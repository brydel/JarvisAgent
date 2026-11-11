// Jetons de design → variables CSS. Source unique : design/board-v2/tokens.json (`themes.nuit`, `themes.jour`).
//   node scripts/jetons.mjs          écrit src/styles/themes.css
//   node scripts/jetons.mjs --verifier   échoue si le fichier n'est plus à jour
// Le test src/styles/jetons.test.ts refait la même vérification et contrôle le contraste AA des paires déclarées.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ICI = path.dirname(fileURLToPath(import.meta.url));
export const CHEMIN_JETONS = path.resolve(ICI, "../../../design/board-v2/tokens.json");
export const CHEMIN_CSS = path.resolve(ICI, "../src/styles/themes.css");

export function lireJetons() {
  return JSON.parse(fs.readFileSync(CHEMIN_JETONS, "utf8"));
}

const bloc = (selecteur, valeurs, schema) =>
  `${selecteur} {\n  color-scheme: ${schema};\n${Object.entries(valeurs).map(([k, v]) => `  --${k}: ${v};`).join("\n")}\n}\n`;

/** Feuille de style des thèmes : nuit par défaut (identité d'origine), jour sur `data-theme="jour"`. */
export function cssDesThemes(themes) {
  return "/* GÉNÉRÉ par scripts/jetons.mjs depuis design/board-v2/tokens.json — ne pas modifier à la main. */\n"
    + bloc(":root", themes.nuit, "dark") + "\n" + bloc(":root[data-theme=\"jour\"]", themes.jour, "light");
}

/** Luminance relative WCAG 2.x d'une couleur « #RRGGBB ». */
export function luminance(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`couleur non opaque ou invalide pour un calcul de contraste : ${hex}`);
  const n = parseInt(m[1], 16);
  const [r, v, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * v + 0.0722 * b;
}

/** Rapport de contraste WCAG entre deux couleurs opaques (1 à 21). */
export function contraste(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

/** Lecture pour les tests (le projet front n'embarque pas les types de Node) : themes.css et les feuilles du Board. */
export function lireCssThemes() {
  return fs.readFileSync(CHEMIN_CSS, "utf8");
}
export function lireFeuille(nom) {
  return fs.readFileSync(path.join(path.dirname(CHEMIN_CSS), path.basename(nom)), "utf8");
}
/** Toutes les feuilles de style écrites à la main du produit (chemins relatifs à src/), sauf themes.css (généré). */
export function feuillesDuProduit() {
  const src = path.resolve(ICI, "../src");
  const trouver = (dossier) => fs.readdirSync(dossier, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? trouver(path.join(dossier, e.name))
    : e.name.endsWith(".css") && e.name !== "themes.css" ? [path.relative(src, path.join(dossier, e.name))] : []));
  return trouver(src).sort().map((chemin) => ({ chemin, css: fs.readFileSync(path.join(src, chemin), "utf8") }));
}
/** Sources TypeScript de l'interface (hors tests et jeux de démonstration), pour y chercher des couleurs écrites en dur. */
export function sourcesInterface() {
  const src = path.resolve(ICI, "../src");
  const trouver = (dossier) => fs.readdirSync(dossier, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? trouver(path.join(dossier, e.name))
    : /\.tsx$/.test(e.name) ? [path.relative(src, path.join(dossier, e.name))] : []));
  return trouver(src).sort().map((chemin) => ({ chemin, code: fs.readFileSync(path.join(src, chemin), "utf8") }));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const css = cssDesThemes(lireJetons().themes);
  if (process.argv.includes("--verifier")) {
    if (fs.readFileSync(CHEMIN_CSS, "utf8") !== css) {
      console.error("src/styles/themes.css n'est plus à jour : lance « npm run jetons ».");
      process.exit(1);
    }
  } else {
    fs.writeFileSync(CHEMIN_CSS, css);
    console.log(`écrit : ${path.relative(process.cwd(), CHEMIN_CSS)}`);
  }
}
