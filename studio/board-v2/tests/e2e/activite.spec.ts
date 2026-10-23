import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("sessions visibles sans carte, aperçu direct et évolution sans événement SSE", async ({ page }) => {
  let attente = false;
  const id = "a".repeat(24);
  await page.route("**/api/v2/activite?**", route => route.fulfill({ json: {
    ts: Date.now() / 1000, demon: true, executant_actif: true, sessions_erreur: "", taches: [],
    sessions: [{ id, project: "repriceo", worktree: "bis-42", status: attente ? "waiting" : "working", kind: "codex",
      elapsed: 30, title: "Correction de la pagination", session: "agents", window: "wm-bis-42" }],
  } }));
  await page.route(`**/api/v2/activite/${id}/apercu?**`, route => route.fulfill({ json: { texte: "Lecture de pagination.py\nTests de régression en cours" } }));
  await ouvrir(page);
  const panneau = page.getByRole("region", { name: "Travail en direct" });
  await expect(panneau.getByText("repriceo / bis-42", { exact: true })).toBeVisible();
  await panneau.getByRole("button", { name: /repriceo \/ bis-42/ }).click();
  await expect(panneau.locator("pre")).toContainText("Tests de régression en cours");
  expect((await page.locator(".canevas").boundingBox())!.height).toBeGreaterThan(200);
  expect((await page.locator(".app").boundingBox())!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
  await page.screenshot({ path: test.info().outputPath("activite-desktop.png") });
  attente = true;
  await expect(panneau.getByText(/Attend une réponse/)).toBeVisible({ timeout: 12000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panneau.getByRole("button", { name: /Travail en direct/ })).toBeVisible();
  const barre = (await page.locator(".subbar").boundingBox())!;
  expect((await panneau.boundingBox())!.y).toBeGreaterThanOrEqual(barre.y + barre.height - 1);
  const canevas = (await page.locator(".canevas").boundingBox())!;
  expect(canevas.height).toBeGreaterThanOrEqual(160);
  expect((await page.locator(".panneau").boundingBox())!.y).toBeGreaterThanOrEqual(canevas.y + canevas.height - 1);
  await page.screenshot({ path: test.info().outputPath("activite-mobile.png") });
  await panneau.getByRole("button", { name: /Travail en direct/ }).click();
  await expect(panneau.locator("#travail-observe")).toHaveCount(0);
});

test("une erreur d'observation n'affiche pas une fausse équipe vide", async ({ page }) => {
  await page.route("**/api/v2/activite?**", route => route.fulfill({ json: {
    ts: Date.now() / 1000, demon: false, executant_actif: false,
    sessions: null, sessions_erreur: "workmux indisponible", taches: [{ id: "TA-1", mission_id: "MI-1", type: "contextualiser",
      statut: "RUNNING", raison: "", fournisseur: "claude", debut: Date.now() / 1000 - 180,
      executant: "poste", objectif: "Analyser la note déposée", objet_id: null, bail_perime: true }],
  } }));
  await ouvrir(page);
  const panneau = page.getByRole("region", { name: "Travail en direct" });
  await expect(panneau.getByText(/Sessions indisponibles/)).toBeVisible();
  await expect(panneau.getByRole("alert")).toContainText("workmux indisponible");
  await expect(panneau.getByText("Analyser la note déposée")).toBeVisible();
  await expect(panneau.getByText(/Bail expiré/)).toBeVisible();
  await expect(panneau.getByText(/Aucun travail observé/)).toHaveCount(0);
});

test("une carte ajoutée hors navigateur apparaît même si le SSE est coupé", async ({ page }) => {
  await page.route("**/api/flux**", route => route.abort());
  await ouvrir(page);
  const id = await page.evaluate(async () => {
    const r = await fetch("/api/v2/objets", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" },
      body: JSON.stringify({ type: "note", contenu: "Ajout externe pendant la coupure", x: 100, y: 100, largeur: 400, hauteur: 300,
        analyser: false, meta: { titre: "Carte arrivée sans SSE" } }) });
    if (!r.ok) throw new Error(await r.text());
    return (await r.json()).objet_id;
  });
  await expect(page.locator(`.react-flow__node[data-id="${id}"]`)).toBeVisible({ timeout: 18000 });
});
