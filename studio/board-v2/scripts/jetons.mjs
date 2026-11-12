// Jetons de design → feuilles de style. Source unique : design/board-v2/tokens.json.
//   node scripts/jetons.mjs              écrit src/styles/themes.css, src/styles/tokens.css et design/board-v2/planche.html
//   node scripts/jetons.mjs --verifier   échoue si l'un des trois n'est plus à jour
//   node scripts/jetons.mjs --usage      compte les emplois de chaque jeton dans src/ (synonymes hérités encore lus, jetons sans emploi)
// Le test src/styles/jetons.test.ts refait la vérification et contrôle le contraste AA des paires déclarées.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { planche } from "./planche.mjs";

const ICI = path.dirname(fileURLToPath(import.meta.url));
export const CHEMIN_JETONS = path.resolve(ICI, "../../../design/board-v2/tokens.json");
export const CHEMIN_CSS = path.resolve(ICI, "../src/styles/themes.css");
export const CHEMIN_FIXES = path.resolve(ICI, "../src/styles/tokens.css");
export const CHEMIN_PLANCHE = path.resolve(ICI, "../../../design/board-v2/planche.html");
const ENTETE = "/* GÉNÉRÉ par scripts/jetons.mjs depuis design/board-v2/tokens.json — ne pas modifier à la main. */\n";
/** largeur sous laquelle les remplacements `fixes.mobile` s'appliquent (même seuil que les feuilles du produit) */
export const SEUIL_MOBILE = 760;
/** groupes de `fixes` qui remplacent des valeurs au lieu d'en déclarer */
const REMPLACEMENTS = ["mobile", "mouvement-reduit"];

export function lireJetons() {
  return JSON.parse(fs.readFileSync(CHEMIN_JETONS, "utf8"));
}

/** entrées d'un groupe sans sa description */
const valeurs = (groupe) => Object.entries(groupe).filter(([k]) => !k.startsWith("$"));
const lignes = (paires, retrait = "  ") => paires.map(([k, v]) => `${retrait}--${k}: ${v};`).join("\n");

/** Synonymes à plat : nom → jeton de thème visé (rôles de la direction, puis anciens noms). */
export function synonymes(jetons) {
  return { ...jetons.synonymes.roles, ...jetons.synonymes.herites };
}

/** Valeurs d'un thème, synonymes compris (chaque synonyme prend la valeur de sa cible) : sert au calcul de contraste. */
export function themeResolu(jetons, theme) {
  const t = Object.fromEntries(valeurs(jetons.themes[theme]));
  for (const [nom, cible] of Object.entries(synonymes(jetons))) {
    if (!(cible in t)) throw new Error(`synonyme ${nom} : la cible ${cible} n'est pas un jeton de thème`);
    if (nom in t) throw new Error(`synonyme ${nom} : ce nom est déjà un jeton de thème`);
  }
  return { ...t, ...Object.fromEntries(Object.entries(synonymes(jetons)).map(([nom, cible]) => [nom, t[cible]])) };
}

/** Feuille des thèmes : nuit par défaut, jour sur `data-theme="jour"`, puis les synonymes (indépendants du thème). */
export function cssDesThemes(jetons) {
  const bloc = (selecteur, theme, schema) => `${selecteur} {\n  color-scheme: ${schema};\n${lignes(valeurs(jetons.themes[theme]))}\n}\n`;
  const renvois = (titre, table) => `  /* ${titre} */\n${lignes(Object.entries(table).map(([nom, cible]) => [nom, `var(--${cible})`]))}`;
  return ENTETE + bloc(":root", "nuit", "dark") + "\n" + bloc(":root[data-theme=\"jour\"]", "jour", "light")
    + `\n:root {\n${renvois("rôles de la direction", jetons.synonymes.roles)}\n${renvois("anciens noms : à remplacer par leur cible quand une feuille est retouchée", jetons.synonymes.herites)}\n}\n`;
}

/** Feuille des jetons fixes : typographie, espacement, rayons, icônes, mouvement, gabarit, et leurs remplacements. */
export function cssDesFixes(jetons) {
  const f = jetons.fixes;
  const groupes = Object.keys(f).filter((g) => !g.startsWith("$") && !REMPLACEMENTS.includes(g));
  const corps = groupes.map((g) => `  /* ${g} — ${f[g].$description} */\n${lignes(valeurs(f[g]))}`).join("\n\n");
  return ENTETE
    + "/* Jetons qui ne dépendent pas du thème. Les couleurs et les ombres vivent dans themes.css. Règles d'usage : docs/jarvis-next/BOARD_DIRECTION.md. */\n"
    + `:root {\n${corps}\n}\n`
    + `\n@media (max-width: ${SEUIL_MOBILE}px) {\n  :root {\n${lignes(valeurs(f.mobile), "    ")}\n  }\n}\n`
    + `\n@media (prefers-reduced-motion: reduce) {\n  :root {\n${lignes(valeurs(f["mouvement-reduit"]), "    ")}\n  }\n`
    + "  /* filet de sécurité : une animation ou une transition écrite sans jeton s'arrête aussi */\n"
    + "  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }\n}\n";
}

/** Noms des jetons fixes (tokens.css). */
export function nomsFixes(jetons) {
  return Object.keys(jetons.fixes).filter((g) => !g.startsWith("$") && !REMPLACEMENTS.includes(g)).flatMap((g) => valeurs(jetons.fixes[g]).map(([k]) => k));
}

/** Tous les noms qu'une feuille peut lire : jetons de thème, synonymes, jetons fixes. */
export function nomsConnus(jetons) {
  return [...valeurs(jetons.themes.nuit).map(([k]) => k), ...Object.keys(synonymes(jetons)), ...nomsFixes(jetons)];
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

/** Les trois fichiers générés : chemin et contenu attendu. */
export function fichiersGeneres(jetons = lireJetons()) {
  return [
    { chemin: CHEMIN_CSS, contenu: cssDesThemes(jetons) },
    { chemin: CHEMIN_FIXES, contenu: cssDesFixes(jetons) },
    { chemin: CHEMIN_PLANCHE, contenu: planche(jetons, { themeResolu, contraste, synonymes }) },
  ];
}

/** Lecture pour les tests (le projet front n'embarque pas les types de Node). */
export function lireFichier(chemin) {
  return fs.readFileSync(chemin, "utf8");
}
export function lireCssThemes() {
  return lireFichier(CHEMIN_CSS);
}
export function lireFeuille(nom) {
  return fs.readFileSync(path.join(path.dirname(CHEMIN_CSS), path.basename(nom)), "utf8");
}
/** Fichier du projet front, par chemin relatif à studio/board-v2 (index.html, public/jarvis-mark.svg…). */
export function lireDuProjet(relatif) {
  return fs.readFileSync(path.resolve(ICI, "..", relatif), "utf8");
}
/** Toutes les feuilles de style du produit (chemins relatifs à src/), sauf themes.css (généré, seul lieu des couleurs). */
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

/** Nombre d'emplois de chaque jeton dans les feuilles et les composants (hors fichiers générés). */
export function usage(jetons = lireJetons()) {
  const textes = [...feuillesDuProduit().filter((f) => f.chemin !== "styles/tokens.css").map((f) => f.css), ...sourcesInterface().map((f) => f.code)].join("\n");
  const compte = (nom) => (textes.match(new RegExp(`--${nom}(?![\\w-])`, "g")) ?? []).length;
  return Object.fromEntries(nomsConnus(jetons).map((nom) => [nom, compte(nom)]));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const jetons = lireJetons();
  if (process.argv.includes("--usage")) {
    const u = usage(jetons);
    const herites = Object.entries(jetons.synonymes.herites);
    console.log(`synonymes hérités encore lus (${herites.filter(([n]) => u[n]).length} sur ${herites.length}) :`);
    for (const [nom, cible] of herites.filter(([n]) => u[n]).sort((a, b) => u[b[0]] - u[a[0]])) console.log(`  --${nom} → --${cible} : ${u[nom]}`);
    console.log(`synonymes hérités sans emploi : ${herites.filter(([n]) => !u[n]).map(([n]) => n).join(", ") || "aucun"}`);
    console.log(`jetons de thème sans emploi direct : ${valeurs(jetons.themes.nuit).map(([k]) => k).filter((k) => !u[k]).join(", ") || "aucun"}`);
    console.log(`jetons fixes sans emploi : ${nomsFixes(jetons).filter((k) => !u[k]).join(", ") || "aucun"}`);
  } else if (process.argv.includes("--verifier")) {
    const perimes = fichiersGeneres(jetons).filter((f) => !fs.existsSync(f.chemin) || fs.readFileSync(f.chemin, "utf8") !== f.contenu);
    if (perimes.length) {
      console.error(`${perimes.map((f) => path.relative(process.cwd(), f.chemin)).join(", ")} : plus à jour, lance « npm run jetons ».`);
      process.exit(1);
    }
  } else {
    for (const f of fichiersGeneres(jetons)) {
      fs.writeFileSync(f.chemin, f.contenu);
      console.log(`écrit : ${path.relative(process.cwd(), f.chemin)}`);
    }
  }
}
