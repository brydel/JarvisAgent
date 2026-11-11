import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { RAPPORTS, attendreStable, ouvrir } from "./outils";

// « De l'intelligence derrière chaque flèche, chaque carte et chaque bouton » : parcours sur le Board RÉEL (API et
// base isolées, exécutant factice). Une flèche « Dépend de » bloque vraiment, « Alimente » joint vraiment le
// contenu au travail, « Faire relire » ouvre une vraie demande, et une commande grisée dit pourquoi.
const CAPTURES = path.join(RAPPORTS, "captures");
const ENTETES = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };
const PAUSE = process.env.JARVIS_E2E_PAUSE!;

interface Relations { bloquee: boolean; bloquee_par: { id: string; titre: string; etat: string }[]; alimentee_par: { id: string; sorte: string }[]; debloque: { id: string; attend: boolean }[] }
interface Objet { id: string; type: string; mission_id: string | null; meta: Record<string, unknown>; relations?: Relations; relecture?: { id: string; statut: string; verdict: string } }

const board = (page: Page): Promise<{ objets: Objet[]; liens: { id: string; style: string }[] }> => page.evaluate(async () => (await fetch("/api/v2/board")).json());
const objet = async (page: Page, id: string) => (await board(page)).objets.find((o) => o.id === id)!;
const poster = (page: Page, chemin: string, corps: Record<string, unknown>): Promise<{ statut: number; corps: Record<string, unknown> }> =>
  page.evaluate(async ([c, b, h]) => {
    const r = await fetch(c as string, { method: "POST", headers: h as Record<string, string>, body: JSON.stringify(b) });
    return { statut: r.status, corps: await r.json().catch(() => ({})) };
  }, [chemin, corps, ENTETES] as const);
const noeud = (page: Page, id: string) => page.locator(`.react-flow__node[data-id="${id}"]`);
async function note(page: Page, titre: string, x: number, y: number, contenu = titre): Promise<string> {
  const r = await poster(page, "/api/v2/objets", { type: "note", contenu, x, y, largeur: 340, hauteur: 220, meta: { titre }, analyser: false });
  await expect(noeud(page, r.corps.objet_id as string)).toBeAttached();
  return r.corps.objet_id as string;
}
/** Clic droit au milieu du tracé de la (seule) flèche du Board. */
async function menuDeLaFleche(page: Page) {
  const milieu = await page.locator(".react-flow__edge .react-flow__edge-path").first().evaluate((p) => {
    const trace = p as SVGPathElement;
    const pt = trace.getPointAtLength(trace.getTotalLength() / 2), m = trace.getScreenCTM()!;
    return { x: pt.x * m.a + pt.y * m.c + m.e, y: pt.x * m.b + pt.y * m.d + m.f };
  });
  await page.mouse.click(milieu.x, milieu.y, { button: "right" });
  const menu = page.getByRole("menu", { name: "Actions de la relation" });
  await expect(menu).toBeVisible();
  return menu;
}
const reprendre = () => fs.rmSync(PAUSE, { force: true });

test.beforeAll(() => fs.mkdirSync(CAPTURES, { recursive: true }));
test.afterEach(reprendre);

test("« Dépend de » : la carte est bloquée, son lancement refusé avec la raison, puis débloquée en direct", async ({ page }) => {
  fs.writeFileSync(PAUSE, "");  // l'exécutant attend : la mission dont on dépend reste « en cours »
  await ouvrir(page);
  const synthese = await note(page, "Rédiger la synthèse", 160, 240, "Synthèse des chiffres du trimestre");
  const mission = (await poster(page, "/api/v2/missions", { objectif: "Collecter les chiffres", x: 760, y: 200 })).corps.objet_id as string;
  await expect(noeud(page, mission)).toBeAttached();
  const lien = (await poster(page, "/api/v2/liens", { source_id: synthese, cible_id: mission, style: "defaut" })).corps.id as string;
  const fleche = page.locator(`.react-flow__edge[data-id="${lien}"]`);
  await expect(fleche).toHaveCount(1);
  await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  await page.waitForTimeout(400);

  // choisir le type : chaque entrée dit ce que ça change, avec les deux cartes nommées
  const menu = await menuDeLaFleche(page);
  const depend = menu.getByRole("menuitemcheckbox", { name: /Relation : Dépend de/ });
  await expect(depend).toContainText("La source est bloquée tant que la cible n'est pas terminée");
  await expect(menu.getByRole("menuitemcheckbox", { name: /Relation : Relation simple/ })).toContainText("Simple repère");
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "relation-types-expliques.png") });
  await depend.click();
  await expect(page.locator(".toast").filter({ hasText: "« Rédiger la synthèse » sera bloquée tant que « Collecter les chiffres » n'est pas terminée" })).toBeVisible();

  // le serveur a calculé le blocage ; la carte, la flèche et le panneau le montrent
  await expect.poll(async () => (await objet(page, synthese)).relations?.bloquee).toBe(true);
  const carte = noeud(page, synthese);
  await expect(carte.locator(".etat-carte.bloquee")).toHaveText("Bloquée");
  const ligne = carte.getByRole("button", { name: /Bloquée par « Collecter les chiffres » \(en cours\)/ });
  await expect(ligne).toBeVisible();
  await expect(noeud(page, mission).getByRole("button", { name: /Débloquera « Rédiger la synthèse »/ })).toBeVisible();
  const etiquette = page.locator(".etiquette-lien");
  await expect(etiquette).toHaveAttribute("data-etat", "bloquante");
  await expect(etiquette).toContainText("bloque");
  const trait = () => fleche.locator(".react-flow__edge-path").evaluate((p) => ({ couleur: getComputedStyle(p).stroke, largeur: parseFloat(getComputedStyle(p).strokeWidth) }));
  const bloquant = await trait();
  expect(bloquant.largeur).toBeGreaterThan(4);

  // lancement refusé par l'API, raison lisible
  const refus = await poster(page, `/api/v2/objets/${synthese}/contextualiser`, {});
  expect(refus.statut).toBe(409);
  expect(String(refus.corps.erreur)).toContain("bloquée par « Collecter les chiffres » (en cours)");
  // … et la commande est grisée avec la même raison : barre flottante (info-bulle), menu de la carte, palette
  await carte.click({ position: { x: 40, y: 40 } });
  const barre = page.getByRole("toolbar", { name: "Sélection" });
  const analyser = barre.getByRole("button", { name: /Analyser avec Jarvis — indisponible : Bloquée par « Collecter les chiffres » \(en cours\)/ });
  await expect(analyser).toHaveAttribute("aria-disabled", "true");
  await expect(analyser).toHaveAttribute("title", /termine d'abord ce dont elle dépend/);
  await analyser.click({ force: true });  // un clic n'exécute rien : il redit pourquoi (Playwright n'attend pas un bouton aria-disabled)
  await expect(page.locator(".toast").filter({ hasText: "Analyser avec Jarvis — indisponible : Bloquée par" })).toBeVisible();
  expect((await objet(page, synthese)).mission_id).toBeNull();
  await carte.click({ button: "right", position: { x: 40, y: 40 } });
  const menuCarte = page.getByRole("menu", { name: "Actions de la sélection" });
  const entree = menuCarte.getByRole("menuitem", { name: /Analyser avec Jarvis/ });
  await expect(entree).toHaveAttribute("aria-disabled", "true");
  await expect(entree).toContainText("Bloquée par « Collecter les chiffres » (en cours)");
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "carte-bloquee-raison.png") });
  await page.keyboard.press("Escape");
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Palette de commandes" });
  await palette.getByRole("combobox").fill("analyser");
  const option = palette.getByRole("option", { name: /Analyser avec Jarvis/ });
  await expect(option).toHaveAttribute("aria-disabled", "true");
  await expect(option).toContainText("Indisponible : Bloquée par « Collecter les chiffres » (en cours)");
  await page.keyboard.press("Enter");  // Entrée sur une ligne indisponible : rien ne s'exécute, la palette reste
  await expect(palette).toBeVisible();
  await page.keyboard.press("Escape");

  // navigation : « Bloquée par X » mène à X
  await page.keyboard.press("Escape");  // désélectionne
  await ligne.click();
  await expect(noeud(page, mission)).toHaveClass(/selected/);

  // une boucle est refusée : « Dépend de » dans l'autre sens est grisée, avec le trajet
  const retour = await poster(page, "/api/v2/liens", { source_id: mission, cible_id: synthese, style: "depend" });
  expect(retour.statut).toBe(409);
  expect(String(retour.corps.erreur)).toContain("boucle");

  // la dépendance se termine : événement dans le flux, carte débloquée sans rechargement
  reprendre();
  await expect(page.locator(".toast").filter({ hasText: "« Rédiger la synthèse » est débloquée" })).toBeVisible({ timeout: 20_000 });
  await expect(carte.locator(".etat-carte.bloquee")).toHaveCount(0);
  // (le livrable de la mission arrive aussi, avec sa propre flèche « alimente · livrable »)
  const liberee = page.locator('.etiquette-lien[data-etat="debloquee"]');
  await expect(liberee).toHaveCount(1);
  await expect(liberee).toContainText("débloquée");
  await expect(page.locator('.etiquette-lien[data-etat="bloquante"]')).toHaveCount(0);
  await expect.poll(async () => (await trait()).largeur).toBeLessThan(bloquant.largeur);
  expect((await trait()).couleur).not.toBe(bloquant.couleur);
  await expect(noeud(page, mission).getByRole("button", { name: /Débloquera « Rédiger la synthèse »/ })).toHaveCount(0);  // plus rien à débloquer
  const lu = await objet(page, synthese);
  expect(lu.relations).toMatchObject({ bloquee: false, bloquee_par: [] });
  await page.keyboard.press("Escape");  // désélectionne
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "dependance-debloquee.png") });
  // débloquée : le lancement passe
  await carte.click({ position: { x: 40, y: 40 } });
  await barre.getByRole("button", { name: "Analyser avec Jarvis" }).click();
  await expect.poll(async () => (await objet(page, synthese)).mission_id).not.toBeNull();
});

test("« Alimente » : la carte dit par quoi elle est alimentée, et le contenu part vraiment avec son travail", async ({ page }) => {
  fs.writeFileSync(PAUSE, "");
  await ouvrir(page);
  const source = await note(page, "Tarifs 2026", 160, 240, "Tarifs 2026 : 12 € par mois, 99 € par an.");
  const cible = await note(page, "Lettre aux clients", 760, 240, "Annoncer les nouveaux tarifs");
  await poster(page, "/api/v2/liens", { source_id: source, cible_id: cible, style: "defaut" });
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  await page.waitForTimeout(400);
  const menu = await menuDeLaFleche(page);
  await menu.getByRole("menuitemcheckbox", { name: /Relation : Alimente/ }).click();
  await expect(noeud(page, cible).getByRole("button", { name: /Alimentée par « Tarifs 2026 » \(contenu\)/ })).toBeVisible();
  await expect(page.locator(".etiquette-lien")).toHaveAttribute("data-etat", "jointe");
  await expect(page.locator(".etiquette-lien")).toContainText("alimente · contenu");
  // le travail préparé pour la carte cible contient la source, marquée comme donnée, avec sa provenance
  await noeud(page, cible).click({ position: { x: 40, y: 40 } });
  await page.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Analyser avec Jarvis" }).click();
  await expect.poll(async () => (await objet(page, cible)).mission_id).not.toBeNull();
  const mission = (await objet(page, cible)).mission_id!;
  const inspection = await page.evaluate(async (id) => (await fetch(`/api/missions/${id}/inspection`)).json(), mission);
  const travail = JSON.stringify(inspection);
  expect(travail).toContain("donnee_non_fiable");
  expect(travail).toContain("12 € par mois");
  expect(travail).toContain(`carte ${source} (note)`);
  await page.keyboard.press("Escape");  // désélectionne
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "relation-alimente.png") });
});

test("« Faire relire » : une vraie demande, visible sur la carte et dans la file, puis un verdict", async ({ page }) => {
  await ouvrir(page);
  const id = (await poster(page, "/api/v2/missions", { objectif: "Rédiger l'offre", x: 300, y: 200 })).corps.objet_id as string;
  // la mission n'a pas encore de livrable : la commande est proposée grisée, avec la raison
  fs.writeFileSync(PAUSE, "");
  const autre = (await poster(page, "/api/v2/missions", { objectif: "Mission sans livrable", x: 900, y: 200 })).corps.objet_id as string;
  await expect(noeud(page, autre)).toBeAttached();
  await noeud(page, autre).click({ button: "right", position: { x: 60, y: 60 } });
  const menu = page.getByRole("menu", { name: "Actions de la sélection" });
  const grisee = menu.getByRole("menuitem", { name: /Faire relire/ });
  await expect(grisee).toHaveAttribute("aria-disabled", "true");
  await expect(grisee).toContainText("Cette mission n'a pas encore rendu de livrable");
  await page.keyboard.press("Escape");
  reprendre();
  // le livrable de la première mission arrive (exécutant factice) : une carte « Livrable » est posée
  await expect.poll(async () => (await board(page)).objets.some((o) => typeof o.meta.livrable_de === "string"), { timeout: 20_000 }).toBe(true);
  const livrable = (await board(page)).objets.find((o) => typeof o.meta.livrable_de === "string")!;
  await expect(noeud(page, livrable.id)).toBeAttached();
  await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  await page.waitForTimeout(400);
  await noeud(page, livrable.id).click({ position: { x: 40, y: 30 } });
  await page.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Faire relire" }).click();
  await expect(page.locator(".toast").filter({ hasText: "Aucun agent n'est lancé par cette demande" })).toBeVisible();
  await expect(noeud(page, livrable.id).locator(".etat-carte.attente")).toHaveText("Relecture demandée");
  // côté serveur : une demande suivie, lisible dans la file ; aucune mission de plus n'a été créée
  const file = await page.evaluate(async () => (await fetch("/api/v2/relectures")).json());
  expect(file.relectures).toHaveLength(1);
  expect(file.relectures[0]).toMatchObject({ objet_id: livrable.id, statut: "demandee", nature: "donnee_non_fiable" });
  expect((await board(page)).objets.filter((o) => o.type === "mission")).toHaveLength(2);
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "relecture-demandee.png") });
  // verdict rendu par l'humain, au menu de la carte
  await noeud(page, livrable.id).click({ button: "right", position: { x: 40, y: 30 } });
  await menu.getByRole("menuitem", { name: "Relecture : corrections demandées" }).click();
  await expect(noeud(page, livrable.id).locator(".etat-carte.bloquee")).toHaveText("Corrections demandées");
  expect((await objet(page, livrable.id)).relecture).toMatchObject({ statut: "rendue", verdict: "corrections" });
  expect((await page.evaluate(async () => (await fetch("/api/v2/relectures")).json())).relectures).toHaveLength(0);
  expect(id).toBeTruthy();
});

test("une commande indisponible dit pourquoi : info-bulle, palette, menu, raccourci", async ({ page }) => {
  await ouvrir(page);
  // rien à annuler : le bouton est grisé, son info-bulle le dit, Ctrl+Z aussi
  const annuler = page.getByRole("toolbar", { name: "Outils" }).getByRole("button", { name: /^Annuler/ });
  await expect(annuler).toHaveAttribute("aria-disabled", "true");
  await expect(annuler).toHaveAttribute("title", /indisponible : Rien à annuler/);
  await page.keyboard.press("Control+z");
  await expect(page.locator(".toast").filter({ hasText: "Annuler — indisponible : Rien à annuler" })).toBeVisible();
  // Échap sans rien à quitter reste silencieux
  await page.keyboard.press("Escape");
  await expect(page.locator(".toast")).toHaveCount(1);
  // aucun cadre : « Présenter » est grisé et dit quoi faire
  await expect(page.getByRole("button", { name: /Présenter .* — indisponible : Aucun cadre sur ce Board/ })).toHaveAttribute("aria-disabled", "true");
  // menu du canevas : « Coller ici » grisé, avec la raison écrite
  await page.locator(".react-flow__pane").click({ button: "right", position: { x: 700, y: 500 } });
  const coller = page.getByRole("menu", { name: "Actions du canevas" }).getByRole("menuitem", { name: /Coller ici/ });
  await expect(coller).toHaveAttribute("aria-disabled", "true");
  await expect(coller).toContainText("Presse-papiers du Board vide");
  await page.keyboard.press("Escape");
  // palette : une commande indisponible est trouvée, grisée, avec sa raison
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Palette de commandes" });
  await palette.getByRole("combobox").fill("aligner à gauche");
  const option = palette.getByRole("option", { name: /Aligner à gauche/ });
  await expect(option).toHaveAttribute("aria-disabled", "true");
  await expect(option).toContainText("Indisponible : Sélectionne au moins deux objets à aligner");
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "palette-raison.png") });
  await page.keyboard.press("Escape");
  // après un geste, « Annuler » redevient disponible (et son info-bulle redevient simple)
  await note(page, "Une note", 300, 300);
  await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Ajouter" }).click();
  await expect(annuler).not.toHaveAttribute("aria-disabled", "true");
  await expect(annuler).toHaveAttribute("title", "Annuler (Ctrl+Z)");
});

test("ouverture : la barre d'outils et la barre d'ajout ne recouvrent aucune carte ; raccourcis lisibles", async ({ page }) => {
  await ouvrir(page);
  // des cartes jusque dans les coins : après rechargement, le cadrage initial les tient hors des barres
  for (const [i, [x, y]] of [[0, 0], [1400, 0], [0, 900], [1400, 900], [700, 450]].entries()) await note(page, `Carte ${i}`, x!, y!);
  await page.reload();
  await attendreStable(page, 700);
  const boite = async (selecteur: string) => (await page.locator(selecteur).first().boundingBox())!;
  const outils = await boite(".barre-modes"), ajout = await boite(".outils");
  const cartes = await page.locator(".react-flow__node").evaluateAll((ns) => ns.map((n) => { const r = n.getBoundingClientRect(); return { x: r.x, y: r.y, l: r.width, h: r.height }; }));
  expect(cartes).toHaveLength(5);
  const croise = (c: { x: number; y: number; l: number; h: number }, b: { x: number; y: number; width: number; height: number }) =>
    c.x < b.x + b.width && c.x + c.l > b.x && c.y < b.y + b.height && c.y + c.h > b.y;
  for (const c of cartes) {
    expect(croise(c, outils), "aucune carte sous la barre d'outils").toBe(false);
    expect(croise(c, ajout), "aucune carte sous la barre d'ajout").toBe(false);
  }
  // « Ajuster à la vue » garde la même zone libre
  await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  await page.waitForTimeout(500);
  const apres = await page.locator(".react-flow__node").evaluateAll((ns) => ns.map((n) => { const r = n.getBoundingClientRect(); return { x: r.x, y: r.y, l: r.width, h: r.height }; }));
  for (const c of apres) expect(croise(c, outils) || croise(c, ajout)).toBe(false);
  // la lettre de chaque outil : au moins 11 px, graisse 600, contraste AA sur la barre
  const lettre = page.locator(".barre-modes .mode kbd").first();
  const style = await lettre.evaluate((k) => { const s = getComputedStyle(k); return { taille: parseFloat(s.fontSize), graisse: Number(s.fontWeight), opacite: Number(s.opacity) }; });
  expect(style.taille).toBeGreaterThanOrEqual(11);
  expect(style.graisse).toBeGreaterThanOrEqual(600);
  expect(style.opacite).toBe(1);
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "ouverture-zone-libre.png") });
});

test("thème jour sur tout le produit : pages, dialogues et références, sans couleur sombre résiduelle", async ({ page }) => {
  await page.goto("/v2/?demo=1&vue=accueil");
  await expect(page.locator(".product-app")).toBeVisible();
  const luminance = (selecteur: string) => page.locator(selecteur).first().evaluate((e) => {
    const m = /rgba?\(([\d.]+), ([\d.]+), ([\d.]+)/.exec(getComputedStyle(e).backgroundColor)!;
    return (0.2126 * Number(m[1]) + 0.7152 * Number(m[2]) + 0.0722 * Number(m[3])) / 255;
  });
  expect(await luminance(".product-app")).toBeLessThan(0.2);
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "accueil-nuit.png") });
  // le thème se change hors du Board, et vaut pour tout le produit
  await page.getByRole("button", { name: "Passer au thème jour" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
  expect(await luminance(".product-app")).toBeGreaterThan(0.85);
  expect(await luminance(".product-nav")).toBeGreaterThan(0.85);
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "accueil-jour.png") });
  for (const vue of ["missions", "agents", "fichiers", "analytique", "configuration"]) {
    await page.goto(`/v2/?demo=1&vue=${vue}`);
    await expect(page.locator(".product-app")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");  // mémorisé d'une page à l'autre
    expect(await luminance(".product-app"), vue).toBeGreaterThan(0.85);
    await page.waitForTimeout(250);
    await page.waitForTimeout(450);  // fin des entrées animées
    await page.screenshot({ path: path.join(CAPTURES, `${vue}-jour.png`) });
  }
  await page.goto("/v2/?demo=1&vue=references");
  await expect(page.locator(".product-app")).toBeVisible();
  expect(await luminance(".product-app")).toBeGreaterThan(0.85);
  await page.waitForTimeout(400);
  await page.waitForTimeout(450);  // fin des entrées animées
  await page.screenshot({ path: path.join(CAPTURES, "references-jour.png") });
  // dialogues du Board réel (absents de la démo) : Réseau, Intégrations, Missions outillées — le thème y est le même
  await ouvrir(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
  for (const [bouton, dialogue, fichier] of [[".reseau-ouvrir", ".reseau-dialog", "reseau"], [".integrations-ouvrir", ".integrations-dialog", "integrations"], [".runtime-ouvrir", ".runtime-dialog", "missions-outillees"]] as const) {
    await page.locator(bouton).click();
    await expect(page.locator(dialogue)).toBeVisible();
    expect(await luminance(dialogue), fichier).toBeGreaterThan(0.85);
    await page.waitForTimeout(300);
    await page.waitForTimeout(450);  // fin des entrées animées
    await page.screenshot({ path: path.join(CAPTURES, `${fichier}-jour.png`) });
    await page.keyboard.press("Escape");
    await expect(page.locator(dialogue)).toBeHidden();
  }
  await page.evaluate(() => localStorage.removeItem("jarvis.board.preferences.v1"));
});
