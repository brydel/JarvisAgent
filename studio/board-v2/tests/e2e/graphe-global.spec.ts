import { expect, test, type Locator, type Page } from "@playwright/test";
import { ouvrir } from "./outils";

async function position(noeud: Locator) {
  return noeud.evaluate((e) => {
    const valeurs = (e as HTMLElement).style.transform.match(/-?[\d.]+/g)!.map(Number);
    return { x: valeurs[0]!, y: valeurs[1]! };
  });
}

async function glisser(page: Page, prise: Locator, dx: number, dy: number) {
  const r = await prise.boundingBox();
  expect(r).not.toBeNull();
  const x = r!.x + r!.width / 2, y = r!.y + r!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 12 });
  await page.mouse.up();
}

test("le graphe global rassemble les projets, les sessions et leurs sources partagées", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await expect(page.getByRole("combobox", { name: "Projet du graphe", exact: true })).toHaveValue("");
  await expect(graphe.locator('[data-id="centroide:AT-demo-integration-echec"]')).toBeAttached();
  await expect(graphe.locator('[data-id="centroide:AR-demo-campagne-redaction"]')).toBeAttached();
  await expect(graphe.locator('[data-id="BO-demo-campagne-note"]')).toBeAttached();
  await expect(graphe.locator('[data-id="RF-demo00000001"]')).toHaveCount(1);
  await expect(graphe.locator('[data-id="ref:BO-demo-campagne-note"]')).toBeAttached();
  await graphe.scrollIntoViewIfNeeded();
  await expect(graphe.locator(".mf-graphe-memoire")).toHaveAttribute("data-libelles", "masques");
  expect(await graphe.locator(".mf-sommet strong, .mf-centroide small, .mf-groupes text").evaluateAll((elements) =>
    elements.filter((e) => { const s = getComputedStyle(e); return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) > 0; }).length)).toBe(0);
  await page.screenshot({ path: "/tmp/graphe-global-sessions-nuit.png", fullPage: false });

  await graphe.locator('[data-id="centroide:AR-demo-campagne-redaction"]').press("Enter");
  const session = page.getByRole("complementary", { name: "Inspecteur de la session" });
  await expect(session.getByRole("heading", { name: "Campagne · Rédaction", exact: true })).toBeVisible();
  await expect(session).toContainText("Campagne de lancement");
  await session.getByRole("button", { name: "Brief de campagne", exact: true }).click();
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await inspecteur.getByRole("button", { name: "Modifier la note", exact: true }).click();
  await inspecteur.getByRole("textbox", { name: "Texte de la note", exact: true }).fill("La mémoire des sessions nourrit cette campagne.");
  await inspecteur.getByRole("button", { name: "Enregistrer la note", exact: true }).click();
  await expect(inspecteur).toContainText("La mémoire des sessions nourrit cette campagne.");

  await page.getByRole("combobox", { name: "Projet du graphe", exact: true }).selectOption("Campagne de lancement");
  await expect(graphe.locator('[data-id="centroide:AT-demo-integration-echec"]')).toHaveCount(0);
  await expect(graphe.locator('[data-id="centroide:AR-demo-campagne-redaction"]')).toBeAttached();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Passer au thème jour", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await graphe.scrollIntoViewIfNeeded();
  await graphe.getByRole("button", { name: "Cadrer le graphe", exact: true }).click();
  await expect(page.locator(".p-feedback")).toBeHidden();
  await page.screenshot({ path: "/tmp/graphe-global-sessions-mobile.png", fullPage: false });
});

test("un centroïde déplace son lot, un membre reste libre et le dessin survit au rechargement", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  const centre = graphe.locator('[data-id="centroide:AT-demo-integration-echec"]');
  const membre = graphe.locator('[data-id="BO-demo-image"]');
  const voisin = graphe.locator('[data-id="BO-demo-pdf"]');
  const autre = graphe.locator('[data-id="BO-demo-campagne-note"]');
  const partagee = graphe.locator('[data-id="RF-demo00000001"]');
  await expect(centre).toBeAttached();
  await graphe.scrollIntoViewIfNeeded();
  const initiales = await Promise.all([centre, membre, voisin, autre, partagee].map(position));
  await glisser(page, membre.locator(".mf-orbe"), 55, 25);
  await expect.poll(() => position(membre)).not.toEqual(initiales[1]);
  expect(await position(centre)).toEqual(initiales[0]);
  expect(await position(voisin)).toEqual(initiales[2]);
  expect(await position(autre)).toEqual(initiales[3]);
  expect(await position(partagee)).toEqual(initiales[4]);

  const avant = await Promise.all([centre, membre, voisin].map(position));
  await glisser(page, centre.locator(".mf-centroide-anneau"), 65, 20);
  await expect.poll(() => position(centre)).not.toEqual(avant[0]);
  const apres = await Promise.all([centre, membre, voisin].map(position));
  const dx = apres[0]!.x - avant[0]!.x, dy = apres[0]!.y - avant[0]!.y;
  for (const i of [1, 2]) {
    expect(apres[i]!.x - avant[i]!.x).toBeCloseTo(dx, 1);
    expect(apres[i]!.y - avant[i]!.y).toBeCloseTo(dy, 1);
  }
  expect(await position(autre)).toEqual(initiales[3]);
  expect(await position(partagee)).toEqual(initiales[4]);
  await page.getByRole("combobox", { name: "Projet du graphe", exact: true }).selectOption("Campagne de lancement");
  await glisser(page, autre.locator(".mf-orbe"), 20, 15);
  await page.getByRole("combobox", { name: "Projet du graphe", exact: true }).selectOption("");
  expect(await position(membre)).toEqual(apres[1]);
  expect(await position(centre)).toEqual(apres[0]);
  await page.reload();
  await expect(centre).toBeAttached();
  expect(await position(centre)).toEqual(apres[0]);
  expect(await position(membre)).toEqual(apres[1]);
  await graphe.getByRole("button", { name: "Réinitialiser la disposition", exact: true }).click();
  await expect.poll(() => position(membre)).toEqual(initiales[1]);
});

test("les fichiers de deux projets réels apparaissent ensemble et ouvrent le bon Board", async ({ page }) => {
  await ouvrir(page);
  const r = await page.request.post("/api/v2/references", { headers: { "X-Jarvis-Studio": "1" },
    data: { titre: "Source interprojets", texte: "# Guide partagé\nUne référence commune aux projets." } });
  expect(r.ok()).toBe(true);
  const reference = (await r.json()).id;
  const cartes: string[] = [];
  for (const espace of ["Global-projet-A", "Global-projet-B"]) {
    const pose = await page.request.post("/api/v2/references/" + reference + "/poser", {
      headers: { "X-Jarvis-Studio": "1" }, data: { espace },
    });
    expect(pose.ok()).toBe(true);
    cartes.push((await pose.json()).objet_id);
  }
  await page.goto("/v2/?vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await expect(graphe.locator('[data-id="' + cartes[0] + '"]')).toBeAttached();
  await expect(graphe.locator('[data-id="' + cartes[1] + '"]')).toBeAttached();
  await expect(graphe.locator('[data-id="' + reference + '"]')).toHaveCount(1);
  await graphe.locator('[data-id="' + cartes[1] + '"]').press("Enter");
  await page.getByRole("complementary", { name: "Inspecteur du fichier" })
    .getByRole("button", { name: "Voir sur le Board", exact: true }).click();
  await expect(page).toHaveURL(/espace=Global-projet-B/);
  await expect(page.locator('.react-flow__node[data-id="' + cartes[1] + '"]')).toBeVisible();
});

test("les noms apparaissent au clic et au zoom rapproché", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  const scene = graphe.locator(".mf-graphe-memoire");
  await expect(scene).toHaveAttribute("data-libelles", "masques");
  const image = graphe.locator('[data-id="BO-demo-image"]');
  await image.press("Enter");
  await expect(image.locator("strong")).toHaveCSS("opacity", "1");
  const centre = graphe.locator('[data-id="centroide:AR-demo-campagne-redaction"]');
  await centre.press("Enter");
  await expect(centre.locator("strong")).toHaveCSS("opacity", "1");
  await expect(image.locator("strong")).toHaveCSS("opacity", "0");
  await graphe.locator(".react-flow__pane").click({ position: { x: 15, y: 180 } });
  await expect(centre.locator("strong")).toHaveCSS("opacity", "0");
  expect(new URL(page.url()).searchParams.has("session")).toBe(false);
  for (let i = 0; i < 12; i++) await graphe.getByRole("button", { name: "Zoom avant", exact: true }).click();
  await expect(scene).toHaveAttribute("data-libelles", "visibles");
  await graphe.getByRole("button", { name: "Cadrer le graphe", exact: true }).click();
  await expect(scene).toHaveAttribute("data-libelles", "masques");
});
