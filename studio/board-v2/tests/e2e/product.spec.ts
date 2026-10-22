import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const output = path.resolve("../../reports/product-studio");
test.beforeAll(() => fs.mkdirSync(output, { recursive: true }));
test.use({ reducedMotion: "reduce" });

for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]] as const) {
  test(`accueil et navigation ${name}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.setViewportSize({ width, height });
    await page.goto("/v2/?demo=1&vue=accueil");
    await expect(page.getByRole("heading", { name: /Une id/ })).toBeVisible();
    await page.screenshot({ path: path.join(output, `accueil-${name}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: "Agents", exact: true }).click();
    await expect(page.locator(".p-agent-card")).toHaveCount(6);
    await page.screenshot({ path: path.join(output, `agents-${name}.png`) });
    await page.locator(".p-agent-card").first().click();
    await expect(page.locator("#agent-brief")).toBeVisible();
    await page.screenshot({ path: path.join(output, `atelier-${name}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("intention pre-remplie, sans lancement implicite", async ({ page }) => {
  await page.goto("/v2/?demo=1&vue=accueil");
  await page.locator(".p-intents button").first().click();
  await expect(page.locator('input[name="objectif"]')).toHaveValue(/comprendre un sujet/);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("brouillon conserve entre vues, controle sans inference", async ({ page }) => {
  await page.goto("/v2/?demo=1&vue=agents");
  await page.locator(".p-agent-card").first().click();
  const initial = await page.locator("#agent-brief").inputValue();
  const next = initial + "\nToujours fournir les limites et les preuves de verification.";
  await page.locator("#agent-brief").fill(next);
  await page.getByRole("button", { name: "Accueil", exact: true }).click();
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.locator(".p-agent-card").first().click();
  await expect(page.locator("#agent-brief")).toHaveValue(next);
  await page.getByRole("button", { name: /V.rifier les consignes/ }).click();
  await expect(page.locator(".p-verification")).toContainText(/structurelles/);
  await expect(page.locator(".p-verification")).toContainText(/aucun appel IA/);
  await page.screenshot({ path: path.join(output, "atelier-comparaison.png") });
});

test("routes utiles et retour au vrai Board", async ({ page }) => {
  await page.goto("/v2/?demo=1&vue=accueil");
  for (const route of ["Missions", "Connaissances", "Fichiers", "Configuration"]) {
    await page.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: route, exact: true }).click();
    await expect(page.locator(".p-page h1")).toBeVisible();
    await page.screenshot({ path: path.join(output, `${route.toLowerCase()}.png`) });
  }
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator(".react-flow")).toBeVisible();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await page.screenshot({ path: path.join(output, "board-preserve.png") });
});

test("atelier reel: proposition, essai limite et retrait", async ({ page, request }) => {
  const token = fs.readFileSync("/tmp/jarvis-e2e-jeton", "utf8").trim();
  await page.goto(`/v2/connexion?vue=agents#${token}`);
  await expect(page.locator(".p-agent-card").first()).toBeVisible();
  await page.locator(".p-agent-card").filter({ hasText: "Designer" }).first().click();
  const initial = await page.locator("#agent-brief").inputValue();
  await page.locator("#agent-brief").fill(initial + "\n\nVerifier chaque livrable avec une preuve documentee et ses limites explicites.");
  await page.locator("#agent-why").fill("Rendre les preuves et les limites faciles a verifier.");
  await page.getByRole("button", { name: /V.rifier les consignes/ }).click();
  await expect(page.locator(".p-verification")).toContainText(/structurelles/);
  await page.getByRole("button", { name: "Enregistrer la proposition" }).click();
  await expect(page.locator(".p-version").first()).toBeVisible();
  await page.locator(".p-version").first().click();
  await expect(page.locator(".p-review-dialog pre")).toContainText("Verifier chaque livrable");
  await expect(page.getByRole("button", { name: /Autoriser l'essai/ })).toBeDisabled();
  await page.locator(".p-consent input").check();
  await page.getByRole("button", { name: /Autoriser l'essai/ }).click();
  await expect(page.locator(".p-review-dialog")).not.toBeVisible();
  await page.locator(".p-version").first().click();
  await page.getByRole("button", { name: "Retirer le candidat" }).click();
  await expect(page.locator(".p-review-dialog")).not.toBeVisible();
  await expect(page.locator("#agent-brief")).toHaveValue(initial);
  await page.screenshot({ path: path.join(output, "atelier-reel.png") });
  const denied = await request.get("/api/v2/atelier");
  expect(denied.status()).toBe(401);
});
