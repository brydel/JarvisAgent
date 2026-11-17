import { describe, expect, test } from "vitest";
import { fixtureDemo } from "../demo/fixture";
import { voirDemo } from "../references/demo";
import { journalDemo } from "./journal-demo";
import { construire, sousGraphe } from "./graphe";

describe("mémoire commune du graphe", () => {
  test("une carte et ses observations partagent une référence canonique et des preuves navigables", async () => {
    const source = await voirDemo("RF-demo00000001");
    const board = fixtureDemo();
    const image = board.objets.find((o) => o.id === "BO-demo-image")!;
    const liee = { ...image, meta: { ...image.meta, reference_id: source.id } };
    const graphe = construire({ ...board, objets: board.objets.map((o) => o.id === image.id ? liee : o) },
      [...journalDemo, journalDemo[0]!], [source, { ...source, observations: undefined }]);
    expect(graphe.racines.filter((e) => e.id === source.id)).toHaveLength(1);
    expect(graphe.entites.get(source.id)).toMatchObject({ titre: source.titre, reference: source.id, sourceRag: { id: source.id } });
    expect(graphe.adjacents.get(source.id)).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: image.id, cible: source.id, style: "source" }),
    ]));
    for (const observation of source.observations ?? []) {
      expect(graphe.entites.get(observation.id)).toMatchObject({ reference: source.id, observation });
      expect(graphe.adjacents.get(observation.id)).toEqual([
        expect.objectContaining({ source: source.id, cible: observation.id, style: "source" }),
      ]);
    }
    expect(graphe.journal).toHaveLength(journalDemo.length);
    expect(new Set(graphe.racines.map((e) => e.id)).size).toBe(graphe.racines.length);
    for (const relation of graphe.relations) {
      expect(graphe.entites.has(relation.source)).toBe(true);
      expect(graphe.entites.has(relation.cible)).toBe(true);
    }
    expect(image.meta.reference_id).toBeUndefined();
  });

  test("une preuve d’une autre référence et une source supprimée ne contaminent pas le graphe", async () => {
    const source = await voirDemo("RF-demo00000001");
    const board = { espace: "accueil", objets: [], liens: [] };
    const graphe = construire(board, [], [
      { ...source, id: "RF-autre" },
      { ...source, supprime: true },
    ]);
    expect(graphe.entites.has("RF-autre")).toBe(true);
    expect(graphe.entites.has(source.id)).toBe(false);
    expect(graphe.racines.some((e) => e.observation)).toBe(false);
    expect(graphe.relations).toEqual([]);
  });

  test("une mémoire volumineuse garde les familles représentées et la preuve demandée visible", async () => {
    const source = await voirDemo("RF-demo00000001");
    const board = fixtureDemo();
    const note = board.objets.find((o) => o.id === "BO-demo-note")!;
    const image = board.objets.find((o) => o.id === "BO-demo-image")!;
    const objets = Array.from({ length: 180 }, (_, i) => ({
      ...(i % 2 ? note : image), id: "BO-nombreux-" + i, asset_id: null, asset: null,
    }));
    const sources = Array.from({ length: 16 }, (_, i) => {
      const id = "RF-source-" + i;
      return { ...source, id, observations: Array.from({ length: 40 }, (_, j) => ({
        ...source.observations![0]!, id: "OB-source-" + i + "-" + j,
        preuve: { ...source.observations![0]!.preuve, reference_id: id },
      })) };
    });
    const graphe = construire({ ...board, objets, liens: [] }, journalDemo, sources);
    const cible = sources.at(-1)!.observations.at(-1)!.id;
    const projection = sousGraphe(graphe, graphe.racines, null, 1, false, true, cible);
    expect(projection.ids.length).toBeLessThanOrEqual(64);
    expect(projection.ids).toContain(cible);
    expect(projection.ids).toEqual(expect.arrayContaining(sources.slice(0, 8).map((s) => s.id)));
    expect(projection.ids).toContain(sources.at(-1)!.id);
    expect(sousGraphe(graphe, graphe.racines, sources.at(-1)!.id, 1, false, true, cible).ids).toContain(cible);
    expect(projection.ids.some((id) => graphe.entites.get(id)?.memoire)).toBe(true);
    expect(projection.ids.some((id) => graphe.entites.get(id)?.type === "image")).toBe(true);
    expect(projection.ids.some((id) => graphe.entites.get(id)?.type === "note")).toBe(true);
    const originesObservees = new Set(projection.ids.flatMap((id) => {
      const e = graphe.entites.get(id);
      return e?.observation ? [e.reference] : [];
    }));
    expect(originesObservees.size).toBeGreaterThan(1);
    const ancien = sousGraphe(graphe, graphe.fichiers, null, 1);
    expect(ancien.ids.some((id) => graphe.entites.get(id)?.memoire)).toBe(false);
  });

  test("missions et dossiers restent visibles même avant de recevoir un fichier", () => {
    const board = fixtureDemo();
    const objets = board.objets.filter((o) => o.type === "mission" || o.type === "dossier");
    const liens = board.liens.filter((l) => objets.some((o) => o.id === l.source_id) && objets.some((o) => o.id === l.cible_id));
    const graphe = construire({ ...board, objets, liens });
    expect(graphe.fichiers).toEqual([]);
    expect(graphe.racines.map((e) => e.id).sort()).toEqual(objets.map((o) => o.id).sort());
    expect(graphe.entites.get("BO-demo-mission")?.missionId).toBe("MI-demo00000001");
    expect(sousGraphe(graphe, graphe.racines, null, 1, false, true).relations).toHaveLength(1);
  });
});
