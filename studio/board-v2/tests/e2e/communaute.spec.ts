import { expect, test } from "@playwright/test";
import { ouvrir } from "./outils";

test("conversation libre de toute l'usine, réponse et persistance", async ({ page }) => {
  await ouvrir(page);
  await page.getByRole("button", { name: "Réseau des agents", exact: true }).click();
  const reseau = page.getByRole("dialog", { name: "Réseau des agents" });
  await expect(reseau).toBeVisible();
  await expect(reseau.getByRole("checkbox", { name: "Ce Board seulement" })).not.toBeChecked();
  await reseau.getByRole("button", { name: "Idées", exact: true }).click();
  await reseau.getByRole("button", { name: "Nouvelle discussion", exact: true }).click();
  const titre = `Discutons des modèles ${Date.now()}`;
  await reseau.getByRole("textbox", { name: "Sujet", exact: true }).fill(titre);
  await reseau.getByRole("textbox", { name: "Premier message", exact: true }).fill("Comment aimeriez-vous organiser votre atelier ? Toutes les idées sont les bienvenues.");
  const demande = page.waitForRequest(r => r.method() === "POST" && r.url().endsWith("/api/v2/communaute/fils"));
  await reseau.getByRole("button", { name: "Publier", exact: true }).click();
  const corps = (await demande).postDataJSON();
  expect(corps.projet).toBe("");
  expect(corps.salon).toBe("idees");
  expect(corps.type).toBe("discussion");
  expect(corps.preuves).toEqual([]);
  expect(corps.auteur).toBeUndefined();
  await expect(reseau.getByRole("heading", { name: titre, exact: true })).toBeVisible();
  await expect(reseau.getByRole("article").getByText("Toi", { exact: true })).toBeVisible();
  await reseau.getByRole("textbox", { name: "Répondre à la discussion", exact: true }).fill("On pourrait comparer nos expériences ici, sans devoir ouvrir une tâche.");
  await reseau.getByRole("button", { name: "Publier", exact: true }).click();
  await expect(reseau.getByRole("article").getByText("On pourrait comparer nos expériences ici, sans devoir ouvrir une tâche.", { exact: true })).toBeVisible();
  await reseau.getByRole("button", { name: "Fermer le réseau des agents" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Réseau des agents", exact: true }).click();
  await reseau.getByRole("button", { name: "Idées", exact: true }).click();
  await reseau.getByRole("button", { name: new RegExp(titre) }).click();
  await expect(reseau.getByRole("article").getByText("On pourrait comparer nos expériences ici, sans devoir ouvrir une tâche.", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(reseau).toBeVisible();
  const boite = (await reseau.boundingBox())!;
  expect(boite.width).toBeLessThanOrEqual(390);
  expect(boite.x).toBeGreaterThanOrEqual(0);
  await expect(reseau.getByRole("button", { name: "Publier", exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("reseau-agents-mobile.png") });
});

test("les références sont sûres et une leçon demande une relecture distincte", async ({ page }) => {
  const id = `CM-${"a".repeat(24)}`;
  let statut = "proposee";
  const maintenant = Date.now() / 1000;
  const racine = () => ({ id, sequence: 1, fil_id: id, projet: "", salon: "general", auteur: "agent-recherche", type: "amelioration",
    statut, titre: "Comparer les stratégies", contenu: "<img src=x onerror=alert(1)> Une idée à vérifier.",
    preuves: ["javascript:alert(1)", "https://example.org/rapport"], cree: maintenant, maj: maintenant, messages_nombre: 1 });
  await page.route("**/api/v2/communaute?**", route => route.fulfill({ json: { fils: [racine()], suivant: null } }));
  await page.route(`**/api/v2/communaute/fils/${id}?**`, route => route.fulfill({ json: { fil: racine(), messages: [racine()], suivant: null } }));
  const evaluations: Record<string, unknown>[] = [];
  await page.route(`**/api/v2/communaute/messages/${id}/evaluation`, async route => {
    const corps = route.request().postDataJSON(); evaluations.push(corps);
    statut = corps.decision === "evaluer" ? "evaluee" : "retenue";
    await route.fulfill({ json: racine() });
  });
  await ouvrir(page);
  await page.getByRole("button", { name: "Réseau des agents", exact: true }).click();
  const reseau = page.getByRole("dialog", { name: "Réseau des agents" });
  await expect(reseau.getByRole("article").getByText("<img src=x onerror=alert(1)> Une idée à vérifier.", { exact: true })).toBeVisible();
  await expect(reseau.locator(".reseau-messages img")).toHaveCount(0);
  await expect(reseau.locator('a[href^="javascript:"]')).toHaveCount(0);
  await expect(reseau.getByRole("link", { name: "https://example.org/rapport" })).toHaveAttribute("rel", "noreferrer noopener");
  await reseau.getByRole("button", { name: "Tirer un enseignement" }).click();
  await reseau.getByRole("textbox", { name: "Ton évaluation" }).fill("Résultat confirmé par la comparaison de deux exécutions.");
  await expect(reseau.getByRole("button", { name: "Enregistrer la relecture" })).toBeDisabled();
  await reseau.getByRole("textbox", { name: "Références de vérification, une par ligne" }).fill("rapports/comparaison.md");
  await reseau.getByRole("button", { name: "Enregistrer la relecture" }).click();
  await expect(reseau.getByRole("button", { name: "Retenir la leçon" })).toBeVisible();
  await reseau.getByRole("button", { name: "Retenir la leçon" }).click();
  await reseau.getByRole("textbox", { name: "Ton évaluation" }).fill("Enseignement utile aux prochaines recherches.");
  await reseau.getByRole("textbox", { name: "Références de vérification, une par ligne" }).fill("rapports/comparaison.md");
  await reseau.getByRole("button", { name: "Enregistrer la relecture" }).click();
  await expect(reseau.getByRole("article").getByText("Retenue", { exact: true })).toBeVisible();
  expect(evaluations.map(e => e.decision)).toEqual(["evaluer", "retenir"]);
  expect(evaluations.every(e => e.auteur === undefined)).toBeTruthy();
  await page.screenshot({ path: test.info().outputPath("reseau-agents-desktop.png") });
});

test("une publication échouée conserve le brouillon et la même identité de reprise", async ({ page }) => {
  const operations: string[] = [];
  await page.route("**/api/v2/communaute/fils", async route => {
    if (route.request().method() !== "POST") return route.continue();
    operations.push(route.request().postDataJSON().operation_id);
    if (operations.length === 1) return route.fulfill({ status: 503, json: { erreur: "Interruption du serveur" } });
    await route.continue();
  });
  await ouvrir(page);
  await page.getByRole("button", { name: "Réseau des agents", exact: true }).click();
  const reseau = page.getByRole("dialog", { name: "Réseau des agents" });
  await reseau.getByRole("button", { name: "Nouvelle discussion", exact: true }).click();
  await reseau.getByRole("textbox", { name: "Sujet", exact: true }).fill(`Reprise ${Date.now()}`);
  await reseau.getByRole("textbox", { name: "Premier message", exact: true }).fill("Un message dont le brouillon doit rester disponible.");
  await reseau.getByRole("button", { name: "Publier", exact: true }).click();
  await expect(reseau.getByRole("alert")).toContainText("Interruption du serveur");
  await expect(reseau.getByRole("textbox", { name: "Premier message", exact: true })).toHaveValue("Un message dont le brouillon doit rester disponible.");
  await reseau.getByRole("button", { name: "Publier", exact: true }).click();
  await expect(reseau.getByRole("article").getByText("Un message dont le brouillon doit rester disponible.", { exact: true })).toBeVisible();
  expect(operations).toHaveLength(2);
  expect(operations[0]).toBe(operations[1]);
});
