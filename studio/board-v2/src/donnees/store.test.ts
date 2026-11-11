import { describe, expect, it, vi } from "vitest";
import { carte, lien } from "./essais";
import { StoreBoard, appliquerChamps } from "./store";

const etat = (objets = [carte("A"), carte("B", { z: 2 })], liens = [lien("L1", "A", "B")]) => ({ espace: "accueil", objets, liens });
const absents = { objets: [], liens: [] };

describe("store normalisé", () => {
  it("range objets et liens par id et rend un instantané trié, stable tant que rien ne change", () => {
    const s = new StoreBoard();
    s.remplacer(etat([carte("B", { z: 2 }), carte("A")]));
    const i = s.lire();
    expect(i.objets.map((o) => o.id)).toEqual(["A", "B"]);
    expect(i.liens.map((l) => l.id)).toEqual(["L1"]);
    expect(s.lire()).toBe(i);
  });

  it("un delta ne change que l'objet touché : les autres gardent leur référence (pas de re-rendu)", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const avant = s.lire();
    const ecoute = vi.fn();
    s.abonner(ecoute);
    const change = s.appliquerDelta({ espace: "accueil", objets: [carte("A", { x: 50, version: 2 })], liens: [lien("L1", "A", "B")], absents }, { objets: ["A"] });
    expect(change).toBe(true);
    expect(ecoute).toHaveBeenCalledTimes(1);
    const apres = s.lire();
    expect(apres.objets[0]!.x).toBe(50);
    expect(apres.objets[1]).toBe(avant.objets[1]);
  });

  it("un delta identique à l'état connu ne publie rien", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const ecoute = vi.fn();
    s.abonner(ecoute);
    expect(s.appliquerDelta({ espace: "accueil", objets: [carte("A")], liens: [lien("L1", "A", "B")], absents }, { objets: ["A"] })).toBe(false);
    expect(ecoute).not.toHaveBeenCalled();
  });

  it("une réponse plus ancienne que la version connue est ignorée", () => {
    const s = new StoreBoard();
    s.remplacer(etat([carte("A", { version: 5, x: 500 })], []));
    s.appliquerDelta({ espace: "accueil", objets: [carte("A", { version: 4, x: 1 })], liens: [], absents }, { objets: ["A"] });
    expect(s.objet("A")!.x).toBe(500);
    s.remplacer(etat([carte("A", { version: 3, x: 2 })], []));
    expect(s.objet("A")!.x).toBe(500);
  });

  it("objet absent d'une lecture ciblée : retiré ; la réponse fait foi pour les relations de l'objet demandé", () => {
    const s = new StoreBoard();
    s.remplacer(etat([carte("A"), carte("B"), carte("C")], [lien("L1", "A", "B"), lien("L2", "B", "C")]));
    // B relu : il n'a plus que L2 → L1 disparaît
    s.appliquerDelta({ espace: "accueil", objets: [carte("B")], liens: [lien("L2", "B", "C")], absents }, { objets: ["B"] });
    expect(s.lire().liens.map((l) => l.id)).toEqual(["L2"]);
    s.appliquerDelta({ espace: "accueil", objets: [], liens: [], absents: { objets: ["C"], liens: [] } }, { objets: ["C"] });
    expect(s.lire().objets.map((o) => o.id)).toEqual(["A", "B"]);
    expect(s.lire().liens).toEqual([]);
  });

  it("une lecture lancée avant un retrait ne ressuscite pas la carte retirée", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const jalon = s.jalon();           // la lecture part…
    s.retirerObjets(["A"]);            // …puis la suppression est confirmée
    s.appliquerDelta({ espace: "accueil", objets: [carte("A")], liens: [lien("L1", "A", "B")], absents }, { objets: ["A"] }, jalon);
    expect(s.objet("A")).toBeUndefined();
    expect(s.lire().liens).toEqual([]);
    s.remplacer(etat(), jalon);        // même garde pour un chargement complet parti trop tôt
    expect(s.objet("A")).toBeUndefined();
    s.remplacer(etat());               // une lecture partie APRÈS le retrait fait de nouveau foi (restauration)
    expect(s.objet("A")).toBeDefined();
  });

  it("surcouche optimiste : visible tout de suite, retirée = retour à l'état serveur", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const cle = s.ajouterSurcouche({ sorte: "objet", id: "A", champs: { x: 300, verrouille: true } });
    expect(s.objet("A")).toMatchObject({ x: 300, verrouille: 1, version: 1 });
    expect(s.objetServeur("A")!.x).toBe(0);
    // une mise à jour distante d'un AUTRE champ arrive : le geste en cours reste appliqué par-dessus
    s.appliquerDelta({ espace: "accueil", objets: [carte("A", { priorite: "P1", version: 2 })], liens: [lien("L1", "A", "B")], absents }, { objets: ["A"] });
    expect(s.objet("A")).toMatchObject({ x: 300, priorite: "P1" });
    s.retirerSurcouche(cle);
    expect(s.objet("A")).toMatchObject({ x: 0, priorite: "P1", verrouille: 0 });
  });

  it("confirmation : les champs et la version entrent dans l'état serveur", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const cle = s.ajouterSurcouche({ sorte: "objet", id: "A", champs: { x: 300 } });
    s.confirmerObjet("A", { x: 300 }, 2);
    s.retirerSurcouche(cle);
    expect(s.objetServeur("A")).toMatchObject({ x: 300, version: 2 });
    expect(s.enAttente()).toBe(0);
  });

  it("suppression optimiste : cartes et relations masquées, puis rendues si l'écriture est annulée", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const cle = s.ajouterSurcouche({ sorte: "suppression", ids: ["A"] });
    expect(s.lire().objets.map((o) => o.id)).toEqual(["B"]);
    expect(s.lire().liens).toEqual([]);
    expect(s.objet("A")).toBeUndefined();
    s.retirerSurcouche(cle);
    expect(s.lire().objets).toHaveLength(2);
    expect(s.lire().liens).toHaveLength(1);
  });

  it("relation : renommage et suppression optimistes", () => {
    const s = new StoreBoard();
    s.remplacer(etat());
    const c1 = s.ajouterSurcouche({ sorte: "lien", id: "L1", champs: { libelle: "alimente" } });
    expect(s.lire().liens[0]!.libelle).toBe("alimente");
    s.confirmerLien("L1", { libelle: "alimente" }, 2);
    s.retirerSurcouche(c1);
    expect(s.lienServeur("L1")).toMatchObject({ libelle: "alimente", version: 2 });
    const c2 = s.ajouterSurcouche({ sorte: "lien", id: "L1", champs: { supprime: true } });
    expect(s.lire().liens).toEqual([]);
    s.retirerSurcouche(c2);
    expect(s.lire().liens).toHaveLength(1);
  });

  it("meta : les clés du chef survivent à une écriture du client, comme sur le serveur", () => {
    const o = carte("A", { meta: { titre: "t", jarvis_resume: "résumé du chef", propositions: [] } });
    const m = appliquerChamps(o, { meta: { titre: "nouveau" } }).meta;
    expect(m).toEqual({ titre: "nouveau", jarvis_resume: "résumé du chef", propositions: [] });
  });

  it("retrouve les cartes d'une mission", () => {
    const s = new StoreBoard();
    s.remplacer(etat([carte("A", { mission_id: "MI-1" }), carte("B")], []));
    expect(s.objetsDeMission("MI-1")).toEqual(["A"]);
  });
});
