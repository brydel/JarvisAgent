// Captures de démonstration de la Bibliothèque de références : quatre sites FICTIFS, écrits ici en HTML avec la palette
// et les polices annoncées par leur fiche (src/references/demo.ts), puis photographiés en 1440 × 900 et 390 × 844.
// Aucune ressource distante : polices embarquées (@fontsource) ou présentes sur le poste, illustrations dessinées en CSS.
//   node scripts/references-demo.mjs        → public/demo/ref-<site>-bureau.jpg et ref-<site>-mobile.jpg
import { chromium } from "@playwright/test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const SORTIE = path.join(ICI, "..", "public", "demo");
const police = (p) => pathToFileURL(path.join(ICI, "..", "node_modules", p)).href;
const POLICES = `
@font-face { font-family: "Newsreader"; src: url("${police("@fontsource-variable/newsreader/files/newsreader-latin-opsz-normal.woff2")}") format("woff2"); font-weight: 200 800; }
@font-face { font-family: "Instrument Sans"; src: url("${police("@fontsource-variable/instrument-sans/files/instrument-sans-latin-wdth-normal.woff2")}") format("woff2"); font-weight: 400 700; font-stretch: 75% 100%; }
@font-face { font-family: "IBM Plex Mono"; src: url("${police("@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2")}") format("woff2"); font-weight: 400; }
@font-face { font-family: "IBM Plex Mono"; src: url("${police("@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2")}") format("woff2"); font-weight: 500; }
* { box-sizing: border-box; } html, body { margin: 0; } body { -webkit-font-smoothing: antialiased; } a { color: inherit; text-decoration: none; }
`;

const SITES = {
  // Atelier Lumière — studio de design : Newsreader pour les titres, Inter pour le texte ; #F7F3EC, #1C1B19, #C8553D, #8A8578
  atelier: `<style>
    body { background: #F7F3EC; color: #1C1B19; font: 400 16px/26px Inter, sans-serif; }
    header { display: flex; align-items: center; justify-content: space-between; padding: 28px 64px; }
    header b { font: 500 22px/1 Newsreader, serif; } nav { display: flex; gap: 32px; font-size: 14px; color: #8A8578; }
    nav .cta { color: #1C1B19; border-bottom: 1px solid #1C1B19; }
    main { display: grid; grid-template-columns: 1.05fr 1fr; gap: 64px; padding: 56px 64px 0; align-items: end; }
    h1 { font: 400 92px/0.98 Newsreader, serif; letter-spacing: -0.02em; margin: 0 0 32px; }
    h1 em { font-style: normal; color: #C8553D; }
    p { max-width: 30em; margin: 0 0 32px; color: #4A4740; }
    .actions { display: flex; gap: 24px; align-items: center; font-size: 15px; }
    .actions a:first-child { background: #1C1B19; color: #F7F3EC; padding: 14px 24px; }
    .planche { height: 520px; background: #EDE6DA; position: relative; overflow: hidden; }
    .planche i { position: absolute; display: block; }
    .planche .a { left: 48px; top: 48px; width: 250px; height: 330px; background: #F7F3EC; box-shadow: 0 1px 0 #D9D0C1; }
    .planche .a::before { content: "Aa"; position: absolute; left: 24px; top: 16px; font: 400 96px/1 Newsreader, serif; color: #1C1B19; }
    .planche .a::after { content: ""; position: absolute; left: 24px; right: 24px; bottom: 28px; height: 64px; background: repeating-linear-gradient(#8A8578 0 2px, transparent 2px 14px); opacity: .45; }
    .planche .b { right: 48px; top: 96px; width: 220px; height: 220px; background: #C8553D; }
    .planche .c { right: 96px; bottom: 0; width: 320px; height: 150px; background: #1C1B19; }
    .planche .d { left: 120px; bottom: 40px; width: 120px; height: 16px; background: #8A8578; }
    footer { display: flex; gap: 64px; padding: 40px 64px; font-size: 13px; color: #8A8578; }
    footer b { display: block; font: 400 28px/1.2 Newsreader, serif; color: #1C1B19; }
    @media (max-width: 700px) { header { padding: 20px; } nav a:not(.cta) { display: none; } main { grid-template-columns: 1fr; gap: 32px; padding: 24px 20px 0; }
      h1 { font-size: 52px; margin-bottom: 20px; } .planche { height: 300px; } .planche .a { left: 20px; top: 24px; width: 150px; height: 210px; } .planche .a::before { font-size: 60px; }
      .planche .b { right: 20px; top: 48px; width: 130px; height: 130px; } .planche .c { right: 40px; width: 200px; height: 90px; } .planche .d { display: none; } footer { gap: 24px; padding: 24px 20px; } }
  </style>
  <header><b>Atelier Lumière</b><nav><a>Projets</a><a>Méthode</a><a>Prix</a><a>Journal</a><a class="cta">Écrire à l'atelier</a></nav></header>
  <main><div><h1>Des sites qui <em>respirent</em></h1>
    <p>Nous concevons des interfaces sobres, avec une grande place laissée au blanc et une hiérarchie typographique nette.</p>
    <div class="actions"><a>Voir les projets</a><a>Nos prix →</a></div></div>
    <div class="planche"><i class="a"></i><i class="b"></i><i class="c"></i><i class="d"></i></div></main>
  <footer><div><b>2 400 €</b>forfait vitrine, sans frais cachés</div><div><b>3 formules</b>le sur-mesure est chiffré après un atelier</div><div><b>Lyon</b>studio de quatre personnes</div></footer>`,

  // Nordkit — tableau de bord d'équipe : Inter et IBM Plex Mono ; #0E1119, #E8EAF2, #4CC38A, #22D3EE
  nordkit: `<style>
    body { background: #0E1119; color: #E8EAF2; font: 400 16px/26px Inter, sans-serif; }
    header { display: flex; align-items: center; gap: 40px; padding: 24px 64px; font-size: 14px; }
    header b { font-weight: 600; font-size: 17px; margin-right: auto; } header a { color: #9AA1B5; }
    header .cta { color: #0E1119; background: #E8EAF2; padding: 8px 16px; border-radius: 8px; }
    .heros { padding: 56px 64px 40px; max-width: 900px; }
    h1 { font: 600 68px/1.04 Inter, sans-serif; letter-spacing: -0.03em; margin: 0 0 20px; }
    .heros p { color: #9AA1B5; font-size: 18px; line-height: 28px; max-width: 34em; margin: 0 0 28px; }
    .heros a { display: inline-block; background: #4CC38A; color: #06150E; font-weight: 500; padding: 12px 20px; border-radius: 8px; }
    .heros small { margin-left: 16px; color: #9AA1B5; font: 400 13px/1 "IBM Plex Mono", monospace; }
    .produit { margin: 0 64px; border: 1px solid #232838; border-bottom: 0; border-radius: 16px 16px 0 0; background: #131722; display: grid; grid-template-columns: 220px 1fr; height: 420px; overflow: hidden; }
    .produit aside { border-right: 1px solid #232838; padding: 20px; font-size: 14px; color: #9AA1B5; display: grid; gap: 12px; align-content: start; }
    .produit aside b { color: #E8EAF2; font-weight: 500; background: #1B2030; margin: 0 -8px; padding: 6px 8px; border-radius: 6px; }
    .produit section { padding: 24px; }
    .produit h2 { margin: 0 0 4px; font: 500 16px/24px Inter, sans-serif; } .produit h2 + span { font: 400 12px/16px "IBM Plex Mono", monospace; color: #9AA1B5; }
    .lignes { margin-top: 20px; display: grid; gap: 0; }
    .lignes div { display: grid; grid-template-columns: 180px 1fr 64px; gap: 16px; align-items: center; height: 44px; border-top: 1px solid #232838; font-size: 14px; }
    .lignes i { display: block; height: 6px; border-radius: 3px; background: #2A3044; } .lignes i::after { content: ""; display: block; height: 100%; border-radius: 3px; background: #6E7690; width: var(--v); }
    .lignes div:first-child i::after { background: #4CC38A; } .lignes span { font: 400 12px/16px "IBM Plex Mono", monospace; color: #9AA1B5; text-align: right; }
    @media (max-width: 700px) { header { padding: 16px 20px; gap: 16px; } header a:not(.cta) { display: none; } .heros { padding: 32px 20px 28px; } h1 { font-size: 40px; }
      .heros p { font-size: 16px; line-height: 24px; } .heros small { display: block; margin: 16px 0 0; } .produit { margin: 0 20px; grid-template-columns: 1fr; height: 400px; } .produit aside { display: none; }
      .produit section { padding: 16px; } .lignes div { grid-template-columns: 150px 1fr 40px; gap: 12px; font-size: 13px; white-space: nowrap; } }
  </style>
  <header><b>Nordkit</b><a>Produit</a><a>Tarifs</a><a>Clients</a><a>Connexion</a><a class="cta">Essayer</a></header>
  <div class="heros"><h1>Le suivi d'équipe sans réunion</h1><p>Chacun écrit où il en est, une fois par jour. Nordkit en fait le point d'équipe, sans visio du lundi.</p>
    <a>Essayer gratuitement</a><small>gratuit jusqu'à 5 personnes</small></div>
  <div class="produit"><aside><b>Cette semaine</b><span>Projets</span><span>Personnes</span><span>Blocages</span><span>Archives</span></aside>
    <section><h2>Semaine 46</h2><span>12 points reçus · 2 blocages</span>
      <div class="lignes"><div>Refonte du tunnel<i style="--v:82%"></i><span>82 %</span></div><div>API de facturation<i style="--v:64%"></i><span>64 %</span></div>
        <div>Appli mobile 3.2<i style="--v:41%"></i><span>41 %</span></div><div>Migration des comptes<i style="--v:27%"></i><span>27 %</span></div><div>Centre d'aide<i style="--v:12%"></i><span>12 %</span></div></div></section></div>`,

  // Maison Verdier — boutique de thés : Bitstream Charter pour les titres, Instrument Sans pour le texte ; #F3EDE2, #2F3B2C, #B98B4E, #D9CBB3
  verdier: `<style>
    body { background: #F3EDE2; color: #2F3B2C; font: 400 16px/26px "Instrument Sans", sans-serif; }
    .bandeau { background: #2F3B2C; color: #F3EDE2; text-align: center; font-size: 13px; line-height: 36px; }
    header { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 24px 64px; font-size: 14px; }
    header nav { display: flex; gap: 28px; } header b { font: 400 28px/1 "Bitstream Charter", Charter, serif; letter-spacing: 0.02em; } header span { text-align: right; }
    main { display: grid; grid-template-columns: 1fr 1fr; min-height: 640px; }
    .photo { background: #D9CBB3; position: relative; overflow: hidden; }
    .photo .boite { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -46%); width: 250px; height: 340px; background: #2F3B2C; border-radius: 6px 6px 3px 3px; box-shadow: 28px 36px 0 rgba(47, 59, 44, .14); }
    .photo .boite::before { content: ""; position: absolute; left: -6px; right: -6px; top: -18px; height: 34px; background: #26301F; border-radius: 6px; }
    .photo .boite::after { content: "Verdier\\A Sencha d'Uji"; white-space: pre; position: absolute; left: 28px; right: 28px; top: 96px; padding: 24px 0; text-align: center; background: #F3EDE2; color: #2F3B2C; font: 400 22px/30px "Bitstream Charter", Charter, serif; border: 1px solid #B98B4E; outline: 4px solid #F3EDE2; }
    .photo .tasse { position: absolute; right: 13%; bottom: 14%; width: 120px; height: 62px; background: #F3EDE2; border-radius: 0 0 60px 60px; box-shadow: 14px 16px 0 rgba(47, 59, 44, .12); }
    .photo .tasse::before { content: ""; position: absolute; left: 8px; right: 8px; top: 0; height: 12px; background: #B98B4E; border-radius: 0 0 50% 50%; }
    .texte { padding: 72px 64px; align-self: center; }
    .texte small { font-size: 13px; color: #B98B4E; } h1 { font: 400 60px/1.06 "Bitstream Charter", Charter, serif; margin: 12px 0 20px; }
    .texte p { max-width: 28em; margin: 0 0 28px; color: #4C5648; } .prix { display: flex; align-items: baseline; gap: 16px; margin-bottom: 24px; font: 400 32px/1 "Bitstream Charter", Charter, serif; }
    .prix span { font: 400 14px/1 "Instrument Sans", sans-serif; color: #6B7466; } .texte a { display: inline-block; background: #2F3B2C; color: #F3EDE2; padding: 14px 28px; font-weight: 500; }
    .texte em { display: block; font-style: normal; margin-top: 16px; font-size: 13px; color: #6B7466; }
    @media (max-width: 700px) { header { grid-template-columns: 1fr auto; padding: 16px 20px; } header nav { display: none; } header b { font-size: 22px; } main { grid-template-columns: 1fr; }
      .photo { height: 340px; } .photo .boite { width: 150px; height: 210px; } .photo .boite::after { left: 14px; right: 14px; top: 56px; padding: 12px 0; font-size: 14px; line-height: 20px; }
      .photo .tasse { width: 80px; height: 42px; right: 10%; } .texte { padding: 28px 20px; } h1 { font-size: 36px; } }
  </style>
  <div class="bandeau">Livraison offerte dès 45 € d'achat</div>
  <header><nav><a>Thés verts</a><a>Thés noirs</a><a>Infusions</a><a>Coffrets</a></nav><b>Maison Verdier</b><span>Panier · 2</span></header>
  <main><div class="photo"><div class="boite"></div><div class="tasse"></div></div>
    <div class="texte"><small>Récolte de printemps · Uji, Japon</small><h1>Thés d'origine, torréfiés à la commande</h1>
      <p>Un sencha ombré trois semaines, cueilli à la main puis torréfié chez nous le jour de ton achat.</p>
      <div class="prix">18,50 €<span>la boîte de 100 g</span></div><a>Ajouter au panier</a><em>Expédié sous 48 h, en boîte consignée</em></div></main>`,

  // Carnet de bord — portfolio d'illustratrice : Instrument Sans étroit pour les titres, IBM Plex Mono pour les légendes ; #FCFBF8, #22201D, #E0457B, #F2B544
  carnet: `<style>
    body { background: #FCFBF8; color: #22201D; font: 400 13px/20px "IBM Plex Mono", monospace; }
    header { display: flex; align-items: baseline; justify-content: space-between; padding: 32px 64px 0; }
    header b { font: 600 20px/1 "Instrument Sans", sans-serif; font-stretch: 75%; } header nav { display: flex; gap: 32px; }
    h1 { font: 500 132px/0.9 "Instrument Sans", sans-serif; font-stretch: 75%; letter-spacing: -0.02em; margin: 40px 64px 32px; }
    .grille { display: grid; grid-template-columns: 1.3fr 1fr 0.8fr; gap: 24px; padding: 0 64px; }
    figure { margin: 0; } figure div { height: 380px; position: relative; overflow: hidden; } figcaption { padding-top: 12px; display: flex; justify-content: space-between; color: #6B665E; }
    .mer { background: #F2B544; } .mer::before { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 46%; background: #22201D; }
    .mer::after { content: ""; position: absolute; left: 58%; top: 20%; width: 120px; height: 120px; border-radius: 50%; background: #E0457B; }
    .mer i { position: absolute; left: 14%; bottom: 46%; width: 0; height: 0; border-left: 60px solid transparent; border-right: 60px solid transparent; border-bottom: 150px solid #FCFBF8; }
    .ville { background: #22201D; } .ville::before { content: ""; position: absolute; left: 12%; bottom: 0; width: 26%; height: 70%; background: #FCFBF8; }
    .ville::after { content: ""; position: absolute; left: 44%; bottom: 0; width: 34%; height: 46%; background: #E0457B; }
    .ville i { position: absolute; right: 12%; top: 14%; width: 44px; height: 44px; border-radius: 50%; background: #F2B544; }
    .gare { background: #E9E4DA; } .gare::before { content: ""; position: absolute; left: 0; right: 0; top: 52%; height: 10px; background: #22201D; }
    .gare::after { content: ""; position: absolute; left: 22%; top: 24%; width: 56%; height: 28%; background: #E0457B; border-radius: 80px 80px 0 0; }
    @media (max-width: 700px) { header { padding: 20px 20px 0; } header nav a:not(:last-child) { display: none; } h1 { font-size: 64px; margin: 24px 20px 20px; }
      .grille { grid-template-columns: 1fr; gap: 20px; padding: 0 20px; } figure div { height: 300px; } }
  </style>
  <header><b>Carnet de bord</b><nav><a>Travaux</a><a>À propos</a><a>Contact</a></nav></header>
  <h1>Illustrations et carnets de voyage</h1>
  <div class="grille"><figure><div class="mer"><i></i></div><figcaption><span>Cap Fréhel, gouache</span><span>2026</span></figcaption></figure>
    <figure><div class="ville"><i></i></div><figcaption><span>Lisbonne la nuit</span><span>2025</span></figcaption></figure>
    <figure><div class="gare"></div><figcaption><span>Gare de Porto</span><span>2025</span></figcaption></figure></div>`,
};

// la page est écrite sur disque puis ouverte en file:// : une page « about:blank » ne peut pas charger les polices locales
const tmp = mkdtempSync(path.join(os.tmpdir(), "references-demo-"));
const navigateur = await chromium.launch();
for (const [nom, corps] of Object.entries(SITES)) {
  const source = path.join(tmp, `${nom}.html`);
  writeFileSync(source, `<!doctype html><html lang="fr"><meta charset="utf-8"><style>${POLICES}</style><body>${corps}</body></html>`);
  for (const [vue, largeur, hauteur] of [["bureau", 1440, 900], ["mobile", 390, 844]]) {
    const page = await navigateur.newPage({ viewport: { width: largeur, height: hauteur }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(source).href);
    await page.evaluate(() => document.fonts.ready);
    const fichier = path.join(SORTIE, `ref-${nom}-${vue}.jpg`);
    await page.screenshot({ path: fichier, type: "jpeg", quality: 84 });
    await page.close();
    console.log(fichier);
  }
}
await navigateur.close();
rmSync(tmp, { recursive: true, force: true });
