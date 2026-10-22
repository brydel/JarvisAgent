import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { ajouterNote, attendreStable, DEMO, deposer, noeud, ouvrir, png, RAPPORTS, regler } from "./outils";

test.describe.configure({ mode: "serial" });

/* ------------------------------------------------------------------ visuel (mode démo, données fictives) -------- */
test.describe("visuel", () => {
  const tailles: [string, number, number][] = [["1672x941", 1672, 941], ["1440x900", 1440, 900], ["1280x800", 1280, 800], ["mobile-390x844", 390, 844]];
  for (const [nom, l, h] of tailles) {
    test(`board démo ${nom}`, async ({ page }) => {
      await page.setViewportSize({ width: l, height: h });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/v2/?demo=1");
      await attendreStable(page, 900);
      if (l > 900) {
        await page.locator(".react-flow__node-mission").click({ position: { x: 60, y: 60 } });
        await page.mouse.move(5, 5);
        await attendreStable(page, 500);
      }
      await expect(page.getByText("DÉMO", { exact: true })).toBeVisible();
      fs.mkdirSync(RAPPORTS, { recursive: true });
      await page.screenshot({ path: path.join(RAPPORTS, `after-${nom}.png`) });
      await expect(page).toHaveScreenshot(`board-demo-${nom}.png`);
    });
  }

  test("états : survol, glisser, panneau, média", async ({ page }) => {
    await page.goto("/v2/?demo=1");
    await attendreStable(page, 800);
    const image = page.locator(".react-flow__node-image");
    await image.hover();
    await page.screenshot({ path: path.join(RAPPORTS, "etat-survol.png") });
    const b = (await image.boundingBox())!;
    await page.mouse.move(b.x + 200, b.y + 100);
    await page.mouse.down();
    await page.mouse.move(b.x + 260, b.y + 140, { steps: 6 });
    await page.screenshot({ path: path.join(RAPPORTS, "etat-glisser.png") });
    await page.mouse.up();
    await page.locator(".react-flow__node-audio .bouton-lecture").click();
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(RAPPORTS, "etat-media-lecture.png") });
    await page.locator(".react-flow__node-audio .bouton-lecture").click();
  });
});

/* ------------------------------------------------------------------ comportements réels (API + base isolée) ------ */
test.describe("board réel", () => {
  test("note : création, édition en place, persistance après rechargement", async ({ page }) => {
    await ouvrir(page);
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Texte" }).click();
    await expect(noeud(page, "Nouvelle note")).toBeVisible();
    const id = await noeud(page, "Nouvelle note").getAttribute("data-id");
    const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
    await carte.getByRole("button", { name: "Modifier le texte" }).click();
    const zone = carte.getByRole("textbox", { name: "Texte de la note" });
    await zone.fill("Plan **important**\n- point un\n- point deux");
    await zone.press("Escape");
    await page.waitForTimeout(900);
    await expect(carte.locator("strong")).toHaveText("important");
    await page.reload();
    await expect(page.locator(`.react-flow__node[data-id="${id}"] strong`)).toHaveText("important");
    await expect(page.locator(`.react-flow__node[data-id="${id}"] li`)).toHaveText(["point un", "point deux"]);
  });

  test("coller une image du presse-papiers crée une vraie carte image", async ({ page }) => {
    await ouvrir(page);
    const donnees = png(64, 36).toString("base64");
    await page.evaluate(async (b64) => {
      const octets = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const dt = new DataTransfer();
      dt.items.add(new File([octets], "capture-ecran.png", { type: "image/png" }));
      window.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt }));
    }, donnees);
    const carte = noeud(page, "capture-ecran");
    await expect(carte).toBeVisible();
    await expect(carte.getByText("64 × 36")).toBeVisible();
    await expect.poll(() => carte.locator("img:not(.avatar img)").evaluate((i: HTMLImageElement) => i.naturalWidth)).toBe(64);
    await page.reload();
    await expect(noeud(page, "capture-ecran")).toBeVisible();
  });

  test("coller plusieurs URL crée plusieurs cartes lien avec repli d'aperçu", async ({ page }) => {
    await ouvrir(page);
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.setData("text/plain", "https://site-un.invalid/page https://site-deux.invalid");
      window.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt }));
    });
    await expect(noeud(page, "site-un.invalid")).toBeVisible();
    await expect(noeud(page, "site-deux.invalid")).toBeVisible();
    await expect(noeud(page, "site-un.invalid").getByText(/Aperçu indisponible/)).toBeVisible({ timeout: 15_000 });
  });

  test("audio importé : lecture réelle, avance, forme d'onde calculée du fichier", async ({ page }) => {
    await ouvrir(page);
    const choix = page.waitForEvent("filechooser");
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Audio" }).click();
    await (await choix).setFiles(path.join(DEMO, "reunion-ideation.mp3"));
    const carte = page.locator(".react-flow__node-audio").filter({ hasText: "reunion-ideation" });
    await expect(carte).toBeVisible();
    await expect(carte.getByText(/00:12/).first()).toBeVisible();
    await expect.poll(() => carte.locator("canvas").evaluate((c: HTMLCanvasElement) => {
      const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4) n += d[i]! > 0 ? 1 : 0;
      return n;
    }), { timeout: 10_000 }).toBeGreaterThan(200);
    await carte.getByRole("button", { name: "Lecture", exact: true }).click();
    await expect.poll(() => carte.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(0.3);
    await carte.getByRole("button", { name: "Pause", exact: true }).click();
    await carte.getByRole("button", { name: "Vitesse de lecture" }).click();
    await expect(carte.getByRole("button", { name: "Vitesse de lecture" })).toHaveText(/1.25x/);
  });

  test("vidéo importée : vignette extraite par le serveur, lecture réelle (WebM), contrôles", async ({ page }) => {
    await ouvrir(page);
    const choix = page.waitForEvent("filechooser");
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Vidéo" }).click();
    await (await choix).setFiles(path.join(DEMO, "presentation-produit.webm"));
    const trouvee = page.locator(".react-flow__node-video").filter({ hasText: "presentation-produit" }).last();
    await expect(trouvee).toBeVisible();
    const carte = page.locator(`.react-flow__node[data-id="${await trouvee.getAttribute("data-id")}"]`);  // le titre disparaît pendant la lecture
    await expect.poll(() => carte.locator("img:not(.avatar img)").evaluate((i: HTMLImageElement) => i.naturalWidth)).toBeGreaterThan(100);
    await carte.getByRole("button", { name: "Lire la vidéo" }).first().click();
    await expect.poll(() => carte.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0.2);
    const curseur = carte.getByRole("slider", { name: "Position dans la vidéo" });
    await curseur.fill("4");
    await expect.poll(() => carte.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(3.5);
    await expect(carte.getByRole("button", { name: "Plein écran" })).toBeVisible();
  });

  test("vidéo MP4 (H.264) : lecture, ou message de codec explicite si ce navigateur ne la décode pas", async ({ page }) => {
    await ouvrir(page);
    const choix = page.waitForEvent("filechooser");
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Vidéo" }).click();
    await (await choix).setFiles(path.join(DEMO, "presentation-produit.mp4"));
    const trouvee = page.locator(".react-flow__node-video").filter({ hasText: "presentation-produit" }).last();
    await expect(trouvee).toBeVisible();
    const carte = page.locator(`.react-flow__node[data-id="${await trouvee.getAttribute("data-id")}"]`);
    await carte.getByRole("button", { name: "Lire la vidéo" }).first().click();
    await expect.poll(async () => {
      const t = await carte.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime).catch(() => 0);
      const erreur = await carte.locator(".erreur-media").first().textContent({ timeout: 500 }).catch(() => "");
      return t > 0.2 || /codec|pris en charge|Lecture impossible/.test(erreur ?? "");
    }, { timeout: 15_000 }).toBe(true);
  });

  test("PDF importé : vignettes rendues par pdf.js, refus d'un fichier déguisé", async ({ page }) => {
    await ouvrir(page);
    const choix = page.waitForEvent("filechooser");
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Document" }).click();
    await (await choix).setFiles(path.join(DEMO, "plan-produit.pdf"));
    const carte = page.locator(".react-flow__node-pdf").filter({ hasText: "plan-produit" });
    await expect(carte).toBeVisible();
    await expect(carte.locator(".pages")).toHaveAttribute("aria-label", "2 pages", { timeout: 15_000 });
    await expect.poll(() => carte.locator("canvas").first().evaluate((c: HTMLCanvasElement) => c.width)).toBeGreaterThan(50);
    // HTML déguisé en PDF : refusé par le serveur (type reconnu par les octets), message lisible
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(["<script>alert(1)</script>"], "facture.pdf", { type: "application/pdf" }));
      window.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt }));
    });
    await expect(page.getByText(/type de fichier non pris en charge/)).toBeVisible();
  });

  test("déplacer, redimensionner, prioriser : persistés après rechargement", async ({ page }) => {
    await ouvrir(page);
    const id = await ajouterNote(page);
    const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
    const avant = (await carte.boundingBox())!;
    await page.mouse.move(avant.x + 120, avant.y + 30);
    await page.mouse.down();
    await page.mouse.move(avant.x + 300, avant.y + 110, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(500);
    await carte.click({ position: { x: 120, y: 30 } });
    const poignee = carte.locator(".react-flow__resize-control.handle.bottom.right");
    const p = (await poignee.boundingBox())!;
    await page.mouse.move(p.x + p.width / 2, p.y + p.height / 2);
    await page.mouse.down();
    await page.mouse.move(p.x + 80, p.y + 60, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(500);
    await carte.getByRole("button", { name: "Actions de la carte" }).click();
    await page.getByRole("menuitemradio").filter({ hasText: "P1" }).click();
    await expect(carte.locator(".badge-p.P1")).toBeVisible();
    const apres = (await carte.boundingBox())!;
    expect(apres.width).toBeGreaterThan(avant.width + 40);
    await page.waitForTimeout(600);
    // géométrie dans le repère du canevas (indépendante du zoom et de l'ajustement de la vue au rechargement)
    const geometrie = () => page.locator(`.react-flow__node[data-id="${id}"]`).evaluate((n: HTMLElement) => {
      const m = /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(n.style.transform)!;
      return { x: Math.round(Number(m[1])), y: Math.round(Number(m[2])), l: Math.round(n.offsetWidth), h: Math.round(n.offsetHeight) };
    });
    const g1 = await geometrie();
    const base = await page.evaluate(async (i) => (await (await fetch("/api/v2/board")).json()).objets.find((o: { id: string }) => o.id === i), id);
    expect([Math.round(base.x), Math.round(base.y), Math.round(base.largeur), Math.round(base.hauteur)]).toEqual([g1.x, g1.y, g1.l, g1.h]);
    await page.reload();
    await attendreStable(page);
    expect(await geometrie()).toEqual(g1);
    await expect(page.locator(`.react-flow__node[data-id="${id}"] .badge-p.P1`)).toBeVisible();
    // filtre P1
    await page.getByRole("button", { name: "Filtrer par priorité" }).click();
    await expect(page.locator(`.react-flow__node[data-id="${id}"]`)).toBeVisible();
  });

  test("relier deux cartes, nommer la relation, persistance", async ({ page }) => {
    await ouvrir(page);
    const ida = await ajouterNote(page);
    const idb = await ajouterNote(page);
    expect(ida).not.toBe(idb);
    const a = page.locator(`.react-flow__node[data-id="${ida}"]`), b = page.locator(`.react-flow__node[data-id="${idb}"]`);
    const ba = (await a.boundingBox())!, bb = (await b.boundingBox())!;
    expect(Math.abs(ba.x - bb.x) + Math.abs(ba.y - bb.y)).toBeGreaterThan(30);  // pas empilées
    await page.mouse.move(ba.x + ba.width / 2, ba.y + 20);  // survol : les points d'attache apparaissent
    const depart = (await a.locator(".react-flow__handle-top").boundingBox())!;
    await page.mouse.move(depart.x + depart.width / 2, depart.y + depart.height / 2);
    await page.mouse.down();
    const cible = (await b.locator(".react-flow__handle-top").boundingBox())!;
    await page.mouse.move(cible.x + cible.width / 2, cible.y + cible.height / 2, { steps: 20 });
    await page.mouse.up();
    await expect(page.getByText(/Relation créée/).first()).toBeVisible();
    const relations = () => page.evaluate(async ([x, y]) => (await (await fetch("/api/v2/board")).json()).liens
      .filter((l: { source_id: string; cible_id: string }) => l.source_id === x && l.cible_id === y).length, [ida, idb]);
    await expect.poll(relations).toBe(1);
    await expect(page.locator(".react-flow__edge").first()).toBeAttached();
    await page.reload();
    await expect(page.locator(".react-flow__edge").first()).toBeAttached();
  });

  test("supprimer puis annuler (Ctrl+Z) et zoom", async ({ page }) => {
    await ouvrir(page);
    const id = await ajouterNote(page);
    const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
    await carte.click({ position: { x: 150, y: 30 } });
    await page.keyboard.press("Delete");
    await expect(page.locator(`.react-flow__node[data-id="${id}"]`)).toHaveCount(0);
    await page.keyboard.press("Control+z");
    await expect(page.locator(`.react-flow__node[data-id="${id}"]`)).toHaveCount(1);
    const zoom = page.locator(".zoom output");
    const z0 = await zoom.textContent();
    await page.getByRole("button", { name: "Zoom avant" }).click();
    await expect(zoom).not.toHaveText(z0!);
    await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  });

  test("dialogue « Lancer une mission » : validation, Échap, focus rendu", async ({ page }) => {
    await ouvrir(page);
    const bouton = page.getByRole("button", { name: "Lancer une mission" });
    await bouton.click();
    const dialogue = page.getByRole("dialog", { name: "Lancer une mission" });
    await expect(dialogue).toBeVisible();
    await expect(dialogue.getByRole("textbox", { name: /Objectif/ })).toBeFocused();
    await expect(dialogue.getByRole("button", { name: "Lancer la mission" })).toBeDisabled();
    await dialogue.getByRole("textbox", { name: /Objectif/ }).fill("   ");
    await expect(dialogue.getByRole("button", { name: "Lancer la mission" })).toBeDisabled();
    await expect(dialogue.getByText(/L1/).first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialogue).toBeHidden();
    await expect(bouton).toBeFocused();
  });

  test("lancer une mission : carte réelle mise à jour en direct par le flux SSE", async ({ page }) => {
    await ouvrir(page);
    await page.getByRole("button", { name: "Lancer une mission" }).click();
    const dialogue = page.getByRole("dialog", { name: "Lancer une mission" });
    await dialogue.getByRole("textbox", { name: /Objectif/ }).fill("Analyser le compte rendu de la réunion produit");
    await dialogue.getByRole("textbox", { name: /Contexte/ }).fill("Démo vendredi 14 h ; budget à confirmer.");
    await dialogue.getByRole("radio", { name: "P2" }).check();
    await expect(dialogue.getByRole("radio", { name: "P2" })).toBeChecked();
    await page.screenshot({ path: path.join(RAPPORTS, "etat-dialogue-mission.png") });
    await page.keyboard.press("Control+Enter");
    await expect(dialogue).toBeHidden();
    const carte = page.locator(".react-flow__node-mission").filter({ hasText: "Analyser le compte rendu" });
    await expect(carte.locator(".badge-p.P2")).toHaveCount(0);  // la carte mission ne montre pas de badge (panneau)
    await expect(carte).toBeVisible();
    // l'exécutant factice du serveur de test prend la tâche : la carte passe à « Réussie » sans rechargement
    await expect(carte.getByText("Réussie")).toBeVisible({ timeout: 20_000 });
    await expect(carte.getByText("100%")).toBeVisible();
    await carte.click({ position: { x: 40, y: 40 } });
    await expect(page.getByRole("complementary", { name: "Panneau contextuel" }).getByText("Tâches (1/1)")).toBeVisible();
    const agents = page.locator(".react-flow__node-agents");
    await expect(agents).toHaveCount(0); // aucune carte d'agents inventée
  });

  test("le chef contextualise un élément déposé et propose des actions, sans geste manuel", async ({ page }) => {
    await ouvrir(page);
    await regler(page, { actions_auto: false });  // ce test suit le parcours manuel (Lancer)
    // dépôt tel que l'ingestion du Board le fait (aucune option « analyser ») : la contextualisation part seule
    const id = await page.evaluate(async () => {
      const r = await fetch("/api/v2/objets", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" },
        body: JSON.stringify({ type: "note", contenu: "Offre de stage DevOps à Lyon, candidature avant vendredi", x: 200, y: 160,
          largeur: 408, hauteur: 320, meta: { titre: "Offre de stage DevOps" } }) });
      return (await r.json()).objet_id as string;
    });
    const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
    // l'exécutant factice du serveur de test traite la mission : le bandeau passe à « 1 action proposée »
    const bandeau = carte.getByRole("button", { name: /Jarvis : 1 action proposée/ });
    await expect(bandeau).toBeVisible({ timeout: 20_000 });
    await bandeau.click();
    const section = page.getByRole("region", { name: "Actions proposées par Jarvis" });
    await expect(section.getByText("Résumer l'élément (factice)")).toBeVisible();
    await expect(section.locator(".resume-jarvis")).toContainText("note");
    await page.screenshot({ path: path.join(RAPPORTS, "etat-chef-propositions.png") });
    await section.getByRole("button", { name: "Lancer « Résumer l'élément (factice) »" }).click();
    // la mission de préparation est posée à côté, reliée à l'élément, et sélectionnée
    const mission = page.locator(".react-flow__node-mission").filter({ hasText: "Préparer : Résumer" });
    await expect(mission).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Panneau contextuel" }).getByRole("heading", { name: /Préparer : Résumer/ })).toBeVisible();
    await expect(page.getByText("proposé par Jarvis")).toBeVisible();
    await expect(mission.getByText("Réussie")).toBeVisible({ timeout: 20_000 });
    // le livrable réel est lisible dans le panneau, titres Markdown rendus
    const livrable = page.getByRole("region", { name: "Livrable" });
    await expect(livrable.getByRole("heading", { name: "Livrable" , exact: true }).last()).toBeVisible();
    await expect(livrable.getByText("factice", { exact: true })).toBeVisible();
    await expect(livrable.getByText(/Action à préparer : Résumer/)).toBeVisible();
    await expect(livrable.getByRole("button", { name: "Copier" })).toBeVisible();
    await page.screenshot({ path: path.join(RAPPORTS, "etat-chef-mission-preparee.png") });
    // plus aucune proposition ouverte : le bandeau l'indique
    await carte.getByRole("button", { name: "Jarvis : Contextualisé. Ouvrir les détails" }).click();
    await expect(section.getByText("Lancée")).toBeVisible();
    // relance humaine depuis le menu de la carte
    await carte.getByRole("button", { name: "Actions de la carte" }).click();
    await page.getByRole("menuitem", { name: "Analyser avec Jarvis" }).click();
    await expect(page.getByText("Jarvis analyse l'élément…").first()).toBeVisible();
    await regler(page, { actions_auto: true });
  });

  test("le chef relie les cartes du projet, lance seul une action L1 et pose son livrable", async ({ page }) => {
    await ouvrir(page);
    await regler(page, { actions_auto: true });
    const offre = await deposer(page, "Offre DevOps chez Sopra, candidature avant vendredi", "Offre Sopra", 120);
    const carteOffre = page.locator(`.react-flow__node[data-id="${offre}"]`);
    // décision autonome : la première action L1 est lancée, réalisée, et son livrable devient une carte reliée
    await expect(carteOffre.getByRole("button", { name: "Jarvis : Contextualisé. Ouvrir les détails" })).toBeVisible({ timeout: 25_000 });
    const livrable = page.locator(".react-flow__node").filter({ hasText: "Livrable — Préparer : Résumer" });
    await expect(livrable).toBeVisible({ timeout: 25_000 });
    await expect(page.locator(".etiquette-lien").filter({ hasText: "livrable" })).toBeVisible();
    // une seconde carte : le chef la relie à l'offre (relation tracée par Jarvis, retirable)
    await deposer(page, "Entretien téléphonique jeudi 10 h", "Entretien", 620);
    const lienJarvis = page.locator(".etiquette-lien.par-jarvis").filter({ hasText: "inspire" });
    await expect(lienJarvis).toBeVisible({ timeout: 25_000 });
    await carteOffre.getByRole("button", { name: /Jarvis :/ }).click();
    await expect(page.getByRole("region", { name: "Actions proposées par Jarvis" }).getByText("Lancée par Jarvis")).toBeVisible();
    await page.screenshot({ path: path.join(RAPPORTS, "etat-chef-autonome.png") });
  });

  test("autonomie du chef réglable depuis le panneau", async ({ page }) => {
    await ouvrir(page);
    await regler(page, { actions_auto: true, auto_analyse: true });
    await page.reload();
    const zone = page.getByRole("region", { name: "Autonomie de Jarvis" });
    const actions = zone.getByRole("switch", { name: /Lancer seul les actions sans risque/ });
    await expect(actions).toBeChecked();
    await actions.click({ force: true });
    await expect(actions).not.toBeChecked();
    expect(await page.evaluate(async () => (await (await fetch("/api/v2/board")).json()).reglages.actions_auto)).toBe(false);
    await actions.click({ force: true });
    await expect(actions).toBeChecked();
  });

  test("un Board par projet : créer, changer, cartes séparées", async ({ page }) => {
    await ouvrir(page);
    await ajouterNote(page);
    await page.getByRole("button", { name: /Board : Accueil\. Changer de projet/ }).click();
    // le menu passe AU-DESSUS de la barre d'outils du canevas (régression : il glissait dessous)
    const item = page.getByRole("menuitem", { name: "Nouveau Board" });
    const b = (await item.boundingBox())!;
    expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest("[role=menuitem]")?.textContent?.trim(),
      { x: b.x + 12, y: b.y + b.height / 2 })).toBe("Nouveau Board");
    await item.click();
    await page.getByRole("textbox", { name: "Nom du nouveau Board" }).fill("Projet test e2e");
    await page.getByRole("button", { name: "Créer" }).click();
    await page.waitForURL(/espace=Projet\+test\+e2e|espace=Projet%20test%20e2e/);
    await expect(page.getByRole("button", { name: /Board : Projet test e2e/ })).toBeVisible();
    await expect(page.locator(".react-flow__node")).toHaveCount(0);  // un Board neuf, sans les cartes de l'accueil
    await page.getByRole("button", { name: /Board : Projet test e2e/ }).click();
    await page.getByRole("menuitemradio", { name: /Accueil/ }).click();
    await page.waitForURL((u) => !u.searchParams.has("espace"));
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
  });

  test("filtres, priorité, recherche et carte sélectionnée reflétés dans l'URL et conservés au rechargement", async ({ page }) => {
    await ouvrir(page);
    const id = await ajouterNote(page);
    await page.locator(`.react-flow__node[data-id="${id}"]`).getByRole("button", { name: "Actions de la carte" }).click();
    await page.getByRole("menuitemradio").filter({ hasText: "P2" }).click();
    await page.getByRole("group", { name: "Filtrer par type" }).getByRole("button", { name: /^Notes/ }).click();
    await page.getByRole("button", { name: "Filtrer par priorité" }).click();
    await page.getByRole("button", { name: "Filtrer par priorité" }).click();  // P1 → P2
    await page.getByRole("searchbox", { name: "Rechercher dans le Board" }).fill("Nouvelle");
    await page.locator(`.react-flow__node[data-id="${id}"]`).click({ position: { x: 150, y: 30 } });
    await expect.poll(() => new URL(page.url()).searchParams.toString()).toContain("filtre=notes");
    const u = new URL(page.url());
    expect([u.searchParams.get("filtre"), u.searchParams.get("priorite"), u.searchParams.get("q"), u.searchParams.get("carte")])
      .toEqual(["notes", "P2", "Nouvelle", id]);
    await page.reload();
    await expect(page.getByRole("group", { name: "Filtrer par type" }).getByRole("button", { name: /^Notes/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("searchbox", { name: "Rechercher dans le Board" })).toHaveValue("Nouvelle");
    await expect(page.locator(".subbar .badge-p.P2")).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Panneau contextuel" }).getByRole("heading", { name: "Note" })).toBeVisible();
    // une valeur invalide est ignorée
    await page.goto("/v2/?filtre=inconnu&priorite=P9&carte=../../x");
    await expect(page.getByRole("group", { name: "Filtrer par type" }).getByRole("button", { name: /^Tous/ })).toHaveAttribute("aria-pressed", "true");
    expect(new URL(page.url()).searchParams.get("filtre")).toBeNull();
  });

  test("mouvement réduit et en-têtes de sécurité", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const r = await page.goto("/v2/?demo=1");
    const csp = r!.headers()["content-security-policy"]!;
    expect(csp).toContain("script-src 'self'");
    expect(csp).not.toContain("unsafe-eval");
    expect(r!.headers()["x-content-type-options"]).toBe("nosniff");
    const duree = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--dur-hover").trim());
    expect(duree).toMatch(/^0m?s$/);
  });
});
