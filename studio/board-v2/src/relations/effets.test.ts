// Effets des relations côté interface : lecture d'une flèche et d'une carte à partir du résumé du serveur, refus
// local des boucles, calcul de la démo, et relecture des cartes touchées quand une relation change.
import { describe, expect, it, vi } from "vitest";
import { SourceDemo } from "../api";
import { FileEcritures } from "../donnees/ecritures";
import { FauxServeur, carte, lien } from "../donnees/essais";
import { StoreBoard } from "../donnees/store";
import { planifier } from "../donnees/synchro";
import type { DeltaBoard, Evenement, ObjetBoard } from "../types";
import { EFFETS, calculerRelations, creeraitBoucle, etiquetteParlante, libelleUtile, lignesRelations, lireFleche, phraseBlocage, phraseConcrete } from "./effets";

const mission = (id: string, statut: string, extra: Partial<ObjetBoard> = {}) => carte(id, {
  type: "mission", mission_id: `MI-${id}`, meta: { titre: `Mission ${id}` },
  mission: { id: `MI-${id}`, objectif: `Mission ${id}`, statut, cree: 1, taches: [], faites: 0, total: 1, progression: 0, agents: [], approbations_en_attente: 0 }, ...extra,
});

/** Les objets tels que le serveur les rendrait : avec leur résumé calculé. */
function avecResume(objets: ObjetBoard[], liens: ReturnType<typeof lien>[]): Map<string, ObjetBoard> {
  const r = calculerRelations(objets, liens);
  return new Map(objets.map((o) => [o.id, r.has(o.id) ? { ...o, relations: r.get(o.id)! } : o]));
}

describe("ce que chaque type de relation change", () => {
  it("une phrase par type ; les types sans effet le disent", () => {
    expect(Object.keys(EFFETS).sort()).toEqual(["alimente", "defaut", "depend", "inspire", "utilise"]);
    for (const e of Object.values(EFFETS)) expect(e.phrase).toMatch(/^[A-Z].{30,}\.$/);
    expect(Object.entries(EFFETS).filter(([, e]) => e.effet).map(([k]) => k).sort()).toEqual(["alimente", "depend", "inspire"]);
    expect(EFFETS.defaut.phrase).toMatch(/Simple repère/);
    expect(EFFETS.utilise.phrase).toMatch(/Simple repère/);
    expect(phraseConcrete("depend", "Synthèse", "Collecte")).toBe("« Synthèse » sera bloquée tant que « Collecte » n'est pas terminée : son lancement sera refusé.");
    expect(phraseConcrete("defaut", "A", "B")).toBe(EFFETS.defaut.phrase);
  });
});

describe("calcul du résumé (mode démo) : mêmes règles que le serveur", () => {
  const objets = [mission("A", "OPEN"), mission("B", "OPEN"), mission("F", "SUCCEEDED", { artefacts: [{ id: "AR", fournisseur: "claude", factice: 0, revue: "acceptee", contenu: "x" }] }),
    carte("N", { meta: { titre: "Note" } }), carte("R", { meta: { titre: "Charte", reference_id: "RF-1" } }), carte("S", { type: "adhesif" }),
    carte("T", { type: "tache", meta: { titre: "JAR-1", statut: "terminé", verdict: "corrections" } })];
  const liens = [lien("d1", "B", "A", { style: "depend" }), lien("d2", "B", "F", { style: "depend" }), lien("d3", "B", "N", { style: "depend" }),
    lien("d4", "B", "T", { style: "depend" }), lien("a1", "F", "N", { style: "alimente" }), lien("a2", "A", "N", { style: "alimente" }),
    lien("a3", "S", "N", { style: "alimente" }), lien("i1", "R", "N", { style: "inspire" }), lien("i2", "A", "N", { style: "inspire" }),
    lien("u1", "A", "B", { style: "utilise" }), lien("x1", "A", "ABSENT", { style: "depend" })];
  const r = calculerRelations(objets, liens);

  it("bloquée par les dépendances suivies et non terminées seulement", () => {
    const b = r.get("B")!;
    expect(b.bloquee).toBe(true);
    expect(b.bloquee_par.map((x) => [x.id, x.etat])).toEqual([["A", "en cours"], ["T", "corrections demandées"]]);
    expect(b.dependances.map((x) => [x.id, x.suivi, x.termine])).toEqual([["A", true, false], ["F", true, true], ["N", false, false], ["T", true, false]]);
    expect(phraseBlocage(b)).toBe("Bloquée par « Mission A » (en cours), « JAR-1 » (corrections demandées)");
    expect(phraseBlocage(r.get("N"))).toBeNull();
    expect(phraseBlocage(undefined)).toBeNull();
  });

  it("débloque : seulement depuis un travail suivi ; alimente et inspire : ce qui sera joint", () => {
    expect(r.get("A")!.debloque).toEqual([{ id: "B", titre: "Mission B", type: "mission", lien_id: "d1", attend: true }]);
    expect(r.get("F")!.debloque[0]).toMatchObject({ id: "B", attend: false });
    const n = r.get("N")!;
    expect(n.debloque).toEqual([]);  // une note n'est pas un travail : elle ne « débloque » rien
    expect(n.alimentee_par.map((x) => [x.id, x.sorte])).toEqual([["F", "livrable"], ["A", "en_attente"], ["S", "aucun"]]);
    expect(n.inspiree_par.map((x) => [x.id, x.effet, x.reference_id])).toEqual([["R", true, "RF-1"], ["A", false, null]]);
    expect(r.has("ABSENT")).toBe(false);
    expect(r.get("A")!.dependances).toEqual([]);  // relation vers une carte absente : sans effet
  });

  it("les lignes affichées sur la carte viennent toutes du résumé", () => {
    expect(lignesRelations(r.get("B")).map((l) => `${l.verbe} ${l.carte.titre} (${l.precision})`)).toEqual([
      "Bloquée par Mission A (en cours)", "Bloquée par JAR-1 (corrections demandées)"]);
    // sur la carte : seulement ce qui a un effet en ce moment ; le reste (rien à joindre, dépendance levée) est dit par la flèche
    expect(lignesRelations(r.get("N")).map((l) => [l.sorte, l.verbe, l.carte.id, l.precision])).toEqual([
      ["alimentee", "Alimentée par", "F", "livrable"], ["citee", "Cite", "R", "référence"]]);
    expect(lignesRelations(r.get("N"), true).map((l) => [l.carte.id, l.precision])).toEqual([["F", "livrable"], ["A", "rien encore"], ["S", "sans effet"], ["R", "référence"]]);
    expect(lignesRelations(r.get("A")).map((l) => [l.sorte, l.verbe, l.carte.id])).toEqual([["debloque", "Débloquera", "B"]]);
    expect(lignesRelations(r.get("F"))).toEqual([]);
    expect(lignesRelations(r.get("F"), true).map((l) => [l.sorte, l.verbe])).toEqual([["libere", "A débloqué"]]);
    expect(lignesRelations(undefined)).toEqual([]);
  });

  it("la flèche montre son effet du moment", () => {
    const o = avecResume(objets, liens);
    const lire = (id: string) => {
      const l = liens.find((x) => x.id === id)!;
      return lireFleche(l, o.get(l.source_id), o.get(l.cible_id));
    };
    expect(lire("d1")).toMatchObject({ etat: "bloquante", libelle: "bloque" });
    expect(lire("d1").detail).toContain("« Mission A » est en cours");
    expect(lire("d2")).toMatchObject({ etat: "debloquee", libelle: "débloquée" });
    expect(lire("d3")).toMatchObject({ etat: "non_suivie" });
    expect(lire("a1")).toMatchObject({ etat: "jointe", libelle: "alimente · livrable" });
    expect(lire("a2")).toMatchObject({ etat: "inerte", libelle: "alimente · rien encore" });
    expect(lire("a3")).toMatchObject({ etat: "inerte" });
    expect(lire("i1")).toMatchObject({ etat: "jointe", libelle: "inspire · citations" });
    expect(lire("i2")).toMatchObject({ etat: "inerte", libelle: "inspire (repère)" });
    expect(lire("u1")).toMatchObject({ etat: "neutre", libelle: "Utilisé par" });
    // résumé pas encore reçu du serveur : rien n'est affirmé
    expect(lireFleche(liens[0]!, objets[1], objets[0])).toMatchObject({ etat: "neutre", libelle: "Dépend de" });
    // l'étiquette reste visible seulement quand la flèche fait quelque chose ; le libellé de l'humain n'est pas une redite
    expect((["bloquante", "debloquee", "jointe", "inerte", "non_suivie", "neutre"] as const).map(etiquetteParlante)).toEqual([true, true, true, false, false, false]);
    expect(libelleUtile("Alimente", lire("a1"), "Alimente")).toBe("");
    expect(libelleUtile("livrable", lire("a1"), "Alimente")).toBe("");
    expect(libelleUtile("chiffres du T3", lire("a1"), "Alimente")).toBe("chiffres du T3");
    expect(libelleUtile("", lire("d1"), "Dépend de")).toBe("");
  });
});

describe("boucles de dépendances (pré-contrôle local)", () => {
  const liens = [lien("1", "A", "B", { style: "depend" }), lien("2", "B", "C", { style: "depend" }), lien("3", "C", "D", { style: "alimente" })];

  it("trajet de la boucle, ou null", () => {
    expect(creeraitBoucle(liens, "C", "A")).toEqual(["C", "A", "B", "C"]);
    expect(creeraitBoucle(liens, "B", "A")).toEqual(["B", "A", "B"]);
    expect(creeraitBoucle(liens, "A", "C")).toBeNull();           // raccourci dans le même sens
    expect(creeraitBoucle(liens, "D", "C")).toBeNull();           // « alimente » ne compte pas
    expect(creeraitBoucle(liens, "B", "A", "1")).toBeNull();      // la relation qu'on modifie est ignorée
  });

  it("la démo refuse comme le serveur : boucle, et lancement d'une carte bloquée", async () => {
    const demo = new SourceDemo();
    const a = await demo.creer({ type: "note", contenu: "A", x: 0, y: 0, largeur: 400, hauteur: 300, meta: { titre: "Alpha" } });
    const b = await demo.creer({ type: "note", contenu: "B", x: 0, y: 0, largeur: 400, hauteur: 300, meta: { titre: "Bravo" } });
    const ab = await demo.lier(a, b, "", "depend");
    await expect(demo.lier(b, a, "", "depend")).rejects.toThrow(/boucle \(« Bravo » → « Alpha » → « Bravo »\)/);
    const ba = await demo.lier(b, a, "", "inspire");
    await expect(demo.modifierLien(ba, { style: "depend" })).rejects.toThrow(/boucle/);
    await demo.modifierLien(ab, { style: "depend", libelle: "attend" });  // renommer une dépendance existante passe
    // une carte qui dépend d'une mission en cours ne se lance pas ; le résumé est servi avec les objets
    const etat = await demo.charger();
    const m = etat.objets.find((o) => o.type === "mission" && o.mission && o.mission.statut !== "SUCCEEDED");
    expect(m, "la démo contient une mission en cours").toBeTruthy();
    await demo.lier(a, m!.id, "", "depend");
    const lu = (await demo.lire({ objets: [a] })).objets[0]!;
    expect(lu.relations?.bloquee).toBe(true);
    await expect(demo.contextualiser(a)).rejects.toThrow(/bloquée par/);
    expect((await demo.lire({ objets: [b] })).objets[0]!.relations).toBeUndefined();  // « inspire » depuis une note : aucun effet
  });

  it("la démo suit une demande de relecture de bout en bout", async () => {
    const demo = new SourceDemo();
    const id = await demo.creer({ type: "note", contenu: "L", x: 0, y: 0, largeur: 400, hauteur: 300, meta: { livrable_de: "MI-x" } });
    const r = await demo.relecture(id, "demander");
    expect((await demo.relecture(id, "demander")).id).toBe(r.id);
    expect((await demo.lire({ objets: [id] })).objets[0]!.relecture).toMatchObject({ statut: "demandee" });
    expect(await demo.relecture(id, "rendre", { verdict: "corrections", avis: "à revoir" })).toMatchObject({ statut: "rendue", verdict: "corrections" });
    await expect(demo.relecture(id, "annuler")).rejects.toThrow(/aucune demande/);
  });
});

describe("le résumé des cartes touchées est relu quand une relation à effet change", () => {
  const ev = (type: string, donnees: Record<string, unknown>): Evenement => ({ seq: 1, type, mission_id: null, tache_id: null, ts: 0, donnees });

  /** Faux serveur qui calcule le résumé, comme le vrai. */
  class ServeurCalculant extends FauxServeur {
    override async lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard> {
      const d = await super.lire(demande);
      const r = calculerRelations([...this.objets.values()], [...this.liens.values()]);
      return { ...d, objets: d.objets.map((o) => (r.has(o.id) ? { ...o, relations: r.get(o.id)! } : o)) };
    }
  }

  async function monter() {
    const serveur = new ServeurCalculant([carte("N"), mission("M", "OPEN"), carte("X")], [lien("L1", "N", "M")]);
    const store = new StoreBoard();
    store.remplacer(await serveur.charger());
    const file = new FileEcritures(serveur, store, { conflit: vi.fn(), erreur: vi.fn() });
    return { serveur, store, file };
  }

  it("changer le type : les deux bouts sont relus, la carte devient bloquée puis libre", async () => {
    const { serveur, store, file } = await monter();
    expect(await file.modifierLien("L1", { style: "depend" })).toBe(true);
    expect(serveur.demandes.at(-1)).toEqual({ objets: ["N", "M"] });
    expect(store.objet("N")!.relations).toMatchObject({ bloquee: true, bloquee_par: [{ id: "M", etat: "en cours" }] });
    expect(store.objet("M")!.relations!.debloque).toMatchObject([{ id: "N", attend: true }]);
    expect(await file.modifierLien("L1", { supprime: true })).toBe(true);
    expect(store.objet("N")!.relations).toBeUndefined();
    expect(await file.modifierLien("L1", { supprime: false })).toBe(true);   // annuler : la relation ET son effet reviennent
    expect(store.objet("N")!.relations?.bloquee).toBe(true);
    const avant = serveur.appels.lire;
    expect(await file.modifierLien("L1", { libelle: "attend" })).toBe(true);  // renommer ne change aucun effet : aucune lecture
    expect(serveur.appels.lire).toBe(avant);
  });

  it("supprimer puis restaurer la carte dont une autre dépend : celle-ci est relue", async () => {
    const { serveur, store, file } = await monter();
    await file.modifierLien("L1", { style: "depend" });
    expect(store.voisinsParEffet(["M"])).toEqual(["N"]);
    expect(store.voisinsParEffet(["X"])).toEqual([]);
    expect(await file.supprimer(["M"])).toBe(true);
    expect(serveur.demandes.at(-1)).toEqual({ objets: ["N"] });
    expect(store.objet("N")!.relations).toBeUndefined();
  });

  it("événements des autres : relation typée, retirée, carte supprimée, déblocage", async () => {
    const { store, file } = await monter();
    // une relation « simple » ou « utilisé par » ne touche aucun résumé
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 2, style: "utilise", source_id: "N", cible_id: "M" }), store, "accueil"))
      .toMatchObject({ liens: ["L1"], objets: [] });
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 2, style: "depend", source_id: "N", cible_id: "M" }), store, "accueil"))
      .toMatchObject({ liens: ["L1"], objets: ["N", "M"] });
    expect(planifier(ev("board_lien", { lien_id: "L9", espace: "accueil", version: 1, style: "alimente", source_id: "X", cible_id: "N" }), store, "accueil"))
      .toMatchObject({ liens: ["L9"], objets: ["X", "N"] });
    // ancien serveur (sans les bouts dans l'événement) : ceux de la relation connue localement
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 2 }), store, "accueil").objets).toEqual(["N", "M"]);
    await file.modifierLien("L1", { style: "depend" });
    // notre propre écriture revient par le flux : déjà relue, rien à refaire
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 2, style: "depend", source_id: "N", cible_id: "M" }), store, "accueil"))
      .toMatchObject({ liens: [], objets: [] });
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 3, supprime: true, style: "depend", source_id: "N", cible_id: "M" }), store, "accueil"))
      .toMatchObject({ retirerLiens: ["L1"], objets: ["N", "M"] });
    expect(planifier(ev("board_supprime", { objets: ["M"], espace: "accueil" }), store, "accueil")).toMatchObject({ retirerObjets: ["M"], objets: ["N"] });
    expect(planifier(ev("board_debloquee", { objet_id: "N", espace: "accueil", grace_a: ["M"] }), store, "accueil").objets).toEqual(["N"]);
    expect(planifier(ev("board_dependance", { objet_id: "N", espace: "accueil", reste: 1 }), store, "accueil").objets).toEqual(["N"]);
    expect(planifier(ev("board_relecture", { objet_id: "X", espace: "accueil", statut: "demandee" }), store, "accueil").objets).toEqual(["X"]);
  });
});
