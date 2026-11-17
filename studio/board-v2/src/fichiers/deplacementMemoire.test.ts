import { describe, expect, it } from "vitest";
import { idCentroide, positionsMemoire, translaterLot } from "./deplacementMemoire";

describe("dessin libre des sessions", () => {
  const centreA = idCentroide("session-a"), centreB = idCentroide("session-b");
  const points = new Map([
    [centreA, { x: 0, y: 0 }], ["a", { x: 20, y: 40 }], ["b", { x: -30, y: 15 }],
    [centreB, { x: 400, y: 0 }], ["c", { x: 430, y: 20 }], ["source-partagee", { x: 200, y: 0 }],
  ]);

  it("déplace un membre seul, en conservant le centroïde et tous ses voisins", () => {
    const suite = translaterLot(points, "a", { x: 135, y: 84 }, []);
    expect(suite.get("a")).toEqual({ x: 135, y: 84 });
    for (const id of [centreA, centreB, "b", "c", "source-partagee"]) expect(suite.get(id)).toEqual(points.get(id));
  });

  it("translate rigidement le lot exclusif du centroïde sans entraîner une autre session", () => {
    const suite = translaterLot(points, centreA, { x: 75, y: -20 }, ["a", "b"]);
    expect(suite.get(centreA)).toEqual({ x: 75, y: -20 });
    expect(suite.get("a")).toEqual({ x: 95, y: 20 });
    expect(suite.get("b")).toEqual({ x: 45, y: -5 });
    for (const id of [centreB, "c", "source-partagee"]) expect(suite.get(id)).toEqual(points.get(id));
  });

  it("garde le dessin d’un membre au prochain geste de groupe et accueille les nouveaux points", () => {
    const libre = translaterLot(points, "a", { x: 130, y: 90 }, []);
    const lot = translaterLot(libre, centreA, { x: 50, y: 40 }, ["a", "b"]);
    expect(lot.get("a")).toEqual({ x: 180, y: 130 });
    const nouveau = new Map([...points, ["arrive", { x: 65, y: 30 }] as const]);
    const fusion = positionsMemoire(nouveau, lot, new Map([[centreA, ["a", "b", "arrive"]]]));
    expect(fusion.get("a")).toEqual({ x: 180, y: 130 });
    expect(fusion.get("arrive")).toEqual({ x: 115, y: 70 });
    expect(fusion.get(centreB)).toEqual(points.get(centreB));
  });
  it("conserve et translate les membres dessinés qui sont temporairement hors projection", () => {
    const dessine = translaterLot(points, "a", { x: 130, y: 90 }, []);
    const masque = new Map(points);
    masque.delete("a");
    const lots = new Map([[centreA, ["a", "b"]]]);
    const scene = positionsMemoire(masque, dessine, lots);
    expect(scene.get("a")).toEqual({ x: 130, y: 90 });
    const deplace = translaterLot(scene, centreA, { x: 50, y: 40 }, lots.get(centreA)!);
    const retour = positionsMemoire(points, deplace, lots);
    expect(retour.get("a")).toEqual({ x: 180, y: 130 });
    expect(retour.get("b")).toEqual({ x: 20, y: 55 });
  });
});
