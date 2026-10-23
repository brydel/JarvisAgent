import path from "node:path";
import { expect, test } from "@playwright/test";
import { ouvrir, RAPPORTS } from "./outils";

test("format libre : couleur d'accent, vignette compacte, et les mêmes réglages depuis le menu de la carte", async ({ page }) => {
  await ouvrir(page);
  const ids = await page.evaluate(async () => {
    const poser = async (corps: object) => (await (await fetch("/api/v2/objets", { method: "POST",
      headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" }, body: JSON.stringify(corps) })).json()).objet_id as string;
    return [
      await poser({ type: "texte", contenu: "Objectifs du trimestre", x: 0, y: 0, largeur: 300, hauteur: 140, analyser: false,
        meta: { titre: "Feuille de route", couleur: "violet", source: "chef" } }),
      await poser({ type: "note", contenu: "Démo vendredi", x: 360, y: 0, largeur: 240, hauteur: 96, analyser: false,
        meta: { titre: "Rappel : démo vendredi", compact: true, couleur: "jaune", source: "chef" } }),
    ];
  });
  await page.reload();
  const feuille = page.locator(`.react-flow__node[data-id="${ids[0]}"] .carte`);
  await expect(feuille).toHaveClass(/accent-violet/);
  const rappel = page.locator(`.react-flow__node[data-id="${ids[1]}"] .carte`);
  await expect(rappel).toHaveClass(/carte-compacte/);
  await expect(rappel.getByText("Rappel : démo vendredi")).toBeVisible();
  expect((await rappel.boundingBox())!.height).toBeLessThan(110);
  await page.screenshot({ path: path.join(RAPPORTS, "etat-dessin-libre.png") });
  // à la main : la vignette repasse en taille normale, puis on change sa couleur
  await rappel.getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitem", { name: "Taille normale" }).click();
  const normale = page.locator(`.react-flow__node[data-id="${ids[1]}"] .carte`);
  await expect(normale).not.toHaveClass(/carte-compacte/);
  await normale.getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitemradio", { name: "Couleur cyan" }).click();
  await expect(page.locator(`.react-flow__node[data-id="${ids[1]}"] .carte`)).toHaveClass(/accent-cyan/);
});
