import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

// Bibliothèque de références : parcours réel (serveur de test isolé, vraie capture Chromium d'une page LOCALE du
// serveur de test — aucun accès à Internet) et parcours de démonstration (données fictives).
const sorties = path.resolve("../../reports/references");
test.beforeAll(() => fs.mkdirSync(sorties, { recursive: true }));
test.use({ reducedMotion: "reduce" });
// le serveur de test n'est pas toujours sur le port par défaut (JARVIS_E2E_PORT) : la page capturée est la sienne
const PORT = process.env.JARVIS_E2E_PORT || "7721";

test.describe.configure({ mode: "serial" });

test("réel : état vide, capture d'un site, états, recherche citée, fiche, pose sur le Board", async ({ page }) => {
  test.setTimeout(120_000);
  const erreurs: string[] = [];
  page.on("pageerror", (e) => erreurs.push(e.message));
  await ouvrir(page);
  await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Références", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Tes références/ })).toBeVisible();
  await expect(page.getByText("Ta bibliothèque attend son premier site")).toBeVisible();
  await page.screenshot({ path: path.join(sorties, "vide.png") });

  // une adresse refusée par la garde : l'état « échec » est montré avec sa raison (rien n'est contacté)
  const formulaire = page.getByRole("form", { name: "Ajouter une référence" });
  await formulaire.getByLabel("Adresse du site à capturer").fill("ftp://exemple.org");
  await formulaire.getByRole("button", { name: "Capturer" }).click();
  await expect(formulaire.getByRole("alert")).toContainText(/http/);

  // capture réelle de la page d'accueil de démonstration servie par CE serveur de test
  await formulaire.getByLabel("Adresse du site à capturer").fill(`http://localhost:${PORT}/v2/?demo=1&vue=accueil`);
  await formulaire.getByLabel("Collection").fill("e2e");
  await formulaire.getByLabel("Étiquettes, séparées par des virgules").fill("accueil, sombre");
  await formulaire.getByRole("button", { name: "Capturer" }).click();
  const carte = page.locator(".rf-card").first();
  await expect(carte).toBeVisible();
  await expect(page.locator(".rf-card.is-prete")).toHaveCount(1, { timeout: 90_000 });
  await expect(carte.locator(".rf-card-preview img")).toBeVisible();
  await expect(carte.locator(".rf-strip i").first()).toBeVisible();
  await expect(carte).toContainText("e2e");
  await expect(carte).toContainText("#accueil");
  await page.screenshot({ path: path.join(sorties, "grille.png") });

  // recherche à la frappe : seule la dernière question compte, les passages sont surlignés et cités
  await page.keyboard.press("/");
  const champ = page.getByRole("searchbox", { name: "Rechercher dans les références" });
  await expect(champ).toBeFocused();
  await champ.pressSequentially("zzz introuvable", { delay: 5 });
  await champ.fill("");
  await champ.pressSequentially("rassembler le contexte", { delay: 15 });
  await expect(page.locator(".rf-count")).toContainText("pour « rassembler le contexte »");
  const passage = page.locator(".rf-result").first();
  await expect(passage.locator("mark").first()).toBeVisible();
  await expect(passage.locator("mark").first()).toHaveText(/rassembler|contexte/i);
  await expect(passage.locator("footer")).toContainText("capturé le");
  await expect(passage.locator("footer a")).toHaveAttribute("rel", /noopener/);
  expect(new URL(page.url()).searchParams.get("q")).toBe("rassembler le contexte");
  await page.screenshot({ path: path.join(sorties, "recherche.png") });

  // clavier : flèche bas vers le premier passage, Entrée ouvre la fiche sur la section d'origine
  await champ.press("ArrowDown");
  await expect(passage.locator(".rf-result-open")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#rf-fiche-titre")).toBeFocused();
  await expect(page.getByRole("img", { name: /Capture bureau/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /Capture mobile/ })).toBeVisible();
  for (const [nom, largeur] of [["bureau", 1440], ["mobile", 390]] as const) {  // les vraies images, aux deux gabarits
    await expect.poll(() => page.getByRole("img", { name: new RegExp(`Capture ${nom}`) }).evaluate((i: HTMLImageElement) => i.naturalWidth)).toBe(largeur);
  }
  await expect(page.locator(".rf-swatches button").first()).toBeVisible();
  await expect(page.locator(".rf-fonts")).toContainText(/Inter/);
  await expect(page.locator(".rf-sections li").first()).toBeVisible();
  await page.locator(".rf-sections button").first().click();
  await expect(page.locator(".rf-zone")).toBeVisible();
  await page.screenshot({ path: path.join(sorties, "fiche.png") });

  // « Poser sur le Board » : une carte reliée à la référence apparaît sur le canevas
  const id = new URL(page.url()).searchParams.get("ref");
  expect(id).toMatch(/^RF-[0-9a-f]{12}$/);
  await page.getByRole("button", { name: "Poser sur le Board" }).click();
  await expect(page.locator(".react-flow")).toBeVisible();
  // (le Board consomme le paramètre ?carte= dès qu'il a sélectionné la carte : on la retrouve par sa référence)
  const cartes = await page.evaluate(async (rid) => (await (await fetch("/api/v2/board")).json()).objets
    .filter((o: { meta: { reference_id?: string } }) => o.meta.reference_id === rid)
    .map((o: { id: string; type: string; asset: { url: string } | null }) => ({ id: o.id, type: o.type, image: Boolean(o.asset) })), id);
  expect(cartes).toHaveLength(1);
  expect(cartes[0]).toMatchObject({ type: "capture", image: true });
  await expect(page.locator(`.react-flow__node[data-id="${cartes[0].id}"]`)).toBeVisible();
  await page.screenshot({ path: path.join(sorties, "board.png") });
  expect(erreurs).toEqual([]);
});

test("réel : un texte s'indexe sans capture, se retire et se restaure", async ({ page }) => {
  await ouvrir(page);
  await page.goto("/v2/?vue=references");
  const formulaire = page.getByRole("form", { name: "Ajouter une référence" });
  await formulaire.getByRole("button", { name: "Texte" }).click();
  await formulaire.getByLabel("Titre du texte").fill("Charte éditoriale");
  await formulaire.getByLabel("Texte à indexer").fill("# Ton\nPhrases courtes, verbes d'action.\n## Couleurs\nLe fond crème et l'encre noire dominent.");
  await formulaire.getByRole("button", { name: "Indexer" }).click();
  await expect(page.locator(".rf-card", { hasText: "Charte éditoriale" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Rechercher dans les références" }).fill("creme");
  await expect(page.locator(".rf-result mark").first()).toHaveText("crème");
  await page.locator(".rf-result-open").first().click();
  await page.getByRole("button", { name: /Retirer Charte éditoriale/ }).click();
  await expect(page.locator(".rf-feedback")).toContainText("retirée");
  await expect(page.locator(".rf-result")).toHaveCount(0);
  await page.locator(".rf-feedback-action").click();
  await expect(page.locator(".rf-result mark").first()).toHaveText("crème");
});

for (const [nom, largeur, hauteur] of [["bureau", 1440, 1000], ["mobile", 390, 844]] as const) {
  test(`démo ${nom} : grille, filtres, recherche, fiche, sans débordement`, async ({ page }) => {
    const erreurs: string[] = [];
    page.on("pageerror", (e) => erreurs.push(e.message));
    await page.setViewportSize({ width: largeur, height: hauteur });
    await page.goto("/v2/?demo=1&vue=references");
    await expect(page.locator(".rf-card")).toHaveCount(4);
    await expect(page.getByRole("button", { name: "Capturer" })).toBeDisabled();
    await page.screenshot({ path: path.join(sorties, `demo-grille-${nom}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("group", { name: "Collections" }).getByRole("button", { name: /inspiration/ }).click();
    await expect(page.locator(".rf-card")).toHaveCount(2);
    await page.getByRole("group", { name: "Collections" }).getByRole("button", { name: /Toutes/ }).click();
    await page.getByRole("searchbox", { name: "Rechercher dans les références" }).fill("tarifs");
    await expect(page.locator(".rf-result")).not.toHaveCount(0);
    await expect(page.locator(".rf-result mark").first()).toBeVisible();
    await page.screenshot({ path: path.join(sorties, `demo-recherche-${nom}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.locator(".rf-result-open").first().click();
    await expect(page.locator("#rf-fiche-titre")).toBeVisible();
    await expect(page.locator(".rf-swatches button")).not.toHaveCount(0);
    await page.screenshot({ path: path.join(sorties, `demo-fiche-${nom}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { level: 1, name: /Tes références/ })).toBeVisible();
    await page.goto("/v2/?demo=1&vue=connaissances");
    await expect(page.getByRole("heading", { level: 1, name: /Tes références/ })).toBeVisible();
    expect(erreurs).toEqual([]);
  });
}
