#!/usr/bin/env node
// capturer.cjs — démontage visuel des concurrents : captures d'écran de pages PUBLIQUES, bureau et
// mobile, puis une planche qui met côte à côte les mêmes écrans chez chaque concurrent (et chez nous).
//
//   node capturer.cjs cibles.json <dossier-de-sortie>
//
// cibles.json :
//   { "formats": ["bureau", "mobile"],                 (défaut : les deux)
//     "pleine_page": false,                             (true : toute la hauteur de la page)
//     "cibles": [
//       { "nom": "tradingview", "ecran": "accueil", "url": "https://www.tradingview.com/" },
//       { "nom": "tradingview", "ecran": "tarifs",  "url": "https://www.tradingview.com/pricing/" },
//       { "nom": "nous",        "ecran": "accueil", "url": "http://localhost:3000/" } ] }
//
// Règles (vérifiées ici, pas seulement écrites) :
//  - http(s) seulement ; robots.txt respecté pour les sites distants (une page interdite est sautée) ;
//  - une page toutes les 3 secondes au plus par site ; aucune connexion, aucun formulaire rempli ;
//  - « nous » ou une adresse locale (localhost, 127.0.0.1) : pas de robots.txt, pas d'attente.
// Sortie : <dossier>/<nom>/<ecran>-<format>.png, index.json (url finale, titre, statut, date) et
// planche-<format>.png (un écran par ligne, un concurrent par colonne).
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { erreur, navigateur } = require(path.join(__dirname, '..', '..', 'jarvis-studio', 'scripts', '_studio.cjs'));

const FORMATS = {
  bureau: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, isMobile: false },
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};
const DELAI_MS = 3000;
const AGENT = 'Mozilla/5.0 (compatible; JarvisVeille/1.0; analyse concurrentielle ponctuelle)';

function local(u) {
  return ['localhost', '127.0.0.1', '::1', '[::1]'].includes(u.hostname);
}

function slug(s) {
  return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'x';
}

// robots.txt minimal : groupes « User-agent: * », règles Allow/Disallow par préfixe, la plus longue gagne.
const _robots = new Map();
async function autorise(u) {
  if (local(u)) return true;
  const origine = u.origin;
  if (!_robots.has(origine)) {
    let regles = [];
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 10000);
      const r = await fetch(`${origine}/robots.txt`, { signal: ctrl.signal, headers: { 'user-agent': AGENT } });
      clearTimeout(t);
      if (r.ok) regles = analyserRobots(await r.text());
    } catch (_) { /* robots.txt injoignable : aucune règle connue */ }
    _robots.set(origine, regles);
  }
  const chemin = u.pathname + u.search;
  let meilleur = null;
  for (const [type, prefixe] of _robots.get(origine)) {
    if (prefixe && chemin.startsWith(prefixe) && (!meilleur || prefixe.length > meilleur[1].length)) meilleur = [type, prefixe];
  }
  return !meilleur || meilleur[0] === 'allow';
}

function analyserRobots(texte) {
  const regles = [];
  let pourTous = false;
  let enGroupe = false;
  for (const brut of texte.split(/\r?\n/)) {
    const ligne = brut.replace(/#.*/, '').trim();
    if (!ligne) continue;
    const [cle, ...reste] = ligne.split(':');
    const valeur = reste.join(':').trim();
    const k = cle.trim().toLowerCase();
    if (k === 'user-agent') {
      if (!enGroupe) pourTous = false;
      enGroupe = true;
      if (valeur === '*') pourTous = true;
    } else {
      enGroupe = false;
      if (pourTous && (k === 'disallow' || k === 'allow')) regles.push([k, valeur]);
    }
  }
  return regles;
}

function attendre(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function planche(nav, dossier, index, format) {
  const items = index.filter((i) => i.format === format && i.fichier);
  if (!items.length) return null;
  const noms = [...new Set(items.map((i) => i.nom))].sort((a, b) => (a === 'nous') - (b === 'nous') || a.localeCompare(b));
  const ecrans = [...new Set(items.map((i) => i.ecran))];
  const largeur = format === 'mobile' ? 260 : 460;
  const hauteur = format === 'mobile' ? 560 : 300;
  const echap = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let html = `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;background:#0e1116;color:#e6e9ef;font:15px/1.3 system-ui,sans-serif;padding:24px}
    h1{font-size:20px;margin:0 0 16px}
    table{border-collapse:separate;border-spacing:14px 10px}
    th{font-weight:600;text-align:left;color:#9aa4b2;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
    th.nous{color:#7ee0a3}
    td{vertical-align:top}
    .c{width:${largeur}px;height:${hauteur}px;overflow:hidden;border-radius:8px;background:#1a1f27;outline:1px solid #2a313c}
    .c img{width:100%;display:block}
    .vide{display:flex;align-items:center;justify-content:center;color:#5b6573;font-size:13px}
    td.e{writing-mode:vertical-rl;transform:rotate(180deg);color:#9aa4b2;font-size:13px;vertical-align:middle;text-align:center}
  </style><h1>Veille — ${echap(format)} — ${new Date().toISOString().slice(0, 10)}</h1><table><tr><th></th>`;
  for (const n of noms) html += `<th class="${n === 'nous' ? 'nous' : ''}">${echap(n)}</th>`;
  html += '</tr>';
  for (const e of ecrans) {
    html += `<tr><td class="e">${echap(e)}</td>`;
    for (const n of noms) {
      const it = items.find((i) => i.nom === n && i.ecran === e);
      html += it ? `<td><div class="c"><img src="file://${path.join(dossier, it.fichier)}"></div></td>`
        : '<td><div class="c vide">—</div></td>';
    }
    html += '</tr>';
  }
  html += '</table>';
  const fichierHtml = path.join(dossier, `planche-${format}.html`);
  fs.writeFileSync(fichierHtml, html);
  const page = await nav.newPage({ viewport: { width: 400, height: 300 } });
  await page.goto(`file://${fichierHtml}`);
  await page.waitForLoadState('load');
  const sortie = path.join(dossier, `planche-${format}.png`);
  await page.screenshot({ path: sortie, fullPage: true });
  await page.close();
  return sortie;
}

async function main() {
  const [fichier, dossierArg] = process.argv.slice(2);
  if (!fichier || !dossierArg) erreur('usage : node capturer.cjs cibles.json <dossier-de-sortie>');
  let conf;
  try { conf = JSON.parse(fs.readFileSync(fichier, 'utf8')); } catch (e) { erreur(`${fichier} illisible : ${e.message}`); }
  if (!conf || !Array.isArray(conf.cibles) || !conf.cibles.length) erreur('le fichier doit contenir une liste « cibles » non vide');
  const formats = conf.formats || ['bureau', 'mobile'];
  for (const f of formats) if (!FORMATS[f]) erreur(`format inconnu « ${f} » (bureau, mobile)`);
  const dossier = path.resolve(dossierArg);
  fs.mkdirSync(dossier, { recursive: true });

  const nav = await navigateur();
  const index = [];
  const dernier = new Map();
  try {
    for (const c of conf.cibles) {
      if (!c || !c.nom || !c.url) erreur('chaque cible a un « nom » et une « url »');
      let u;
      try { u = new URL(c.url); } catch (_) { erreur(`adresse invalide : ${c.url}`); }
      if (!['http:', 'https:'].includes(u.protocol)) erreur(`seules les adresses http(s) sont acceptées : ${c.url}`);
      const nom = slug(c.nom);
      const ecran = slug(c.ecran || u.pathname.split('/').filter(Boolean).pop() || 'accueil');
      if (!(await autorise(u))) {
        console.log(`  sauté (robots.txt l'interdit) : ${c.url}`);
        for (const f of formats) index.push({ nom, ecran, format: f, url: c.url, statut: 'interdit-robots' });
        continue;
      }
      for (const f of formats) {
        if (!local(u)) {
          const attente = DELAI_MS - (Date.now() - (dernier.get(u.host) || 0));
          if (attente > 0) await attendre(attente);
          dernier.set(u.host, Date.now());
        }
        const ctx = await nav.newContext({ ...FORMATS[f], userAgent: AGENT, locale: conf.langue || 'fr-CA' });
        const page = await ctx.newPage();
        const rel = path.join(nom, `${ecran}-${f}.png`);
        const entree = { nom, ecran, format: f, url: c.url, date: new Date().toISOString() };
        try {
          const rep = await page.goto(c.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
          await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
          await attendre(1200);  // animations d'entrée
          fs.mkdirSync(path.join(dossier, nom), { recursive: true });
          await page.screenshot({ path: path.join(dossier, rel), fullPage: !!conf.pleine_page });
          Object.assign(entree, { fichier: rel, statut: rep ? rep.status() : 0, url_finale: page.url(), titre: await page.title() });
          console.log(`  ${nom} · ${ecran} · ${f} → ${rel}`);
        } catch (e) {
          entree.statut = 'echec';
          entree.erreur = String(e.message).split('\n')[0];
          console.log(`  échec : ${c.url} (${f}) — ${entree.erreur}`);
        } finally {
          await ctx.close();
        }
        index.push(entree);
      }
    }
    fs.writeFileSync(path.join(dossier, 'index.json'), JSON.stringify(index, null, 2));
    for (const f of formats) {
      const p = await planche(nav, dossier, index, f);
      if (p) console.log(`Planche ${f} : ${p}`);
    }
  } finally {
    await nav.close();
  }
  const ok = index.filter((i) => i.fichier).length;
  console.log(`${ok}/${index.length} capture(s). Index : ${path.join(dossier, 'index.json')}`);
  if (!ok) process.exit(1);
}

main().catch((e) => erreur(String(e && e.message || e), 1));
