// Géométrie du canevas : boîtes, polygones (lasso), segments (gomme), périmètre réel des formes (flèches).
// Fonctions pures, coordonnées du canevas. Testées dans geometrie.test.ts.

export interface Point {
  x: number;
  y: number;
}
export interface Boite extends Point {
  largeur: number;
  hauteur: number;
}
export type Contour = "rectangle" | "ellipse" | "losange";

export const centre = (b: Boite): Point => ({ x: b.x + b.largeur / 2, y: b.y + b.hauteur / 2 });

export function contient(b: Boite, p: Point): boolean {
  return p.x >= b.x && p.x <= b.x + b.largeur && p.y >= b.y && p.y <= b.y + b.hauteur;
}

export function seChevauchent(a: Boite, b: Boite): boolean {
  return a.x <= b.x + b.largeur && b.x <= a.x + a.largeur && a.y <= b.y + b.hauteur && b.y <= a.y + a.hauteur;
}

/** Plus petite boîte qui contient toutes les autres ; null si la liste est vide. */
export function englobante(boites: readonly Boite[]): Boite | null {
  if (!boites.length) return null;
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const b of boites) {
    x1 = Math.min(x1, b.x);
    y1 = Math.min(y1, b.y);
    x2 = Math.max(x2, b.x + b.largeur);
    y2 = Math.max(y2, b.y + b.hauteur);
  }
  return { x: x1, y: y1, largeur: x2 - x1, hauteur: y2 - y1 };
}

export function boiteDePoints(points: readonly Point[]): Boite | null {
  return englobante(points.map((p) => ({ x: p.x, y: p.y, largeur: 0, hauteur: 0 })));
}

/** Boîte normalisée entre deux coins quelconques (tracé d'une forme dans n'importe quel sens). */
export function entreCoins(a: Point, b: Point): Boite {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), largeur: Math.abs(a.x - b.x), hauteur: Math.abs(a.y - b.y) };
}

/** Point dans un polygone (règle pair-impair) : sélection au lasso. */
export function dansPolygone(p: Point, polygone: readonly Point[]): boolean {
  let dedans = false;
  for (let i = 0, j = polygone.length - 1; i < polygone.length; j = i++) {
    const a = polygone[i]!, b = polygone[j]!;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) dedans = !dedans;
  }
  return dedans;
}

export function distancePointSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x, dy = b.y - a.y;
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** Paramètre t ∈ [0, 1] sur [a, b] où il croise [c, d] ; null s'ils ne se croisent pas. */
export function croisement(a: Point, b: Point, c: Point, d: Point): number | null {
  const r = { x: b.x - a.x, y: b.y - a.y }, s = { x: d.x - c.x, y: d.y - c.y };
  const det = r.x * s.y - r.y * s.x;
  if (Math.abs(det) < 1e-12) return null;
  const t = ((c.x - a.x) * s.y - (c.y - a.y) * s.x) / det;
  const u = ((c.x - a.x) * r.y - (c.y - a.y) * r.x) / det;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? t : null;
}

/** Distance entre deux segments (0 s'ils se croisent) : test fin de la gomme sur un trait. */
export function distanceSegments(a: Point, b: Point, c: Point, d: Point): number {
  if (croisement(a, b, c, d) !== null) return 0;
  return Math.min(distancePointSegment(a, c, d), distancePointSegment(b, c, d), distancePointSegment(c, a, b), distancePointSegment(d, a, b));
}

/** Vrai si `p` est dans la forme inscrite dans `b`. */
export function dansContour(contour: Contour, b: Boite, p: Point): boolean {
  const c = centre(b);
  const nx = (p.x - c.x) / (b.largeur / 2 || 1), ny = (p.y - c.y) / (b.hauteur / 2 || 1);
  if (contour === "ellipse") return nx * nx + ny * ny <= 1 + 1e-9;
  if (contour === "losange") return Math.abs(nx) + Math.abs(ny) <= 1 + 1e-9;
  return Math.abs(nx) <= 1 + 1e-9 && Math.abs(ny) <= 1 + 1e-9;
}

/** Point du PÉRIMÈTRE RÉEL de la forme où arrive une flèche venant de `depuis` et visant `ancre` (un point de la
 *  forme, son centre par défaut). Ellipse et losange compris : la pointe touche le bord dessiné, pas la boîte.
 *  Si `depuis` est déjà dans la forme, rend l'ancre. */
export function pointSurContour(contour: Contour, b: Boite, depuis: Point, ancre: Point = centre(b)): Point {
  const cible = dansContour(contour, b, ancre) ? ancre : centre(b);
  if (dansContour(contour, b, depuis)) return cible;
  // dichotomie sur [depuis → cible] : dehors au départ, dedans à l'arrivée ; exacte à 1/1000 de pixel près en 24 pas,
  // et la même pour les trois contours (aucun cas particulier à maintenir)
  let dehors = 0, dedans = 1;
  for (let i = 0; i < 24; i++) {
    const t = (dehors + dedans) / 2;
    if (dansContour(contour, b, { x: depuis.x + (cible.x - depuis.x) * t, y: depuis.y + (cible.y - depuis.y) * t })) dedans = t;
    else dehors = t;
  }
  return { x: depuis.x + (cible.x - depuis.x) * dedans, y: depuis.y + (cible.y - depuis.y) * dedans };
}

/** Ancre normalisée (0..1 sur la boîte) : survit au déplacement et au redimensionnement de l'objet. */
export function normaliser(b: Boite, p: Point): { nx: number; ny: number } {
  const borne = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 1000) / 1000;
  return { nx: borne((p.x - b.x) / (b.largeur || 1)), ny: borne((p.y - b.y) / (b.hauteur || 1)) };
}

export function denormaliser(b: Boite, a: { nx: number; ny: number }): Point {
  return { x: b.x + a.nx * b.largeur, y: b.y + a.ny * b.hauteur };
}
