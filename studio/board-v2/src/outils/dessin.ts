// Dessin libre : du geste (points du pointeur avec pression) à l'objet « trait » enregistré, puis à son chemin SVG.
// - le geste est SIMPLIFIÉ (Ramer-Douglas-Peucker) et BORNÉ avant l'envoi : le serveur refuse au-delà de 1 500 points ;
// - le trait enregistré = points relatifs à sa boîte (x, y au dixième, pression en %) : redimensionner la boîte
//   met le trait à l'échelle ;
// - le chemin SVG (contour perfect-freehand, MIT) est calculé UNE fois par trait et gardé en cache : un trait figé
//   ne coûte plus qu'un <path> au rendu.
import { getStroke } from "perfect-freehand";
import type { Boite } from "./geometrie";

/** Point de geste : coordonnées du canevas et pression (0..1). */
export type PointTrait = [x: number, y: number, pression: number];
export type OutilTrait = "crayon" | "surligneur";

export const POINTS_MAX = 700;        // bien sous la borne du serveur (1 500) et sous 20 000 caractères de meta
export const BOITE_MIN = 40;          // taille minimale d'un objet côté serveur (board.TAILLE_MIN)

function distanceALaCorde(p: PointTrait, a: PointTrait, b: PointTrait): number {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Ramer-Douglas-Peucker itératif (pas de récursion : un geste peut compter des milliers de points). */
export function simplifier(points: readonly PointTrait[], epsilon: number): PointTrait[] {
  if (points.length <= 2 || epsilon <= 0) return [...points];
  const garde = new Uint8Array(points.length);
  garde[0] = garde[points.length - 1] = 1;
  const pile: [number, number][] = [[0, points.length - 1]];
  while (pile.length) {
    const [d, f] = pile.pop()!;
    let max = 0, index = -1;
    for (let i = d + 1; i < f; i++) {
      const dist = distanceALaCorde(points[i]!, points[d]!, points[f]!);
      if (dist > max) {
        max = dist;
        index = i;
      }
    }
    if (index >= 0 && max > epsilon) {
      garde[index] = 1;
      pile.push([d, index], [index, f]);
    }
  }
  return points.filter((_, i) => garde[i]);
}

/** Au plus `max` points, extrémités conservées (échantillonnage régulier : dernier recours après la simplification). */
export function limiter(points: readonly PointTrait[], max = POINTS_MAX): PointTrait[] {
  if (points.length <= max) return [...points];
  const pas = (points.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, i) => points[Math.round(i * pas)]!);
}

export interface TraitEnregistre {
  boite: Boite;
  /** triplets (x, y, pression en %) relatifs au coin de la boîte */
  points: number[];
  /** boîte d'origine [largeur, hauteur] : repère de mise à l'échelle */
  origine: [number, number];
}

/** Prépare un geste pour l'enregistrement. `epaisseur` élargit la boîte pour que le trait n'en déborde pas. */
export function figer(geste: readonly PointTrait[], epaisseur: number, zoom = 1): TraitEnregistre | null {
  if (!geste.length) return null;
  // un simple clic laisse un point : deux points confondus (le serveur exige au moins deux points)
  const brut = geste.length === 1 ? [geste[0]!, [geste[0]![0] + 0.1, geste[0]![1] + 0.1, geste[0]![2]] as PointTrait] : geste;
  let pts = simplifier(brut, 0.6 / Math.max(zoom, 0.05));
  // geste très long : on desserre la tolérance avant de rééchantillonner
  for (let e = 1.2; pts.length > POINTS_MAX && e <= 8; e *= 2) pts = simplifier(brut, e / Math.max(zoom, 0.05));
  pts = limiter(pts);
  const marge = epaisseur / 2 + 2;
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const [x, y] of pts) {
    x1 = Math.min(x1, x);
    y1 = Math.min(y1, y);
    x2 = Math.max(x2, x);
    y2 = Math.max(y2, y);
  }
  // boîte au moins à la taille minimale du serveur, trait centré dedans
  const largeur = Math.max(BOITE_MIN, Math.ceil(x2 - x1 + 2 * marge)), hauteur = Math.max(BOITE_MIN, Math.ceil(y2 - y1 + 2 * marge));
  const ox = Math.round(x1 - (largeur - (x2 - x1)) / 2), oy = Math.round(y1 - (hauteur - (y2 - y1)) / 2);
  const points: number[] = [];
  for (const [x, y, p] of pts) points.push(Math.round((x - ox) * 10) / 10, Math.round((y - oy) * 10) / 10, Math.round(Math.max(0, Math.min(1, p)) * 100));
  return { boite: { x: ox, y: oy, largeur, hauteur }, points, origine: [largeur, hauteur] };
}

/** Contour (polygone) → chemin SVG lissé par des courbes quadratiques passant par les milieux. */
export function cheminDuContour(contour: readonly number[][]): string {
  if (contour.length < 2) return "";
  const f = (n: number) => Math.round(n * 100) / 100;
  let d = `M${f(contour[0]![0]!)},${f(contour[0]![1]!)} Q`;
  for (let i = 0; i < contour.length; i++) {
    const [x0, y0] = contour[i]!, [x1, y1] = contour[(i + 1) % contour.length]!;
    d += `${f(x0!)},${f(y0!)} ${f((x0! + x1!) / 2)},${f((y0! + y1!) / 2)} `;
  }
  return `${d}Z`;
}

export interface OptionsTrait {
  epaisseur: number;
  outil: OutilTrait;
  /** vrai si la pression vient d'un stylet ; sinon elle est simulée par la vitesse */
  pressionReelle?: boolean;
  /** vrai pendant le geste (le bout du trait reste ouvert) */
  enCours?: boolean;
}

/** Chemin SVG d'un geste (points [x, y, pression 0..1]). */
export function cheminDuGeste(points: readonly number[][], o: OptionsTrait): string {
  const surligneur = o.outil === "surligneur";
  return cheminDuContour(getStroke(points as number[][], {
    size: o.epaisseur, thinning: surligneur ? 0 : 0.55, smoothing: 0.55, streamline: surligneur ? 0.35 : 0.45,
    simulatePressure: !o.pressionReelle && !surligneur, last: !o.enCours,
    start: { cap: !surligneur }, end: { cap: !surligneur },
  }));
}

const cache = new WeakMap<readonly number[], Map<string, string>>();

/** Chemin SVG d'un trait ENREGISTRÉ (triplets relatifs, pression en %), calculé une fois par trait et par style. */
export function cheminDuTrait(points: readonly number[], epaisseur: number, outil: OutilTrait, pressionReelle = false): string {
  const cle = `${epaisseur}|${outil}|${pressionReelle ? 1 : 0}`;
  let parStyle = cache.get(points);
  if (!parStyle) cache.set(points, (parStyle = new Map()));
  let d = parStyle.get(cle);
  if (d === undefined) {
    const pts: number[][] = [];
    for (let i = 0; i + 2 < points.length; i += 3) pts.push([points[i]!, points[i + 1]!, points[i + 2]! / 100]);
    d = cheminDuGeste(pts, { epaisseur, outil, pressionReelle });
    parStyle.set(cle, d);
  }
  return d;
}

/** Une pression qui varie d'un point à l'autre vient d'un stylet ; la souris envoie une valeur fixe. */
export function aPressionReelle(points: readonly number[]): boolean {
  for (let i = 5; i < points.length; i += 3) if (points[i] !== points[2]) return true;
  return false;
}
