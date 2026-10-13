#!/usr/bin/env node
// enregistrer.cjs — filme un parcours dans le produit (application locale) selon un scénario.
//
//   node enregistrer.cjs scenario.json sortie.webm
//
// Scénario (JSON) :
//   { "largeur": 1600, "hauteur": 1000,
//     "etapes": [
//       { "aller": "http://localhost:3000" },
//       { "attendre": 1200 },                      (millisecondes)
//       { "attendre_selecteur": "text=Tableau de bord" },
//       { "cliquer": "text=Commencer" },           (le curseur s'y déplace, puis clique)
//       { "ecrire": { "dans": "#email", "texte": "demo@exemple.com" } },
//       { "touche": "Enter" },
//       { "survoler": ".carte:first-child" },
//       { "defiler": 600 },                        (pixels, défilement doux)
//       { "masquer": ".email-utilisateur" },       (sélecteur CSS : floute cette zone sur toutes les pages qui suivent)
//       { "capture": "captures/tableau.png" }      (image fixe, sans le curseur)
//     ] }
//
// Une étape = une seule action. Les chemins de « capture » partent du dossier du scénario
// (ou de « $JARVIS_LIVRABLES/… »). La sortie est un film .webm.
//
// Le film commence avant le premier affichage : un fichier <sortie>.json indique à monter.py où
// commence la partie utile. N'enregistre jamais la production ni de vraies données de clients.
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const S = require('./_studio.cjs');

const { libres } = S.arguments_(process.argv.slice(2), {});
if (libres.length !== 2) S.erreur('usage : node enregistrer.cjs scenario.json sortie.webm');
const [fichier, sortie] = libres.map((f) => path.resolve(f));
const sc = S.lireJson(fichier);
const base = path.dirname(fichier);
const largeur = Number(sc.largeur) || 1600;
const hauteur = Number(sc.hauteur) || 1000;
if (!Array.isArray(sc.etapes) || !sc.etapes.length) S.erreur('le scénario ne contient aucune étape');
if (!/\.webm$/i.test(sortie)) S.erreur('le film de sortie doit se terminer par .webm (monter.py le convertira en .mp4)');
const ACTIONS = ['aller', 'attendre', 'attendre_selecteur', 'cliquer', 'survoler', 'ecrire', 'touche', 'defiler', 'masquer', 'capture'];
sc.etapes.forEach((e, n) => {
  const cles = e && typeof e === 'object' && !Array.isArray(e) ? Object.keys(e) : [];
  if (cles.length !== 1) S.erreur(`étape ${n + 1} : une étape contient exactement une action (${JSON.stringify(e)})`);
  if (!ACTIONS.includes(cles[0])) S.erreur(`étape ${n + 1} : action inconnue « ${cles[0]} » (actions : ${ACTIONS.join(', ')})`);
  if (cles[0] === 'ecrire' && (!e.ecrire || !e.ecrire.dans || e.ecrire.texte === undefined)) S.erreur(`étape ${n + 1} : « ecrire » attend { "dans": sélecteur, "texte": … }`);
});
// Un ancien film ne doit pas passer pour le résultat d'un enregistrement qui échoue.
for (const f of [sortie, `${sortie}.json`]) fs.rmSync(f, { force: true });

// Curseur visible (un enregistrement sans tête n'en a pas) et onde au clic.
const CURSEUR = () => {
  const poser = () => {
    if (document.getElementById('__jarvis_curseur')) return;
    const c = document.createElement('div');
    c.id = '__jarvis_curseur';
    c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:26px;height:26px;' +
      'transform:translate(-100px,-100px);transition:transform 40ms linear;' +
      'filter:drop-shadow(0 2px 4px rgba(0,0,0,.45))';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15.5 9.2-6.8 1.7-3.5 6.4z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', (e) => { c.style.transform = `translate(${e.clientX - 4}px,${e.clientY - 2}px)`; }, true);
    addEventListener('mousedown', (e) => {
      const o = document.createElement('div');
      o.style.cssText = `position:fixed;left:${e.clientX - 18}px;top:${e.clientY - 18}px;width:36px;height:36px;border-radius:50%;` +
        'border:3px solid rgba(91,140,255,.9);z-index:2147483646;pointer-events:none';
      document.documentElement.appendChild(o);
      o.animate([{ transform: 'scale(.4)', opacity: 1 }, { transform: 'scale(1.8)', opacity: 0 }], { duration: 520, easing: 'ease-out' })
        .finished.then(() => o.remove());
    }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', poser); else poser();
};

(async () => {
  const nav = await S.navigateur();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-film-'));
  const contexte = await nav.newContext({
    viewport: { width: largeur, height: hauteur }, deviceScaleFactor: 1, locale: sc.langue || 'fr-FR',
    recordVideo: { dir: tmp, size: { width: largeur, height: hauteur } },
  });
  if (sc.curseur !== false) await contexte.addInitScript(CURSEUR);
  // Zones à flouter : la règle est réinjectée dans chaque nouvelle page, pas seulement dans celle en cours.
  const FLOU = (selecteurs) => {
    const poser = () => {
      const st = document.createElement('style');
      st.textContent = `${selecteurs}{filter:blur(9px)!important;user-select:none!important}`;
      document.documentElement.appendChild(st);
    };
    if (document.documentElement) poser(); else addEventListener('DOMContentLoaded', poser);
  };
  const page = await contexte.newPage();
  const depart = Date.now();
  let debutUtile = null;
  let souris = { x: largeur / 2, y: hauteur / 2 };
  let code = 0;

  const viser = async (selecteur) => {
    const cible = page.locator(selecteur).first();
    await cible.waitFor({ state: 'visible', timeout: 15000 });
    await cible.scrollIntoViewIfNeeded();
    const b = await cible.boundingBox();
    if (!b) throw new Error(`élément invisible : ${selecteur}`);
    const x = b.x + b.width / 2;
    const y = b.y + b.height / 2;
    const pas = Math.max(12, Math.round(Math.hypot(x - souris.x, y - souris.y) / 22));
    await page.mouse.move(x, y, { steps: pas });   // déplacement progressif : le curseur se voit bouger
    souris = { x, y };
    await page.waitForTimeout(180);
    return cible;
  };

  try {
    for (const [n, e] of sc.etapes.entries()) {
      const [action, valeur] = Object.entries(e)[0] || [];
      try {
        if (action === 'aller') {
          // « load » et non « networkidle » : une application qui garde une connexion ouverte n'est jamais « au repos ».
          await page.goto(valeur, { waitUntil: 'load', timeout: 45000 });
          await page.waitForTimeout(400);
          if (debutUtile === null) debutUtile = (Date.now() - depart) / 1000;
        } else if (action === 'attendre') await page.waitForTimeout(Number(valeur) || 500);
        else if (action === 'attendre_selecteur') await page.locator(valeur).first().waitFor({ state: 'visible', timeout: 20000 });
        else if (action === 'cliquer') { await viser(valeur); await page.mouse.down(); await page.waitForTimeout(70); await page.mouse.up(); await page.waitForTimeout(350); }
        else if (action === 'survoler') await viser(valeur);
        else if (action === 'ecrire') {
          await viser(valeur.dans); await page.mouse.down(); await page.mouse.up();
          await page.keyboard.type(String(valeur.texte), { delay: Number(valeur.delai) || 55 });
        } else if (action === 'touche') await page.keyboard.press(valeur);
        else if (action === 'defiler') {
          await page.evaluate((y) => window.scrollBy({ top: y, behavior: 'smooth' }), Number(valeur) || 400);
          await page.waitForTimeout(900);
        } else if (action === 'masquer') {
          // Un sélecteur qui n'est pas du CSS (« text=… ») ne flouterait rien, sans le dire.
          const valide = await page.evaluate((sel) => { try { document.querySelector(sel); return true; } catch (_) { return false; } }, valeur);
          if (!valide) throw new Error('« masquer » attend un sélecteur CSS (par exemple .email ou #compte), pas un sélecteur de texte');
          await contexte.addInitScript(FLOU, valeur);   // pages suivantes
          await page.evaluate(FLOU, valeur);            // page en cours
        } else if (action === 'capture') {
          const dest = S.chemin(base, valeur);
          fs.mkdirSync(path.dirname(dest), { recursive: true });
          await page.evaluate(() => { const c = document.getElementById('__jarvis_curseur'); if (c) c.style.visibility = 'hidden'; });
          await page.screenshot({ path: dest });
          await page.evaluate(() => { const c = document.getElementById('__jarvis_curseur'); if (c) c.style.visibility = ''; });
          console.log(`Capture écrite : ${dest}`);
        } else throw new Error(`action inconnue « ${action} »`);
      } catch (err) {
        throw new Error(`étape ${n + 1} (${JSON.stringify(e)}) : ${String(err.message).split('\n')[0]}`);
      }
    }
    await page.waitForTimeout(400);
  } catch (err) {
    console.error(`Erreur : ${err.message}`);
    code = 1;
  }
  const duree = (Date.now() - depart) / 1000;
  const video = page.video();
  await contexte.close();   // termine l'écriture du film
  await nav.close();
  if (video && code === 0) {
    fs.mkdirSync(path.dirname(sortie), { recursive: true });
    fs.copyFileSync(await video.path(), sortie);
    fs.writeFileSync(`${sortie}.json`, JSON.stringify({ debut_utile: Number(((debutUtile ?? 0) + 0.15).toFixed(2)), duree: Number(duree.toFixed(2)), largeur, hauteur }, null, 2));
    console.log(`Film écrit : ${sortie} (${duree.toFixed(1)} s, partie utile à partir de ${(debutUtile ?? 0).toFixed(1)} s)`);
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  process.exit(code);
})();
