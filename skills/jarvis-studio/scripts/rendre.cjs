#!/usr/bin/env node
// rendre.cjs — transforme un storyboard en vidéo animée (titres, captures mises en scène, écran de fin).
//
//   node rendre.cjs storyboard.json sortie.mp4 [--format 16:9|9:16|1:1|4:5] [--ips 30]
//   node rendre.cjs storyboard.json sortie.png --image 4.2 [--format 1:1]     (une image fixe à 4,2 s)
//
// Le rendu est fait image par image : chaque image est calculée pour son instant exact, puis
// encodée par ffmpeg. Le résultat est fluide et identique à chaque fois, même sur un PC chargé.
// Format du storyboard : voir SKILL.md.
'use strict';
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const S = require('./_studio.cjs');

const { libres, opts } = S.arguments_(process.argv.slice(2), { format: 'val', ips: 'val', image: 'val', silencieux: 'bool' });
if (libres.length !== 2) S.erreur('usage : node rendre.cjs storyboard.json sortie.mp4 [--format 16:9] [--ips 30] [--image secondes]');
const [fichierSb, sortie] = libres.map((f) => path.resolve(f));
const ips = Math.max(12, Math.min(60, Number(opts.ips) || 30));
const sb = S.lireJson(fichierSb);
const { largeur, hauteur } = S.format(opts.format || sb.format);
const base = path.dirname(fichierSb);
const dire = (m) => { if (!opts.silencieux) console.log(m); };

const avertissements = S.verifierStoryboard(sb);
if (!opts.image && !S.ffmpegPresent()) S.erreur('ffmpeg introuvable : sudo apt install ffmpeg', 3);
if (!opts.image && !/\.(mp4|mov|m4v)$/i.test(sortie)) S.erreur('la vidéo de sortie doit se terminer par .mp4');
avertissements.forEach((a) => console.error(`Attention : ${a}`));

// Dossier de travail, supprimé quelle que soit la façon dont le script se termine.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-studio-'));
process.on('exit', () => { try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (_) { /* rien */ } });

// Chemins du storyboard (relatifs à lui, ou « $JARVIS_LIVRABLES/… ») → adresses file:// lisibles par la page.
const distant = (f) => /^(https?:|data:|file:)/.test(f);
const adresse = (f) => (distant(f) ? f : pathToFileURL(S.chemin(base, f)).href);
const absent = (f) => !distant(f) && !fs.existsSync(S.chemin(base, f));
const manquants = [];
if (sb.marque && sb.marque.logo) { if (absent(sb.marque.logo)) manquants.push(sb.marque.logo); else sb.marque.logo = adresse(sb.marque.logo); }
sb.scenes.forEach((s, i) => {
  if (s.image) { if (absent(s.image)) manquants.push(s.image); else s.image = adresse(s.image); }
  if (s.video) {
    if (absent(s.video)) { manquants.push(s.video); return; }
    // Clip du produit : ses images sont extraites à la cadence du rendu, la page les affiche une à une.
    const dossier = path.join(tmp, `clip-${i}`);
    fs.mkdirSync(dossier);
    const duree = Math.max(0.8, Number(s.duree) || 3);
    const args = ['-hide_banner', '-loglevel', 'error', '-y', '-ss', String(Number(s.debut) || 0), '-t', String(duree + 0.5),
                  '-i', S.chemin(base, s.video), '-vf', `fps=${ips},scale=1600:-2:flags=lanczos`, '-q:v', '3',
                  path.join(dossier, '%05d.jpg')];
    const r = spawnSync('ffmpeg', args, { encoding: 'utf8' });
    const nombre = fs.readdirSync(dossier).length;
    if (r.status !== 0 || !nombre) S.erreur(`impossible de lire le clip ${s.video} : ${(r.stderr || '').trim().split('\n').pop()}`);
    s.images_clip = { dossier: pathToFileURL(dossier).href, nombre, ips };
    if (!s.proportions) {
      const p = spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', S.chemin(base, s.video)], { encoding: 'utf8' });
      const [l, h] = (p.stdout || '').trim().split(',').map(Number);
      if (l && h) s.proportions = [l, h];
    }
  }
});
if (manquants.length) S.erreur(`fichier(s) introuvable(s) à côté du storyboard : ${manquants.join(', ')}`);

(async () => {
  const nav = await S.navigateur();
  let code = 0;
  try {
    const page = await nav.newPage({ viewport: { width: largeur, height: hauteur }, deviceScaleFactor: 1 });
    await page.addInitScript((storyboard) => { window.STORYBOARD = storyboard; }, sb);
    await page.goto(pathToFileURL(path.join(__dirname, 'scenes.html')).href);
    const info = await page.evaluate(() => window.jarvis.pret());
    if (info.images_introuvables.length) throw new Error(`image(s) illisible(s) : ${info.images_introuvables.join(', ')}`);
    const duree = info.duree / 1000;

    if (opts.image !== undefined) {
      const t = Math.max(0, Math.min(info.duree, Number(opts.image) * 1000));
      await page.evaluate((ms) => window.jarvis.aller(ms), t);
      await page.screenshot({ path: sortie, type: sortie.toLowerCase().endsWith('.png') ? 'png' : 'jpeg' });
      dire(`Image écrite : ${sortie} (${largeur}×${hauteur}, instant ${(t / 1000).toFixed(1)} s)`);
      return;
    }

    const images = Math.round(duree * ips);
    dire(`Rendu : ${info.scenes} scène(s), ${duree.toFixed(1)} s, ${largeur}×${hauteur}, ${ips} images/s (${images} images)…`);
    fs.mkdirSync(path.dirname(sortie), { recursive: true });
    const ff = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
      '-f', 'image2pipe', '-framerate', String(ips), '-c:v', 'mjpeg', '-i', '-',
      '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', String(ips),
      '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', sortie], { stdio: ['pipe', 'inherit', 'pipe'] });
    let ffErr = '';
    let ffFini = null;   // code de sortie de ffmpeg, dès qu'il s'arrête
    ff.stderr.on('data', (d) => { ffErr += d; });
    ff.stdin.on('error', () => { /* ffmpeg est mort : on le constate ci-dessous, sans planter sur EPIPE */ });
    const fini = new Promise((ok) => ff.on('close', (c) => { ffFini = c ?? 1; ok(ffFini); }));
    const echec = () => new Error(`ffmpeg a échoué : ${ffErr.trim().split('\n').pop() || `code ${ffFini}`}`);
    for (let i = 0; i < images; i++) {
      if (ffFini !== null) throw echec();   // sans cela, on attendrait pour toujours un ffmpeg qui n'écoute plus
      await page.evaluate((ms) => window.jarvis.aller(ms), (i * 1000) / ips);
      const jpeg = await page.screenshot({ type: 'jpeg', quality: 95 });
      if (!ff.stdin.write(jpeg)) await Promise.race([new Promise((ok) => ff.stdin.once('drain', ok)), fini]);
      if (!opts.silencieux && i && i % (ips * 5) === 0) dire(`  ${(i / ips).toFixed(0)} s / ${duree.toFixed(0)} s`);
    }
    ff.stdin.end();
    const statut = await fini;
    if (statut !== 0) throw echec();
    dire(`Vidéo écrite : ${sortie}`);
    dire('Contrôle-la maintenant : python3 verifier.py ' + sortie);
  } catch (e) {
    console.error(`Erreur : ${e.message}`);
    code = 1;
  } finally {
    await nav.close();
  }
  process.exit(code);
})();
