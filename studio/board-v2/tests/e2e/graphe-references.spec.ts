import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";
import { voirDemo } from "../../src/references/demo";

test("une observation RAG conserve sa preuve au retour depuis le graphe", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers&sources=1&ref=RF-demo00000005");
  const inspection = page.getByRole("complementary", { name: "Inspecteur des sources RAG" });
  await expect(inspection.getByRole("heading", { name: "Carte de sélection lumineuse", exact: true })).toBeVisible();
  await inspection.getByRole("button", { name: /Style et mouvement/ }).click();
  await inspection.getByRole("button", { name: "Transition d’opacité", exact: true }).press("Enter");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await expect(graphe.locator('[data-id="OB-demo5mouvement"]')).toBeAttached();
  const preuve = inspection.getByRole("region", { name: "Preuve de l’observation" });
  await expect(preuve).toContainText("180 ms");
  await preuve.getByRole("button", { name: "Voir l’observation dans la source" }).click();
  const observation = page.getByRole("region", { name: "Transition d’opacité" });
  await expect(observation).toContainText("180 ms");
  await observation.getByRole("button", { name: "Retrouver dans le graphe" }).click();
  await expect(preuve).toContainText("180 ms");
  expect(await page.locator(".mf-page").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});


test("la preuve suit le fragment puis l’observation et les retours sur une même référence", async ({ page }) => {
  await ouvrir(page);
  const id = "RF-111111111111";
  const alpha = "FR-aaaaaaaaaaaa";
  const beta = "FR-bbbbbbbbbbbb";
  const fiche = await voirDemo("RF-demo00000001");
  fiche.id = id;
  fiche.sections = [
    { titre: "Section alpha", niveau: 2, zone: { y: 0, hauteur: 300 }, caracteres: 11, extrait: "Preuve alpha" },
    { titre: "Section bêta", niveau: 2, zone: { y: 400, hauteur: 300 }, caracteres: 11, extrait: "Preuve bêta" },
  ];
  fiche.observations = [{
    id: "OB-preuve-independante", type: "structure", titre: "Observation indépendante", texte: "Une autre preuve.",
    preuve: { reference_id: id, capture_le: fiche.capture_le }, nature: "donnee_non_fiable",
  }];
  await page.route("**/api/v2/references/" + id, (route) => route.fulfill({ json: fiche }));
  for (const [fragment, section, texte] of [[alpha, "Section alpha", "Preuve alpha"], [beta, "Section bêta", "Preuve bêta"]]) {
    await page.route("**/api/v2/references/fragments/" + fragment, (route) =>
      route.fulfill({ json: { reference_id: id, section, texte, titre: fiche.titre } }));
  }
  const adresse = (fragment: string) => "/v2/?vue=references&ref=" + id + "&fragment=" + fragment;
  await page.goto(adresse(alpha));
  const passage = page.getByRole("region", { name: "Passage cité", exact: true });
  const sectionAlpha = page.locator(".rf-sections").getByRole("button", { name: /Section alpha/ });
  const sectionBeta = page.locator(".rf-sections").getByRole("button", { name: /Section bêta/ });
  await expect(passage).toContainText("Preuve alpha");
  await expect(sectionAlpha).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Retirer le repère", exact: true }).click();
  await expect(sectionAlpha).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("button", { name: "Observation indépendante", exact: true }).click();
  await expect(page.getByRole("region", { name: "Observation indépendante", exact: true })).toBeVisible();
  await expect(passage).toHaveCount(0);
  await expect(page.locator(".rf-sections button[aria-pressed=true]")).toHaveCount(0);
  expect(new URL(page.url()).searchParams.has("fragment")).toBe(false);

  const naviguer = async (url: string) => page.evaluate((adresse) => {
    history.pushState(null, "", adresse);
    dispatchEvent(new PopStateEvent("popstate"));
  }, url);
  await naviguer(adresse(alpha));
  await expect(passage).toContainText("Preuve alpha");
  await expect(sectionAlpha).toHaveAttribute("aria-pressed", "true");
  await naviguer(adresse(beta));
  await expect(passage).toContainText("Preuve bêta");
  await expect(sectionBeta).toHaveAttribute("aria-pressed", "true");
  await expect(sectionAlpha).toHaveAttribute("aria-pressed", "false");
  await page.goBack();
  await expect(passage).toContainText("Preuve alpha");
  await expect(sectionAlpha).toHaveAttribute("aria-pressed", "true");
  await page.goForward();
  await expect(passage).toContainText("Preuve bêta");
  await expect(sectionBeta).toHaveAttribute("aria-pressed", "true");
});
