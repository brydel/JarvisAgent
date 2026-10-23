import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("mission outillée réelle : publication, relecture et persistance avec modèle de test explicite", async ({ page }) => {
  await ouvrir(page);
  await page.getByRole("button", { name: "Missions outillées", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Missions outillées", exact: true });
  await panneau.getByRole("tab", { name: "Modèle", exact: true }).click();
  const modele = panneau.getByRole("form", { name: "Configuration du modèle" });
  await modele.getByRole("textbox", { name: "Identifiant du modèle", exact: true }).fill("modele-e2e-sans-fournisseur");
  await modele.getByRole("textbox", { name: "Variable contenant la clé API" }).fill("JARVIS_TEST_OPENAI_KEY");
  await modele.getByRole("spinbutton", { name: "Sortie maximale par tour" }).fill("128");
  await modele.getByRole("button", { name: "Enregistrer le modèle", exact: true }).click();
  await expect(panneau.getByRole("status").filter({ hasText: "Configuration du modèle enregistrée" })).toBeVisible();
  await expect(panneau.getByText("Disponible", { exact: true })).toBeVisible();

  await panneau.getByRole("tab", { name: "Mandats", exact: true }).click();
  await panneau.getByRole("button", { name: "Nouveau mandat", exact: true }).click();
  const mandat = panneau.getByRole("form", { name: "Nouveau mandat", exact: true });
  await mandat.getByRole("checkbox", { name: /communaute\.publier/ }).check();
  await mandat.getByRole("textbox", { name: "Destinations exactes, une par ligne" }).fill("api.openai.com\nusine");
  const reponseMandat = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v2/os/mandats");
  await mandat.getByRole("button", { name: "Créer ce mandat", exact: true }).click();
  const nouveauMandat = await (await reponseMandat).json();
  expect(nouveauMandat.tools).toEqual(expect.arrayContaining(["model.openai_responses.inference", "communaute.publier"]));
  await expect(panneau.getByRole("status").filter({ hasText: "Mandat enregistré" })).toBeVisible();

  await panneau.getByRole("tab", { name: "Missions", exact: true }).click();
  await panneau.getByRole("button", { name: "Nouvelle mission outillée", exact: true }).click();
  const mission = panneau.getByRole("form", { name: "Nouvelle mission outillée", exact: true });
  const objectif = `Publier une observation dans le réseau ${Date.now()}`;
  await mission.getByRole("textbox", { name: "Objectif de la mission" }).fill(objectif);
  await mission.getByRole("combobox", { name: "Mandat existant", exact: true }).selectOption(nouveauMandat.id);
  await mission.getByRole("textbox", { name: "Critères de réussite, un par ligne" }).fill("Une publication de l'agent est visible dans le salon Atelier du réseau.");
  await mission.getByRole("checkbox", { name: /communaute\.publier/ }).check();
  const reponseCreation = page.waitForResponse(r => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v2/runtime");
  await mission.getByRole("button", { name: "Créer la mission", exact: true }).click();
  const run = await (await reponseCreation).json();
  expect(run.status).toBe("planned");
  const detail = panneau.getByRole("region", { name: "Détail de la mission outillée" });
  await expect(detail.getByRole("heading", { name: objectif, exact: true })).toBeVisible();
  await expect(detail.getByText("Vérifiée", { exact: true })).toHaveCount(0);
  await detail.getByRole("button", { name: "Démarrer la mission", exact: true }).click();
  await expect(detail.getByText("À vérifier", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(detail.getByText("Fournisseur de test", { exact: true })).toBeVisible();
  const verification = await page.evaluate(async id => {
    const r = await (await fetch(`/api/v2/runtime/${id}`)).json();
    const reseau = await (await fetch("/api/v2/communaute?salon=atelier")).json();
    return { preuves: r.preuves, publication: reseau.fils.find((f: { contenu: string }) => f.contenu === "Publication réelle du scénario de test, par la passerelle de l'agent.") };
  }, run.id);
  expect(verification.publication).toBeTruthy();
  expect(verification.publication.auteur).toBe("agent:" + run.agent.id);
  expect(verification.preuves.length).toBeGreaterThan(0);
  const revue = detail.getByRole("form", { name: "Vérifier le résultat", exact: true });
  await revue.getByRole("textbox", { name: "Commentaire de vérification" }).fill("La publication de l'agent est présente ; le critère est vérifié.");
  await expect(revue.getByRole("button", { name: "Valider les preuves", exact: true })).toBeDisabled();
  await revue.getByRole("textbox", { name: "Preuves de vérification, une par ligne" }).fill(verification.preuves[0]);
  await revue.getByRole("button", { name: "Valider les preuves", exact: true }).click();
  await expect(detail.getByText("Vérifiée", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Missions outillées", exact: true }).click();
  await panneau.getByRole("button", { name: new RegExp(objectif) }).click();
  await expect(detail.getByText("Vérifiée", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("runtime-verifie-desktop.png") });
});

test("modèle manquant : configuration par référence et disponibilité distincte de l'inférence", async ({ page }) => {
  let configuration: Record<string, unknown> | null = null;
  let verification: Record<string, unknown> | null = null;
  const requetes: Record<string, unknown>[] = [];
  await page.route("**/api/v2/runtime", r => r.fulfill({ json: { runs: [] } }));
  await page.route("**/api/v2/modeles-runtime", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: { configuration, verification } });
    const corps = route.request().postDataJSON(); requetes.push(corps);
    configuration = { ...corps, auth: { mode: "bearer_env", configuree: false }, inference_verifiee: false };
    await route.fulfill({ json: { configuration } });
  });
  await page.route("**/api/v2/modeles-runtime/verifier", r => {
    verification = { authentification: "non_verifiee", modele: "non_verifie", inference: "non_verifiee", preuve: "Variable de clé absente du serveur." };
    return r.fulfill({ json: verification });
  });
  await ouvrir(page);
  await page.getByRole("button", { name: "Missions outillées", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Missions outillées", exact: true });
  await expect(panneau.getByText("Configure d'abord un modèle", { exact: true })).toBeVisible();
  await panneau.getByRole("button", { name: "Configurer le modèle", exact: true }).click();
  const formulaire = panneau.getByRole("form", { name: "Configuration du modèle", exact: true });
  await expect(formulaire.getByRole("button", { name: "Enregistrer le modèle", exact: true })).toBeDisabled();
  await formulaire.getByRole("textbox", { name: "Identifiant du modèle", exact: true }).fill("modele-explicite");
  await formulaire.getByRole("textbox", { name: "Variable contenant la clé API" }).fill("JARVIS_MON_MODELE");
  await formulaire.getByRole("button", { name: "Enregistrer le modèle", exact: true }).click();
  await expect(panneau.getByText("Variable manquante", { exact: true })).toBeVisible();
  expect(requetes[0]?.api_key_env).toBe("JARVIS_MON_MODELE");
  expect(requetes[0]?.api_key).toBeUndefined();
  await formulaire.getByRole("button", { name: "Vérifier la disponibilité", exact: true }).click();
  await expect(panneau.getByText("Variable de clé absente du serveur.", { exact: true })).toBeVisible();
  await expect(panneau.getByText("Non vérifiée par ce contrôle", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const boite = (await panneau.boundingBox())!;
  expect(boite.x).toBeGreaterThanOrEqual(0);
  expect(boite.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: test.info().outputPath("runtime-configuration-mobile.png") });
});

test("Gmail : permissions choisies, autorisation Google réelle préparée et refus d'une URL inattendue", async ({ page }) => {
  let connexion: Record<string, unknown> | null = null;
  let mauvaiseUrl = true;
  const configurations: Record<string, unknown>[] = [];
  await page.route("**/api/v2/oauth", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: { connexions: connexion ? [connexion] : [] } });
    const corps = route.request().postDataJSON(); configurations.push(corps);
    connexion = { id: corps.id, nom: corps.nom, provider: "google_gmail", scopes: corps.scopes, redirect_uri: corps.redirect_uri,
      adresse_expediteur: corps.adresse_expediteur, client_id_configure: true, client_secret_configure: true, etat: "configuree" };
    await route.fulfill({ status: 201, json: connexion });
  });
  await page.route("**/api/v2/oauth/gmail-e2e/commencer", route => route.fulfill({ json: {
    authorization_url: mauvaiseUrl ? "https://ailleurs.example/authorization" : "https://accounts.google.com/o/oauth2/v2/auth?state=etat-opaque-de-test&code_challenge=pkce-test",
  } }));
  await ouvrir(page);
  await page.getByRole("button", { name: "Missions outillées", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Missions outillées", exact: true });
  await panneau.getByRole("tab", { name: "Courriel", exact: true }).click();
  await panneau.getByRole("button", { name: "Configurer Gmail", exact: true }).click();
  const formulaire = panneau.getByRole("form", { name: "Configurer Gmail", exact: true });
  await formulaire.getByRole("textbox", { name: "Nom de la connexion Gmail", exact: true }).fill("Gmail de test");
  await formulaire.getByRole("textbox", { name: "Identifiant de connexion Gmail", exact: true }).fill("gmail-e2e");
  await formulaire.getByRole("textbox", { name: "Identifiant client Google", exact: true }).fill("client-public-e2e.apps.googleusercontent.com");
  await formulaire.getByRole("textbox", { name: "Variable du secret client, si nécessaire" }).fill("JARVIS_GOOGLE_CLIENT_SECRET");
  await formulaire.getByRole("textbox", { name: "Adresse expéditrice Gmail", exact: true }).fill("agent@example.test");
  await formulaire.getByRole("checkbox", { name: "Envoyer des courriels", exact: true }).check();
  await formulaire.getByRole("button", { name: "Enregistrer l'application Gmail", exact: true }).click();
  const carte = panneau.getByRole("article").filter({ hasText: "Gmail de test" });
  await expect(carte.getByText("À connecter", { exact: true })).toBeVisible();
  expect(configurations[0]?.client_secret_env).toBe("JARVIS_GOOGLE_CLIENT_SECRET");
  expect(configurations[0]?.client_secret).toBeUndefined();
  expect(configurations[0]?.adresse_expediteur).toBe("agent@example.test");
  await carte.getByRole("button", { name: "Autoriser dans Google", exact: true }).click();
  await expect(panneau.getByRole("alert")).toContainText("Adresse d'autorisation inattendue");
  await expect(panneau.getByRole("link", { name: "Continuer dans Google" })).toHaveCount(0);
  mauvaiseUrl = false;
  await carte.getByRole("button", { name: "Autoriser dans Google", exact: true }).click();
  await expect(panneau.getByRole("link", { name: "Continuer dans Google" })).toHaveAttribute("href", /^https:\/\/accounts\.google\.com\//);
  await expect(carte.getByText("À connecter", { exact: true })).toBeVisible();
  await expect(panneau.getByText("Connectée", { exact: true })).toHaveCount(0);
});

test("MCP stdio : commande propriétaire structurée, sans shell ni valeur secrète", async ({ page }) => {
  const requetes: Record<string, unknown>[] = [];
  let connexion: Record<string, unknown> | null = null;
  await page.route("**/api/v2/connexions", async route => {
    if (route.request().method() === "GET") return route.fulfill({ json: { connexions: connexion ? [connexion] : [] } });
    const corps = route.request().postDataJSON(); requetes.push(corps);
    connexion = { id: corps.id, nom: corps.nom, type: "mcp_stdio", active: true, hote: `mcp:${corps.id}`,
      auth: { mode: "processus_local", configuree: true }, outils: [], outils_autorises: [],
      etat: "configuree_non_verifiee", created_at: Date.now() / 1000, verified_at: null,
      stdio: { executable: corps.command, env: [{ nom: "JARVIS_SERVICE_TOKEN", presente: false }] } };
    await route.fulfill({ status: 201, json: connexion });
  });
  await ouvrir(page);
  await page.getByRole("button", { name: "Intégrations", exact: true }).click();
  const panneau = page.getByRole("dialog", { name: "Intégrations", exact: true });
  await panneau.getByRole("button", { name: "Connecter un serveur MCP", exact: true }).click();
  const formulaire = panneau.getByRole("form", { name: "Connecter un serveur MCP", exact: true });
  await formulaire.getByRole("combobox", { name: "Transport du serveur MCP" }).selectOption("mcp_stdio");
  await formulaire.getByRole("textbox", { name: "Nom de la connexion", exact: true }).fill("Recherche locale");
  await formulaire.getByRole("textbox", { name: "Identifiant", exact: true }).fill("recherche-locale");
  await formulaire.getByRole("textbox", { name: "Exécutable local, chemin absolu" }).fill("serveur-relatif");
  await expect(formulaire.getByRole("button", { name: "Enregistrer la connexion" })).toBeDisabled();
  await formulaire.getByRole("textbox", { name: "Exécutable local, chemin absolu" }).fill("/opt/outils/serveur-mcp");
  await formulaire.getByRole("textbox", { name: "Arguments, un par ligne", exact: true }).fill("--mode\nlecture\nargument avec espaces");
  await formulaire.getByRole("textbox", { name: "Variables à transmettre, noms uniquement" }).fill("JARVIS_SERVICE_TOKEN");
  await expect(formulaire.getByText(/La découverte lancera cet exécutable/)).toBeVisible();
  await formulaire.getByRole("button", { name: "Enregistrer la connexion" }).click();
  await expect(panneau.getByRole("article").getByText("Processus local", { exact: true })).toBeVisible();
  expect(requetes[0]).toMatchObject({ type: "mcp_stdio", command: "/opt/outils/serveur-mcp", args: ["--mode", "lecture", "argument avec espaces"], env_allowlist: ["JARVIS_SERVICE_TOKEN"] });
  expect(requetes[0]?.shell).toBeUndefined();
  expect(requetes[0]?.url).toBeUndefined();
});
