// Jetons de design : source unique, deux thèmes complets, contraste AA vérifié sur les paires texte / fond déclarées.
import { describe, expect, it } from "vitest";
import { contraste, feuillesDuProduit, fichiersGeneres, lireDuProjet, lireFichier, lireJetons, nomsConnus, sourcesInterface, synonymes, themeResolu } from "../../scripts/jetons.mjs";
import { ICONE } from "./systeme";
import { ZONE_LIBRE, ZOOM_BLOC, ZOOM_MAX, ZOOM_MIN, ZOOM_RESUME, vientDEtrePose } from "../board/detail";

const jetons = lireJetons();
const THEMES = ["nuit", "jour"] as const;
/** variables posées par le code (style en ligne) ou par une autre feuille, lues ici */
const LOCAUX = new Set(["teinte", "accent-carte", "p-bg", "p-panel", "p-raised", "p-line", "p-muted", "p-ink", "p-accent", "p-action", "p-mint", "p-shadow"]);
const px = (v: string) => Number(/^(-?[\d.]+)px$/.exec(v)?.[1] ?? NaN);

describe("jetons de design", () => {
  it("themes.css, tokens.css et la planche sont le miroir exact de tokens.json", () => {
    for (const f of fichiersGeneres(jetons)) expect(lireFichier(f.chemin), f.chemin).toBe(f.contenu);
  });

  it("les deux thèmes définissent exactement les mêmes jetons", () => {
    expect(Object.keys(jetons.themes.jour).sort()).toEqual(Object.keys(jetons.themes.nuit).sort());
  });

  it("chaque synonyme vise un jeton de thème, sans chaîne ni doublon de nom", () => {
    const noms = new Set(Object.keys(jetons.themes.nuit));
    for (const [nom, cible] of Object.entries(synonymes(jetons))) {
      expect(noms.has(cible), `${nom} → ${cible}`).toBe(true);
      expect(noms.has(nom), `${nom} est aussi un jeton de thème`).toBe(false);
    }
    expect(Object.keys(jetons.synonymes.roles).filter((n) => n in jetons.synonymes.herites)).toEqual([]);
  });

  it("le calcul de contraste suit WCAG (noir sur blanc = 21)", () => {
    expect(contraste("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contraste("#777777", "#FFFFFF")).toBeCloseTo(4.48, 2);
  });

  for (const theme of THEMES) {
    it(`contraste AA des paires texte / fond — thème ${theme}`, () => {
      const t = themeResolu(jetons, theme);
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
      expect(verifiees).toBeGreaterThan(120);
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
    const connus = new Set(nomsConnus(jetons));
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
      // Palette de calcul du shader tiers : les couleurs visibles des points restent des jetons dans ZoomGraphe.
      if (f.chemin === "ui/react-bits/crystalized-ball/CrystalizedBall.tsx") continue;
      for (const m of f.code.matchAll(/["'`](#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}|rgba?\([^"'`]*\))["'`]/g)) fautifs.push(`${f.chemin} : ${m[1]}`);
    }
    expect(fautifs).toEqual([]);
  });

  it("échelles du système : grille de 4 px, rien sous 12 px, rayons imbriqués, une courbe, des durées courtes", () => {
    const f = jetons.fixes;
    for (const [nom, v] of Object.entries(f.espace!)) if (nom.startsWith("space-") && nom !== "space-half") expect(px(v) % 4, nom).toBe(0);
    for (const [nom, v] of Object.entries(f.espace!)) if (/^space-\d+$/.test(nom)) expect(px(v), nom).toBe(Number(nom.slice(6)) * 4);
    for (const [nom, v] of Object.entries(f.hauteur!)) if (!nom.startsWith("$")) expect(px(v) % 4, nom).toBe(0);
    for (const groupe of [f.taille!, f["taille-canevas"]!, f.mobile!]) for (const [nom, v] of Object.entries(groupe)) if (/^fsc?-/.test(nom)) {
      expect(Number.isInteger(px(v)), `${nom} : taille entière`).toBe(true);
      // une unité du canevas vaut 0,8 px écran au zoom de référence
      expect(px(v) * (nom.startsWith("fsc-") ? jetons.layout.reference.canvasZoom : 1), nom).toBeGreaterThanOrEqual(12);
    }
    for (const [nom, v] of Object.entries(f.police!)) if (nom.startsWith("fw-")) expect([400, 500, 600], nom).toContain(Number(v));
    const rayons = Object.entries(f.rayon!).filter(([nom]) => !nom.startsWith("$") && nom !== "radius-pill").map(([, v]) => px(v));
    expect(rayons).toEqual([...rayons].sort((a, b) => a - b));
    expect(Math.min(...rayons)).toBe(4);
    // un contrôle (8) posé à 4 px du bord d'une carte (12), une carte posée à 4 px du bord d'un panneau (16)
    expect(px(f.rayon!["radius-card"]!) - px(f.espace!["space-1"]!)).toBe(px(f.rayon!["radius-sm"]!));
    expect(px(f.rayon!["radius-panel"]!) - px(f.espace!["space-1"]!)).toBe(px(f.rayon!["radius-card"]!));
    const courbes = Object.entries(f.mouvement!).filter(([nom]) => nom.startsWith("ease-")).map(([, v]) => v).filter((v) => !v.startsWith("var("));
    expect(courbes).toEqual(["cubic-bezier(0.22, 1, 0.36, 1)"]);
    for (const [nom, v] of Object.entries(f.mouvement!)) if (nom.startsWith("dur-")) {
      expect(Number.parseInt(v, 10), nom).toBeGreaterThanOrEqual(120);
      expect(Number.parseInt(v, 10), nom).toBeLessThanOrEqual(500);
      expect(f["mouvement-reduit"]![nom], `${nom} sous prefers-reduced-motion`).toBe("0ms");
    }
    expect(px(f.gabarit!["topbar-h"]!)).toBe(jetons.layout.topbar.height);
    expect(px(f.gabarit!["subbar-h"]!)).toBe(jetons.layout.subbar.height);
    expect(px(f.gabarit!["panel-w"]!)).toBe(jetons.layout.panel.width);
  });

  it("aucune feuille ne transite « all », écrit ou sous-entendu", () => {
    const fautifs: string[] = [];
    for (const f of feuillesDuProduit()) {
      const css = f.css.replace(/\/\*[\s\S]*?\*\//g, "");
      for (const m of css.matchAll(/transition(?:-property)?\s*:\s*([^;}]+)/g)) {
        const v = m[1]!.trim();
        // « all » écrit, ou sous-entendu par une transition qui commence par sa durée
        if (/(^|[\s,])all\b/.test(v) || /^[\d.]+m?s\b/.test(v) || /^var\(--dur-/.test(v)) fautifs.push(`${f.chemin} : ${m[0]}`);
      }
    }
    expect(fautifs).toEqual([]);
  });

  it("icônes, favicon et couleur de la barre du navigateur suivent les jetons", () => {
    expect(`${ICONE.taille}px`).toBe(jetons.fixes.icone!["icon-size"]);
    expect(String(ICONE.trait)).toBe(jetons.fixes.icone!["icon-stroke"]);
    const [marque, page] = [lireDuProjet("public/jarvis-mark.svg"), lireDuProjet("index.html")];
    // la marque est à plat, d'une seule couleur par thème : l'encre
    expect(marque).not.toMatch(/Gradient|filter|opacity/);
    expect([...new Set(marque.match(/#[0-9a-fA-F]{6}/g))].sort()).toEqual([jetons.themes.nuit.encre, jetons.themes.jour.encre].sort());
    expect(page).toContain(`content="${jetons.themes.nuit["bg-bar"]}" media="(prefers-color-scheme: dark)"`);
    expect(page).toContain(`content="${jetons.themes.jour["bg-bar"]}" media="(prefers-color-scheme: light)"`);
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
