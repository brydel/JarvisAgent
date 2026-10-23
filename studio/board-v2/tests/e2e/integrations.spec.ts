import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("connexion MCP, découverte, sélection des outils et révocation", async ({ page }) => {
  const appels: { chemin: string; corps: Record<string, unknown> }[] = [];
  let connexion: Record<string, unknown> | null = null;
  await page.route("**/api/v2/connexions", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: { connexions: connexion ? [connexion] : [] } });
    const corps = route.request().postDataJSON(); appels.push({ chemin: "creer", corps });
    connexion = { id: corps.id, nom: corps.nom, type: "mcp_http", active: true, hote: "mcp.example.org",
      auth: { mode: "bearer_env", configuree: true }, outils_autorises: [], outils: [],
      etat: "configuree_non_verifiee", created_at: Date.now() / 1000, verified_at: null };
    await route.fulfill({ status: 201, json: connexion });
  });
  await page.route("**/api/v2/connexions/recherche/**", async route => {
    const commande = route.request().url().split("/").at(-1)!;
    const corps = route.request().postDataJSON(); appels.push({ chemin: commande, corps });
    if (commande === "decouvrir") connexion = { ...connexion, etat: "decouverte_verifiee", verified_at: Date.now() / 1000,
      outils: [{ name: "search_documents", description: "Recherche dans les documents du projet", inputSchema: { type: "object", properties: { query: { type: "string" } } }, autorise: false }] };
    if (commande === "outils") connexion = { ...connexion, outils_autorises: corps.outils_autorises,
      outils: [{ name: "search_documents", description: "Recherche dans les documents du projet", inputSchema: { type: "object" }, autorise: true }] };
    if (commande === "revoquer") connexion = { ...connexion, active: false, etat: "revoquee" };
    await route.fulfill({ json: connexion });
  });
  await ouvrir(page);
  await page.getByRole("button", { name: "Intégrations", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Intégrations", exact: true });
  await expect(panneau.getByText("Aucun serveur MCP n'est encore connecté à cette installation.")).toBeVisible();
  await panneau.getByRole("button", { name: "Connecter un serveur MCP", exact: true }).click();
  const formulaire = panneau.getByRole("form", { name: "Connecter un serveur MCP", exact: true });
  await formulaire.getByRole("textbox", { name: "Nom de la connexion", exact: true }).fill("Espace de recherche");
  await formulaire.getByRole("textbox", { name: "Identifiant", exact: true }).fill("recherche");
  await formulaire.getByRole("textbox", { name: "Adresse HTTPS du serveur MCP", exact: true }).fill("https://mcp.example.org/mcp?token=valeur-interdite");
  await expect(formulaire.getByRole("button", { name: "Enregistrer la connexion" })).toBeDisabled();
  await formulaire.getByRole("textbox", { name: "Adresse HTTPS du serveur MCP", exact: true }).fill("https://mcp.example.org/mcp");
  await formulaire.getByRole("textbox", { name: "Variable d'authentification, facultative", exact: true }).fill("JARVIS_MCP_TOKEN");
  await formulaire.getByRole("button", { name: "Enregistrer la connexion" }).click();
  const carte = panneau.getByRole("article").filter({ hasText: "Espace de recherche" });
  await expect(carte.getByText("À vérifier", { exact: true })).toBeVisible();
  await expect(carte.getByText("Variable disponible", { exact: true })).toBeVisible();
  await carte.getByRole("button", { name: "Découvrir les outils" }).click();
  await expect(carte.getByText("Découverte vérifiée", { exact: true })).toBeVisible();
  await carte.getByRole("checkbox", { name: /search_documents/ }).check();
  await carte.getByRole("button", { name: "Enregistrer les outils" }).click();
  await expect(panneau.getByRole("status")).toContainText("Sélection des outils enregistrée");
  expect(appels[0]!.corps).toMatchObject({ id: "recherche", token_env: "JARVIS_MCP_TOKEN", outils_autorises: [] });
  expect(appels.find(a => a.chemin === "outils")!.corps).toEqual({ outils_autorises: ["search_documents"] });
  expect(JSON.stringify(appels)).not.toContain("valeur-interdite");
  await page.screenshot({ path: test.info().outputPath("integrations-mcp-desktop.png") });
  await carte.getByRole("button", { name: "Révoquer" }).click();
  await expect(carte.getByText("Révoquée", { exact: true })).toBeVisible();
  await expect(carte.getByRole("checkbox", { name: /search_documents/ })).toBeDisabled();
  await expect(carte.getByRole("button", { name: "Découvrir les outils" })).toHaveCount(0);
});

test("capacités non vérifiées, résultat inconnu et affichage mobile", async ({ page }) => {
  await page.route("**/api/v2/connexions", route => route.fulfill({ json: { connexions: [] } }));
  await page.route("**/api/v2/os/capacites", route => route.fulfill({ json: { capacites: [
    { id: "provider.codex.cli", etat: "verifie", available: true, scope: "Lecture de version seulement", preuve: "Le CLI répond à --version." },
    { id: "provider.codex.inference", etat: "inconnu", available: false, scope: "Inférence réelle", preuve: "Aucun appel de modèle n'a été effectué." },
  ] } }));
  await page.route("**/api/v2/outils/operations**", route => route.fulfill({ json: { operations: [
    { operation_id: "operation-incertaine", project: "projet-test", tool: "mcp:recherche:search_documents", status: "unknown", created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000, mandat_id: "mandat-test", erreur: null },
  ] } }));
  await page.setViewportSize({ width: 390, height: 844 });
  await ouvrir(page);
  await page.getByRole("button", { name: "Intégrations", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Intégrations", exact: true });
  await panneau.getByRole("tab", { name: "Capacités", exact: true }).click();
  const inference = panneau.getByRole("article").filter({ hasText: "provider.codex.inference" });
  await expect(inference.getByText("Non vérifié", { exact: true })).toBeVisible();
  await expect(inference.getByText("Aucun appel de modèle n'a été effectué.", { exact: true })).toBeVisible();
  await panneau.getByRole("tab", { name: "Activité des outils", exact: true }).click();
  await expect(panneau.getByText("Résultat inconnu", { exact: true })).toBeVisible();
  await expect(panneau.getByText("operation-incertaine", { exact: true })).toBeVisible();
  const boite = (await panneau.boundingBox())!;
  expect(boite.x).toBeGreaterThanOrEqual(0);
  expect(boite.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("integrations-mobile.png") });
  await page.keyboard.press("Escape");
  await expect(panneau).not.toBeVisible();
});
