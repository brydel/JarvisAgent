// Les lignes posées hors d'une carte ne recouvrent jamais une carte voisine : la place libre est mesurée.
import { describe, expect, it } from "vitest";
import { IndexSpatial } from "../outils/espace";
import type { ObjetBoard } from "../types";
import { CREDIT, LIGNE, MARGE, PORTEE, creditTient, degagementDe, lignesQuiTiennent } from "./degagement";

function carte(id: string, x: number, y: number, largeur = 400, hauteur = 300, type: ObjetBoard["type"] = "note"): ObjetBoard {
  return { id, type, x, y, largeur, hauteur, espace: "accueil", contenu: "", z: 1, priorite: "", meta: {}, asset_id: null, asset: null,
    mission_id: null, mission: null, parent_id: null, verrouille: 0, version: 1, cree: 0, maj: 0, commentaires: 0 } as ObjetBoard;
}

describe("dégagement autour d'une carte", () => {
  it("une carte seule a toute la place", () => {
    const a = carte("a", 0, 0);
    expect(degagementDe(a, new IndexSpatial([a]))).toEqual({ dessous: PORTEE, dessus: PORTEE });
  });

  it("mesure l'espace jusqu'à la carte du dessous et du dessus, dans sa colonne seulement", () => {
    const a = carte("a", 0, 400), dessous = carte("b", 100, 730), dessus = carte("c", -200, 60), aCote = carte("d", 420, 705);
    const d = degagementDe(a, new IndexSpatial([a, dessous, dessus, aCote]));
    expect(d).toEqual({ dessous: 30, dessus: 40 });
  });

  it("une carte qui chevauche le bord ne laisse aucune place", () => {
    const a = carte("a", 0, 0), b = carte("b", 50, 280);
    expect(degagementDe(a, new IndexSpatial([a, b])).dessous).toBe(0);
    expect(degagementDe(b, new IndexSpatial([a, b])).dessus).toBe(0);
  });

  it("un cadre, un trait, une flèche ou une carte masquée par le filtre n'occupent pas la place", () => {
    const a = carte("a", 0, 0), cadre = carte("k", -50, -50, 600, 600, "cadre"), masquee = carte("m", 0, 310);
    const d = degagementDe(a, new IndexSpatial([a, cadre, masquee]), (v) => v.id !== "m");
    expect(d).toEqual({ dessous: PORTEE, dessus: PORTEE });
  });

  it("ne garde que les lignes qui tiennent, marges comprises", () => {
    expect(lignesQuiTiennent(0)).toBe(0);
    expect(lignesQuiTiennent(2 * MARGE + LIGNE - 1)).toBe(0);
    expect(lignesQuiTiennent(2 * MARGE + LIGNE)).toBe(1);
    expect(lignesQuiTiennent(PORTEE)).toBeGreaterThanOrEqual(3);
  });

  it("la ligne de crédit ne s'affiche que s'il reste sa hauteur sous les lignes", () => {
    expect(creditTient(2 * MARGE + CREDIT, 0)).toBe(true);
    expect(creditTient(2 * MARGE + CREDIT - 1, 0)).toBe(false);
    expect(creditTient(2 * MARGE + CREDIT, 1)).toBe(false);
    expect(creditTient(PORTEE, 3)).toBe(true);
  });
});
