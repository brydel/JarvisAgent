// Jetons de design : source unique, deux thèmes complets, contraste AA vérifié sur les paires texte / fond déclarées.
import { describe, expect, it } from "vitest";
import { contraste, cssDesThemes, feuillesDuProduit, lireCssThemes, lireJetons, sourcesInterface } from "../../scripts/jetons.mjs";
import { ZONE_LIBRE, ZOOM_BLOC, ZOOM_MAX, ZOOM_MIN, ZOOM_RESUME, vientDEtrePose } from "../board/detail";

const jetons = lireJetons();
const THEMES = ["nuit", "jour"] as const;
/** variables posées par le code (style en ligne) ou par une autre feuille, lues ici */
const LOCAUX = new Set(["teinte", "accent-carte", "p-bg", "p-panel", "p-raised", "p-line", "p-muted", "p-ink", "p-accent", "p-action", "p-mint", "p-shadow"]);

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

  it("aucune feuille de style du produit n'écrit de couleur en dur (jetons seulement) : Board, pages, dialogues, références", () => {
    const feuilles = feuillesDuProduit();
    expect(feuilles.map((f) => f.chemin)).toEqual(expect.arrayContaining(["styles/app.css", "styles/tableau.css", "styles/product.css",
      "styles/communaute.css", "styles/connexions.css", "styles/runtime.css", "styles/activite.css", "references/references.css", "product/navigation.css"]));
    for (const f of feuilles) {
      const css = f.css.replace(/\/\*[\s\S]*?\*\//g, "");
      // seule exception : les masques (alpha pur, pas une couleur visible)
      const hors = css.split("\n").filter((l: string) => !/mask-image/.test(l)).join("\n");
      expect(hors.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|:\s*(?:white|black)\b/g) ?? [], f.chemin).toEqual([]);
    }
  });

  it("chaque jeton utilisé par une feuille existe dans les deux thèmes", () => {
    const connus = new Set([...Object.keys(jetons.themes.nuit), "font-sans", "radius-xs", "radius-sm", "radius-card", "radius-panel", "radius-pill",
      "dur-hover", "dur-appear", "dur-panel", "dur-lift", "ease-standard", "ease-exit", "topbar-h", "subbar-h", "panel-w"]);
    const inconnus: string[] = [];
    for (const f of feuillesDuProduit()) {
      const locaux = new Set([...f.css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]!.slice(2)));
      for (const m of f.css.matchAll(/var\(--([\w-]+)/g)) if (!connus.has(m[1]!) && !locaux.has(m[1]!) && !LOCAUX.has(m[1]!)) inconnus.push(`${f.chemin} : --${m[1]}`);
    }
    expect([...new Set(inconnus)]).toEqual([]);
  });

  it("les composants n'écrivent pas de couleur en dur non plus (attributs et styles en ligne)", () => {
    const fautifs: string[] = [];
    for (const f of sourcesInterface()) {
      if (/demo|fixture|\.test\./.test(f.chemin)) continue;
      for (const m of f.code.matchAll(/["'`](#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}|rgba?\([^"'`]*\))["'`]/g)) fautifs.push(`${f.chemin} : ${m[1]}`);
    }
    expect(fautifs).toEqual([]);
  });

  it("la zone libre du canevas (barres flottantes) est celle du contrat de design, et dégage les deux barres", () => {
    const { $description: _, ...zone } = jetons.layout["canvas-safe-area"];
    expect(ZONE_LIBRE).toEqual(zone);
    // barre d'outils : 14 px du haut + 52 px de haut ; barre d'ajout : 16 px du bord + 68 px de large
    expect(ZONE_LIBRE.top).toBeGreaterThanOrEqual(14 + 52 + 8);
    expect(ZONE_LIBRE.left).toBeGreaterThanOrEqual(jetons.layout.toolbar.x + jetons.layout.toolbar.width + 8);
  });

  it("un objet « vient d'être posé » pendant deux secondes, jamais au rechargement", () => {
    expect(vientDEtrePose(1000, 1000.5)).toBe(true);
    expect(vientDEtrePose(1000, 1002.5)).toBe(false);
    expect(vientDEtrePose(0, 1)).toBe(false);          // date inconnue
    expect(vientDEtrePose(1000, 990)).toBe(false);     // horloge du serveur en avance : pas d'animation à contretemps
  });

  it("les seuils de zoom du code sont ceux du contrat de design", () => {
    expect([ZOOM_MIN, ZOOM_MAX, ZOOM_RESUME, ZOOM_BLOC]).toEqual(
      [jetons.layout.zoom.min, jetons.layout.zoom.max, jetons.layout.zoom["detail-resume"], jetons.layout.zoom["detail-bloc"]]);
  });
});
