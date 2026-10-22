import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { RAPPORTS } from "./outils";

// Mesures de fluidité (mode démo + ?charge=N cartes de types mixtes). Les durées d'image sont relevées dans la page
// par requestAnimationFrame pendant des gestes réels (événements souris CDP). Chromium sans GPU sous WSL : les
// chiffres sont PESSIMISTES par rapport à Chrome/Edge avec accélération matérielle sur l'ASUS.

async function enregistrer(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __images: number[]; __fin: boolean };
    w.__images = [];
    w.__fin = false;
    let t0 = performance.now();
    const boucle = (t: number) => {
      w.__images.push(t - t0);
      t0 = t;
      if (!w.__fin) requestAnimationFrame(boucle);
    };
    requestAnimationFrame(boucle);
  });
}

async function arreter(page: Page) {
  const images = await page.evaluate(() => {
    const w = window as unknown as { __images: number[]; __fin: boolean };
    w.__fin = true;
    return w.__images.slice(2);
  });
  const tri = [...images].sort((a, b) => a - b);
  const q = (p: number) => Math.round((tri[Math.min(tri.length - 1, Math.floor(p * tri.length))] ?? 0) * 10) / 10;
  const moyenne = images.reduce((s, x) => s + x, 0) / Math.max(1, images.length);
  return { images: images.length, mediane_ms: q(0.5), p95_ms: q(0.95), max_ms: q(1), ips_moyen: Math.round(1000 / moyenne),
    images_longues_50ms: images.filter((x) => x > 50).length };
}

const SORTIE = path.join(RAPPORTS, "perf.json");
test.beforeAll(() => fs.rmSync(SORTIE, { force: true }));

for (const charge of [0, 100, 250]) {
  test(`fluidité avec ${charge} cartes supplémentaires`, async ({ page }) => {
    await page.goto(`/v2/?demo=1${charge ? `&charge=${charge}` : ""}`);
    await page.locator(".react-flow__node").first().waitFor();
    await page.waitForTimeout(800);
    // vue d'ensemble : toutes les cartes sont dans le cadre (cas le plus coûteux)
    await page.getByRole("button", { name: "Ajuster à la vue" }).click();
    await page.waitForTimeout(600);
    const noeudsRendus = await page.locator(".react-flow__node").count();
    const pane = (await page.locator(".react-flow__pane").boundingBox())!;
    const cx = pane.x + pane.width / 2, cy = pane.y + pane.height / 2;

    await enregistrer(page);
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    for (let i = 0; i < 90; i++) await page.mouse.move(cx + Math.sin(i / 8) * 260, cy + Math.cos(i / 10) * 140);
    await page.mouse.up();
    const pan = await arreter(page);

    await enregistrer(page);
    for (let i = 0; i < 24; i++) {
      await page.mouse.wheel(0, i < 12 ? -120 : 120);
      await page.waitForTimeout(16);
    }
    const zoom = await arreter(page);

    await page.getByRole("button", { name: "Ajuster à la vue" }).click();
    await page.waitForTimeout(400);
    // une carte effectivement rendue dans le cadre (les autres sont virtualisées)
    const carte = page.locator(".react-flow__node").first();
    const b = (await carte.boundingBox())!;
    await enregistrer(page);
    await page.mouse.move(b.x + b.width / 2, b.y + 12);
    await page.mouse.down();
    for (let i = 0; i < 60; i++) await page.mouse.move(b.x + b.width / 2 + i * 3, b.y + 12 + Math.sin(i / 6) * 40);
    await page.mouse.up();
    const glisser = await arreter(page);

    // réactivité : du clic « Ajouter » à l'apparition de la carte (mode démo, sans réseau)
    const avant = await page.locator(".react-flow__node").count();
    const t0 = Date.now();
    await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Ajouter" }).click();
    await expect(page.locator(".react-flow__node")).toHaveCount(avant + 1);
    const ajoutMs = Date.now() - t0;

    const resultats: Record<string, unknown> = fs.existsSync(SORTIE) ? JSON.parse(fs.readFileSync(SORTIE, "utf8")) : {};
    resultats.environnement = { navigateur: `Chromium ${page.context().browser()?.version()} (Playwright, sans GPU, WSL2)`,
      machine: "ASUS — Intel Core i9-13900H, 20 fils (WSL2)", date: new Date().toISOString(), viewport: "1672×941",
      note: "Chiffres pessimistes : rendu logiciel. Chrome/Edge Windows avec GPU sur l'ASUS non mesuré par ce test." };
    resultats[`charge_${charge}`] = { cartes_total: 9 + charge, noeuds_rendus_vue_ensemble: noeudsRendus, panoramique: pan, zoom_molette: zoom,
      glisser_carte: glisser, clic_ajouter_vers_carte_ms: ajoutMs };
    fs.mkdirSync(RAPPORTS, { recursive: true });
    fs.writeFileSync(SORTIE, JSON.stringify(resultats, null, 1));
    expect(pan.max_ms).toBeLessThan(1000);  // aucune interaction gelée
  });
}

