// Outils du tableau blanc : un mode à la fois, une touche chacun (V, H, N, T, R, O, D, A, P, S, E, F, L).
import { Circle, Diamond, Eraser, Frame, Hand, Highlighter, Lasso, MousePointer2, MoveUpRight, Pencil, Square, StickyNote, Type } from "lucide-react";
import type { IdOutil } from "../../etat/ui";
import { enLecture, raisonLecture, type ContexteBoard } from "../contexte";
import type { Commande, Icone } from "../types";

export interface DefOutil {
  id: IdOutil;
  libelle: string;
  touche: string;
  icone: Icone;
  aide: string;
  /** groupe visuel de la barre d'outils */
  groupe: "pointeur" | "contenu" | "forme" | "dessin";
}

export const OUTILS: DefOutil[] = [
  { id: "selection", libelle: "Sélection", touche: "v", icone: MousePointer2, groupe: "pointeur", aide: "Sélectionner, déplacer, redimensionner" },
  { id: "main", libelle: "Main", touche: "h", icone: Hand, groupe: "pointeur", aide: "Déplacer la vue sans rien sélectionner" },
  { id: "lasso", libelle: "Lasso", touche: "l", icone: Lasso, groupe: "pointeur", aide: "Entourer des objets pour les sélectionner" },
  { id: "adhesif", libelle: "Note adhésive", touche: "n", icone: StickyNote, groupe: "contenu", aide: "Cliquer pour poser une note adhésive" },
  { id: "texte", libelle: "Texte", touche: "t", icone: Type, groupe: "contenu", aide: "Cliquer pour écrire directement sur le canevas" },
  { id: "cadre", libelle: "Cadre", touche: "f", icone: Frame, groupe: "contenu", aide: "Tracer un cadre : il emporte son contenu et devient une diapositive" },
  { id: "rectangle", libelle: "Rectangle", touche: "r", icone: Square, groupe: "forme", aide: "Tracer un rectangle" },
  { id: "ellipse", libelle: "Ellipse", touche: "o", icone: Circle, groupe: "forme", aide: "Tracer une ellipse" },
  { id: "losange", libelle: "Losange", touche: "d", icone: Diamond, groupe: "forme", aide: "Tracer un losange" },
  { id: "fleche", libelle: "Flèche", touche: "a", icone: MoveUpRight, groupe: "forme", aide: "Tirer une flèche ; d'une carte à une autre, elle crée une relation" },
  { id: "crayon", libelle: "Crayon", touche: "p", icone: Pencil, groupe: "dessin", aide: "Dessiner à main levée (souris, doigt ou stylet avec pression)" },
  { id: "surligneur", libelle: "Surligneur", touche: "s", icone: Highlighter, groupe: "dessin", aide: "Surligner en transparence" },
  { id: "gomme", libelle: "Gomme", touche: "e", icone: Eraser, groupe: "dessin", aide: "Effacer traits, formes et notes adhésives (jamais une carte)" },
];

export const commandesOutils: Commande<ContexteBoard>[] = OUTILS.map((o) => ({
  id: `outil.${o.id}`, libelle: `Outil : ${o.libelle}`, icone: o.icone, raccourci: o.touche, categorie: "Outils", niveau: "lecture",
  motsCles: `${o.aide} mode`,
  disponible: (c) => !enLecture(c), raison: raisonLecture,
  actif: (c) => c.ui.outil === o.id,
  executer: (c) => c.b.ui.definir({ outil: o.id, liaison: null }),
}));
