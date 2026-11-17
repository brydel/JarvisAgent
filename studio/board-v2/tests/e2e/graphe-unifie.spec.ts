import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("un même graphe relie fichiers, références, observations et journal, avec ses preuves", async ({ page }) => {
  const erreurs: string[] = [];
  page.on("pageerror", (e) => erreurs.push(e.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await expect(graphe.locator(".mf-canevas")).toHaveCount(1);
  await expect(graphe.locator('[data-id="BO-demo-pdf"]')).toBeAttached();
  await expect(graphe.locator('[data-id="RF-demo00000001"]')).toHaveCount(1);
  await expect(graphe.locator('[data-id="OB-demo1grille"]')).toBeAttached();
  await expect(graphe.locator('[data-id="journal:demo-105"]')).toBeAttached();
  await expect(graphe.getByRole("button", { name: "Afficher les groupes", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Sources RAG", exact: true })).toHaveCount(0);
  await graphe.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/graphe-commun-bureau.png", fullPage: false });

  await graphe.locator('[data-id="RF-demo00000001"]').click();
  const inspection = page.getByRole("complementary", { name: "Inspecteur des sources RAG" });
  await inspection.getByRole("button", { name: /Structure et composants/ }).click();
  await inspection.getByRole("button", { name: "Grille principale", exact: true }).click();
  await expect(inspection.getByRole("region", { name: "Preuve de l’observation" })).toContainText("64px");
  await expect(page.locator(".mf-canevas")).toHaveCount(1);
  await inspection.getByRole("button", { name: "Voir l’observation dans la source", exact: true }).click();
  const preuve = page.getByRole("region", { name: "Grille principale", exact: true });
  await expect(preuve).toContainText("64px");
  await preuve.getByRole("button", { name: "Retrouver dans le graphe", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Inspecteur des sources RAG" })
    .getByRole("region", { name: "Preuve de l’observation" })).toContainText("64px");
  await expect(page.locator(".mf-canevas")).toHaveCount(1);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Passer au thème jour", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("region", { name: "Graphe de mémoire", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/graphe-commun-mobile.png", fullPage: false });
  expect(erreurs).toEqual([]);
});

test("une référence déjà reliée au Board garde son identité et les lots préservent le cadrage", async ({ page }) => {
  await ouvrir(page);
  const creer = async (titre: string) => {
    const r = await page.request.post("/api/v2/references", { headers: { "X-Jarvis-Studio": "1" },
      data: { titre, texte: "# " + titre + "\nUne preuve de mémoire partagée." } });
    expect(r.ok()).toBe(true);
    return (await r.json()).id as string;
  };
  const reference = await creer("Guide commun du graphe");
  const poser = await page.request.post("/api/v2/references/" + reference + "/poser", {
    headers: { "X-Jarvis-Studio": "1" }, data: { espace: "accueil" },
  });
  expect(poser.ok()).toBe(true);
  const carte = (await poser.json()).objet_id;
  for (let i = 0; i < 9; i++) await creer("Lot du graphe " + i);
  const total = (await (await page.request.get("/api/v2/references/graphe")).json()).total as number;

  await page.goto("/v2/?vue=fichiers&sources=1&ref=" + reference);
  await expect(page.getByRole("complementary", { name: "Inspecteur des sources RAG" })
    .getByRole("heading", { name: "Guide commun du graphe", exact: true })).toBeVisible();
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await expect(graphe.locator('[data-id="' + reference + '"]')).toHaveCount(1);
  await expect(graphe.locator('[data-id="' + carte + '"]')).toBeAttached();
  const transformation = await graphe.locator(".react-flow__viewport").getAttribute("style");
  await page.getByRole("button", { name: "Charger d’autres références", exact: true }).click();
  await expect(page.locator(".mf-compte")).toContainText(Math.min(total, 16) + "/" + total);
  await expect(graphe.locator('[data-id="' + reference + '"]')).toHaveCount(1);
  await expect(graphe.locator(".react-flow__viewport")).toHaveAttribute("style", transformation!);
  await expect(page.locator(".mf-canevas")).toHaveCount(1);
});
