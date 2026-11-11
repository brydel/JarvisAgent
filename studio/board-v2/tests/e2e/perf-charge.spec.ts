import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { RAPPORTS } from "./outils";

// Jeu d'essai lourd (mode démo, ?charge=5000 : cartes de types mixtes). Mêmes relevés que perf.spec.ts
// (durée de chaque image par requestAnimationFrame pendant des gestes réels), à deux échelles :
// vue de travail (zoom 80 %, une trentaine de cartes à l'écran) et vue d'ensemble (tout le Board dans le cadre).
// Lancé seulement sur demande : JARVIS_PERF_CHARGE=5000 JARVIS_PERF_ETIQUETTE=avant|apres npx playwright test perf-charge
const CHARGE = Number(process.env.JARVIS_PERF_CHARGE || 0);
const ETIQUETTE = process.env.JARVIS_PERF_ETIQUETTE || "apres";
const SORTIE = path.join(RAPPORTS, "perf-charge.json");

async function mesurer(page: Page, geste: () => Promise<void>) {
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
  const debut = Date.now();
  await geste();
  const duree = Date.now() - debut;
  const images = await page.evaluate(() => {
    const w = window as unknown as { __images: number[]; __fin: boolean };
    w.__fin = true;
    return w.__images.slice(2);
  });
  const tri = [...images].sort((a, b) => a - b);
  const q = (p: number) => Math.round((tri[Math.min(tri.length - 1, Math.floor(p * tri.length))] ?? 0) * 10) / 10;
  const total = images.reduce((s, x) => s + x, 0);
  return { images: images.length, duree_geste_ms: duree, ips_moyen: Math.round((1000 * images.length) / Math.max(1, total) * 10) / 10,
    mediane_ms: q(0.5), p95_ms: q(0.95), max_ms: q(1), images_longues_50ms: images.filter((x) => x > 50).length };
}

test.skip(!CHARGE, "mesure lourde : définir JARVIS_PERF_CHARGE");
test(`fluidité avec ${CHARGE} objets (${ETIQUETTE})`, async ({ page }) => {
  test.setTimeout(600_000);
  const t0 = Date.now();
  await page.goto(`/v2/?demo=1&charge=${CHARGE}`);
  await page.locator(".react-flow__node").first().waitFor({ timeout: 120_000 });
  const chargementMs = Date.now() - t0;
  await page.waitForTimeout(1500);
  const pane = (await page.locator(".react-flow__pane").boundingBox())!;
  const cx = pane.x + pane.width / 2, cy = pane.y + pane.height / 2;
  const panoramique = async () => {
    await page.mouse.move(cx, cy);
    await page.mouse.down({ button: "middle" });
    for (let i = 0; i < 90; i++) await page.mouse.move(cx + Math.sin(i / 8) * 260, cy + Math.cos(i / 10) * 140);
    await page.mouse.up({ button: "middle" });
  };
  const zoomer = async () => {
    for (let i = 0; i < 24; i++) {
      await page.mouse.wheel(0, i < 12 ? -120 : 120);
      await page.waitForTimeout(16);
    }
  };
  // 1. vue de travail : zoom initial (80 %), au milieu des cartes de charge
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(cx - 600, cy - 200, { steps: 4 });
  await page.mouse.up({ button: "middle" });
  await page.waitForTimeout(500);
  const lireZoom = async () => (await page.locator(".zoom output").textContent())?.trim() ?? "";
  const travail = { zoom: await lireZoom(), noeuds_rendus: await page.locator(".react-flow__node").count(),
    panoramique: await mesurer(page, panoramique), zoom_molette: await mesurer(page, zoomer) };
  // 2. vue d'ensemble : tout le Board dans le cadre (cas le plus coûteux)
  await page.getByRole("button", { name: "Ajuster à la vue" }).click();
  await page.waitForTimeout(3000);
  const ensemble = { zoom: await lireZoom(), noeuds_rendus: await page.locator(".react-flow__node").count(),
    panoramique: await mesurer(page, panoramique), zoom_molette: await mesurer(page, zoomer) };
  // 3. même échelle qu'avant le lot (15 %, l'ancien zoom minimal) quand la vue d'ensemble descend plus bas
  let quinze: typeof ensemble | null = null;
  if (parseInt(ensemble.zoom, 10) < 15) {
    await page.mouse.move(cx, cy);
    for (let i = 0; i < 60 && parseInt(await lireZoom(), 10) < 15; i++) {
      await page.mouse.wheel(0, -40);
      await page.waitForTimeout(40);
    }
    await page.waitForTimeout(1500);
    quinze = { zoom: await lireZoom(), noeuds_rendus: await page.locator(".react-flow__node").count(),
      panoramique: await mesurer(page, panoramique), zoom_molette: await mesurer(page, zoomer) };
  }

  const resultats: Record<string, unknown> = fs.existsSync(SORTIE) ? JSON.parse(fs.readFileSync(SORTIE, "utf8")) : {};
  resultats[`${ETIQUETTE}_${CHARGE}`] = {
    date: new Date().toISOString(), navigateur: `Chromium ${page.context().browser()?.version()} (Playwright, sans GPU, WSL2)`,
    viewport: "1672×941", objets: 9 + CHARGE, chargement_ms: chargementMs, vue_de_travail: travail, vue_d_ensemble: ensemble, ...(quinze ? { vue_a_15_pour_cent: quinze } : {}),
  };
  fs.mkdirSync(RAPPORTS, { recursive: true });
  fs.writeFileSync(SORTIE, JSON.stringify(resultats, null, 1));
  expect(travail.noeuds_rendus).toBeGreaterThan(0);
});
