// Annuler / rétablir : pile de commandes inverses, seule puis branchée sur la file d'écritures optimistes réelle
// (faux serveur à versions de src/donnees/essais.ts) : conflits 409, restauration des relations, gestes groupés.
import { describe, expect, it } from "vitest";
import { FileEcritures } from "../donnees/ecritures";
import { FauxServeur, carte, lien } from "../donnees/essais";
import { StoreBoard } from "../donnees/store";
import { Historique, type Entree } from "./historique";

const entree = (trace: string[], nom: string, ok: boolean | void = undefined): Entree => ({
  libelle: nom,
  annuler: async () => { trace.push(`-${nom}`); return ok; },
  refaire: async () => { trace.push(`+${nom}`); return ok; },
});
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("historique", () => {
  it("annule et rétablit dans l'ordre ; un nouveau geste vide le « rétablir »", async () => {
    const t: string[] = [];
    const h = new Historique();
    h.ajouter(entree(t, "a"));
    h.ajouter(entree(t, "b"));
    expect(h.etat()).toEqual({ annuler: "b", refaire: null });
    expect(await h.annuler()).toMatchObject({ libelle: "b", ok: true });
    expect(await h.annuler()).toMatchObject({ libelle: "a", ok: true });
    expect(await h.annuler()).toBeNull();
    expect(await h.refaire()).toMatchObject({ libelle: "a" });
    h.ajouter(entree(t, "c"));
    expect(await h.refaire()).toBeNull();
    expect(t).toEqual(["-b", "-a", "+a"]);
  });

  it("dix Ctrl+Z rapides s'exécutent un par un, jamais entrelacés", async () => {
    const t: string[] = [];
    const h = new Historique();
    for (const nom of ["a", "b", "c"]) {
      h.ajouter({ libelle: nom, refaire: async () => undefined, annuler: async () => {
        t.push(`début ${nom}`);
        await pause(nom === "c" ? 15 : 1);
        t.push(`fin ${nom}`);
      } });
    }
    await Promise.all([h.annuler(), h.annuler(), h.annuler()]);
    expect(t).toEqual(["début c", "fin c", "début b", "fin b", "début a", "fin a"]);
  });

  it("une annulation refusée est abandonnée, signalée, et ne bloque pas les suivantes", async () => {
    const t: string[] = [];
    const h = new Historique();
    h.ajouter(entree(t, "a"));
    h.ajouter(entree(t, "conflit", false));
    expect(await h.annuler()).toEqual({ libelle: "conflit", ok: false, commande: undefined });
    expect(h.etat()).toEqual({ annuler: "a", refaire: null });  // ni rejouable, ni rétablissable
    expect(await h.annuler()).toMatchObject({ libelle: "a", ok: true });
    const casse = new Historique();
    casse.ajouter({ libelle: "x", annuler: async () => { throw new Error("réseau"); }, refaire: async () => undefined });
    expect(await casse.annuler()).toMatchObject({ ok: false });
  });

  it("un geste groupé = une entrée, annulée en ordre inverse", async () => {
    const t: string[] = [];
    const h = new Historique();
    h.ajouter(entree(t, "avant"));
    const r = await h.grouper("Duplication", async () => {
      h.ajouter(entree(t, "1"));
      await pause(1);
      h.ajouter(entree(t, "2"));
      const refusee = entree(t, "refusée");
      h.ajouter(refusee);
      h.retirer(refusee);
      return 42;
    });
    expect(r).toBe(42);
    expect(h.etat().annuler).toBe("Duplication");
    await h.annuler();
    await h.refaire();
    expect(t).toEqual(["-2", "-1", "+1", "+2"]);
    await h.annuler();
    expect(h.etat().annuler).toBe("avant");
  });

  it("un groupe vide ne laisse aucune entrée ; la pile est bornée", async () => {
    const h = new Historique(3);
    await h.grouper("rien", async () => undefined);
    expect(h.etat().annuler).toBeNull();
    for (const n of ["a", "b", "c", "d"]) h.ajouter(entree([], n));
    const vus: string[] = [];
    for (let r = await h.annuler(); r; r = await h.annuler()) vus.push(r.libelle);
    expect(vus).toEqual(["d", "c", "b"]);
  });

  it("prévient ses abonnés (boutons annuler / rétablir)", async () => {
    const h = new Historique();
    let n = 0;
    const fin = h.abonner(() => { n += 1; });
    h.ajouter(entree([], "a"));
    await h.annuler();
    fin();
    h.ajouter(entree([], "b"));
    expect(n).toBe(2);
  });
});

describe("historique branché sur la file d'écritures optimistes", () => {
  function monter() {
    const serveur = new FauxServeur([carte("A", { x: 0, y: 0 }), carte("B", { x: 100, y: 0 })], [lien("L", "A", "B")]);
    const store = new StoreBoard();
    store.remplacer({ espace: "accueil", objets: [...serveur.objets.values()].map((o) => structuredClone(o)), liens: [...serveur.liens.values()].map((l) => structuredClone(l)) });
    const conflits: string[][] = [];
    const file = new FileEcritures(serveur, store, { conflit: (ids) => conflits.push(ids), erreur: () => undefined });
    const h = new Historique();
    /** Le service `modifier` du Board, réduit à l'essentiel : entrée posée au moment du geste, inverse lu dans le store. */
    const deplacer = async (id: string, x: number) => {
      const avant = store.objet(id)!.x;
      const jouer = async (v: number) => (await file.modifier([{ id, champs: { x: v } }])).some((r) => r.ok);
      const e = { libelle: "Déplacement", annuler: () => jouer(avant), refaire: () => jouer(x) };
      h.ajouter(e);
      if (!(await jouer(x))) h.retirer(e);
    };
    const supprimer = async (ids: string[]) => {
      h.ajouter({ libelle: "Suppression", annuler: () => file.restaurer(ids), refaire: () => file.supprimer(ids) });
      await file.supprimer(ids);
    };
    return { serveur, store, file, h, deplacer, supprimer, conflits };
  }

  it("Ctrl+Z fonctionne avant même la réponse du serveur, dans l'ordre de la file", async () => {
    const { serveur, store, h, deplacer } = monter();
    const geste = deplacer("A", 500);   // pas attendu : l'utilisateur tape Ctrl+Z tout de suite
    expect(store.objet("A")!.x).toBe(500);
    const annulation = h.annuler();
    await Promise.all([geste, annulation]);
    expect(serveur.objets.get("A")!.x).toBe(0);
    expect(store.objet("A")!.x).toBe(0);
    await h.refaire();
    expect(serveur.objets.get("A")!.x).toBe(500);
  });

  it("supprimer puis annuler restaure la carte ET ses relations", async () => {
    const { serveur, store, h, supprimer } = monter();
    await supprimer(["A"]);
    expect(store.lire().objets.map((o) => o.id)).toEqual(["B"]);
    expect(store.lire().liens).toEqual([]);
    expect((await h.annuler())?.ok).toBe(true);
    expect(store.lire().objets.map((o) => o.id).sort()).toEqual(["A", "B"]);
    expect(store.lire().liens.map((l) => l.id)).toEqual(["L"]);
    expect(serveur.liens.has("L")).toBe(true);
  });

  it("annulation en conflit (409) : refusée proprement, l'état du serveur est gardé, la pile continue", async () => {
    const { serveur, store, h, deplacer, conflits } = monter();
    await deplacer("B", 300);
    await deplacer("A", 500);
    serveur.ailleurs("A", { x: 900 });   // quelqu'un d'autre déplace A entre-temps
    const r = await h.annuler();
    expect(r).toMatchObject({ libelle: "Déplacement", ok: false });
    expect(conflits).toEqual([["A"]]);
    expect(store.objet("A")!.x).toBe(900);       // rien n'est écrasé
    expect(serveur.objets.get("A")!.x).toBe(900);
    expect((await h.annuler())?.ok).toBe(true);  // l'entrée suivante (B) s'annule normalement
    expect(serveur.objets.get("B")!.x).toBe(100);
  });
});
