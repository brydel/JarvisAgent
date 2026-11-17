import { describe, expect, it } from "vitest";
import { centresMemoire, disposerMemoire } from "./DispositionMemoire";
import { grouperMemoire, relationsSessionsPartagees, teintesGroupes, voisinage, type GroupeMemoire } from "./GroupesMemoire";
import type { Entite, Relation } from "./graphe";

const lien = (source: string, cible: string): Relation => ({ id: source + ":" + cible, source, cible, style: "source", texte: "Preuve" });

describe("groupes du graphe de mémoire", () => {
  it("conserve chaque point une fois et privilégie la mission liée pour nommer le groupe", () => {
    const ids = ["mission", "note", "reference", "observation-1", "observation-2", "isole"];
    const voisins = voisinage(ids, [lien("mission", "note"), lien("note", "reference"),
      lien("reference", "observation-1"), lien("reference", "observation-2")]);
    const groupes = grouperMemoire(voisins, new Set(), new Map([["mission", 3], ["reference", 1]]));
    expect(groupes.flatMap((g) => g.ids).sort()).toEqual([...ids].sort());
    expect(groupes.find((g) => g.ids.includes("note"))?.ancre).toBe("mission");
    expect(groupes.find((g) => g.ids.includes("isole"))?.ids).toEqual(["isole"]);
  });

  it("conserve la teinte de chaque groupe quand son voisinage ou l’ordre des données change", () => {
    const groupes: GroupeMemoire[] = Array.from({ length: 8 }, (_, i) => ({ ancre: "mission-" + i, ids: ["mission-" + i, "preuve-" + i] }));
    const couleurs = teintesGroupes(groupes);
    expect(new Set(Object.values(couleurs.styles)).size).toBe(8);
    expect(teintesGroupes([...groupes].reverse())).toEqual(couleurs);
    const isole = teintesGroupes([groupes[3]!]);
    const variable = couleurs.variables.get(groupes[3]!.ancre)!;
    expect(isole.variables.get(groupes[3]!.ancre)).toBe(variable);
    expect(isole.styles[variable]).toBe(couleurs.styles[variable]);
  });

  it("sépare les groupes connectés tout en conservant le centre et des positions déterministes", () => {
    const groupes = ["a", "b", "c"].map((ancre) => ({ ancre, ids: [ancre, ancre + "1", ancre + "2", ancre + "3"] }));
    const ids = groupes.flatMap((g) => g.ids);
    const liens = groupes.flatMap((g) => g.ids.slice(1).map((id) => lien(g.ancre, id)));
    const positions = disposerMemoire(ids, liens, "a", groupes);
    expect(positions.get("a")).toEqual({ x: 0, y: 0 });
    expect([...positions]).toEqual([...disposerMemoire([...ids].reverse(), liens, "a", groupes)]);
    expect([...positions.values()].every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
    const moyenne = (g: GroupeMemoire) => g.ids.reduce((p, id) => ({
      x: p.x + positions.get(id)!.x / g.ids.length, y: p.y + positions.get(id)!.y / g.ids.length,
    }), { x: 0, y: 0 });
    const a = moyenne(groupes[0]!), b = moyenne(groupes[1]!);
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(120);
  });
  it("relie le même hub partagé aux deux centroïdes, même sans membre exclusif", () => {
    const entites = new Map<string, Entite>([
      ["hub", { id: "hub", titre: "Preuve partagée", type: "note", sessionIds: ["a", "b"] }],
      ["simple", { id: "simple", titre: "Preuve simple", type: "note", sessionIds: ["a"] }],
    ]);
    const groupes: GroupeMemoire[] = ["a", "b"].map((ancre) => ({ ancre, ids: [], explicite: true, nature: "session" }));
    const liens = relationsSessionsPartagees(entites, ["hub", "simple"], groupes);
    expect(liens).toHaveLength(2);
    expect(new Set(liens.map((r) => r.source))).toEqual(new Set(["centroide:a", "centroide:b"]));
    expect(liens.every((r) => r.cible === "hub" && r.texte === "Élément partagé de la session")).toBe(true);
  });

  it("place les centres des sessions vides sans les ajouter à la simulation des vrais points", () => {
    const groupes: GroupeMemoire[] = Array.from({ length: 1000 }, (_, i) => ({ ancre: "session-" + i,
      ids: [], explicite: true, nature: "session" }));
    const centres = centresMemoire(groupes, null);
    expect(centres.size).toBe(1000);
    expect(new Set([...centres.values()].map((p) => p.x + ":" + p.y)).size).toBe(1000);
    expect(disposerMemoire([], [], null, groupes).size).toBe(0);
  });
});
