import { expect, test, type Page } from "@playwright/test";
import { ajouterNote, ouvrir } from "./outils";

// Fondations de données du Board, vues du navigateur : synchronisation incrémentale (plus de rechargement complet
// à chaque événement ni toutes les 10 s), flux ouvert au curseur, écritures versionnées avec retour arrière.
test.describe.configure({ mode: "serial" });

const ENTETES = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };

/** Écriture faite « ailleurs » (autre onglet, chef) : même API, sans passer par l'interface de cette page. */
async function ailleurs(page: Page, chemin: string, corps: unknown) {
  return page.evaluate(async ({ chemin, corps, entetes }) => {
    const r = await fetch(chemin, { method: "POST", headers: entetes, body: JSON.stringify(corps) });
    return { statut: r.status, corps: await r.json() };
  }, { chemin, corps, entetes: ENTETES });
}

async function objetServeur(page: Page, id: string) {
  return page.evaluate(async (i) => (await (await fetch(`/api/v2/objets?ids=${i}`)).json()).objets[0], id);
}

test("un seul chargement complet : les changements distants arrivent par lecture ciblée, le flux part du curseur", async ({ page }) => {
  await ouvrir(page);
  for (let i = 0; i < 3; i++) await ailleurs(page, "/api/v2/objets", { type: "note", contenu: `historique ${i}`, x: i * 460, y: 0, largeur: 408, hauteur: 320, analyser: false });
  const complets: string[] = [], cibles: string[] = [], flux: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() !== "GET") return;
    if (u.pathname === "/api/v2/board") complets.push(u.search);
    if (u.pathname === "/api/v2/objets") cibles.push(u.search);
    if (u.pathname === "/api/flux") flux.push(u.search);
  });
  const chargement = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v2/board");
  await page.reload();
  const curseur = (await (await chargement).json()).curseur as number;
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await expect.poll(() => flux.length).toBe(1);
  // le flux reprend au curseur rendu par le chargement, filtré sur ce Board : l'historique n'est pas rejoué
  expect(curseur).toBeGreaterThan(0);
  expect(new URLSearchParams(flux[0]).get("apres")).toBe(String(curseur));
  expect(new URLSearchParams(flux[0]).get("espace")).toBe("accueil");

  // un autre client crée une carte, la déplace, puis la supprime : cette page suit, sans recharger le Board
  const cree = await ailleurs(page, "/api/v2/objets", { type: "note", contenu: "posée ailleurs", x: 100, y: 500, largeur: 408, hauteur: 320, analyser: false });
  const id = cree.corps.objet_id as string;
  const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
  await expect(carte).toBeVisible();
  await ailleurs(page, `/api/v2/objets/${id}`, { champs: { priorite: "P2" }, version: 1 });
  await expect(carte.locator(".badge-p.P2")).toBeVisible();
  // un événement d'un AUTRE Board ne déclenche rien ici
  const avant = cibles.length;
  await ailleurs(page, "/api/v2/objets", { type: "note", contenu: "autre projet", x: 0, y: 0, largeur: 408, hauteur: 320, analyser: false, espace: "Projet voisin" });
  await page.waitForTimeout(1200);
  expect(cibles.length).toBe(avant);
  await ailleurs(page, "/api/v2/objets/supprimer", { ids: [id] });
  await expect(carte).toHaveCount(0);

  // mes propres écritures : optimistes, sans relecture du Board
  const mienne = await ajouterNote(page);
  await page.locator(`.react-flow__node[data-id="${mienne}"]`).getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitemradio").filter({ hasText: "P1" }).click();
  await expect(page.locator(`.react-flow__node[data-id="${mienne}"] .badge-p.P1`)).toBeVisible();
  await expect.poll(async () => (await objetServeur(page, mienne)).priorite).toBe("P1");

  // au-delà de l'ancien intervalle de relecture (10 s) : toujours UN seul chargement complet
  await page.waitForTimeout(11_000);
  expect(complets).toHaveLength(1);
  expect(cibles.length).toBeGreaterThan(0);
  expect(cibles.every((s) => /[?&](ids|liens)=/.test(s))).toBe(true);
});

test("conflit : une écriture périmée est refusée, annulée à l'écran et la carte relue ; rien n'est écrasé", async ({ page }) => {
  await ouvrir(page);
  const id = await ajouterNote(page);
  // cette page ne reçoit plus le flux : elle reste sur la version qu'elle connaît (cas d'un onglet en retard)
  await page.route("**/api/flux**", (r) => r.abort());
  await page.reload();
  const carte = page.locator(`.react-flow__node[data-id="${id}"]`);
  await expect(carte).toBeVisible();

  // ailleurs : la priorité passe à P2 (version 2). Ici, on choisit P1 sur la version 1 → refus
  expect((await ailleurs(page, `/api/v2/objets/${id}`, { champs: { priorite: "P2" }, version: 1 })).corps).toEqual({ version: 2 });
  await carte.getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitemradio").filter({ hasText: "P1" }).click();
  await expect(page.locator(".toast.erreur")).toContainText("modifié ailleurs");
  await expect(carte.locator(".badge-p.P2")).toBeVisible();   // l'écran montre la version du serveur
  await expect(carte.locator(".badge-p.P1")).toHaveCount(0);
  expect(await objetServeur(page, id)).toMatchObject({ priorite: "P2", version: 2 });  // pas de « dernière écriture gagne »

  // la carte a été relue : la même action, faite en connaissance de cause, passe
  await carte.getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitemradio").filter({ hasText: "P1" }).click();
  await expect(carte.locator(".badge-p.P1")).toBeVisible();
  await expect.poll(async () => (await objetServeur(page, id)).version).toBe(3);

  // changement ailleurs d'un AUTRE champ (position) : ma priorité est rejouée sur la nouvelle version, rien n'est perdu
  await ailleurs(page, `/api/v2/objets/${id}`, { champs: { x: 1234, y: 321 }, version: 3 });
  await carte.getByRole("button", { name: "Actions de la carte" }).click();
  await page.getByRole("menuitemradio").filter({ hasText: "P3" }).click();
  await expect.poll(async () => {
    const o = await objetServeur(page, id);
    return [o.priorite, o.x, o.y, o.version];
  }).toEqual(["P3", 1234, 321, 5]);
  await expect(carte.locator(".badge-p.P3")).toBeVisible();

  // suppression d'une carte modifiée ailleurs : refusée, la carte reste
  await ailleurs(page, `/api/v2/objets/${id}`, { champs: { contenu: "réécrite ailleurs" }, version: 5 });
  await carte.click({ position: { x: 150, y: 30 } });
  await page.keyboard.press("Delete");
  await expect(page.locator(".toast.erreur").last()).toContainText("modifié ailleurs");
  await expect(carte).toHaveCount(1);
  await expect(carte).toContainText("réécrite ailleurs");
});

test("le bouton « Dossier » de la barre d'outils crée bien un dossier (et ne s'appelle plus « Mind map »)", async ({ page }) => {
  await ouvrir(page);
  const barre = page.getByRole("toolbar", { name: "Ajouter au Board" });
  await expect(barre.getByRole("button", { name: "Mind map" })).toHaveCount(0);
  await barre.getByRole("button", { name: "Dossier" }).click();
  await expect(page.locator(".react-flow__node-dossier")).toHaveCount(1);
});
