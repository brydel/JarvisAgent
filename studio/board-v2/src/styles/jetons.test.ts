// Jetons de design : source unique, deux thèmes complets, contraste AA vérifié sur les paires texte / fond déclarées.
import { describe, expect, it } from "vitest";
import { contraste, cssDesThemes, lireCssThemes, lireFeuille, lireJetons } from "../../scripts/jetons.mjs";
import { ZOOM_BLOC, ZOOM_MAX, ZOOM_MIN, ZOOM_RESUME } from "../board/detail";

const jetons = lireJetons();
const THEMES = ["nuit", "jour"] as const;

describe("jetons de design", () => {
  it("themes.css est le miroir exact de tokens.json", () => {
    expect(lireCssThemes()).toBe(cssDesThemes(jetons.themes));
  });

  it("les deux thèmes définissent exactement les mêmes jetons", () => {
    expect(Object.keys(jetons.themes.jour).sort()).toEqual(Object.keys(jetons.themes.nuit).sort());
  });

  it("le calcul de contraste suit WCAG (noir sur blanc = 21)", () => {
    expect(contraste("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contraste("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
  });

  for (const theme of THEMES) {
    it(`contraste AA des paires texte / fond — thème ${theme}`, () => {
      const t = jetons.themes[theme];
      const echecs: string[] = [];
      let verifiees = 0;
      for (const p of jetons.contraste.paires) {
        for (const fond of p.fonds) {
          expect(t[p.texte], `jeton ${p.texte}`).toBeDefined();
          expect(t[fond], `jeton ${fond}`).toBeDefined();
          const c = contraste(t[p.texte]!, t[fond]!);
          verifiees += 1;
          if (c < p.min) echecs.push(`${p.texte} (${t[p.texte]}) sur ${fond} (${t[fond]}) : ${c.toFixed(2)} < ${p.min}`);
        }
      }
      expect(echecs).toEqual([]);
      expect(verifiees).toBeGreaterThan(80);
    });
  }

  it("les feuilles du Board n'écrivent aucune couleur en dur (jetons seulement)", () => {
    for (const f of ["app.css", "tableau.css"]) {
      const css = lireFeuille(f).replace(/\/\*[\s\S]*?\*\//g, "");
      // seule exception : les masques (alpha pur, pas une couleur visible)
      const hors = css.split("\n").filter((l: string) => !/mask-image/.test(l)).join("\n");
      expect(hors.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|:\s*(?:white|black)\b/g) ?? [], f).toEqual([]);
    }
  });

  it("les seuils de zoom du code sont ceux du contrat de design", () => {
    expect([ZOOM_MIN, ZOOM_MAX, ZOOM_RESUME, ZOOM_BLOC]).toEqual(
      [jetons.layout.zoom.min, jetons.layout.zoom.max, jetons.layout.zoom["detail-resume"], jetons.layout.zoom["detail-bloc"]]);
  });
});
