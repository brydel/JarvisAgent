// Pilote de capture de la Bibliothèque de références (appelé par lib/jarvis/capture_site.py, jamais à la main).
//
// Entrée : un objet JSON sur l'entrée standard { url, dossier, mandataire, gabarits, delai_navigation_ms,
// hauteur_max, requetes_max, texte_max, sections_max }. Sortie : UNE ligne JSON sur la sortie standard
// (le résultat, ou { erreur }). Les captures sont écrites dans `dossier` sous des noms fixes.
//
// La page est NON FIABLE : contexte neuf par gabarit (aucun stockage persistant), téléchargements refusés,
// service workers bloqués, fenêtres surgissantes fermées, boîtes de dialogue rejetées. Tout le trafic passe par
// le mandataire de garde (anti-SSRF, résolution épinglée) ; Chromium ne résout aucun nom lui-même.
'use strict';
const { execSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function playwright() {
  const pistes = [process.env.JARVIS_PLAYWRIGHT, 'playwright',
    path.join(__dirname, '..', 'studio', 'board-v2', 'node_modules', 'playwright')].filter(Boolean);
  for (const p of pistes) { try { return require(p); } catch (_) { /* piste suivante */ } }
  try {
    const racine = execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
    return require(path.join(racine, 'playwright'));
  } catch (_) { /* absent */ }
  throw new Error('Playwright introuvable : installe le studio (./install.sh --studio) ou lance « npm ci » dans studio/board-v2');
}

const PRIVE = /^(localhost|.*\.localhost|.*\.local|.*\.internal|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.|\[?::1\]?$|\[?f[cde])/i;

// Exécutée DANS la page (environnement non fiable) : ne renvoie que des données simples, revalidées côté Python.
function extraire(limites) {
  const txt = (v, n) => String(v == null ? '' : v).replace(/\s+/g, ' ').trim().slice(0, n);
  const meta = (noms) => {
    for (const n of noms) {
      const e = document.querySelector(`meta[name="${n}"], meta[property="${n}"]`);
      if (e && e.getAttribute('content')) return txt(e.getAttribute('content'), 600);
    }
    return '';
  };
  const visible = (e) => {
    try {
      if (e.checkVisibility && !e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    } catch (_) { return false; }
  };
  const hauteurPage = Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0);
  const IGNORES = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'IFRAME', 'CANVAS', 'VIDEO', 'AUDIO', 'OBJECT', 'SELECT', 'TEXTAREA']);
  const BLOCS = new Set(['P', 'DIV', 'LI', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'MAIN', 'ASIDE', 'BLOCKQUOTE', 'PRE', 'TR', 'DD', 'DT', 'FIGCAPTION', 'BR', 'UL', 'OL', 'TABLE', 'NAV', 'FORM']);
  const sections = [{ titre: '', niveau: 0, texte: [], y: 0 }];
  let total = 0;
  const parcourir = (noeud) => {
    if (total > limites.texte_max || sections.length > limites.sections_max) return;
    if (noeud.nodeType === Node.TEXT_NODE) {
      const t = noeud.nodeValue.replace(/\s+/g, ' ');
      if (t.trim()) { sections[sections.length - 1].texte.push(t); total += t.length; }
      return;
    }
    if (noeud.nodeType !== Node.ELEMENT_NODE || IGNORES.has(noeud.tagName.toUpperCase())) return;
    if (noeud.getAttribute('aria-hidden') === 'true' || !visible(noeud)) {
      // « display: contents » n'a pas de boîte mais ses enfants sont visibles
      if (!(getComputedStyle(noeud).display === 'contents')) return;
    }
    const balise = noeud.tagName.toUpperCase();
    if (balise === 'H1' || balise === 'H2' || balise === 'H3') {
      const titre = txt(noeud.innerText || noeud.textContent, 200);
      if (titre) {
        const r = noeud.getBoundingClientRect();
        sections.push({ titre, niveau: Number(balise[1]), texte: [], y: Math.max(0, r.top + window.scrollY) });
        return;
      }
    }
    for (const enfant of noeud.childNodes) parcourir(enfant);
    // fin de bloc : saut de ligne ; fin d'un élément qui n'est pas du texte courant (bouton, lien, puce flex…) :
    // une espace, sinon « Accueil » et « Board » voisins se collent en « AccueilBoard »
    if (BLOCS.has(balise)) sections[sections.length - 1].texte.push('\n');
    else if (balise === 'A' || balise === 'BUTTON' || getComputedStyle(noeud).display !== 'inline') sections[sections.length - 1].texte.push(' ');
  };
  if (document.body) parcourir(document.body);
  const propres = sections.map((s, i) => {
    // colonnes côte à côte : la zone s'arrête au prochain titre situé plus bas, pas au voisin de la même ligne
    const suivante = sections.slice(i + 1).find((x) => x.y > s.y + 4);
    const brute = suivante ? suivante.y - s.y : hauteurPage - s.y;
    return { titre: s.titre, niveau: s.niveau, y: Math.round(s.y), hauteur: Math.round(Math.max(40, Math.min(brute, 4000))),
      texte: s.texte.join('').replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim().slice(0, 40000) };
  }).filter((s) => s.titre || s.texte);

  const style = (sel) => { const e = document.querySelector(sel); return e && visible(e) ? getComputedStyle(e) : null; };
  const premiere = (famille) => txt(String(famille || '').split(',')[0].replace(/["']/g, ''), 80);
  const roles = {};
  for (const [role, sel] of [['corps', 'body'], ['titre', 'h1'], ['sous_titre', 'h2'], ['bouton', 'button, a[class*="btn"], a[class*="button"], [role="button"]'], ['code', 'code, pre']]) {
    const s = style(sel);
    if (s) roles[role] = premiere(s.fontFamily);
  }
  let declarees = [];
  try { declarees = Array.from(document.fonts).filter((f) => f.status === 'loaded').map((f) => premiere(f.family)); } catch (_) { /* API absente */ }

  const entete = document.querySelector('header, [role="banner"]');
  const pied = document.querySelector('footer, [role="contentinfo"]');
  const dans = (e, conteneur) => !!(conteneur && conteneur.contains(e));
  const liens = [];
  for (const a of Array.from(document.querySelectorAll('a[href]')).slice(0, 1500)) {
    let u;
    try { u = new URL(a.getAttribute('href'), document.baseURI); } catch (_) { continue; }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') continue;
    u.hash = '';
    liens.push({ url: u.href.slice(0, 2048), texte: txt(a.innerText || a.getAttribute('aria-label') || a.title, 120),
      externe: u.hostname !== location.hostname, zone: dans(a, entete) ? 'entete' : dans(a, pied) ? 'pied' : 'corps' });
  }
  const poids = (l) => (l.zone === 'entete' ? 0 : l.externe ? 1 : l.zone === 'corps' ? 2 : 3);
  liens.sort((a, b) => poids(a) - poids(b));

  const h1 = Array.from(document.querySelectorAll('h1')).find(visible);
  let heros = null;
  if (h1) {
    const r = h1.getBoundingClientRect();
    const zone = h1.closest('section, header, main, [class*="hero"]') || h1.parentElement;
    const appel = zone ? Array.from(zone.querySelectorAll('a, button')).filter(visible).find((e) => {
      const t = txt(e.innerText, 80); return t.length > 1 && t.length < 60 && !dans(e, document.querySelector('nav'));
    }) : null;
    heros = { titre: txt(h1.innerText, 200), appel_action: appel ? txt(appel.innerText, 80) : '',
      visible_d_emblee: r.top + window.scrollY < window.innerHeight };
  }
  const bouton = style('button:not([disabled]), a[class*="btn"], a[class*="button"], [role="button"]');
  const lien = style('main a, a');
  const corps = document.body ? getComputedStyle(document.body) : null;
  const fondHtml = getComputedStyle(document.documentElement).backgroundColor;
  const transparent = (c) => !c || c === 'transparent' || /rgba\(.*,\s*0\)$/.test(c);
  return {
    titre: txt(document.title, 300) || meta(['og:title', 'twitter:title']),
    description: meta(['description', 'og:description', 'twitter:description']),
    langue: txt(document.documentElement.lang, 12), url_finale: location.href.slice(0, 2048),
    sections: propres.slice(0, limites.sections_max),
    polices: { roles, declarees: Array.from(new Set(declarees)).slice(0, 30) },
    couleurs_css: { fond: corps && !transparent(corps.backgroundColor) ? corps.backgroundColor : (transparent(fondHtml) ? 'rgb(255, 255, 255)' : fondHtml),
      texte: corps ? corps.color : '', accent: bouton && !transparent(bouton.backgroundColor) ? bouton.backgroundColor : '', lien: lien ? lien.color : '' },
    liens: liens.slice(0, 400),
    structure: { entete: !!entete, navigation: document.querySelectorAll('nav a, header a').length, principal: !!document.querySelector('main, [role="main"]'),
      pied: !!pied, heros, images: document.images.length, boutons: document.querySelectorAll('button, [role="button"], input[type="submit"]').length,
      formulaires: document.forms.length, hauteur_page: hauteurPage },
  };
}

async function defiler(page, hauteurMax) {
  // fait apparaître les images paresseuses, sans dépasser 6 s ni la hauteur maximale
  await page.evaluate(async (max) => {
    const fin = Date.now() + 6000;
    const total = Math.min(document.documentElement.scrollHeight, max);
    for (let y = 0; y < total && Date.now() < fin; y += Math.round(window.innerHeight * 0.8)) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 90));
    }
    window.scrollTo(0, 0);
  }, hauteurMax).catch(() => undefined);
  await page.waitForTimeout(350);
}

async function gabarit(navigateur, cfg, nom, [largeur, hauteur], compteur) {
  const mobile = nom === 'mobile';
  const contexte = await navigateur.newContext({
    viewport: { width: largeur, height: hauteur }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile,
    acceptDownloads: false, serviceWorkers: 'block', locale: 'fr-FR', permissions: [], colorScheme: 'light',
    reducedMotion: 'reduce',
    ...(mobile ? { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' } : {}),
  });
  try {
    await contexte.route('**/*', (route) => {
      const requete = route.request();
      let u;
      try { u = new URL(requete.url()); } catch (_) { return route.abort('blockedbyclient'); }
      compteur.n += 1;
      if ((u.protocol !== 'http:' && u.protocol !== 'https:') || u.username || u.password) return route.abort('blockedbyclient');
      if (compteur.n > cfg.requetes_max) return route.abort('blockedbyclient');
      const port = u.port || (u.protocol === 'https:' ? '443' : '80');
      if (!cfg.prives_permis && PRIVE.test(u.hostname) && !(cfg.exceptions || []).includes(`${u.hostname}:${port}`)) {
        compteur.refus += 1;  // refus immédiat ; le mandataire de garde aurait refusé de toute façon
        return route.abort('addressunreachable');
      }
      if (requete.resourceType() === 'media') return route.abort('blockedbyclient');  // pas de vidéo ni d'audio
      return route.continue();
    });
    const page = await contexte.newPage();
    contexte.on('page', (p) => { if (p !== page) p.close().catch(() => undefined); });
    page.on('dialog', (d) => d.dismiss().catch(() => undefined));
    page.on('download', (d) => d.cancel().catch(() => undefined));
    const reponse = await page.goto(cfg.url, { waitUntil: 'domcontentloaded', timeout: cfg.delai_navigation_ms });
    if (!reponse) throw new Error('la page ne répond pas');
    const statut = reponse.status();
    if (statut >= 400) throw new Error(`le site répond ${statut}`);
    const type = String(reponse.headers()['content-type'] || '').split(';')[0].trim().toLowerCase();
    if (type && type !== 'text/html' && type !== 'application/xhtml+xml') throw new Error(`type de contenu inattendu : ${type}`);
    await page.waitForLoadState('load', { timeout: 10000 }).catch(() => undefined);
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => undefined);
    await defiler(page, cfg.hauteur_max);
    const donnees = mobile ? {} : await page.evaluate(extraire, { texte_max: cfg.texte_max, sections_max: cfg.sections_max });
    const fichiers = {};
    const vue = path.join(cfg.dossier, `${nom}_vue.jpg`);
    await page.screenshot({ path: vue, type: 'jpeg', quality: 86, animations: 'disabled', caret: 'hide', timeout: 20000 });
    fichiers[`${nom}_vue`] = { largeur, hauteur };
    const totale = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)).catch(() => hauteur);
    const pleine = path.join(cfg.dossier, `${nom}_page.jpg`);
    if (totale <= cfg.hauteur_max) {
      await page.screenshot({ path: pleine, type: 'jpeg', quality: 80, fullPage: true, animations: 'disabled', caret: 'hide', timeout: 30000 });
      fichiers[`${nom}_page`] = { largeur, hauteur: Math.max(hauteur, Math.round(totale)), tronquee: false };
    } else {  // page interminable : on s'arrête à la hauteur maximale
      await page.screenshot({ path: pleine, type: 'jpeg', quality: 80, fullPage: true, clip: { x: 0, y: 0, width: largeur, height: cfg.hauteur_max },
        animations: 'disabled', caret: 'hide', timeout: 30000 });
      fichiers[`${nom}_page`] = { largeur, hauteur: cfg.hauteur_max, tronquee: true };
    }
    return { donnees, fichiers, statut };
  } finally {
    await contexte.close().catch(() => undefined);
  }
}

// Palette dominante, calculée dans une page À NOUS (vide, sans réseau) à partir de la capture d'écran.
async function palette(navigateur, image) {
  const contexte = await navigateur.newContext({ javaScriptEnabled: true, serviceWorkers: 'block' });
  try {
    await contexte.route('**/*', (route) => route.abort('blockedbyclient'));
    const page = await contexte.newPage();
    const pixels = await page.evaluate(async (donnees) => {
      const img = new Image();
      await new Promise((ok, non) => { img.onload = ok; img.onerror = non; img.src = donnees; });
      const c = document.createElement('canvas');
      c.width = 120; c.height = 75;
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0, c.width, c.height);
      return Array.from(ctx.getImageData(0, 0, c.width, c.height).data);
    }, 'data:image/jpeg;base64,' + fs.readFileSync(image).toString('base64'));
    const seaux = new Map();
    for (let i = 0; i < pixels.length; i += 4) {
      const cle = ((pixels[i] >> 3) << 10) | ((pixels[i + 1] >> 3) << 5) | (pixels[i + 2] >> 3);
      const s = seaux.get(cle) || { n: 0, r: 0, v: 0, b: 0 };
      s.n += 1; s.r += pixels[i]; s.v += pixels[i + 1]; s.b += pixels[i + 2];
      seaux.set(cle, s);
    }
    const total = pixels.length / 4;
    const couleurs = Array.from(seaux.values()).map((s) => ({ n: s.n, r: s.r / s.n, v: s.v / s.n, b: s.b / s.n })).sort((a, b) => b.n - a.n);
    const retenues = [];
    for (const c of couleurs) {  // fusionne les teintes voisines pour ne garder que des couleurs distinctes
      const proche = retenues.find((r) => Math.hypot(r.r - c.r, r.v - c.v, r.b - c.b) < 36);
      if (proche) { proche.n += c.n; continue; }
      if (retenues.length < 24) retenues.push({ ...c });
    }
    const hex = (x) => Math.round(x).toString(16).padStart(2, '0');
    return retenues.sort((a, b) => b.n - a.n).slice(0, 6).filter((c) => c.n / total >= 0.004)
      .map((c) => ({ hex: `#${hex(c.r)}${hex(c.v)}${hex(c.b)}`, part: Number((c.n / total).toFixed(4)) }));
  } finally {
    await contexte.close().catch(() => undefined);
  }
}

async function lancer(chromium, cfg, bacASable) {
  const options = {
    headless: true, chromiumSandbox: bacASable,
    proxy: { server: cfg.mandataire, bypass: '<-loopback>' },
    args: ['--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1', '--disable-quic', '--no-first-run', '--disable-sync',
      '--disable-background-networking', '--disable-extensions', '--disable-component-update', '--no-default-browser-check',
      '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', '--force-color-profile=srgb'],
  };
  if (process.env.JARVIS_CHROMIUM) options.executablePath = process.env.JARVIS_CHROMIUM;
  return chromium.launch(options);
}

async function principal() {
  const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
  if (!/^https?:\/\//i.test(cfg.url) || !/^http:\/\/127\.0\.0\.1:\d+$/.test(cfg.mandataire)) throw new Error('configuration de capture invalide');
  const { chromium } = playwright();
  let navigateur;
  let bacASable = true;
  try { navigateur = await lancer(chromium, cfg, true); } catch (_) {
    bacASable = false;  // certains postes (WSL, conteneurs) n'offrent pas le bac à sable de Chromium
    try { navigateur = await lancer(chromium, cfg, false); } catch (e) {
      throw new Error(`Chromium ne démarre pas (${String(e.message).split('\n')[0]}) : npx playwright install chromium`);
    }
  }
  try {
    const compteur = { n: 0, refus: 0 };
    const bureau = await gabarit(navigateur, cfg, 'bureau', cfg.gabarits.bureau, compteur);
    let mobile = { fichiers: {} };
    try { mobile = await gabarit(navigateur, cfg, 'mobile', cfg.gabarits.mobile, compteur); } catch (e) {
      bureau.donnees.mobile_erreur = String(e.message).split('\n')[0].slice(0, 200);
    }
    let couleurs = [];
    try { couleurs = await palette(navigateur, path.join(cfg.dossier, 'bureau_vue.jpg')); } catch (_) { /* palette facultative */ }
    return { ...bureau.donnees, palette: couleurs, fichiers: { ...bureau.fichiers, ...mobile.fichiers }, statut_http: bureau.statut,
      bac_a_sable: bacASable, requetes: compteur.n, refus_navigateur: compteur.refus };
  } finally {
    await navigateur.close().catch(() => undefined);
  }
}

// La sortie peut dépasser le tampon du tube (64 Ko) : on ne quitte qu'une fois tout écrit.
const rendre = (r) => process.stdout.write(JSON.stringify(r) + '\n', () => process.exit(0));
principal().then(rendre)
  .catch((e) => {
    let message = String(e && e.message ? e.message : e).split('\n')[0].slice(0, 280);
    if (/ERR_TUNNEL_CONNECTION_FAILED|ERR_PROXY|ERR_ADDRESS_UNREACHABLE|ERR_NAME_NOT_RESOLVED/.test(message)) message = 'adresse refusée ou injoignable (réseau local, boucle locale, métadonnées ou hôte inconnu)';
    else if (/Timeout/.test(message)) message = 'le site met trop de temps à répondre';
    rendre({ erreur: message });
  });
