import { describe, expect, it, vi } from "vitest";
import { FileEcritures } from "./ecritures";
import { FauxServeur, carte, lien } from "./essais";
import { StoreBoard } from "./store";

async function monter(objets = [carte("A"), carte("B")], liens = [lien("L1", "A", "B")]) {
  const serveur = new FauxServeur(objets, liens);
  const store = new StoreBoard();
  store.remplacer(await serveur.charger());
  const rappels = { conflit: vi.fn(), erreur: vi.fn() };
  const file = new FileEcritures(serveur, store, rappels);
  serveur.appels.charger = 0;
  return { serveur, store, file, rappels };
}

describe("file d'écritures optimistes", () => {
  it("toute modification part avec la version connue et s'affiche avant la réponse", async () => {
    const { serveur, store, file } = await monter();
    const p = file.modifier([{ id: "A", champs: { x: 120, y: 40 } }]);
    expect(store.objet("A")).toMatchObject({ x: 120, y: 40 });   // optimiste : avant tout aller-retour
    expect(serveur.appels.modifier).toBe(0);
    const r = await p;
    expect(r).toEqual([{ id: "A", ok: true, version: 2 }]);
    expect(serveur.envois[0]).toEqual([{ id: "A", champs: { x: 120, y: 40 }, version: 1 }]);
    expect(store.objetServeur("A")).toMatchObject({ x: 120, version: 2 });
    expect(store.enAttente()).toBe(0);
    expect(serveur.appels.lire + serveur.appels.charger).toBe(0);  // aucune relecture après une écriture réussie
  });

  it("deux gestes rapides sur la même carte s'enchaînent : la seconde écriture porte la version rendue par la première", async () => {
    const { serveur, store, file, rappels } = await monter();
    const p1 = file.modifier([{ id: "A", champs: { x: 10 } }]);
    const p2 = file.modifier([{ id: "A", champs: { x: 20 } }]);
    expect(store.objet("A")!.x).toBe(20);
    await Promise.all([p1, p2]);
    expect(serveur.envois.map((e) => e[0]!.version)).toEqual([1, 2]);
    expect(serveur.objets.get("A")).toMatchObject({ x: 20, version: 3 });
    expect(rappels.conflit).not.toHaveBeenCalled();
  });

  it("conflit sur le MÊME champ : retour arrière, relecture de l'objet, l'autre écriture n'est pas écrasée", async () => {
    const { serveur, store, file, rappels } = await monter();
    serveur.ailleurs("A", { x: 999 });                       // un autre onglet a déplacé la carte
    const r = await file.modifier([{ id: "A", champs: { x: 120 } }]);
    expect(r[0]).toMatchObject({ ok: false, code: "conflit" });
    expect(serveur.objets.get("A")!.x).toBe(999);            // pas de « dernière écriture gagne »
    expect(store.objet("A")).toMatchObject({ x: 999, version: 2 });  // l'écran montre la version du serveur
    expect(serveur.demandes).toEqual([{ objets: ["A"] }]);   // UN objet relu, pas le Board
    expect(serveur.appels.charger).toBe(0);
    expect(rappels.conflit).toHaveBeenCalledWith(["A"]);
    expect(store.enAttente()).toBe(0);
  });

  it("conflit sur un AUTRE champ : l'écriture est rejouée une fois sur la nouvelle version, rien n'est perdu", async () => {
    const { serveur, store, file, rappels } = await monter();
    serveur.ailleurs("A", { priorite: "P1" });               // le chef a changé la priorité pendant que je déplaçais
    const r = await file.modifier([{ id: "A", champs: { x: 120 } }]);
    expect(r[0]).toMatchObject({ ok: true, version: 3 });
    expect(serveur.objets.get("A")).toMatchObject({ x: 120, priorite: "P1", version: 3 });
    expect(store.objet("A")).toMatchObject({ x: 120, priorite: "P1", version: 3 });
    expect(serveur.envois.map((e) => e[0]!.version)).toEqual([1, 2]);
    expect(rappels.conflit).not.toHaveBeenCalled();
  });

  it("meta : une proposition du chef arrivée entre-temps ne bloque pas une étiquette, et n'est pas effacée", async () => {
    const { serveur, store, file, rappels } = await monter([carte("A", { meta: { titre: "t" } })], []);
    serveur.ailleurs("A", { meta: { titre: "t", jarvis_resume: "lu par le chef" } });
    const r = await file.modifier([{ id: "A", champs: { meta: { titre: "t", tags: ["urgent"] } } }]);
    expect(r[0]!.ok).toBe(true);
    expect(store.objet("A")!.meta).toEqual({ titre: "t", tags: ["urgent"], jarvis_resume: "lu par le chef" });
    expect(rappels.conflit).not.toHaveBeenCalled();
  });

  it("le rejeu n'a lieu qu'une fois : un second conflit annule l'écriture", async () => {
    const { serveur, store, file, rappels } = await monter();
    serveur.ailleurs("A", { priorite: "P1" });
    let n = 0;
    const original = serveur.modifier.bind(serveur);
    serveur.modifier = async (mods) => {
      if (++n === 2) serveur.ailleurs("A", { priorite: "P2" });  // encore modifié juste avant le rejeu
      return original(mods);
    };
    const r = await file.modifier([{ id: "A", champs: { x: 120 } }]);
    expect(r.at(-1)).toMatchObject({ ok: false, code: "conflit" });
    expect(n).toBe(2);
    expect(store.objet("A")!.x).toBe(0);
    expect(rappels.conflit).toHaveBeenCalledTimes(1);
  });

  it("refus métier (carte verrouillée) : retour arrière et message, sans relecture", async () => {
    const { serveur, store, file, rappels } = await monter([carte("A", { verrouille: 1 })], []);
    const r = await file.modifier([{ id: "A", champs: { x: 50 } }]);
    expect(r[0]!.ok).toBe(false);
    expect(store.objet("A")!.x).toBe(0);
    expect(rappels.erreur).toHaveBeenCalledWith("objet verrouillé");
    expect(serveur.appels.lire).toBe(0);
  });

  it("panne réseau : toutes les écritures du lot sont annulées à l'écran", async () => {
    const { serveur, store, file, rappels } = await monter();
    serveur.panne = new Error("réseau coupé");
    const r = await file.modifier([{ id: "A", champs: { x: 5 } }, { id: "B", champs: { x: 6 } }]);
    expect(r.every((x) => !x.ok)).toBe(true);
    expect([store.objet("A")!.x, store.objet("B")!.x]).toEqual([0, 0]);
    expect(rappels.erreur).toHaveBeenCalledWith("réseau coupé");
    // la file n'est pas bloquée par l'échec
    expect((await file.modifier([{ id: "A", champs: { x: 7 } }]))[0]!.ok).toBe(true);
  });

  it("lot : un conflit n'empêche pas les autres cartes d'être enregistrées", async () => {
    const { serveur, store, file } = await monter();
    serveur.ailleurs("A", { x: 999 });
    const r = await file.modifier([{ id: "A", champs: { x: 1 } }, { id: "B", champs: { x: 2 } }]);
    expect(r.find((x) => x.id === "B")!.ok).toBe(true);
    expect(r.find((x) => x.id === "A")!.ok).toBe(false);
    expect([store.objet("A")!.x, store.objet("B")!.x]).toEqual([999, 2]);
  });

  it("suppression versionnée : optimiste, puis confirmée avec les relations", async () => {
    const { serveur, store, file } = await monter();
    const p = file.supprimer(["A"]);
    expect(store.lire().objets.map((o) => o.id)).toEqual(["B"]);
    expect(await p).toBe(true);
    expect(serveur.objets.has("A")).toBe(false);
    expect(store.lire().liens).toEqual([]);
    expect(store.enAttente()).toBe(0);
  });

  it("suppression d'une carte modifiée ailleurs : refusée, la carte revient dans sa dernière version", async () => {
    const { serveur, store, file, rappels } = await monter();
    serveur.ailleurs("A", { contenu: "réécrit ailleurs" });
    expect(await file.supprimer(["A"])).toBe(false);
    expect(serveur.objets.has("A")).toBe(true);
    expect(store.objet("A")).toMatchObject({ contenu: "réécrit ailleurs", version: 2 });
    expect(rappels.conflit).toHaveBeenCalledWith(["A"]);
    expect(await file.supprimer(["A"])).toBe(true);           // en connaissance de cause : accepté
  });

  it("restauration : la carte est relue avec sa nouvelle version", async () => {
    const { serveur, store, file } = await monter();
    await file.supprimer(["A"]);
    expect(await file.restaurer(["A"])).toBe(true);
    expect(store.objet("A")).toMatchObject({ id: "A", version: 3 });
    expect(serveur.demandes.at(-1)).toEqual({ objets: ["A"] });
  });

  it("relation : renommage versionné ; conflit = retour arrière et relecture de la relation", async () => {
    const { serveur, store, file, rappels } = await monter();
    expect(await file.modifierLien("L1", { libelle: "alimente" })).toBe(true);
    expect(store.lienServeur("L1")).toMatchObject({ libelle: "alimente", version: 2 });
    serveur.liens.set("L1", { ...serveur.liens.get("L1")!, libelle: "renommé ailleurs", version: 3 });
    const p = file.modifierLien("L1", { libelle: "mon nom" });
    expect(store.lire().liens[0]!.libelle).toBe("mon nom");
    expect(await p).toBe(false);
    expect(store.lire().liens[0]).toMatchObject({ libelle: "renommé ailleurs", version: 3 });
    expect(rappels.conflit).toHaveBeenCalledWith(["L1"]);
  });

  it("relation : suppression puis restauration (annuler)", async () => {
    const { serveur, store, file } = await monter();
    expect(await file.modifierLien("L1", { supprime: true })).toBe(true);
    expect(store.lire().liens).toEqual([]);
    expect(serveur.liensSupprimes.has("L1")).toBe(true);             // le serveur la garde (suppression douce)
    expect(await file.modifierLien("L1", { supprime: false })).toBe(true);
    expect(store.lire().liens.map((l) => [l.id, l.version])).toEqual([["L1", 3]]);
  });

  it("annuler aussitôt (avant la réponse du serveur) : la restauration attend son tour et la carte revient", async () => {
    const { serveur, store, file } = await monter();
    const suppression = file.supprimer(["A"]);       // Suppr…
    const restauration = file.restaurer(["A"]);      // …puis Ctrl+Z dans la foulée
    const encore = file.supprimer(["A"]);            // …puis Ctrl+Maj+Z
    expect(await suppression).toBe(true);
    expect(await restauration).toBe(true);
    expect(await encore).toBe(true);
    expect(serveur.objets.has("A")).toBe(false);
    expect(store.objet("A")).toBeUndefined();
    expect(await file.restaurer(["A"])).toBe(true);
    expect(store.objet("A")).toMatchObject({ id: "A", version: 5 });
    expect(store.enAttente()).toBe(0);
  });

  it("relation supprimée puis rétablie aussitôt : elle revient", async () => {
    const { store, file } = await monter();
    const suppression = file.modifierLien("L1", { supprime: true });
    const retour = file.modifierLien("L1", { supprime: false });
    expect(await suppression).toBe(true);
    expect(await retour).toBe(true);
    expect(store.lire().liens.map((l) => l.id)).toEqual(["L1"]);
    expect(store.enAttente()).toBe(0);
  });

  it("objet inconnu : aucun envoi", async () => {
    const { serveur, file } = await monter();
    expect(await file.modifier([{ id: "ZZ", champs: { x: 1 } }])).toEqual([{ id: "ZZ", ok: false, erreur: "objet inconnu" }]);
    expect(serveur.appels.modifier).toBe(0);
  });
});
