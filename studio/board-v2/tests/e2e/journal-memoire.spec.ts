import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("le journal relie la frustration déclarée à sa tentative et à son événement", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/v2/?demo=1&vue=fichiers");
  await page.getByRole("button", { name: /^Journal/ }).click();
  const filtre = page.getByRole("combobox", { name: "Type d’événement" });
  await filtre.selectOption("frustration");
  const entree = page.getByRole("button", { name: /Intégration React.*Frustration déclarée/ }).first();
  await expect(entree).toBeVisible();
  await entree.click();
  const indice = page.getByRole("region", { name: "Détail et preuve de l’événement" });
  await expect(indice).toContainText("Agent d’intégration (démo)");
  await expect(indice).toContainText("répété deux vérifications");
  const lien = indice.getByRole("link", { name: "Voir la preuve" });
  await expect(lien).toHaveAttribute("href", /evenement=105/);
  await lien.click();
  const preuve = page.getByRole("region", { name: "Preuve du journal" });
  await expect(preuve).toContainText("#105");
  await expect(preuve).toContainText("AT-demo-integration-echec");
  await expect(preuve).toContainText("Frustration déclarée");
  await expect(preuve).toBeFocused();
  await page.reload();
  await expect(preuve).toContainText("répété deux vérifications");
});

test("un blocage réel du moteur apparaît dans le journal de son projet", async ({ page }) => {
  await ouvrir(page);
  const projet = "Journal-e2e";
  const objectif = "Vérifier le blocage d’un fournisseur";
  const r = await page.request.post("/api/v2/missions", {
    headers: { "X-Jarvis-Studio": "1" }, data: { espace: projet, objectif, fournisseur: "codex" },
  });
  expect(r.ok()).toBe(true);
  const { mission_id } = await r.json();
  const endpoint = "/api/v2/journal-memoire?espace=" + projet + "&nature=blocage";
  let titre = "";
  let sequence = 0;
  await expect.poll(async () => {
    const reponse = await page.request.get(endpoint);
    if (!reponse.ok()) return 0;
    const { entrees } = await reponse.json();
    const entree = entrees.find((e: { preuve: { mission_id: string } }) => e.preuve.mission_id === mission_id);
    titre = entree?.titre ?? "";
    sequence = entree?.preuve.sequence ?? 0;
    return sequence;
  }).toBeGreaterThan(0);
  const accueil = await page.request.get("/api/v2/journal-memoire?espace=accueil&nature=blocage");
  expect(accueil.ok()).toBe(true);
  expect((await accueil.json()).entrees.every((e: { preuve: { mission_id: string } }) => e.preuve.mission_id !== mission_id)).toBe(true);
  await page.goto("/v2/?vue=fichiers&espace=" + projet);
  await page.getByRole("button", { name: /^Journal/ }).click();
  const journal = page.getByRole("region", { name: "Journal des agents" });
  await journal.getByRole("button").filter({ hasText: titre }).click();
  await page.getByRole("link", { name: "Voir la preuve" }).click();
  const preuve = page.getByRole("region", { name: "Preuve du journal" });
  await expect(preuve).toContainText("#" + sequence);
  await expect(preuve).toContainText("codex");
  await expect(page.getByRole("article", { name: objectif })).toBeVisible();
});
