// Planche de contrôle des jetons : une page statique, générée, qui montre le système tel que les feuilles le lisent
// (design/board-v2/planche.html, à ouvrir depuis le dépôt après `npm ci` ; `?theme=jour` pour le thème clair).
// Elle ne fait pas partie du produit : elle sert à relire la rampe, l'échelle typographique, les rayons et la ligne de crédit.

const STYLES = "../../studio/board-v2/src/styles";
const POLICES = "../../studio/board-v2/node_modules";
const fr = (n) => n.toFixed(1).replace(".", ",");
const estHex = (v) => /^#[0-9a-f]{6}$/i.test(v);

const SURFACES = ["bg-bar", "bg-app", "bg-canvas", "surface-panel", "surface-card", "surface-card-raised", "surface-inset", "surface-hover", "surface-more"];
const TEXTES = [["text-primary", "Texte primaire : titres, corps, valeurs"], ["text-secondary", "Texte secondaire : libellés, descriptions, icônes"], ["text-muted", "Texte atténué : méta, légendes, crédits"],
  ["accent-texte", "Encre d'accent : le mot qui compte, rarement"], ["text-success", "Positif : vérifié, terminé"], ["text-warning", "Attention : à corriger"], ["text-danger", "Négatif : échec, blocage"]];
const FLECHES = [["edge-default", "Relation"], ["edge-inspire", "Inspire"], ["edge-alimente", "Alimente"], ["edge-utilise", "Utilisé par"], ["edge-depend", "Dépend de"], ["edge-bloquante", "Bloquante"], ["edge-debloquee", "Débloquée"]];
const TAILLES = [["fs-display", "lh-display", "serif", "Cadre une mission sur le Board"], ["fs-title-lg", "lh-title", "serif", "Références"], ["fs-title", "lh-title", "serif", "Refondre l'accueil du Studio"],
  ["fs-2xl", "lh-2xl", "sans", "Lancer une mission"], ["fs-xl", "lh-xl", "sans", "Équipe d'agents"], ["fs-lg", "lh-lg", "sans", "Jarvis Studio"],
  ["fs-base", "lh-base", "sans", "Pose des notes, des liens et des fichiers, relie-les par des flèches"], ["fs-sm", "lh-sm", "sans", "Relis avant tout envoi"], ["fs-meta", "lh-meta", "mono", "3 actifs · 12 min · 2 / 4 tâches"]];
const ESPACES = ["space-half", "space-1", "space-2", "space-3", "space-4", "space-5", "space-6", "space-8", "space-10", "space-12", "space-16"];

export function planche(jetons, { themeResolu, contraste, synonymes }) {
  const [nuit, jour] = [themeResolu(jetons, "nuit"), themeResolu(jetons, "jour")];
  const f = Object.assign({}, ...Object.values(jetons.fixes).filter((g) => typeof g === "object").slice(0, -2));
  const nbTheme = Object.keys(jetons.themes.nuit).length;
  const rapport = (texte, fond) => (estHex(nuit[texte]) && estHex(nuit[fond]) ? `${fr(contraste(nuit[texte], nuit[fond]))} nuit · ${fr(contraste(jour[texte], jour[fond]))} jour` : "");
  const pastille = (nom) => `<li><span class="pastille" style="background: var(--${nom})"></span><span class="nom">${nom}</span><span class="val">${nuit[nom]} · ${jour[nom]}</span></li>`;
  const texte = ([nom, phrase]) => `<li><span class="ex" style="color: var(--${nom})">${phrase}</span><span class="val">${nom} · ${rapport(nom, "surface-card")}</span></li>`;
  const fleche = ([nom, libelle]) => `<li><svg width="64" height="12" viewBox="0 0 64 12" aria-hidden="true"><path d="M2 6h54m-6-4 6 4-6 4" fill="none" stroke="var(--${nom})" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span class="nom">${libelle}</span><span class="val">${nom} · ${rapport(nom, "bg-canvas")}</span></li>`;
  const taille = ([fs, lh, famille, phrase]) => `<li><span class="val">${fs} · ${f[fs]} / ${f[lh]}</span><span style="font: ${famille === "sans" && fs !== "fs-base" && fs !== "fs-sm" ? 500 : 400} var(--${fs})/var(--${lh}) var(--font-${famille})${fs === "fs-display" ? "; letter-spacing: var(--tracking-display)" : ""}">${phrase}</span></li>`;
  const espace = (nom) => `<li><span class="val">${nom} · ${f[nom]}</span><span class="barre" style="width: var(--${nom})"></span></li>`;
  return `<!doctype html>
<!-- GÉNÉRÉ par studio/board-v2/scripts/jetons.mjs depuis design/board-v2/tokens.json — ne pas modifier à la main. -->
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis Studio — planche des jetons</title>
<link rel="stylesheet" href="${POLICES}/@fontsource-variable/instrument-sans/index.css">
<link rel="stylesheet" href="${POLICES}/@fontsource-variable/newsreader/opsz.css">
<link rel="stylesheet" href="${POLICES}/@fontsource/ibm-plex-mono/latin-400.css">
<link rel="stylesheet" href="${POLICES}/@fontsource/ibm-plex-mono/latin-500.css">
<link rel="stylesheet" href="${STYLES}/themes.css">
<link rel="stylesheet" href="${STYLES}/tokens.css">
<script>document.documentElement.dataset.theme = new URLSearchParams(location.search).get("theme") === "jour" ? "jour" : "nuit";</script>
<style>
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg-app); color: var(--text-primary); font: var(--fw-regular) var(--fs-base)/var(--lh-base) var(--font-sans); -webkit-font-smoothing: antialiased; }
main { max-width: 1200px; margin: 0 auto; padding: var(--space-8) var(--pad-page) var(--space-16); }
header { display: flex; align-items: center; gap: var(--icon-gap); height: var(--topbar-h); margin-bottom: var(--space-8); border-bottom: 1px solid var(--border-card); }
header b { font-size: var(--fs-lg); font-weight: var(--fw-strong); }
h1 { margin: 0 0 var(--space-3); font: var(--fw-regular) var(--fs-title-lg)/var(--lh-title) var(--font-serif); }
h2 { margin: 0 0 var(--space-4); font-size: var(--fs-lg); line-height: var(--lh-lg); font-weight: var(--fw-medium); }
p { margin: 0 0 var(--space-4); max-width: var(--measure); color: var(--text-secondary); }
section { padding: var(--space-8) 0; border-top: 1px solid var(--border-subtle); }
.colonnes { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-12); }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
li { display: flex; align-items: center; gap: var(--space-3); min-height: var(--row-h-compact); min-width: 0; }
.credit { display: flex; align-items: center; gap: var(--space-2); margin: 0; font: var(--type-credit); color: var(--credit); font-variant-numeric: tabular-nums; }
.credit::before { content: ""; flex: none; width: var(--space-3); height: 2px; background: var(--credit-filet); }
main > .credit { margin-bottom: var(--space-8); }
.val { font: var(--type-credit); color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.nom { flex: 1; font-size: var(--fs-sm); color: var(--text-secondary); }
.pastille { flex: none; width: var(--space-12); height: var(--space-8); border-radius: var(--radius-xs); border: 1px solid var(--border-card); }
.ex { flex: 1; }
.tailles li { align-items: baseline; gap: var(--space-6); min-height: 0; padding: var(--space-2) 0; }
.tailles .val, .espaces .val { flex: none; width: 176px; }
.barre { height: var(--space-2); background: var(--encre); border-radius: 1px; }
.carte { background: var(--surface-card); border: 1px solid var(--border-card); border-radius: var(--radius-card); padding: var(--pad-card); box-shadow: var(--shadow-card); }
.rangee { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); margin-bottom: var(--space-4); }
.bouton { height: var(--control-h); padding: 0 var(--space-4); border-radius: var(--radius-sm); border: 1px solid var(--border-strong); background: var(--surface-card-raised); color: var(--text-primary); font: var(--fw-medium) var(--fs-base)/var(--lh-base) var(--font-sans); transition: background-color var(--dur-hover) var(--ease-standard), transform var(--dur-hover) var(--ease-standard); }
.bouton:hover { background: var(--surface-hover); }
.bouton:active { transform: scale(var(--press-scale)); }
.bouton.encre { border-color: transparent; background: var(--encre); color: var(--sur-encre); }
.bouton.encre:hover { background: var(--encre-survol); }
.bouton.vu, .bouton:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.champ { display: flex; align-items: center; gap: var(--space-2); width: 240px; height: var(--control-h); padding: 0 var(--space-3); border-radius: var(--radius-sm); border: 1px solid var(--border-strong); background: var(--surface-field); color: var(--text-muted); }
.champ span { flex: 1; }
kbd { min-width: var(--space-5); padding: 0 var(--space-1); border-radius: var(--radius-2xs); border: 1px solid var(--border-card); background: var(--surface-inset); color: var(--text-secondary); font: var(--type-credit); text-align: center; }
.selection { box-shadow: var(--shadow-selection); }
.une h3 { margin: 0 0 var(--space-2); font: var(--fw-regular) var(--fs-title)/var(--lh-title) var(--font-serif); }
.nid { display: inline-flex; padding: var(--space-2); border-radius: var(--radius-panel); border: 1px solid var(--border-card); background: var(--surface-panel); }
.nid > div { display: flex; padding: var(--space-1); border-radius: calc(var(--radius-panel) - var(--space-2)); border: 1px solid var(--border-card); background: var(--surface-card); }
.nid > div > div { height: var(--control-h-sm); padding: 0 var(--space-3); border-radius: calc(var(--radius-panel) - var(--space-2) - var(--space-1)); background: var(--surface-hover); font: var(--type-credit); line-height: var(--control-h-sm); color: var(--text-secondary); }
@media (max-width: 760px) { .colonnes { grid-template-columns: 1fr; gap: var(--space-8); } .tailles li { flex-direction: column; align-items: flex-start; gap: var(--space-1); } li { flex-wrap: wrap; } }
</style>
</head>
<body>
<main>
<header>
<svg width="20" height="20" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M24.5 8.2A12 12 0 1 0 27.6 19" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"/><circle cx="16" cy="16" r="3.5" fill="currentColor"/></svg>
<b>Jarvis Studio</b>
</header>
<h1>Planche des jetons du Board</h1>
<p>${jetons.direction.caractere} ${jetons.direction.monde}</p>
<p class="credit">design/board-v2/tokens.json · ${nbTheme} jetons de thème · ${Object.keys(synonymes(jetons)).length} synonymes · nuit et jour</p>

<section class="colonnes">
<div><h2>Surfaces</h2><ul>${SURFACES.map(pastille).join("")}</ul></div>
<div><h2>Texte sur une carte</h2><div class="carte"><ul>${TEXTES.map(texte).join("")}</ul></div></div>
</section>

<section class="colonnes">
<div>
<h2>Encre, filets, sélection</h2>
<div class="rangee"><button class="bouton encre" type="button">Lancer une mission</button><button class="bouton" type="button">Ouvrir mon Board</button><button class="bouton vu" type="button">Au clavier</button></div>
<div class="rangee"><div class="champ"><span>Rechercher</span><kbd>/</kbd></div><div class="nid"><div><div>16 › 8 › 4</div></div></div></div>
<div class="carte une selection">
<h3>Refondre l'accueil du Studio</h3>
<p class="credit">Mission · 4 rôles d'agents · en cours depuis 12 min</p>
</div>
</div>
<div><h2>Flèches sur le canevas</h2><ul>${FLECHES.map(fleche).join("")}</ul></div>
</section>

<section>
<h2>Échelle typographique</h2>
<ul class="tailles">${TAILLES.map(taille).join("")}</ul>
</section>

<section class="colonnes">
<div><h2>Grille de 4 px</h2><ul class="espaces">${ESPACES.map(espace).join("")}</ul></div>
<div>
<h2>Mouvement</h2>
<ul>${["ease-standard", "dur-lift", "dur-hover", "dur-appear", "dur-panel", "dur-enter", "stagger", "rise", "press-scale"].map((n) => `<li><span class="nom">${n}</span><span class="val">${f[n]}</span></li>`).join("")}</ul>
</div>
</section>
</main>
</body>
</html>
`;
}
