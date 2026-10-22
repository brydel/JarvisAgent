import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { expect, type Page } from "@playwright/test";

export const DEMO = path.resolve(import.meta.dirname, "../../public/demo");
export const RAPPORTS = path.resolve(import.meta.dirname, "../../../../reports/board-v2");

/** Ouvre le Board réel avec une session (jeton du serveur de test, passé dans le fragment comme en production). */
export async function ouvrir(page: Page) {
  const jeton = fs.readFileSync("/tmp/jarvis-e2e-jeton", "utf8").trim();
  await page.goto(`/v2/connexion#${jeton}`);
  await expect(page.locator(".react-flow")).toBeVisible();
  // chaque test part d'un Board vide (suppression douce par l'API : rien n'est effacé de la base de test)
  await page.evaluate(async () => {
    const ids = (await (await fetch("/api/v2/board")).json()).objets.map((o: { id: string }) => o.id);
    for (let i = 0; i < ids.length; i += 400) {
      await fetch("/api/v2/objets/supprimer", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" },
        body: JSON.stringify({ ids: ids.slice(i, i + 400) }) });
    }
  });
  await page.reload();
  await expect(page.locator(".react-flow")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

export async function attendreStable(page: Page, ms = 400) {
  // pas de « networkidle » : le flux SSE du Board réel garde une connexion ouverte en permanence
  await page.locator(".react-flow__node").first().waitFor({ state: "visible", timeout: 15_000 }).catch(() => undefined);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(ms);
}

/** Petit PNG valide généré à la volée (aucun fichier externe). */
export function png(largeur: number, hauteur: number): Buffer {
  const crc = (b: Buffer) => {
    let c = ~0;
    for (const x of b) {
      c ^= x;
      for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
    return ~c >>> 0;
  };
  const bloc = (t: string, d: Buffer) => {
    const tb = Buffer.from(t);
    const l = Buffer.alloc(4);
    l.writeUInt32BE(d.length);
    const c = Buffer.alloc(4);
    c.writeUInt32BE(crc(Buffer.concat([tb, d])));
    return Buffer.concat([l, tb, d, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(largeur, 0);
  ihdr.writeUInt32BE(hauteur, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const lignes = Buffer.concat(Array.from({ length: hauteur }, (_, y) =>
    Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: largeur }, (_, x) => [x * 2 % 255, 90, 200 - y % 120]).flat())])));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), bloc("IHDR", ihdr), bloc("IDAT", zlib.deflateSync(lignes)), bloc("IEND", Buffer.alloc(0))]);
}

export function noeud(page: Page, texte: string) {
  return page.locator(".react-flow__node").filter({ hasText: texte }).first();
}

/** Ajoute une note par la barre d'outils et renvoie l'identifiant de LA carte créée (pas « la dernière » du DOM). */
export async function ajouterNote(page: Page): Promise<string> {
  const avant = new Set(await page.locator(".react-flow__node").evaluateAll((ns) => ns.map((n) => n.getAttribute("data-id"))));
  await page.getByRole("toolbar", { name: "Ajouter au Board" }).getByRole("button", { name: "Ajouter" }).click();
  let id = "";
  await expect.poll(async () => {
    const ids = await page.locator(".react-flow__node").evaluateAll((ns) => ns.map((n) => n.getAttribute("data-id")));
    id = (ids.find((x) => x && !avant.has(x)) as string) ?? "";
    return id;
  }).not.toBe("");
  return id;
}
