// Flèche libre : deux extrémités. Chacune est soit LIBRE (un point du canevas), soit ANCRÉE à un objet par une
// position normalisée sur sa boîte (elle suit l'objet quand il bouge ou change de taille). Une extrémité ancrée
// s'arrête sur le PÉRIMÈTRE RÉEL de la forme visée (ellipse et losange compris), pas sur sa boîte englobante.
// Fonctions pures : la même géométrie sert à la création, à l'édition des extrémités et au rendu.
import type { AncreFleche, ObjetBoard } from "../types";
import { BOITE_MIN } from "./dessin";
import { denormaliser, entreCoins, normaliser, pointSurContour, type Boite, type Contour, type Point } from "./geometrie";

export interface Extremite {
  point: Point;
  /** objet visé, s'il y en a un sous le point */
  cible?: Pick<ObjetBoard, "id" | "x" | "y" | "largeur" | "hauteur" | "type" | "meta">;
}

export interface Cible {
  boite: Boite;
  contour: Contour;
}

export const contourDe = (o: Pick<ObjetBoard, "type" | "meta">): Contour =>
  (o.type === "forme" && (o.meta.forme === "ellipse" || o.meta.forme === "losange") ? o.meta.forme : "rectangle");

/** Boîte, extrémités normalisées et ancres d'une flèche tirée de `a` à `b` : ce qui est enregistré. */
export function geometrieFleche(a: Extremite, b: Extremite): { boite: Boite; points: number[]; ancres: { de?: AncreFleche; vers?: AncreFleche } } {
  const brute = entreCoins(a.point, b.point);
  // boîte au moins à la taille minimale du serveur, flèche centrée dedans
  const largeur = Math.max(BOITE_MIN, Math.ceil(brute.largeur)), hauteur = Math.max(BOITE_MIN, Math.ceil(brute.hauteur));
  const boite = { x: Math.round(brute.x - (largeur - brute.largeur) / 2), y: Math.round(brute.y - (hauteur - brute.hauteur) / 2), largeur, hauteur };
  const na = normaliser(boite, a.point), nb = normaliser(boite, b.point);
  const ancre = (e: Extremite): AncreFleche | undefined =>
    (e.cible ? { id: e.cible.id, ...normaliser({ x: e.cible.x, y: e.cible.y, largeur: e.cible.largeur, hauteur: e.cible.hauteur }, e.point) } : undefined);
  const de = ancre(a), vers = ancre(b);
  return { boite, points: [na.nx, na.ny, nb.nx, nb.ny], ancres: { ...(de ? { de } : {}), ...(vers ? { vers } : {}) } };
}

/** Extrémités enregistrées (sans tenir compte des ancres), en coordonnées du canevas. */
export function extremitesBrutes(o: Pick<ObjetBoard, "x" | "y" | "largeur" | "hauteur" | "meta">, origine: Point = o): [Point, Point] {
  const p = Array.isArray(o.meta.points) && o.meta.points.length === 4 ? o.meta.points : [0, 0, 1, 1];
  const boite = { x: origine.x, y: origine.y, largeur: o.largeur, hauteur: o.hauteur };
  return [denormaliser(boite, { nx: p[0]!, ny: p[1]! }), denormaliser(boite, { nx: p[2]!, ny: p[3]! })];
}

/** Extrémités RÉELLES : une extrémité ancrée vise son ancre sur l'objet et s'arrête sur son périmètre. `cible` rend
 *  la boîte et le contour actuels d'un objet (undefined s'il n'existe plus : l'extrémité redevient libre). */
export function extremitesReelles(o: Pick<ObjetBoard, "x" | "y" | "largeur" | "hauteur" | "meta">, cible: (id: string) => Cible | undefined,
  origine: Point = o): [Point, Point] {
  const [a, b] = extremitesBrutes(o, origine);
  const ca = o.meta.ancres?.de ? cible(o.meta.ancres.de.id) : undefined, cb = o.meta.ancres?.vers ? cible(o.meta.ancres.vers.id) : undefined;
  const viseA = ca ? denormaliser(ca.boite, o.meta.ancres!.de!) : a, viseB = cb ? denormaliser(cb.boite, o.meta.ancres!.vers!) : b;
  return [ca ? pointSurContour(ca.contour, ca.boite, viseB, viseA) : a, cb ? pointSurContour(cb.contour, cb.boite, viseA, viseB) : b];
}

/** Triangle de pointe au bout du segment [de → vers]. */
export function pointe(de: Point, vers: Point, taille: number): string {
  const angle = Math.atan2(vers.y - de.y, vers.x - de.x);
  const f = (n: number) => Math.round(n * 10) / 10;
  const coin = (a: number) => `${f(vers.x - taille * Math.cos(angle + a))},${f(vers.y - taille * Math.sin(angle + a))}`;
  return `${f(vers.x)},${f(vers.y)} ${coin(0.42)} ${coin(-0.42)}`;
}
