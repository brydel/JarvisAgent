import path from "node:path";
import { expect, test } from "@playwright/test";
import { ouvrir, RAPPORTS } from "./outils";

const ENTETES = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };

test("le travail du chef apparaît en cartes : plan, tâche (rôle, modèle) et équipe au travail", async ({ page }) => {
  await ouvrir(page);
  // cartes telles que travail_board.py les pose (même format, même source)
  await page.evaluate(async (entetes) => {
    const poser = (corps: object) => fetch("/api/v2/objets", { method: "POST", headers: entetes, body: JSON.stringify(corps) });
    await poser({ type: "plan", x: 0, y: 0, largeur: 440, hauteur: 320, analyser: false, meta: {
      titre: "Authentification 2FA", plan_id: "P-0042", statut: "approuve", mode: "vague", origine: "chef", source: "chef",
      elements: [{ issue: "BIS-82", role: "frontend", agent: "claude", modele: "opus", desc: "écran 2FA", lance: true }] } });
    await poser({ type: "tache", x: 560, y: 0, largeur: 400, hauteur: 260, analyser: false, meta: {
      titre: "BIS-82 · Ingénieur interface", issue: "BIS-82", role: "frontend", role_titre: "Ingénieur interface", agent: "claude",
      modele: "opus", effort: "high", statut: "travaille", actif: true, worktree: "bis-82-2fa", debut: Date.now() / 1000 - 600, source: "chef" } });
    await poser({ type: "agents", x: 1080, y: 0, largeur: 360, hauteur: 360, analyser: false, meta: {
      titre: "Équipe repriceo", actifs: 1, source: "chef", membres: [
        { id: "bis-82-2fa", role: "frontend", titre: "Ingénieur interface", modele: "opus", agent: "claude", statut: "travaille", actif: true, issue: "BIS-82", depuis: "10 min" },
        { id: "bis-90", role: "qa", titre: "Ingénieur qualité", modele: "sol", agent: "codex", statut: "terminé", actif: false, issue: "BIS-90", depuis: "" }] } });
  }, ENTETES);
  await page.reload();
  const plan = page.locator(".react-flow__node-plan");
  await expect(plan.getByText("PLAN P-0042")).toBeVisible();
  await expect(plan.getByText("Approuvé")).toBeVisible();
  const tache = page.locator(".react-flow__node-tache");
  await expect(tache.getByText("Ingénieur interface")).toBeVisible();
  await expect(tache.getByText(/opus · high/)).toBeVisible();
  await expect(tache.getByText(/travaille · 10 min/)).toBeVisible();
  const equipe = page.locator(".react-flow__node-agents");
  await expect(equipe.getByText("1 au travail")).toBeVisible();
  await expect(equipe.getByText("Ingénieur qualité")).toBeVisible();
  await expect(equipe.getByText("sol")).toBeVisible();
  // le filtre « Missions » regroupe le travail du chef
  await page.getByRole("group", { name: "Filtrer par type" }).getByRole("button", { name: /^Missions/ }).click();
  await expect(plan).toBeVisible();
  await expect(tache).toBeVisible();
  await page.screenshot({ path: path.join(RAPPORTS, "etat-travail-du-chef.png") });
});

test("réseau ouvert : régler la vie sociale et lancer un débat que les agents mènent seuls", async ({ page }) => {
  await ouvrir(page);
  await page.getByRole("button", { name: "Réseau des agents", exact: true }).click();
  const reseau = page.getByRole("dialog", { name: "Réseau des agents" });
  const vie = reseau.getByRole("radiogroup", { name: "Vie sociale des agents" });
  await expect(vie.getByRole("radio", { name: "Coupée" })).toHaveAttribute("aria-checked", "true");
  await vie.getByRole("radio", { name: "Animée" }).click();
  await expect(vie.getByRole("radio", { name: "Animée" })).toHaveAttribute("aria-checked", "true");
  const sujet = `Faut-il ralentir les features pour les tests ${Date.now()}`;
  await reseau.getByRole("textbox", { name: "Sujet du débat" }).fill(sujet);
  await reseau.getByRole("button", { name: "Lancer un débat" }).click();
  await expect(reseau.getByText(/Débat lancé :/)).toBeVisible();
  // l'exécutant (factice) fait parler les agents ; le fil s'ouvre puis s'allonge seul, sans geste humain
  const fil = reseau.locator(".reseau-fil").filter({ hasText: "Sujet (factice)" }).first();
  await expect(fil).toBeVisible({ timeout: 30_000 });
  await fil.click();
  await expect.poll(async () => reseau.getByRole("article").count(), { timeout: 40_000 }).toBeGreaterThanOrEqual(3);
  await expect(reseau.getByText("🎉 Bravo").first()).toBeVisible();
  await expect(reseau.locator(".reseau-message .avatar").first()).toBeVisible();
  await page.screenshot({ path: path.join(RAPPORTS, "etat-reseau-ouvert.png") });
  await vie.getByRole("radio", { name: "Coupée" }).click();
  await expect(vie.getByRole("radio", { name: "Coupée" })).toHaveAttribute("aria-checked", "true");
});
