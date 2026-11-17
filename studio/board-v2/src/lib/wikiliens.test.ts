import { describe, expect, test } from "vitest";
import { fixtureDemo } from "../demo/fixture";
import { construire } from "../fichiers/graphe";
import { analyserWiki, ciblesWiki, encoderWiki, indexerNotes, lireWikiliens, resoudreWiki } from "./wikiliens";

const board = fixtureDemo();
const origine = board.objets.find((o) => o.id === "BO-demo-decisions")!;
const cible = board.objets.find((o) => o.id === "BO-demo-note")!;

describe("wikiliens des notes", () => {
  test("distingue les titres uniques, les homonymes et les projets", () => {
    expect(resoudreWiki(indexerNotes(board.objets), origine, " note DE cadrage ")).toBe(cible.id);
    const doublon = { ...cible, id: "BO-000000000001" };
    const autreProjet = { ...cible, id: "BO-000000000002", espace: "ailleurs" };
    const objets = [...board.objets, doublon, autreProjet];
    const notes = indexerNotes(objets);
    expect(ciblesWiki(objets, origine, "cadrage").map((r) => r.id).sort()).toEqual([cible.id, doublon.id].sort());
    expect(resoudreWiki(notes, origine, "Note de cadrage")).toBeUndefined();
    expect(resoudreWiki(notes, origine, autreProjet.id)).toBeUndefined();
    expect(resoudreWiki(notes, origine, origine.id)).toBeUndefined();
  });

  test("un lien choisi survit au renommage et disparaît à la suppression", () => {
    const saisi = encoderWiki({ id: cible.id, titre: "Note de cadrage" });
    expect(analyserWiki(saisi)).toEqual({ cible: cible.id, texte: "Note de cadrage" });
    const source = { ...origine, contenu: saisi + " / " + saisi };
    const renommee = { ...cible, meta: { ...cible.meta, titre: "Nom différent" } };
    const b = { ...board, objets: [source, renommee] };
    const g = construire(b);
    expect(g.adjacents.get(renommee.id)).toMatchObject([{ style: "wikilien", source: source.id, cible: renommee.id }]);
    expect(construire({ ...b, objets: [source] }).relations).toEqual([]);
  });

  test("les exemples de code et les liens échappés restent du texte", () => {
    const code = "\x60";
    const fence = code.repeat(3);
    expect([...lireWikiliens(["**[[Note A]]**", "\\[[Échappé]]", code + "[[Inline]]" + code, fence, "[[Exemple]]", fence,
      "[[BO-demo-note|Alias]]"].join("\n"))]).toEqual(["Note A", "BO-demo-note"]);
  });
});
