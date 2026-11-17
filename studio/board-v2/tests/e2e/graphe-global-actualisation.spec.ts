import { expect, test } from "@playwright/test";
import type { ObjetBoard } from "../../src/types";
import type { PageGrapheGlobal, SessionGraphe } from "../../src/fichiers/global-donnees";
import { ouvrir } from "./outils";

test("une actualisation conserve les lots chargés et le centroïde de la seconde page", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await ouvrir(page);
  const creer = async (espace: string, titre: string) => {
    const resultat = await page.request.post("/api/v2/objets", { headers: { "X-Jarvis-Studio": "1" },
      data: { espace, type: "note", contenu: titre, meta: { titre }, analyser: false } });
    expect(resultat.ok()).toBe(true);
    return (await resultat.json()).objet_id as string;
  };
  const ids = [
    await creer("Actualisation-A", "Point du premier lot"),
    await creer("Actualisation-B", "Point du second lot"),
  ];
  const resultat = await page.request.get("/api/v2/graphe-global");
  expect(resultat.ok()).toBe(true);
  const reels = (await resultat.json()).objets as ObjetBoard[];
  const objets = ids.map((id) => reels.find((o) => o.id === id)!);
  expect(objets.every(Boolean)).toBe(true);
  const sessions: SessionGraphe[] = objets.map((objet, index) => ({
    id: index === 0 ? "AR-a11111111111" : "AR-b22222222222",
    titre: index === 0 ? "Session du premier lot" : "Session du second lot",
    projet: objet.espace, projets: [objet.espace], origine: "runtime", statut: "en cours",
    debut: 1, fin: null, objet_ids: [objet.id], mission_ids: [], evenement_ids: [],
  }));
  let phase = 1;
  const lectures: { phase: number; page: number }[] = [];
  // Le transport renvoie deux lots contrôlés pour observer les relectures après visibilité.
  await page.route("**/api/v2/graphe-global?*", async (route) => {
    const numero = Number(new URL(route.request().url()).searchParams.get("page") || 1);
    expect([1, 2]).toContain(numero);
    const generation = phase;
    lectures.push({ phase: generation, page: numero });
    const index = numero - 1;
    const objet = objets[index]!;
    const session = sessions[index]!;
    const donnees: PageGrapheGlobal = {
      page: numero, limite: 1,
      objets: [{ ...objet, contenu: generation === 2 ? "Point actualisé du lot " + numero : objet.contenu }],
      liens: [], entrees: [],
      sessions: [{ ...session, titre: generation === 2 ? session.titre + " actualisée" : session.titre }],
      projets: objets.map((o) => ({ nom: o.espace, objets: 1 })),
      couverture: {
        objets: { charges: 1, total: 2 }, sessions: { charges: 1, total: 2 },
        liens: { charges: 0, total: 0 }, entrees: { charges: 0, total: 0 },
      },
      suivant: numero === 1 ? 2 : null, avertissements: [], cle_disposition: "a00000000000000000000001",
    };
    await route.fulfill({ json: donnees });
  });

  await page.goto("/v2/?vue=fichiers");
  const graphe = page.getByRole("region", { name: "Graphe de mémoire", exact: true });
  await page.getByRole("button", { name: "Charger d’autres projets et sessions", exact: true }).click();
  await expect(page.getByRole("button", { name: "Charger d’autres projets et sessions", exact: true })).toHaveCount(0);
  await graphe.getByRole("button", { name: "Cadrer le graphe", exact: true }).click();
  const centreSecond = graphe.locator('[data-id="centroide:' + sessions[1]!.id + '"]');
  await expect(centreSecond).toBeVisible();

  phase = 2;
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect.poll(() => [...new Set(lectures.filter((l) => l.phase === 2).map((l) => l.page))].sort()).toEqual([1, 2]);
  await expect(centreSecond).toBeVisible();
  await expect(centreSecond).toHaveAttribute("aria-label", "Centroïde de Session du second lot actualisée");
  await expect(graphe.locator('[data-id="' + ids[1] + '"]')).toBeAttached();
  await expect(page.getByRole("button", { name: "Charger d’autres projets et sessions", exact: true })).toHaveCount(0);
});
