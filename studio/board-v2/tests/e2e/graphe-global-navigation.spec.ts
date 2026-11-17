import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("ouvrir le Board d’un autre projet de démonstration conserve la note modifiée", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers&fichier=BO-demo-campagne-note");
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: "Brief de campagne", exact: true })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Modifier la note", exact: true }).click();
  await inspecteur.getByRole("textbox", { name: "Texte de la note", exact: true }).fill("Campagne vérifiée depuis le graphe global.");
  await inspecteur.getByRole("button", { name: "Enregistrer la note", exact: true }).click();
  await expect(inspecteur).toContainText("Campagne vérifiée depuis le graphe global.");
  await inspecteur.getByRole("button", { name: "Voir sur le Board", exact: true }).click();
  await expect(page.getByRole("region", { name: "Canevas du Board" })
    .locator('[data-id="BO-demo-campagne-note"]')).toContainText("Campagne vérifiée depuis le graphe global.");
  expect(new URL(page.url()).searchParams.get("espace")).toBe("Campagne de lancement");

  await page.goBack();
  await expect(inspecteur).toContainText("Campagne vérifiée depuis le graphe global.");
  await page.goForward();
  await expect(page.getByRole("region", { name: "Canevas du Board" })
    .locator('[data-id="BO-demo-campagne-note"]')).toContainText("Campagne vérifiée depuis le graphe global.");
});

test("le Board réel ouvre la carte du projet sélectionné depuis le graphe global", async ({ page }) => {
  await ouvrir(page);
  const creer = async (espace: string, titre: string) => {
    const r = await page.request.post("/api/v2/objets", { headers: { "X-Jarvis-Studio": "1" },
      data: { espace, type: "note", contenu: titre, meta: { titre }, analyser: false } });
    expect(r.ok()).toBe(true);
    return (await r.json()).objet_id as string;
  };
  const origine = await creer("Navigation-A", "Note du premier projet");
  const cible = await creer("Navigation-B", "Note du second projet");
  await page.goto("/v2/?vue=fichiers&espace=Navigation-A&fichier=" + cible);
  const inspecteur = page.getByRole("complementary", { name: "Inspecteur du fichier" });
  await expect(inspecteur.getByRole("heading", { name: "Note du second projet", exact: true })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Voir sur le Board", exact: true }).click();
  expect(new URL(page.url()).searchParams.get("espace")).toBe("Navigation-B");
  const canevas = page.getByRole("region", { name: "Canevas du Board" });
  await expect(canevas.locator('[data-id="' + cible + '"]')).toBeVisible();
  await expect(canevas.locator('[data-id="' + origine + '"]')).toHaveCount(0);
  await page.goBack();
  await expect(inspecteur.getByRole("heading", { name: "Note du second projet", exact: true })).toBeVisible();
  await inspecteur.getByRole("button", { name: "Voir sur le Board", exact: true }).click();
  await expect(canevas.locator('[data-id="' + cible + '"]')).toBeVisible();
  // Une entrée d’historique peut changer le projet tout en conservant la même vue Board.
  await page.evaluate((id) => {
    history.pushState(null, "", "/v2/?vue=board&espace=Navigation-A&carte=" + id);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, origine);
  await expect(canevas.locator('[data-id="' + origine + '"]')).toBeVisible();
  await expect(canevas.locator('[data-id="' + cible + '"]')).toHaveCount(0);
  await page.goBack();
  await expect(canevas.locator('[data-id="' + cible + '"]')).toBeVisible();
  await expect(canevas.locator('[data-id="' + origine + '"]')).toHaveCount(0);
});
