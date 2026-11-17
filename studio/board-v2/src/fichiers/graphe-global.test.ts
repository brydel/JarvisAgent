import { describe, expect, test } from "vitest";
import { SourceDemo } from "../api";
import { fixtureDemo } from "../demo/fixture";
import { voirDemo } from "../references/demo";
import { construire, sousGraphe } from "./graphe";
import { grapheGlobalDemo, sourceProjetDemo } from "./global-demo";
import { fusionnerGlobal, rafraichirLotsGlobaux } from "./useGrapheGlobal";
import type { SessionGraphe } from "./global-donnees";

const session = (id: string, projet: string, objet_ids: string[]): SessionGraphe => ({
  id, titre: id, projet, projets: [projet], origine: "runtime", statut: "terminée",
  debut: 1, fin: 2, objet_ids, mission_ids: [], evenement_ids: [],
});

describe("sessions du graphe global", () => {
  test("plusieurs projets et sessions conservent les hubs partagés et les preuves", async () => {
    const source = new SourceDemo();
    const donnees = await grapheGlobalDemo(source);
    const reference = await voirDemo("RF-demo00000001");
    const graphe = construire({ espace: "global", objets: donnees.objets, liens: donnees.liens },
      donnees.entrees, [reference], donnees.sessions);
    expect(donnees.projets).toHaveLength(2);
    expect(graphe.groupes!.filter((g) => g.nature === "session")).toHaveLength(4);
    expect(graphe.entites.get("BO-demo-note")).toMatchObject({
      sessionId: "AT-demo-integration-echec", projet: source.espace,
    });
    expect(graphe.entites.get("journal:demo-105")?.sessionId).toBe("AT-demo-integration-echec");
    expect(graphe.entites.get("journal:demo-106")?.sessionId).toBe("AT-demo-integration-reprise");
    expect(graphe.entites.get("BO-demo-mission")?.sessionId).toBeUndefined();
    expect(graphe.entites.get("BO-demo-mission")?.sessionIds).toEqual([
      "AT-demo-integration-echec", "AT-demo-integration-reprise",
    ]);
    expect(graphe.entites.get(reference.id)?.sessionId).toBeUndefined();
    expect(graphe.entites.get(reference.id)?.sessionIds).toEqual([
      "AR-demo-campagne-redaction", "AR-demo-campagne-relecture", "AT-demo-integration-echec",
    ]);
    expect(graphe.racines.filter((e) => e.id === reference.id)).toHaveLength(1);
    for (const groupe of graphe.groupes!) {
      expect(groupe.ids).not.toContain(reference.id);
      expect(groupe.ids).not.toContain("BO-demo-mission");
    }
    const original = await source.charger();
    expect(original.objets.find((o) => o.id === "BO-demo-note")?.meta.reference_id).toBeUndefined();
  });

  test("un favori du journal conserve son identité historique et sa session exacte", async () => {
    const donnees = await grapheGlobalDemo(new SourceDemo());
    const entree = { ...donnees.entrees[0]!, id: "memoire:123" };
    const session = { ...donnees.sessions[1]!, evenement_ids: [entree.id] };
    const graphe = construire({ espace: "global", objets: donnees.objets, liens: donnees.liens },
      [entree], [], [session]);
    const id = "journal:memoire:123";
    expect(graphe.entites.get(id)).toMatchObject({ sessionId: session.id, memoire: { id: entree.id } });
    expect(sousGraphe(graphe, graphe.racines, null, 1, false, true, id).ids).toContain(id);
  });

  test("les éléments historiques gardent leur projet et une attribution sans session explicite", () => {
    const board = fixtureDemo();
    const graphe = construire(board, [], [], []);
    expect(graphe.sessions).toEqual([]);
    expect(graphe.groupes).toEqual([expect.objectContaining({
      id: "hors-session:accueil", nature: "hors_session", titre: "Sans session · accueil",
    })]);
    expect(graphe.groupes![0]!.ids).toHaveLength(board.objets.length);
    expect([...graphe.entites.values()].every((e) => !e.sessionId)).toBe(true);
  });

  test("un fichier commun relie deux sessions de projets différents sans dupliquer le fichier source", () => {
    const board = fixtureDemo();
    const image = board.objets.find((o) => o.id === "BO-demo-image")!;
    const autre = { ...image, id: "BO-demo-autre-image", espace: "Campagne" };
    const sessions = [session("AR-a", image.espace, [image.id]), session("AR-b", autre.espace, [autre.id])];
    const graphe = construire({ ...board, objets: [image, autre], liens: [] }, [], [], sessions);
    expect(graphe.relations).toEqual([expect.objectContaining({
      source: autre.id, cible: image.id, style: "fichier",
    })]);
    expect(graphe.groupes!.filter((g) => g.nature === "session").map((g) => g.ids)).toEqual([[image.id], [autre.id]]);
  });

  test("la projection représente les sessions avant de détailler une seule grande session", () => {
    const note = fixtureDemo().objets.find((o) => o.type === "note")!;
    const objets = Array.from({ length: 180 }, (_, i) => ({ ...note, id: "BO-global-" + i, contenu: "", espace: "Projet" }));
    const sessions = Array.from({ length: 9 }, (_, i) => session("AR-session-" + i, "Projet",
      objets.slice(i * 20, (i + 1) * 20).map((o) => o.id)));
    const graphe = construire({ espace: "global", objets, liens: [] }, [], [], sessions);
    const projection = sousGraphe(graphe, graphe.racines, null, 1, false, true);
    expect(projection.ids.length).toBeLessThanOrEqual(64);
    for (const s of sessions) expect(projection.ids.some((id) => graphe.entites.get(id)?.sessionId === s.id)).toBe(true);
  });

  test("les lots fusionnent appartenances et compteurs sans perdre la pagination", async () => {
    const premier = await grapheGlobalDemo(new SourceDemo());
    const s = premier.sessions[0]!;
    const supplement = {
      ...premier, page: 2, objets: [premier.objets[0]!], liens: [], entrees: [],
      sessions: [{ ...s, objet_ids: ["BO-cible-tardive"], evenement_ids: ["memoire:456"] }],
      suivant: 3,
    };
    const fusion = fusionnerGlobal(premier, supplement);
    expect(fusion.objets).toHaveLength(premier.objets.length);
    expect(fusion.sessions).toHaveLength(premier.sessions.length);
    expect(fusion.sessions[0]!.objet_ids).toEqual(expect.arrayContaining([...s.objet_ids, "BO-cible-tardive"]));
    expect(fusion.sessions[0]!.evenement_ids).toContain("memoire:456");
    expect(fusion.couverture.objets.charges).toBe(fusion.objets.length);
    expect(fusion.suivant).toBe(3);
    const cible = fusionnerGlobal(fusion, { ...supplement, page: 1, suivant: 2 }, true);
    expect(cible.page).toBe(2);
    expect(cible.suivant).toBe(3);
  });

  test("une actualisation reconstruit tous les lots chargés, retire les suppressions et borne ses lectures", async () => {
    const ancienne = await grapheGlobalDemo(new SourceDemo());
    const controle = new AbortController();
    const retires = ancienne.objets[0]!.id;
    const objets = ancienne.objets.slice(1, 5);
    let actives = 0, maximum = 0;
    const lectures: number[] = [];
    const actuelle = await rafraichirLotsGlobaux(async (page) => {
      lectures.push(page);
      actives++;
      maximum = Math.max(maximum, actives);
      await new Promise((resolve) => setTimeout(resolve, 2));
      actives--;
      const objet = objets[page - 1]!;
      return { ...ancienne, page, suivant: page === 4 ? 5 : page + 1, objets: [objet], liens: [], entrees: [],
        sessions: [{ ...ancienne.sessions[0]!, objet_ids: [objet.id], evenement_ids: [] }] };
    }, 4, controle.signal);
    expect(lectures).toEqual([1, 2, 3, 4]);
    expect(maximum).toBe(2);
    expect(actuelle.page).toBe(4);
    expect(actuelle.suivant).toBe(5);
    expect(actuelle.objets.map((o) => o.id)).toEqual(objets.map((o) => o.id));
    expect(actuelle.objets.some((o) => o.id === retires)).toBe(false);
    expect(actuelle.sessions[0]!.objet_ids).toEqual(objets.map((o) => o.id));
    expect(actuelle.couverture.objets.charges).toBe(4);
    expect(actuelle.cle_disposition).toBe(ancienne.cle_disposition);
  });

  test("une génération annulée ne lance pas les lots suivants", async () => {
    const donnees = await grapheGlobalDemo(new SourceDemo());
    const controle = new AbortController();
    let liberer!: () => void;
    const attente = new Promise<void>((resolve) => { liberer = resolve; });
    const lectures: number[] = [];
    const rafraichissement = rafraichirLotsGlobaux(async (page) => {
      lectures.push(page);
      await attente;
      return { ...donnees, page };
    }, 8, controle.signal);
    controle.abort();
    liberer();
    await expect(rafraichissement).rejects.toMatchObject({ name: "AbortError" });
    expect(lectures).toEqual([1, 2]);
  });

  test("une lecture échouée ne publie pas de remplacement partiel des données précédentes", async () => {
    const ancienne = await grapheGlobalDemo(new SourceDemo());
    const controle = new AbortController();
    const original = structuredClone(ancienne);
    const rafraichissement = rafraichirLotsGlobaux(async (page) => {
      if (page === 2) throw new Error("Lecture temporairement indisponible");
      await new Promise((resolve) => setTimeout(resolve, 2));
      return { ...ancienne, page, objets: [] };
    }, 3, controle.signal).catch((erreur) => { controle.abort(); throw erreur; });
    await expect(rafraichissement).rejects.toThrow("Lecture temporairement indisponible");
    expect(ancienne).toEqual(original);
  });

  test("une note du second projet de démonstration reste éditable en mémoire", async () => {
    const source = new SourceDemo();
    const initial = await grapheGlobalDemo(source);
    const note = initial.objets.find((o) => o.id === "BO-demo-campagne-note")!;
    const projet = sourceProjetDemo(source, note.espace);
    await projet.modifier([{ id: note.id, champs: { contenu: "Message de lancement revu." } }]);
    const suivant = await grapheGlobalDemo(source);
    expect(suivant.objets.find((o) => o.id === note.id)?.contenu).toBe("Message de lancement revu.");
    expect(sourceProjetDemo(source, source.espace)).toBe(source);
  });
});
