import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { RAPPORTS, attendreStable, ouvrir } from "./outils";

// Tableau blanc du Board : registre de commandes (palette, raccourcis, menus), annuler / rétablir, outils, cartes
// intelligentes, modes d'affichage, niveau de détail, flèches, export. Board RÉEL (API + base isolée) sauf mention.
const CAPTURES = path.join(RAPPORTS, "captures");
const ENTETES = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };

interface Objet { id: string; type: string; x: number; y: number; largeur: number; hauteur: number; contenu: string; version: number; meta: Record<string, unknown> }
interface Lien { id: string; source_id: string; cible_id: string; style: string }

async function board(page: Page): Promise<{ objets: Objet[]; liens: Lien[] }> {
  return page.evaluate(async () => (await fetch("/api/v2/board")).json());
}
async function creer(page: Page, objet: Record<string, unknown>): Promise<string> {
  const id = await page.evaluate(async ([o, h]) => (await (await fetch("/api/v2/objets", { method: "POST", headers: h as Record<string, string>,
    body: JSON.stringify({ analyser: false, ...(o as object) }) })).json()).objet_id as string, [objet, ENTETES] as const);
  await expect(noeud(page, id)).toBeAttached();
  return id;
}
const noeud = (page: Page, id: string) => page.locator(`.react-flow__node[data-id="${id}"]`);
const objetsDeType = async (page: Page, type: string) => (await board(page)).objets.filter((o) => o.type === type);
/** Zone libre du canevas (hors barre d'ajout à gauche et barre d'outils en haut). */
async function zone(page: Page) {
  const b = (await page.locator(".canevas").boundingBox())!;
  return { x: b.x + 220, y: b.y + 160, l: b.width - 320, h: b.height - 260 };
}
async function glisser(page: Page, de: [number, number], a: [number, number], pas = 12) {
  await page.mouse.move(de[0], de[1]);
  await page.mouse.down();
  await page.mouse.move(a[0], a[1], { steps: pas });
  await page.mouse.up();
}
const outils = (page: Page) => page.getByRole("toolbar", { name: "Outils" });

test.beforeAll(() => fs.mkdirSync(CAPTURES, { recursive: true }));

test.describe("commandes", () => {
  test("palette Ctrl+K : recherche floue, raccourci affiché, exécution, récents, journal d'usage local", async ({ page }) => {
    await ouvrir(page);
    await page.keyboard.press("Control+k");
    const palette = page.getByRole("dialog", { name: "Palette de commandes" });
    await expect(palette).toBeVisible();
    const champ = palette.getByRole("combobox", { name: "Chercher une commande" });
    await expect(champ).toBeFocused();
    await champ.fill("alg");  // aucune sélection : « aligner » n'est pas disponible, donc pas proposé
    await expect(palette.getByRole("option", { name: /Aligner à gauche/ })).toHaveCount(0);
    await champ.fill("outil rect");
    await expect(palette.getByRole("option").first()).toContainText("Outil : Rectangle");
    await expect(palette.getByRole("option").first().locator("kbd")).toHaveText("R");
    await champ.fill("outil");
    await expect(palette.getByRole("option").nth(12)).toContainText("Outil : ");  // les 13 outils d'abord, chacun avec sa touche
    await page.screenshot({ path: path.join(CAPTURES, "palette-commandes.png") });
    await champ.fill("theme jour");
    await expect(palette.getByRole("option").first()).toContainText("Thème jour");
    await page.keyboard.press("Enter");
    await expect(palette).toBeHidden();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
    // la commande exécutée remonte dans « Récents » ; Échap ferme sans rien exécuter
    await page.keyboard.press("Control+k");
    await expect(palette.locator(".palette-groupe").first()).toHaveText("Récents");
    await expect(palette.getByRole("option").first()).toContainText("Thème jour");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    await expect(palette).toBeHidden();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
    // journal local : compteur et chemin d'exécution, identifiants de commandes seulement
    const journal = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.board.commandes.v1") ?? "{}"));
    const parId = Object.fromEntries((journal.commandes as { id: string; n: number; origines: Record<string, number> }[]).map((c) => [c.id, c]));
    expect(parId["affichage.theme.jour"]).toMatchObject({ n: 1, origines: { palette: 1 } });
    expect(parId["palette.ouvrir"]).toMatchObject({ n: 2, origines: { raccourci: 2 } });
    // la préférence de thème est mémorisée
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
    await page.evaluate(() => localStorage.removeItem("jarvis.board.preferences.v1"));
  });

  test("menu contextuel et barre flottante : mêmes commandes, actions selon le type de carte", async ({ page }) => {
    await ouvrir(page);
    const lien = await creer(page, { type: "lien", contenu: "https://exemple.test/article", x: 300, y: 200, largeur: 434, hauteur: 356,
      meta: { url: "https://exemple.test/article", hote: "exemple.test", titre: "Article de fond" } });
    await noeud(page, lien).click({ button: "right", position: { x: 60, y: 300 } });
    const menu = page.getByRole("menu", { name: "Actions de la sélection" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Dupliquer/ })).toContainText("Ctrl+D");
    await page.keyboard.press("ArrowDown");  // navigation au clavier dans le menu
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    // la barre flottante propose l'action propre aux liens ; elle crée une note reliée par « Inspire », sans mission
    const barre = page.getByRole("toolbar", { name: "Sélection" });
    await barre.getByRole("button", { name: "Créer une tâche inspirée de ceci" }).click();
    await expect.poll(async () => (await board(page)).liens.map((l) => l.style)).toEqual(["inspire"]);
    const etat = await board(page);
    const tache = etat.objets.find((o) => o.type === "note")!;
    expect(tache.meta.titre).toBe("Tâche : Article de fond");
    expect(etat.liens[0]).toMatchObject({ source_id: lien, cible_id: tache.id });
    // un seul Ctrl+Z défait la note ET sa relation (geste groupé)
    await page.keyboard.press("Control+z");
    await expect.poll(async () => { const e = await board(page); return [e.objets.length, e.liens.length]; }).toEqual([1, 0]);
  });

  test("type de relation : choisi au menu contextuel, rendu distinct, annulable", async ({ page }) => {
    await ouvrir(page);
    const a = await creer(page, { type: "note", contenu: "A", x: 200, y: 260, largeur: 300, hauteur: 220, meta: { titre: "Source" } });
    const b = await creer(page, { type: "note", contenu: "B", x: 760, y: 260, largeur: 300, hauteur: 220, meta: { titre: "Cible" } });
    await page.evaluate(async ([s, c, h]) => fetch("/api/v2/liens", { method: "POST", headers: h as Record<string, string>,
      body: JSON.stringify({ source_id: s, cible_id: c, libelle: "", style: "defaut" }) }), [a, b, ENTETES] as const);
    const arete = page.locator(".react-flow__edge");
    await expect(arete).toHaveCount(1);
    const avant = await arete.locator(".react-flow__edge-path").evaluate((p) => getComputedStyle(p).strokeDasharray);
    // clic droit au milieu de la flèche (entre les deux cartes)
    const ba = (await noeud(page, a).boundingBox())!, bb = (await noeud(page, b).boundingBox())!;
    await page.mouse.click((ba.x + ba.width + bb.x) / 2, ba.y + ba.height / 2, { button: "right" });
    const menu = page.getByRole("menu", { name: "Actions de la relation" });
    await expect(menu.getByRole("menuitemcheckbox", { name: "Relation : Relation simple" })).toHaveAttribute("aria-checked", "true");
    await menu.getByRole("menuitemcheckbox", { name: "Relation : Dépend de" }).click();
    await expect.poll(async () => (await board(page)).liens[0]?.style).toBe("depend");
    await expect.poll(() => arete.locator(".react-flow__edge-path").evaluate((p) => getComputedStyle(p).strokeDasharray)).not.toBe(avant);
    await page.keyboard.press("Control+z");
    await expect.poll(async () => (await board(page)).liens[0]?.style).toBe("defaut");
  });
});

test.describe("outils de tableau blanc", () => {
  test("formes au raccourci, redimensionnables, persistées ; annuler / rétablir", async ({ page }) => {
    await ouvrir(page);
    const z = await zone(page);
    await page.keyboard.press("r");
    await expect(outils(page).getByRole("button", { name: "Rectangle" })).toHaveAttribute("aria-pressed", "true");
    await glisser(page, [z.x, z.y], [z.x + 240, z.y + 160]);
    await expect(page.locator(".react-flow__node-forme")).toHaveCount(1);
    await expect(outils(page).getByRole("button", { name: "Sélection" })).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("o");
    await glisser(page, [z.x + 320, z.y], [z.x + 520, z.y + 160]);
    await page.keyboard.press("d");
    await glisser(page, [z.x + 600, z.y], [z.x + 760, z.y + 160]);
    await expect.poll(async () => (await objetsDeType(page, "forme")).map((o) => o.meta.forme).sort()).toEqual(["ellipse", "losange", "rectangle"]);
    const rect = (await objetsDeType(page, "forme")).find((o) => o.meta.forme === "rectangle")!;
    expect([rect.largeur, rect.hauteur]).toEqual([300, 200]);  // 240 × 160 px à 80 % de zoom
    // redimensionner par la poignée bas-droite du dernier objet créé (sélectionné)
    const losange = (await objetsDeType(page, "forme")).find((o) => o.meta.forme === "losange")!;
    const poignee = noeud(page, losange.id).locator(".react-flow__resize-control.bottom.right");
    const p = (await poignee.boundingBox())!;
    await glisser(page, [p.x + p.width / 2, p.y + p.height / 2], [p.x + 60, p.y + 50]);
    await expect.poll(async () => (await objetsDeType(page, "forme")).find((o) => o.id === losange.id)!.largeur).toBeGreaterThan(losange.largeur + 40);
    // annuler trois fois : redimensionnement, losange, ellipse ; rétablir une fois : l'ellipse revient
    for (let i = 0; i < 3; i++) await page.keyboard.press("Control+z");
    await expect.poll(async () => (await objetsDeType(page, "forme")).map((o) => o.meta.forme)).toEqual(["rectangle"]);
    await page.keyboard.press("Control+Shift+z");
    await expect.poll(async () => (await objetsDeType(page, "forme")).map((o) => o.meta.forme).sort()).toEqual(["ellipse", "rectangle"]);
    await page.reload();
    await expect(page.locator(".react-flow__node-forme")).toHaveCount(2);
  });

  test("note adhésive et texte libre : édition en place hors du calque transformé, tout reste du texte", async ({ page }) => {
    await ouvrir(page);
    const z = await zone(page);
    await page.keyboard.press("n");
    await page.mouse.click(z.x + 150, z.y + 150);
    const editeur = page.locator(".editeur-texte");
    await expect(editeur).toBeFocused();
    // la surcouche d'édition n'est pas dans le calque mis à l'échelle : curseur net, pas de transform hérité
    expect(await editeur.evaluate((e) => Boolean(e.closest(".react-flow__viewport")))).toBe(false);
    expect(await editeur.evaluate((e) => getComputedStyle(e).transform)).toBe("none");
    const piege = "<img src=x onerror=\"window.__pirate=1\"> <b>gras</b> javascript:alert(1)";
    await page.keyboard.type("Idée : ");
    await page.keyboard.insertText(piege);
    await page.keyboard.press("Escape");
    await expect(editeur).toHaveCount(0);
    await expect.poll(async () => (await objetsDeType(page, "adhesif"))[0]?.contenu).toBe(`Idée : ${piege}`);
    const adhesif = page.locator(".react-flow__node-adhesif");
    await expect(adhesif).toContainText("<img src=x");
    expect(await adhesif.locator("img, b, a").count()).toBe(0);
    expect(await page.evaluate(() => (window as unknown as { __pirate?: number }).__pirate)).toBeUndefined();
    // texte libre : créé au clic, s'agrandit avec le texte ; laissé vide, il disparaît
    await page.keyboard.press("t");
    await page.mouse.click(z.x + 500, z.y + 60);
    await expect(editeur).toBeFocused();
    await page.keyboard.type("Titre du tableau");
    await page.keyboard.press("Control+Enter");
    await expect.poll(async () => (await objetsDeType(page, "texte_libre"))[0]?.contenu).toBe("Titre du tableau");
    await page.keyboard.press("t");
    await page.mouse.click(z.x + 500, z.y + 300);
    await expect(editeur).toBeFocused();
    await page.keyboard.press("Escape");
    await expect.poll(async () => (await objetsDeType(page, "texte_libre")).length).toBe(1);
    // rouvrir par double-clic : le texte enregistré est dans le champ
    await adhesif.dblclick();
    await expect(editeur).toHaveValue(`Idée : ${piege}`);
    await page.keyboard.press("Escape");
  });

  test("crayon, surligneur, gomme : traits bornés, figés en chemin SVG, effaçables et annulables", async ({ page }) => {
    await ouvrir(page);
    const z = await zone(page);
    await page.keyboard.press("p");
    const couche = page.locator(".couche-outils");
    await expect(couche).toHaveCSS("touch-action", "none");
    await page.mouse.move(z.x, z.y + 100);
    await page.mouse.down();
    for (let i = 1; i <= 120; i++) await page.mouse.move(z.x + i * 4, z.y + 100 + Math.sin(i / 6) * 60);
    await page.mouse.up();
    await expect.poll(async () => (await objetsDeType(page, "trait")).length).toBe(1);
    const trait = (await objetsDeType(page, "trait"))[0]!;
    const points = trait.meta.points as number[];
    expect(points.length % 3).toBe(0);
    expect(points.length / 3).toBeGreaterThan(8);
    expect(points.length / 3).toBeLessThanOrEqual(700);
    expect(trait.meta).toMatchObject({ outil: "crayon", couleur: "indigo" });
    const chemin = noeud(page, trait.id).locator("svg.trait path");
    await expect(chemin).toHaveAttribute("d", /^M[\d.,-]+ Q/);
    // le crayon reste actif : un second trait au surligneur, puis la gomme efface le premier seulement
    await page.keyboard.press("s");
    await glisser(page, [z.x, z.y + 320], [z.x + 400, z.y + 330], 20);
    await expect.poll(async () => (await objetsDeType(page, "trait")).map((o) => o.meta.outil).sort()).toEqual(["crayon", "surligneur"]);
    await page.keyboard.press("e");
    await glisser(page, [z.x + 200, z.y - 20], [z.x + 200, z.y + 220], 20);
    await expect.poll(async () => (await objetsDeType(page, "trait")).map((o) => o.meta.outil)).toEqual(["surligneur"]);
    await page.keyboard.press("Control+z");
    await expect.poll(async () => (await objetsDeType(page, "trait")).length).toBe(2);
    // le serveur refuse un trait hors bornes, même envoyé à la main
    const code = await page.evaluate(async (h) => (await fetch("/api/v2/objets", { method: "POST", headers: h,
      body: JSON.stringify({ type: "trait", meta: { points: Array(3 * 1501).fill(1), boite: [10, 10] } }) })).status, ENTETES);
    expect(code).toBe(400);
  });

  test("lasso, barre flottante, aligner ; guides magnétiques pendant le glisser", async ({ page }) => {
    await ouvrir(page);
    const a = await creer(page, { type: "forme", x: 300, y: 300, largeur: 160, hauteur: 120, meta: { forme: "rectangle", couleur: "vert" } });
    const b = await creer(page, { type: "forme", x: 620, y: 380, largeur: 160, hauteur: 120, meta: { forme: "ellipse", couleur: "rose" } });
    await page.waitForTimeout(600);  // la vue s'ajuste à l'arrivée des premiers objets
    const ba = (await noeud(page, a).boundingBox())!, bb = (await noeud(page, b).boundingBox())!;
    await page.keyboard.press("l");
    await page.mouse.move(ba.x - 40, ba.y - 40);
    await page.mouse.down();
    for (const [x, y] of [[bb.x + bb.width + 40, ba.y - 40], [bb.x + bb.width + 40, bb.y + bb.height + 40], [ba.x - 40, bb.y + bb.height + 40], [ba.x - 40, ba.y - 30]] as const) {
      await page.mouse.move(x, y, { steps: 8 });
    }
    await page.mouse.up();
    const barre = page.getByRole("toolbar", { name: "Sélection" });
    await expect(barre).toContainText("2 objets");
    await barre.getByRole("button", { name: "Aligner en haut" }).click();
    await expect.poll(async () => (await board(page)).objets.map((o) => o.y)).toEqual([300, 300]);
    // guides : glisser B vers la droite sur la même ligne ; une légère dérive verticale est rattrapée par l'accroche
    await page.keyboard.press("Escape");
    await expect(barre).toHaveCount(0);
    const depart = (await noeud(page, b).boundingBox())!;
    await page.mouse.move(depart.x + 80, depart.y + 60);
    await page.mouse.down();
    await page.mouse.move(depart.x + 200, depart.y + 63, { steps: 10 });
    await expect(page.locator(".guides line").first()).toBeAttached();
    await page.mouse.up();
    await expect(page.locator(".guides line")).toHaveCount(0);
    await expect.poll(async () => (await board(page)).objets.find((o) => o.id === b)!.x).toBeGreaterThan(700);
    expect((await board(page)).objets.find((o) => o.id === b)!.y).toBe(300);
  });

  test("un cadre emporte son contenu ; un seul Ctrl+Z remet tout en place", async ({ page }) => {
    await ouvrir(page);
    const cadre = await creer(page, { type: "cadre", x: 260, y: 220, largeur: 520, hauteur: 360, meta: { titre: "Sprint 1" } });
    const dedans = await creer(page, { type: "adhesif", contenu: "dedans", x: 320, y: 300, largeur: 160, hauteur: 160, meta: { couleur: "jaune" } });
    const dehors = await creer(page, { type: "adhesif", contenu: "dehors", x: 900, y: 300, largeur: 160, hauteur: 160, meta: { couleur: "rose" } });
    const titre = noeud(page, cadre).locator(".cadre-titre");
    await expect(titre).toHaveText("Sprint 1");
    await page.waitForTimeout(600);  // la vue s'ajuste à l'arrivée des premiers objets
    const t = (await titre.boundingBox())!;
    await glisser(page, [t.x + 20, t.y + 12], [t.x + 20 + 120, t.y + 12 + 80]);
    const position = async (id: string) => { const o = (await board(page)).objets.find((x) => x.id === id)!; return [o.x, o.y]; };
    await expect.poll(async () => (await position(cadre))[0]).toBeGreaterThan(300);
    // le contenu a bougé exactement du même décalage que le cadre ; ce qui est dehors n'a pas bougé
    const [cx, cy] = await position(cadre);
    expect(cy).toBeGreaterThan(260);
    expect(await position(dedans)).toEqual([320 + cx! - 260, 300 + cy! - 220]);
    expect(await position(dehors)).toEqual([900, 300]);
    await page.keyboard.press("Control+z");
    await expect.poll(() => position(cadre)).toEqual([260, 220]);
    expect(await position(dedans)).toEqual([320, 300]);
  });

  test("flèche : d'une carte à une autre = relation ; vers une forme = extrémité ancrée sur le périmètre", async ({ page }) => {
    await ouvrir(page);
    const a = await creer(page, { type: "note", contenu: "A", x: 200, y: 300, largeur: 280, hauteur: 200, meta: { titre: "Départ" } });
    const b = await creer(page, { type: "note", contenu: "B", x: 620, y: 300, largeur: 280, hauteur: 200, meta: { titre: "Arrivée" } });
    const rond = await creer(page, { type: "forme", x: 1050, y: 520, largeur: 200, hauteur: 200, meta: { forme: "ellipse" } });
    await page.waitForTimeout(600);  // la vue s'ajuste à l'arrivée des premiers objets
    const ba = (await noeud(page, a).boundingBox())!, bb = (await noeud(page, b).boundingBox())!, br = (await noeud(page, rond).boundingBox())!;
    await page.keyboard.press("a");
    await glisser(page, [ba.x + ba.width / 2, ba.y + ba.height / 2], [bb.x + bb.width / 2, bb.y + bb.height / 2]);
    await expect.poll(async () => (await board(page)).liens.map((l) => [l.source_id, l.cible_id])).toEqual([[a, b]]);
    // depuis le vide vers l'ellipse : une flèche libre, ancrée à l'ellipse
    await page.keyboard.press("a");
    await glisser(page, [br.x - br.width * 0.8, br.y + br.height / 2], [br.x + br.width / 2, br.y + br.height / 2]);
    await expect.poll(async () => (await objetsDeType(page, "fleche")).length).toBe(1);
    const fleche = (await objetsDeType(page, "fleche"))[0]!;
    expect(fleche.meta.ancres).toEqual({ vers: { id: rond, nx: 0.5, ny: 0.5 } });
    // la pointe s'arrête sur le bord gauche de l'ellipse (périmètre réel), pas en son centre
    const pointe = noeud(page, fleche.id).locator("line.fleche-trait");
    const x2 = Number(await pointe.getAttribute("x2")) + fleche.x;
    expect(Math.abs(x2 - 1050)).toBeLessThan(2);
    // déplacer l'ellipse par l'API : la flèche suit son ancre sans être réécrite
    await page.evaluate(async ([id, h]) => fetch(`/api/v2/objets/${id}`, { method: "POST", headers: h as Record<string, string>, body: JSON.stringify({ champs: { x: 1150 } }) }), [rond, ENTETES] as const);
    await expect.poll(async () => Number(await pointe.getAttribute("x2")) + fleche.x).toBeGreaterThan(1145);
    expect((await objetsDeType(page, "fleche"))[0]!.version).toBe(fleche.version);
  });
});

test.describe("modes d'affichage", () => {
  test("thèmes jour, nuit et automatique (captures) ; zen ; plein écran", async ({ page }) => {
    await page.goto("/v2/?demo=1");
    await attendreStable(page);
    await page.locator(".react-flow__pane").click({ position: { x: 1000, y: 760 } });
    await page.screenshot({ path: path.join(CAPTURES, "theme-nuit.png") });
    const fond = () => page.locator(".canevas").evaluate((e) => getComputedStyle(e).backgroundColor);
    const sombre = await fond();
    await page.getByRole("button", { name: "Basculer jour / nuit" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
    expect(await fond()).not.toBe(sombre);
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(CAPTURES, "theme-jour.png") });
    // automatique : suit la préférence du système
    await page.keyboard.press("Control+k");
    await page.keyboard.type("theme auto");
    await page.keyboard.press("Enter");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "nuit");
    // zen : l'interface disparaît, le canevas et ses outils restent ; Échap en sort
    await page.keyboard.press("Control+.");
    await expect(page.locator(".subbar")).toHaveCount(0);
    await expect(page.locator(".panneau, aside").first()).toHaveCount(0);
    await expect(outils(page)).toBeVisible();
    // Échap désélectionne d'abord s'il y a une sélection, puis quitte le zen
    await expect(async () => {
      await page.keyboard.press("Escape");
      await expect(page.locator(".subbar")).toBeVisible({ timeout: 400 });
    }).toPass({ timeout: 8000 });
    await page.keyboard.press("Shift+f");
    await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
    await page.keyboard.press("Shift+f");
    await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);
    await page.evaluate(() => localStorage.removeItem("jarvis.board.preferences.v1"));
  });

  test("présentation : les cadres deviennent des diapositives, flèches du clavier ; concentration sur un cadre", async ({ page }) => {
    await ouvrir(page);
    const un = await creer(page, { type: "cadre", x: 0, y: 0, largeur: 800, hauteur: 500, meta: { titre: "Contexte" } });
    await creer(page, { type: "cadre", x: 1000, y: 0, largeur: 800, hauteur: 500, meta: { titre: "Plan" } });
    await creer(page, { type: "adhesif", contenu: "Pourquoi maintenant", x: 80, y: 120, largeur: 240, hauteur: 200, meta: { couleur: "jaune" } });
    await creer(page, { type: "forme", contenu: "Étape 1", x: 1100, y: 140, largeur: 260, hauteur: 160, meta: { forme: "losange", couleur: "cyan" } });
    const hors = await creer(page, { type: "adhesif", contenu: "hors cadre", x: 300, y: 800, largeur: 200, hauteur: 160, meta: { couleur: "rose" } });
    await page.keyboard.press("Shift+p");
    const barre = page.getByRole("toolbar", { name: "Présentation" });
    await expect(barre.locator("output")).toHaveText("1 / 2");
    await expect(barre).toContainText("Contexte");
    await expect(page.locator(".subbar")).toHaveCount(0);
    await expect(outils(page)).toHaveCount(0);
    await expect(noeud(page, hors)).toHaveClass(/estompe/);
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(CAPTURES, "mode-presentation.png") });
    await page.keyboard.press("ArrowRight");
    await expect(barre.locator("output")).toHaveText("2 / 2");
    await expect(barre).toContainText("Plan");
    await page.keyboard.press("Delete");  // aucune écriture possible pendant la présentation
    await page.keyboard.press("ArrowLeft");
    await expect(barre.locator("output")).toHaveText("1 / 2");
    await page.keyboard.press("Escape");
    await expect(barre).toHaveCount(0);
    await expect(page.locator(".subbar")).toBeVisible();
    expect((await board(page)).objets).toHaveLength(5);
    // concentration : sélectionner le cadre, Maj+C ; le reste s'estompe ; Échap en sort
    await page.keyboard.press("Shift+1");
    await page.waitForTimeout(400);
    await noeud(page, un).locator(".cadre-titre").click();
    await page.keyboard.press("Shift+c");
    await expect(page.getByRole("status").filter({ hasText: "Concentration sur « Contexte »" })).toBeVisible();
    await expect(noeud(page, hors)).toHaveClass(/estompe/);
    await page.keyboard.press("Escape");
    await expect(noeud(page, hors)).not.toHaveClass(/estompe/);
  });

  test("niveau de détail : rectangle titré sous 35 %, bloc de couleur sous 12 %, zoom de 5 % à 800 %", async ({ page }) => {
    await page.goto("/v2/?demo=1&charge=600");
    await attendreStable(page);
    await expect(page.locator(".carte").first()).toBeVisible();
    expect(await page.locator(".react-flow__node img, .react-flow__node audio, .react-flow__node video").count()).toBeGreaterThan(0);
    const zoom = page.locator(".zoom output");
    const pane = (await page.locator(".react-flow__pane").boundingBox())!;
    await page.mouse.move(pane.x + pane.width / 2, pane.y + pane.height / 2);
    const jusqua = async (cible: number, sens: 1 | -1) => {
      for (let i = 0; i < 80 && sens * (parseInt((await zoom.textContent())!, 10) - cible) > 0; i++) {
        await page.mouse.wheel(0, 240 * sens);
        await page.waitForTimeout(30);
      }
    };
    await jusqua(30, 1);
    await expect(page.locator(".carte-resume").first()).toBeVisible();
    await expect(page.locator(".react-flow__node .carte:not(.carte-resume):not(.carte-bloc)")).toHaveCount(0);
    expect(await page.locator(".react-flow__node img, .react-flow__node audio, .react-flow__node video, .react-flow__node iframe").count()).toBe(0);
    await jusqua(10, 1);
    await expect(page.locator(".carte-bloc").first()).toBeVisible();
    await expect(page.locator(".carte-resume")).toHaveCount(0);
    await jusqua(5, 1);
    await expect(zoom).toHaveText("5%");
    await jusqua(800, -1);
    await expect(zoom).toHaveText("800%");
  });
});

test("vitrine : un tableau blanc complet, enregistré par l'API, rendu dans les deux thèmes (captures)", async ({ page }) => {
  await ouvrir(page);
  const cadre = await creer(page, { type: "cadre", x: 0, y: 0, largeur: 1500, hauteur: 820, meta: { titre: "Atelier de lancement" } });
  await creer(page, { type: "texte_libre", contenu: "Lancement v2", x: 60, y: 50, largeur: 420, hauteur: 70, meta: { couleur: "neutre", taille_police: 48 } });
  const idees = [["Onboarding en 3 étapes", "jaune"], ["Mode hors ligne", "rose"], ["Partage par lien", "vert"], ["Tarifs à l'usage", "cyan"], ["Import depuis Notion", "violet"], ["Thème clair", "orange"]] as const;
  for (const [i, [texte, couleur]] of idees.entries()) {
    await creer(page, { type: "adhesif", contenu: texte, x: 60 + (i % 3) * 210, y: 170 + Math.floor(i / 3) * 210, largeur: 190, hauteur: 190, meta: { couleur } });
  }
  const a = await creer(page, { type: "forme", contenu: "Idées triées", x: 780, y: 170, largeur: 220, hauteur: 120, meta: { forme: "rectangle", couleur: "indigo", epaisseur: 3 } });
  const b = await creer(page, { type: "forme", contenu: "Assez de\nsignal ?", x: 790, y: 390, largeur: 200, hauteur: 170, meta: { forme: "losange", couleur: "orange", epaisseur: 3 } });
  const c = await creer(page, { type: "forme", contenu: "Prototype", x: 1160, y: 400, largeur: 220, hauteur: 150, meta: { forme: "ellipse", couleur: "vert", epaisseur: 3 } });
  const note = await creer(page, { type: "note", contenu: "**Décision** : on teste l'onboarding d'abord.\n- 5 utilisateurs\n- une semaine", x: 1080, y: 110, largeur: 360, hauteur: 230, priorite: "P1", meta: { titre: "Compte rendu" } });
  for (const [s, t, style, libelle] of [[a, b, "defaut", ""], [b, c, "alimente", "oui"], [c, note, "depend", ""]] as const) {
    await page.evaluate(async ([s, t, style, libelle, h]) => fetch("/api/v2/liens", { method: "POST", headers: h as Record<string, string>,
      body: JSON.stringify({ source_id: s, cible_id: t, libelle, style }) }), [s, t, style, libelle, ENTETES] as const);
  }
  // un trait de crayon et un coup de surligneur, enregistrés comme le fait l'outil (points relatifs, pression en %)
  const vague = Array.from({ length: 60 }, (_, i) => [10 + i * 6, 40 + Math.round(Math.sin(i / 5) * 26), 30 + (i % 20) * 3]).flat();
  await creer(page, { type: "trait", x: 60, y: 610, largeur: 380, hauteur: 80, meta: { points: vague, boite: [380, 80], outil: "crayon", couleur: "rose", epaisseur: 6 } });
  await creer(page, { type: "trait", x: 50, y: 56, largeur: 440, hauteur: 60, meta: { points: [10, 30, 50, 430, 32, 50], boite: [440, 60], outil: "surligneur", couleur: "jaune", epaisseur: 34 } });
  await creer(page, { type: "fleche", contenu: "à creuser", x: 480, y: 640, largeur: 300, hauteur: 40, meta: { points: [0, 0.5, 1, 0.5], pointes: "fin", couleur: "neutre", epaisseur: 3,
    ancres: { vers: { id: b, nx: 0.5, ny: 0.9 } } } });
  await expect(page.locator(".react-flow__edge")).toHaveCount(3);
  // mode zen (tout l'écran pour le canevas), cadré sur le cadre
  await page.keyboard.press("Control+.");
  await expect(page.locator(".subbar")).toHaveCount(0);
  await noeud(page, cadre).locator(".cadre-titre").click();
  await page.keyboard.press("Shift+2");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(CAPTURES, "tableau-blanc-nuit.png") });
  await page.keyboard.press("Shift+d");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "jour");
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(CAPTURES, "tableau-blanc-jour.png") });
  // les objets viennent du serveur : après rechargement, tout est encore là
  expect((await board(page)).objets).toHaveLength(15);
  await page.evaluate(() => localStorage.removeItem("jarvis.board.preferences.v1"));
});

test("export PNG de la sélection : fichier téléchargé, image valide", async ({ page }) => {
  await ouvrir(page);
  const forme = await creer(page, { type: "forme", contenu: "À exporter", x: 300, y: 300, largeur: 240, hauteur: 160, meta: { forme: "ellipse", couleur: "violet" } });
  await creer(page, { type: "adhesif", contenu: "pas dans l'export", x: 700, y: 300, largeur: 200, hauteur: 200, meta: { couleur: "jaune" } });
  await noeud(page, forme).click();
  const vue = await page.locator(".react-flow__viewport").evaluate((e) => getComputedStyle(e).transform);
  const telechargement = page.waitForEvent("download");
  await page.keyboard.press("Control+Shift+e");
  const fichier = await telechargement;
  expect(fichier.suggestedFilename()).toBe("selection.png");
  const chemin = path.join(CAPTURES, "export-selection.png");
  await fichier.saveAs(chemin);
  const octets = fs.readFileSync(chemin);
  expect(octets.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  // 240 × 160 + marge de 24 de chaque côté, à l'échelle 2
  expect([octets.readUInt32BE(16), octets.readUInt32BE(20)]).toEqual([576, 416]);
  expect(octets.length).toBeGreaterThan(2000);
  // la vue est remise où elle était
  await expect.poll(() => page.locator(".react-flow__viewport").evaluate((e) => getComputedStyle(e).transform)).toBe(vue);
});

test("accessibilité : barre d'outils au clavier, objets atteignables et nommés, focus visible", async ({ page }) => {
  await ouvrir(page);
  await creer(page, { type: "forme", contenu: "", x: 300, y: 300, largeur: 200, hauteur: 140, meta: { forme: "losange" } });
  const barre = outils(page);
  await expect(barre.getByRole("button")).toHaveCount(16);  // 13 outils, annuler, rétablir, palette
  for (const b of await barre.getByRole("button").all()) expect(await b.getAttribute("aria-label")).toBeTruthy();
  await barre.getByRole("button", { name: "Sélection" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(barre.getByRole("button", { name: "Main" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(barre.getByRole("button", { name: "Main" })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("v");
  // l'objet est un élément focalisable nommé ; son contour de focus est visible
  const forme = page.locator(".react-flow__node-forme");
  await expect(forme).toHaveAttribute("aria-label", "forme");
  await forme.focus();
  expect(await forme.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe("none");
});
