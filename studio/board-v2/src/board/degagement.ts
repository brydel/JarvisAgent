// Place libre autour d'une carte. Les lignes posées HORS de la carte (effets de ses relations et ligne de crédit
// dessous, états dessus) ne doivent jamais recouvrir une carte voisine : on mesure donc l'espace réellement libre,
// en unités du canevas, et la carte n'affiche dehors que ce qui y tient. Le reste se replie dans son propre cadre.
//
// Le calcul se fait une fois par instantané du Board, avec l'index spatial déjà construit pour le lasso et les
// guides ; chaque carte lit ensuite SA valeur (un entier), sans abonnement au store de React Flow.
import { useSyncExternalStore } from "react";
import type { IndexSpatial } from "../outils/espace";
import type { ObjetBoard } from "../types";

/** Au-delà, la place ne manque plus : inutile de chercher plus loin. */
export const PORTEE = 160;
/** Hauteur d'une ligne posée sous la carte, et écart entre deux lignes. */
export const LIGNE = 28;
export const ECART = 4;
/** Distance entre le bord de la carte et la première ligne, et marge gardée avant la carte voisine. */
export const MARGE = 8;
/** Hauteur de la ligne de crédit (provenance). */
export const CREDIT = 20;
/** Débord des états au-dessus de la carte, marge comprise. */
export const DEBORD_HAUT = 20;

export interface Degagement {
  /** espace libre sous la carte, plafonné à PORTEE */
  dessous: number;
  /** espace libre au-dessus de la carte, plafonné à PORTEE */
  dessus: number;
}

const LIBRE: Degagement = { dessous: PORTEE, dessus: PORTEE };
/** objets qui n'occupent pas la place : un cadre entoure, un trait ou une flèche traverse */
const TRAVERSANTS = new Set<string>(["cadre", "trait", "fleche"]);

/** Espace libre sous et au-dessus de `o`, jusqu'au premier objet visible qui partage sa colonne. */
export function degagementDe(o: ObjetBoard, index: IndexSpatial, visible: (v: ObjetBoard) => boolean = () => true): Degagement {
  const l = o.largeur || 1, h = o.hauteur || 1;
  const bas = o.y + h;
  let dessous = PORTEE, dessus = PORTEE;
  for (const v of index.dans({ x: o.x, y: o.y - PORTEE, largeur: l, hauteur: h + 2 * PORTEE })) {
    if (v.id === o.id || TRAVERSANTS.has(v.type) || !visible(v)) continue;
    // un objet qui ne fait que toucher le bord de la colonne ne gêne pas
    if (v.x + (v.largeur || 1) <= o.x || v.x >= o.x + l) continue;
    const vBas = v.y + (v.hauteur || 1);
    if (v.y < bas && vBas > bas) dessous = 0;              // chevauche le bord du bas
    else if (v.y >= bas) dessous = Math.min(dessous, v.y - bas);
    if (v.y < o.y && vBas > o.y) dessus = 0;               // chevauche le bord du haut
    else if (vBas <= o.y) dessus = Math.min(dessus, o.y - vBas);
  }
  return { dessous: Math.max(0, Math.round(dessous)), dessus: Math.max(0, Math.round(dessus)) };
}

/** Nombre de lignes de relation qui tiennent sous la carte, sans toucher la voisine. */
export function lignesQuiTiennent(dessous: number): number {
  return Math.max(0, Math.floor((dessous - 2 * MARGE + ECART) / (LIGNE + ECART)));
}

/** Vrai si la ligne de crédit tient encore sous `lignes` lignes de relation. */
export function creditTient(dessous: number, lignes: number): boolean {
  const occupe = lignes ? lignes * (LIGNE + ECART) : 0;
  return dessous >= MARGE + occupe + CREDIT + MARGE;
}

/* ---------------------------------------------------------------- distribution aux cartes -------------------- */
// Un entier par carte (dessous + 1000 × dessus) : la carte ne se re-rend que si SA place change.
let courant = new Map<string, number>();
const abonnes = new Set<() => void>();
const abonner = (f: () => void) => {
  abonnes.add(f);
  return () => abonnes.delete(f);
};
const coder = (d: Degagement) => d.dessous + 1000 * d.dessus;
const LIBRE_CODE = coder(LIBRE);

/** Publie les dégagements de l'instantané courant (appelé par le canevas). */
export function publierDegagements(valeurs: Map<string, Degagement>): void {
  courant = new Map([...valeurs].map(([id, d]) => [id, coder(d)]));
  for (const f of abonnes) f();
}

/** Place libre autour de cette carte ; « tout est libre » tant que rien n'a été mesuré. */
export function useDegagement(id: string): Degagement {
  const code = useSyncExternalStore(abonner, () => courant.get(id) ?? LIBRE_CODE, () => LIBRE_CODE);
  return { dessous: code % 1000, dessus: Math.floor(code / 1000) };
}
