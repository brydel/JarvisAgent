// Outils communs du studio Jarvis : trouver Playwright, lancer Chromium, formats de sortie.
'use strict';
const { execSync, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const FORMATS = { '16:9': [1920, 1080], '9:16': [1080, 1920], '1:1': [1080, 1080], '4:5': [1080, 1350] };

function erreur(message, code = 2) {
  console.error(`Erreur : ${message}`);
  process.exit(code);
}

function playwright() {
  try { return require('playwright'); } catch (_) { /* pas dans le projet : on cherche l'installation globale */ }
  try {
    const racine = execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    return require(path.join(racine, 'playwright'));
  } catch (_) { /* absent */ }
  return erreur('Playwright introuvable. Installe le studio : ./install.sh --studio (dans le dépôt JarvisAgent).', 3);
}

async function navigateur() {
  const { chromium } = playwright();
  const options = { headless: true, args: ['--force-color-profile=srgb', '--font-render-hinting=none'] };
  if (process.env.JARVIS_CHROMIUM) options.executablePath = process.env.JARVIS_CHROMIUM;
  try {
    return await chromium.launch(options);
  } catch (e) {
    return erreur(`Chromium ne démarre pas (${String(e.message).split('\n')[0]}). Installe-le : npx playwright install --with-deps chromium`, 3);
  }
}

function format(nom) {
  const f = FORMATS[nom || '16:9'];
  if (!f) erreur(`format inconnu « ${nom} » (valeurs : ${Object.keys(FORMATS).join(', ')})`);
  return { largeur: f[0], hauteur: f[1] };
}

// Options « --cle valeur » et arguments libres.
function arguments_(argv, connues) {
  const libres = [];
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const cle = a.slice(2);
      if (!(cle in connues)) erreur(`option inconnue : ${a}`);
      if (connues[cle] === 'bool') opts[cle] = true;
      else { opts[cle] = argv[++i]; if (opts[cle] === undefined) erreur(`${a} attend une valeur`); }
    } else libres.push(a);
  }
  return { libres, opts };
}

// Chemin d'un fichier cité dans un JSON : « $JARVIS_LIVRABLES/… » et « ~/… » sont développés, un chemin
// relatif part du dossier du fichier JSON (et non du dossier courant).
function chemin(base, f) {
  let p = String(f);
  if (p.startsWith('$JARVIS_LIVRABLES')) {
    if (!process.env.JARVIS_LIVRABLES) erreur('la variable JARVIS_LIVRABLES n\'est pas définie : écris le chemin complet du fichier');
    p = process.env.JARVIS_LIVRABLES + p.slice('$JARVIS_LIVRABLES'.length);
  } else if (p.startsWith('~/')) {
    p = path.join(require('node:os').homedir(), p.slice(2));
  }
  return path.resolve(base, p);
}

const SCENES = {
  titre: { requis: ['titre'] },
  capture: { requis: [] },
  points: { requis: ['titre', 'points'] },
  chiffre: { requis: ['valeur'] },
  fin: { requis: ['titre'] },
};

// Vérifie un storyboard avant tout rendu : une faute de frappe dans un type de scène donnerait une
// image vide, que le contrôle technique ne sait pas voir. Renvoie la liste des avertissements.
function verifierStoryboard(sb) {
  if (!sb || typeof sb !== 'object' || !Array.isArray(sb.scenes) || !sb.scenes.length) erreur('le storyboard doit contenir une liste « scenes » non vide');
  const avertissements = [];
  sb.scenes.forEach((s, i) => {
    const ou = `scène ${i + 1}`;
    if (!s || typeof s !== 'object' || Array.isArray(s)) erreur(`${ou} : une scène est un objet { "type": …, "duree": … }`);
    if (!SCENES[s.type]) erreur(`${ou} : type « ${s.type} » inconnu (types : ${Object.keys(SCENES).join(', ')})`);
    for (const champ of SCENES[s.type].requis) {
      if (s[champ] === undefined || s[champ] === null || s[champ] === '') erreur(`${ou} (${s.type}) : champ « ${champ} » manquant`);
    }
    if (s.type === 'capture' && !s.image && !s.video) erreur(`${ou} (capture) : il faut « image » ou « video »`);
    if (s.type === 'points' && (!Array.isArray(s.points) || !s.points.length)) erreur(`${ou} (points) : « points » est une liste de phrases`);
    if (s.type === 'chiffre' && !Number.isFinite(Number(s.valeur))) erreur(`${ou} (chiffre) : « valeur » doit être un nombre`);
    if (s.reperes !== undefined && !Array.isArray(s.reperes)) erreur(`${ou} : « reperes » est une liste`);
    const d = Number(s.duree);
    if (s.duree !== undefined && !(d > 0)) erreur(`${ou} : « duree » doit être un nombre de secondes positif`);
    if (d > 60) erreur(`${ou} : ${d} s, c'est trop long pour un plan (60 s au plus)`);
    const limite = s.type === 'capture' ? 15 : 8;
    if (d > limite) avertissements.push(`${ou} (${s.type}) dure ${d} s : au-delà de ${limite} s sur le même plan, le spectateur décroche`);
  });
  return avertissements;
}

function ffmpegPresent() {
  return spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0;
}

function lireJson(fichier) {
  try { return JSON.parse(fs.readFileSync(fichier, 'utf8')); } catch (e) { return erreur(`${fichier} illisible : ${e.message}`); }
}

module.exports = { FORMATS, erreur, playwright, navigateur, format, arguments_, ffmpegPresent, lireJson, chemin, verifierStoryboard };
