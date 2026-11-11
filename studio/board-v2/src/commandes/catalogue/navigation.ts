// Navigation au clavier entre les objets : Alt+flèche sélectionne l'objet voisin dans cette direction, lui donne le
// focus (lecteurs d'écran : son nom est annoncé) et amène la vue dessus s'il est hors champ. Tab parcourt aussi les
// objets visibles (comportement de React Flow) ; les flèches seules déplacent l'objet sélectionné.
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp } from "lucide-react";
import { boiteDe } from "../../outils/espace";
import { centre, type Point } from "../../outils/geometrie";
import type { ObjetBoard } from "../../types";
import { enLecture, raisonLecture, un, type ContexteBoard } from "../contexte";
import type { Commande, Icone } from "../types";

/** Voisin de `depuis` dans la direction (ux, uy) : le plus proche, les objets bien dans l'axe d'abord. */
export function voisin(objets: readonly ObjetBoard[], depuis: Point, ux: number, uy: number, sauf?: string): ObjetBoard | undefined {
  let meilleur: ObjetBoard | undefined, cout = Infinity;
  for (const o of objets) {
    if (o.id === sauf || o.parent_id) continue;
    const c = centre(boiteDe(o));
    const dx = c.x - depuis.x, dy = c.y - depuis.y;
    const avance = dx * ux + dy * uy, ecart = Math.abs(dx * uy - dy * ux);
    if (avance <= 1 || ecart > avance * 2) continue;  // derrière, ou trop de côté (hors d'un cône de ±63°)
    const valeur = avance + 2 * ecart;
    if (valeur < cout) {
      cout = valeur;
      meilleur = o;
    }
  }
  return meilleur;
}

const DIRECTIONS: [string, string, string, number, number, Icone][] = [
  ["droite", "à droite", "alt+droite", 1, 0, ArrowRight], ["gauche", "à gauche", "alt+gauche", -1, 0, ArrowLeft],
  ["haut", "au-dessus", "alt+haut", 0, -1, ArrowUp], ["bas", "en dessous", "alt+bas", 0, 1, ArrowDown],
];

export const commandesNavigation: Commande<ContexteBoard>[] = DIRECTIONS.map(([cle, nom, raccourci, ux, uy, icone]) => ({
  id: `navigation.objet.${cle}`, libelle: `Aller à l'objet ${nom}`, icone, raccourci, categorie: "Navigation", niveau: "lecture",
  motsCles: "clavier voisin suivant sélectionner",
  disponible: (c) => !enLecture(c) && c.b.objets().length > 0,
  raison: (c) => raisonLecture(c) ?? "Le Board est vide : il n'y a aucun objet où aller",
  executer: (c) => {
    const actuel = un(c) ?? c.selection[0];
    const depuis = actuel ? centre(boiteDe(actuel)) : c.b.centreVue();
    const cible = voisin(c.b.objets(), depuis, ux, uy, actuel?.id);
    if (!cible) return;
    c.b.selectionner([cible.id]);
    c.b.montrer(boiteDe(cible));
    if (typeof document !== "undefined") {
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(cible.id)}"]`)?.focus({ preventScroll: true }));
    }
  },
}));
