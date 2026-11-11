// Requêtes spatiales sur les objets du Board : index R-tree (rbush, MIT) construit une fois par instantané du
// store et réutilisé par le lasso, la gomme, les guides magnétiques et les cadres. Chercher « ce qui touche cette
// zone » coûte alors O(log n + résultats) au lieu d'un parcours des 5 000 objets à chaque image d'un geste.
import RBush from "rbush";
import type { ObjetBoard } from "../types";
import { centre, contient, dansPolygone, distanceSegments, englobante, seChevauchent, type Boite, type Point } from "./geometrie";

interface Feuille {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  objet: ObjetBoard;
}

export const boiteDe = (o: Pick<ObjetBoard, "x" | "y" | "largeur" | "hauteur">): Boite => ({ x: o.x, y: o.y, largeur: o.largeur || 1, hauteur: o.hauteur || 1 });

/** Types du tableau blanc : seuls objets que la gomme efface (une carte de travail ne s'efface pas d'un coup de gomme). */
export const TYPES_TABLEAU = new Set<string>(["adhesif", "texte_libre", "forme", "trait", "cadre", "fleche"]);

export class IndexSpatial {
  private arbre = new RBush<Feuille>();
  readonly taille: number;

  constructor(objets: readonly ObjetBoard[]) {
    const feuilles: Feuille[] = [];
    for (const o of objets) {
      if (o.parent_id) continue;  // rangé dans un dossier : pas sur le canevas
      feuilles.push({ minX: o.x, minY: o.y, maxX: o.x + (o.largeur || 1), maxY: o.y + (o.hauteur || 1), objet: o });
    }
    this.arbre.load(feuilles);
    this.taille = feuilles.length;
  }

  /** Objets dont la boîte touche la zone. */
  dans(zone: Boite): ObjetBoard[] {
    return this.arbre.search({ minX: zone.x, minY: zone.y, maxX: zone.x + zone.largeur, maxY: zone.y + zone.hauteur }).map((f) => f.objet);
  }
}

const parInstantane = new WeakMap<readonly ObjetBoard[], IndexSpatial>();

/** Index de cet instantané (le tableau `objets` du store change d'identité à chaque modification). */
export function indexDe(objets: readonly ObjetBoard[]): IndexSpatial {
  let index = parInstantane.get(objets);
  if (!index) parInstantane.set(objets, (index = new IndexSpatial(objets)));
  return index;
}

/** Lasso : objets dont le centre est dans le polygone. */
export function dansLeLasso(index: IndexSpatial, polygone: readonly Point[]): ObjetBoard[] {
  const zone = englobante(polygone.map((p) => ({ ...p, largeur: 0, hauteur: 0 })));
  if (!zone || polygone.length < 3) return [];
  return index.dans(zone).filter((o) => dansPolygone(centre(boiteDe(o)), polygone));
}

/** Contenu d'un cadre : objets dont le centre est dans le cadre (ni lui-même, ni un cadre qui le contient). */
export function contenuDuCadre(index: IndexSpatial, cadre: ObjetBoard): ObjetBoard[] {
  const zone = boiteDe(cadre);
  return index.dans(zone).filter((o) => o.id !== cadre.id && contient(zone, centre(boiteDe(o)))
    && !(o.type === "cadre" && o.largeur * o.hauteur >= cadre.largeur * cadre.hauteur));
}

/** Vrai si le coup de gomme [a → b] de rayon `rayon` touche l'objet : test fin sur les points d'un trait, boîte sinon. */
export function gommeTouche(o: ObjetBoard, a: Point, b: Point, rayon: number): boolean {
  const zone = boiteDe(o);
  const coup = { x: Math.min(a.x, b.x) - rayon, y: Math.min(a.y, b.y) - rayon, largeur: Math.abs(a.x - b.x) + 2 * rayon, hauteur: Math.abs(a.y - b.y) + 2 * rayon };
  if (!seChevauchent(zone, coup)) return false;
  const points = o.type === "trait" && Array.isArray(o.meta.points) ? o.meta.points : null;
  if (!points || points.length < 6) return true;
  const [l0, h0] = o.meta.boite ?? [o.largeur, o.hauteur];
  const ex = o.largeur / (l0 || 1), ey = o.hauteur / (h0 || 1);
  const seuil = rayon + (Number(o.meta.epaisseur) || 4) / 2;
  for (let i = 0; i + 5 < points.length; i += 3) {
    const p = { x: o.x + points[i]! * ex, y: o.y + points[i + 1]! * ey }, q = { x: o.x + points[i + 3]! * ex, y: o.y + points[i + 4]! * ey };
    if (distanceSegments(a, b, p, q) <= seuil) return true;
  }
  return false;
}

/** Objets de tableau blanc touchés par un coup de gomme. */
export function sousLaGomme(index: IndexSpatial, a: Point, b: Point, rayon: number): ObjetBoard[] {
  const zone = { x: Math.min(a.x, b.x) - rayon, y: Math.min(a.y, b.y) - rayon, largeur: Math.abs(a.x - b.x) + 2 * rayon, hauteur: Math.abs(a.y - b.y) + 2 * rayon };
  return index.dans(zone).filter((o) => TYPES_TABLEAU.has(o.type) && o.type !== "cadre" && !o.verrouille && gommeTouche(o, a, b, rayon));
}

/** Objet le plus haut sous un point (pour ancrer une flèche) ; les cadres et les traits ne s'ancrent pas. */
export function sousLePoint(index: IndexSpatial, p: Point, sauf?: string): ObjetBoard | undefined {
  return index.dans({ x: p.x, y: p.y, largeur: 0, hauteur: 0 })
    .filter((o) => o.id !== sauf && o.type !== "cadre" && o.type !== "trait" && o.type !== "fleche")
    .sort((a, b) => b.z - a.z)[0];
}

/* ---------------------------------------------------------------- guides magnétiques ---------------------- */
export interface Guide {
  /** « x » : ligne verticale à l'abscisse `position` ; « y » : ligne horizontale à l'ordonnée `position` */
  axe: "x" | "y";
  position: number;
  debut: number;
  fin: number;
}

export interface Accroche {
  dx: number;
  dy: number;
  guides: Guide[];
}

/** Accroche d'une boîte en mouvement sur les bords et les centres de ses voisines. `seuil` en unités du canevas
 *  (quelques pixels écran divisés par le zoom). Rend le décalage à appliquer et les lignes à montrer. */
export function accrocher(mobile: Boite, voisines: readonly Boite[], seuil: number): Accroche {
  const reperes = (b: Boite, axe: "x" | "y") => (axe === "x" ? [b.x, b.x + b.largeur / 2, b.x + b.largeur] : [b.y, b.y + b.hauteur / 2, b.y + b.hauteur]);
  const sortie: Accroche = { dx: 0, dy: 0, guides: [] };
  for (const axe of ["x", "y"] as const) {
    let meilleur = seuil + 1e-9, delta = 0;
    for (const v of voisines) {
      for (const m of reperes(mobile, axe)) {
        for (const r of reperes(v, axe)) {
          if (Math.abs(r - m) < meilleur) {
            meilleur = Math.abs(r - m);
            delta = r - m;
          }
        }
      }
    }
    if (meilleur > seuil) continue;
    if (axe === "x") sortie.dx = delta;
    else sortie.dy = delta;
    // toutes les voisines alignées sur la position retenue : une ligne par repère, étendue d'un objet à l'autre
    const cale: Boite = axe === "x" ? { ...mobile, x: mobile.x + delta } : { ...mobile, y: mobile.y + delta };
    for (const m of reperes(cale, axe)) {
      const alignees = voisines.filter((v) => reperes(v, axe).some((r) => Math.abs(r - m) < 0.01));
      if (!alignees.length) continue;
      const tout = englobante([cale, ...alignees])!;
      sortie.guides.push(axe === "x" ? { axe, position: m, debut: tout.y, fin: tout.y + tout.hauteur } : { axe, position: m, debut: tout.x, fin: tout.x + tout.largeur });
    }
  }
  return sortie;
}
