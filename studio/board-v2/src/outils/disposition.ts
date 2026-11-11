// Aligner et répartir une sélection : fonctions pures qui rendent les déplacements à écrire (rien si déjà en place).
import type { Boite } from "./geometrie";

export type Alignement = "gauche" | "droite" | "haut" | "bas" | "centreV" | "centreH";
export type Axe = "horizontal" | "vertical";
export interface Place extends Boite {
  id: string;
}
export interface Deplacement {
  id: string;
  x: number;
  y: number;
}

const change = (o: Place, x: number, y: number): Deplacement[] => {
  const d = { id: o.id, x: Math.round(x), y: Math.round(y) };
  return d.x === Math.round(o.x) && d.y === Math.round(o.y) ? [] : [d];
};

/** Aligne sur le bord extrême de la sélection, ou sur la moyenne des centres (centreV : même axe vertical). */
export function aligner(objets: readonly Place[], mode: Alignement): Deplacement[] {
  if (objets.length < 2) return [];
  const moyenne = (f: (o: Place) => number) => objets.reduce((s, o) => s + f(o), 0) / objets.length;
  const gauche = Math.min(...objets.map((o) => o.x)), droite = Math.max(...objets.map((o) => o.x + o.largeur));
  const haut = Math.min(...objets.map((o) => o.y)), bas = Math.max(...objets.map((o) => o.y + o.hauteur));
  const cx = moyenne((o) => o.x + o.largeur / 2), cy = moyenne((o) => o.y + o.hauteur / 2);
  return objets.flatMap((o) => {
    switch (mode) {
      case "gauche": return change(o, gauche, o.y);
      case "droite": return change(o, droite - o.largeur, o.y);
      case "haut": return change(o, o.x, haut);
      case "bas": return change(o, o.x, bas - o.hauteur);
      case "centreV": return change(o, cx - o.largeur / 2, o.y);
      case "centreH": return change(o, o.x, cy - o.hauteur / 2);
    }
  });
}

/** Espaces égaux entre les objets, les deux extrêmes restant en place. Trois objets au moins. */
export function repartir(objets: readonly Place[], axe: Axe): Deplacement[] {
  if (objets.length < 3) return [];
  const h = axe === "horizontal";
  const pos = (o: Place) => (h ? o.x : o.y), taille = (o: Place) => (h ? o.largeur : o.hauteur);
  const tri = [...objets].sort((a, b) => pos(a) - pos(b));
  const dernier = tri[tri.length - 1]!;
  const espace = (pos(dernier) + taille(dernier) - pos(tri[0]!) - tri.reduce((s, o) => s + taille(o), 0)) / (tri.length - 1);
  let curseur = pos(tri[0]!);
  return tri.flatMap((o) => {
    const d = h ? change(o, curseur, o.y) : change(o, o.x, curseur);
    curseur += taille(o) + espace;
    return d;
  });
}

/** Ordre de lecture des cadres (présentation) : de haut en bas par rangées, puis de gauche à droite. */
export function ordreDeLecture<T extends Boite>(cadres: readonly T[]): T[] {
  const tri = [...cadres].sort((a, b) => a.y - b.y);
  const rangees: T[][] = [];
  for (const c of tri) {
    const r = rangees[rangees.length - 1];
    // même rangée si le haut du cadre tombe dans la moitié haute de la rangée en cours
    if (r && c.y < r[0]!.y + r[0]!.hauteur / 2) r.push(c);
    else rangees.push([c]);
  }
  return rangees.flatMap((r) => r.sort((a, b) => a.x - b.x));
}
