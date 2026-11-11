// Outils de tableau blanc : géométrie, dessin (simplification, bornes), index spatial, guides, disposition, flèches.
import { describe, expect, it } from "vitest";
import { niveauPour } from "../board/detail";
import { echelleExport, nomDeFichier } from "../board/exportPng";
import { genererCharge, versNoeud } from "../board/noeuds";
import { carte } from "../donnees/essais";
import { resoudreTheme } from "../etat/ui";
import { BOITE_MIN, POINTS_MAX, aPressionReelle, cheminDuTrait, figer, limiter, simplifier, type PointTrait } from "./dessin";
import { aligner, ordreDeLecture, repartir } from "./disposition";
import { IndexSpatial, accrocher, contenuDuCadre, dansLeLasso, gommeTouche, indexDe, sousLaGomme, sousLePoint } from "./espace";
import { extremitesReelles, geometrieFleche, pointe } from "./fleche";
import { croisement, dansContour, dansPolygone, distanceSegments, englobante, entreCoins, normaliser, pointSurContour } from "./geometrie";

const boite = (x: number, y: number, largeur: number, hauteur: number) => ({ x, y, largeur, hauteur });

describe("géométrie", () => {
  it("boîtes, polygones, segments", () => {
    expect(englobante([boite(0, 0, 10, 10), boite(20, -5, 10, 10)])).toEqual(boite(0, -5, 30, 15));
    expect(englobante([])).toBeNull();
    expect(entreCoins({ x: 10, y: 10 }, { x: 0, y: 30 })).toEqual(boite(0, 10, 10, 20));
    const triangle = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 10 }];
    expect(dansPolygone({ x: 2, y: 2 }, triangle)).toBe(true);
    expect(dansPolygone({ x: 8, y: 8 }, triangle)).toBe(false);
    expect(croisement({ x: 0, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 10, y: 0 })).toBeCloseTo(0.5);
    expect(croisement({ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 5, y: 5 }, { x: 6, y: 9 })).toBeNull();
    expect(distanceSegments({ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 3 }, { x: 10, y: 3 })).toBe(3);
    expect(distanceSegments({ x: 0, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 10, y: 0 })).toBe(0);
  });

  it("une flèche s'arrête sur le périmètre RÉEL : ellipse et losange, pas leur boîte", () => {
    const b = boite(0, 0, 200, 100);
    const depuis = { x: 400, y: 250 };  // en bas à droite, en diagonale
    const rect = pointSurContour("rectangle", b, depuis), ellipse = pointSurContour("ellipse", b, depuis), losange = pointSurContour("losange", b, depuis);
    // rectangle : sur un bord de la boîte ; ellipse et losange : strictement à l'intérieur de la boîte, sur leur courbe
    expect(Math.abs(rect.x - 200) < 0.01 || Math.abs(rect.y - 100) < 0.01).toBe(true);
    const nx = (ellipse.x - 100) / 100, ny = (ellipse.y - 50) / 50;
    expect(nx * nx + ny * ny).toBeCloseTo(1, 3);
    expect(Math.abs((losange.x - 100) / 100) + Math.abs((losange.y - 50) / 50)).toBeCloseTo(1, 3);
    expect(ellipse.x).toBeLessThan(rect.x);
    expect(losange.x).toBeLessThan(ellipse.x);
    // un point visé hors de la forme (coin de la boîte d'une ellipse) retombe sur le centre ; un départ intérieur rend l'ancre
    expect(dansContour("ellipse", b, { x: 1, y: 1 })).toBe(false);
    expect(pointSurContour("ellipse", b, { x: 100, y: 50 })).toEqual({ x: 100, y: 50 });
  });

  it("une ancre normalisée survit au redimensionnement", () => {
    const a = normaliser(boite(100, 100, 200, 100), { x: 150, y: 175 });
    expect(a).toEqual({ nx: 0.25, ny: 0.75 });
    expect(normaliser(boite(0, 0, 10, 10), { x: 50, y: -3 })).toEqual({ nx: 1, ny: 0 });
  });
});

describe("dessin libre", () => {
  const droite: PointTrait[] = Array.from({ length: 200 }, (_, i) => [i, i * 0.5, 0.5]);
  const zigzag: PointTrait[] = Array.from({ length: 5000 }, (_, i) => [i, (i % 2) * 40 + Math.sin(i) * 9, 0.3 + (i % 7) / 10]);

  it("simplifie une droite à ses deux extrémités et garde les angles", () => {
    expect(simplifier(droite, 0.5)).toEqual([droite[0], droite[199]]);
    const coude: PointTrait[] = [[0, 0, 0.5], [50, 0, 0.5], [100, 0, 0.5], [100, 50, 0.5], [100, 100, 0.5]];
    expect(simplifier(coude, 1)).toEqual([[0, 0, 0.5], [100, 0, 0.5], [100, 100, 0.5]]);
    expect(limiter(zigzag, 100)).toHaveLength(100);
    expect(limiter(zigzag, 100)[99]).toEqual(zigzag[4999]);
  });

  it("fige un geste : borné, relatif à sa boîte, dans les limites du serveur", () => {
    const t = figer(zigzag, 6)!;
    expect(t.points.length % 3).toBe(0);
    expect(t.points.length / 3).toBeLessThanOrEqual(POINTS_MAX);
    expect(JSON.stringify({ points: t.points, boite: t.origine, outil: "crayon", couleur: "indigo", epaisseur: 6 }).length).toBeLessThan(20_000);
    expect(Math.min(...t.points.filter((_, i) => i % 3 === 0))).toBeGreaterThanOrEqual(0);
    expect(Math.max(...t.points.filter((_, i) => i % 3 === 0))).toBeLessThanOrEqual(t.boite.largeur);
    expect(t.points.filter((_, i) => i % 3 === 2).every((p) => Number.isInteger(p) && p >= 0 && p <= 100)).toBe(true);
    expect(t.origine).toEqual([t.boite.largeur, t.boite.hauteur]);
  });

  it("un simple clic donne un point valide (deux points, boîte minimale)", () => {
    const t = figer([[10, 10, 0.5]], 4)!;
    expect(t.points.length).toBe(6);
    expect([t.boite.largeur, t.boite.hauteur]).toEqual([BOITE_MIN, BOITE_MIN]);
    expect(figer([], 4)).toBeNull();
  });

  it("le chemin SVG d'un trait est calculé une fois puis servi du cache", () => {
    const t = figer(droite, 6)!;
    const d = cheminDuTrait(t.points, 6, "crayon");
    expect(d.startsWith("M")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    expect(d).not.toMatch(/NaN|undefined/);
    expect(cheminDuTrait(t.points, 6, "crayon")).toBe(d);
    expect(cheminDuTrait(t.points, 12, "surligneur")).not.toBe(d);
    expect(aPressionReelle(t.points)).toBe(false);
    expect(aPressionReelle([0, 0, 20, 5, 5, 80])).toBe(true);
  });
});

describe("index spatial", () => {
  const objets = [
    carte("A", { x: 0, y: 0, largeur: 100, hauteur: 100, z: 1 }),
    carte("B", { x: 300, y: 0, largeur: 100, hauteur: 100, z: 5 }),
    carte("C", { x: 320, y: 20, largeur: 100, hauteur: 100, z: 9, type: "adhesif" }),
    carte("cadre", { x: -50, y: -50, largeur: 500, hauteur: 300, type: "cadre" }),
    carte("range", { x: 10, y: 10, parent_id: "dossier" }),
    carte("trait", { x: 600, y: 0, largeur: 100, hauteur: 100, type: "trait", meta: { points: [0, 0, 50, 100, 100, 50], boite: [100, 100], epaisseur: 4 } }),
  ];
  const index = new IndexSpatial(objets);

  it("cherche par zone, ignore ce qui est rangé dans un dossier, se met en cache par instantané", () => {
    expect(index.taille).toBe(5);
    expect(index.dans(boite(0, 0, 50, 50)).map((o) => o.id).sort()).toEqual(["A", "cadre"]);
    expect(index.dans(boite(2000, 2000, 10, 10))).toEqual([]);
    expect(indexDe(objets)).toBe(indexDe(objets));
    expect(indexDe([...objets])).not.toBe(indexDe(objets));
  });

  it("lasso : les objets dont le centre est entouré", () => {
    const tour = [{ x: 280, y: -20 }, { x: 460, y: -20 }, { x: 460, y: 160 }, { x: 280, y: 160 }];
    expect(dansLeLasso(index, tour).map((o) => o.id).sort()).toEqual(["B", "C"]);
    expect(dansLeLasso(index, tour.slice(0, 2))).toEqual([]);
  });

  it("un cadre emporte ce dont le centre est dedans, jamais lui-même", () => {
    expect(contenuDuCadre(index, objets[3]!).map((o) => o.id).sort()).toEqual(["A", "B", "C"]);
  });

  it("gomme : test fin sur les points d'un trait, jamais une carte", () => {
    const trait = objets[5]!;
    // la diagonale du trait va de (600,0) à (700,100) : un coup de gomme dans le coin opposé ne le touche pas
    expect(gommeTouche(trait, { x: 690, y: 10 }, { x: 695, y: 12 }, 5)).toBe(false);
    expect(gommeTouche(trait, { x: 640, y: 60 }, { x: 660, y: 40 }, 5)).toBe(true);
    expect(sousLaGomme(index, { x: 640, y: 60 }, { x: 660, y: 40 }, 5).map((o) => o.id)).toEqual(["trait"]);
    expect(sousLaGomme(index, { x: 10, y: 10 }, { x: 60, y: 60 }, 5)).toEqual([]);         // A est une carte
    expect(sousLaGomme(index, { x: 330, y: 30 }, { x: 340, y: 40 }, 5).map((o) => o.id)).toEqual(["C"]);  // adhésif
  });

  it("sous un point : l'objet le plus haut, hors cadres et traits", () => {
    expect(sousLePoint(index, { x: 350, y: 50 })?.id).toBe("C");
    expect(sousLePoint(index, { x: 350, y: 50 }, "C")?.id).toBe("B");
    expect(sousLePoint(index, { x: 200, y: 200 })).toBeUndefined();
  });

  it("5 000 objets : une requête de zone reste locale", () => {
    const charge = genererCharge(5000);
    const gros = new IndexSpatial(charge);
    const t0 = performance.now();
    let trouves = 0;
    for (let i = 0; i < 1000; i++) trouves += gros.dans(boite(2000 + (i % 60) * 500, (i % 50) * 400, 600, 500)).length;
    expect(trouves).toBeGreaterThan(1000);
    expect(trouves).toBeLessThan(1000 * 12);
    expect(performance.now() - t0).toBeLessThan(250);  // large marge : ~5 ms sur le poste de développement
  });
});

describe("guides magnétiques", () => {
  const voisines = [boite(0, 0, 100, 100), boite(400, 300, 100, 60)];

  it("accroche un bord proche et montre la ligne", () => {
    const a = accrocher(boite(203, 104, 100, 100), [boite(200, -300, 50, 50), ...voisines], 6);
    expect(a.dx).toBe(-3);
    expect(a.dy).toBe(-4);  // haut de la boîte mobile sur le bas de la première voisine (y = 100)
    expect(a.guides.some((g) => g.axe === "x" && g.position === 200)).toBe(true);
  });

  it("centre sur centre, et rien au-delà du seuil", () => {
    expect(accrocher(boite(404, 500, 92, 40), voisines, 6)).toMatchObject({ dx: 0 });  // centres alignés à x = 450
    expect(accrocher(boite(402, 500, 100, 40), voisines, 6).dx).toBe(-2);
    expect(accrocher(boite(150, 150, 30, 30), voisines, 6)).toEqual({ dx: 0, dy: 0, guides: [] });
    expect(accrocher(boite(203, 104, 100, 100), [], 6)).toEqual({ dx: 0, dy: 0, guides: [] });
  });
});

describe("aligner, répartir, ordre de lecture", () => {
  const sel = [{ id: "a", ...boite(10, 0, 100, 50) }, { id: "b", ...boite(300, 40, 50, 50) }, { id: "c", ...boite(120, 200, 80, 100) }];

  it("aligne sur les bords et les centres, sans écrire ce qui est déjà en place", () => {
    expect(aligner(sel, "gauche")).toEqual([{ id: "b", x: 10, y: 40 }, { id: "c", x: 10, y: 200 }]);
    expect(aligner(sel, "bas")).toEqual([{ id: "a", x: 10, y: 250 }, { id: "b", x: 300, y: 250 }]);
    expect(aligner(sel, "droite").find((d) => d.id === "a")).toEqual({ id: "a", x: 250, y: 0 });
    expect(aligner(sel.slice(0, 1), "gauche")).toEqual([]);
    const cx = aligner(sel, "centreV");
    expect(new Set(cx.map((d) => d.x + sel.find((s) => s.id === d.id)!.largeur / 2)).size).toBe(1);
  });

  it("répartit à espaces égaux en gardant les extrêmes", () => {
    const d = repartir(sel, "horizontal");
    expect(d).toEqual([{ id: "c", x: 165, y: 200 }]);  // a : 10→110, c : 165→245, b : 300→350 → deux espaces de 55
    expect(repartir(sel.slice(0, 2), "horizontal")).toEqual([]);
  });

  it("présentation : cadres lus par rangées, de gauche à droite", () => {
    const cadres = [boite(900, 20, 400, 300), boite(0, 0, 400, 300), boite(0, 500, 400, 300), boite(450, 60, 400, 300)];
    expect(ordreDeLecture(cadres).map((c) => `${c.x},${c.y}`)).toEqual(["0,0", "450,60", "900,20", "0,500"]);
  });
});

describe("flèches libres", () => {
  const rond = carte("R", { x: 400, y: 0, largeur: 200, hauteur: 200, type: "forme", meta: { forme: "ellipse" } });

  it("enregistre des extrémités normalisées et une ancre normalisée sur l'objet visé", () => {
    const g = geometrieFleche({ point: { x: 0, y: 100 } }, { point: { x: 500, y: 100 }, cible: rond });
    expect(g.boite).toEqual(boite(0, 80, 500, 40));   // boîte minimale du serveur, flèche centrée dedans
    expect(g.points).toEqual([0, 0.5, 1, 0.5]);
    expect(g.ancres).toEqual({ vers: { id: "R", nx: 0.5, ny: 0.5 } });
  });

  it("l'extrémité ancrée suit l'objet et s'arrête sur son périmètre, même redimensionné", () => {
    const g = geometrieFleche({ point: { x: 0, y: 100 } }, { point: { x: 500, y: 100 }, cible: rond });
    const fleche = carte("F", { ...g.boite, type: "fleche", meta: { points: g.points, ancres: g.ancres } });
    const cible = (b: ReturnType<typeof boite>) => () => ({ boite: b, contour: "ellipse" as const });
    const [, fin] = extremitesReelles(fleche, cible(boite(400, 0, 200, 200)));
    expect(fin.x).toBeCloseTo(400, 1);                // bord gauche de l'ellipse, sur l'axe horizontal
    expect(fin.y).toBeCloseTo(100, 1);
    const [, apres] = extremitesReelles(fleche, cible(boite(800, 300, 400, 100)));  // objet déplacé ET redimensionné
    const nx = (apres.x - 1000) / 200, ny = (apres.y - 350) / 50;
    expect(nx * nx + ny * ny).toBeCloseTo(1, 2);
    // objet supprimé : l'extrémité redevient libre, à sa dernière place enregistrée
    expect(extremitesReelles(fleche, () => undefined)[1]).toEqual({ x: 500, y: 100 });
  });

  it("dessine une pointe finie", () => {
    expect(pointe({ x: 0, y: 0 }, { x: 100, y: 0 }, 10)).toMatch(/^100,0 9\d\.\d,-?\d/);
  });
});

describe("niveau de détail, thème, export", () => {
  it("trois niveaux selon le zoom", () => {
    expect([1, 0.35, 0.34, 0.12, 0.11, 0.05].map(niveauPour)).toEqual([0, 0, 1, 1, 2, 2]);
  });

  it("le thème automatique suit le système", () => {
    expect([resoudreTheme("auto", true), resoudreTheme("auto", false), resoudreTheme("jour", false), resoudreTheme("nuit", true)])
      .toEqual(["jour", "nuit", "jour", "nuit"]);
  });

  it("export : échelle bornée, nom de fichier sûr", () => {
    expect(echelleExport(boite(0, 0, 800, 600))).toBe(2);
    expect(echelleExport(boite(0, 0, 8192, 100))).toBe(0.5);
    expect(nomDeFichier("Idées & plan / v2")).toBe("idees-plan-v2.png");
    expect(nomDeFichier("../../etc/passwd")).toBe("etc-passwd.png");
    expect(nomDeFichier("")).toBe("board.png");
  });

  it("un objet inchangé garde son nœud (aucun re-rendu), un objet verrouillé n'est pas déplaçable", () => {
    const o = carte("A", { type: "cadre", z: 7 });
    const n = versNoeud(o, false, 0, false);
    expect(versNoeud(o, false, 0, false, n)).toBe(n);
    expect(versNoeud(o, false, 2, false, n)).not.toBe(n);
    expect(versNoeud(o, false, 0, true, n).className).toBe("estompe");
    expect(n.zIndex).toBeLessThan(0);  // un cadre passe sous son contenu
    expect(n.draggable).toBeUndefined();
    expect(versNoeud(carte("B", { verrouille: 1 }), false, 0, false).draggable).toBe(false);
  });

  it("le jeu d'essai de charge garde le jeu d'avant, et sait ajouter des objets de tableau blanc valides", () => {
    expect(new Set(genererCharge(60).map((o) => o.type))).toEqual(new Set(["note", "image", "lien", "pdf", "audio", "video"]));
    const mixte = genererCharge(100, true);
    expect(mixte.filter((o) => o.type === "trait").every((o) => o.meta.points!.length === 120 && o.meta.boite!.length === 2)).toBe(true);
    expect(mixte.filter((o) => ["adhesif", "forme", "trait"].includes(o.type))).toHaveLength(30);
  });
});
