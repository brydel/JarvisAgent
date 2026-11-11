// Disposition : aligner et répartir la sélection (calcul pur dans outils/disposition.ts, une écriture annulable).
import { AlignCenterHorizontal, AlignCenterVertical, AlignEndHorizontal, AlignEndVertical, AlignHorizontalSpaceAround, AlignStartHorizontal, AlignStartVertical, AlignVerticalSpaceAround } from "lucide-react";
import { aligner, repartir, type Alignement, type Axe, type Deplacement } from "../../outils/disposition";
import { enLecture, type ContexteBoard } from "../contexte";
import type { Commande, Icone } from "../types";

const places = (c: ContexteBoard) => c.selection.filter((o) => !o.verrouille).map((o) => ({ id: o.id, x: o.x, y: o.y, largeur: o.largeur, hauteur: o.hauteur }));
const ecrire = (c: ContexteBoard, d: Deplacement[], libelle: string) =>
  (d.length ? c.b.modifier(d.map((m) => ({ id: m.id, champs: { x: m.x, y: m.y } })), libelle) : Promise.resolve());

const ALIGNEMENTS: [Alignement, string, string, Icone][] = [
  ["gauche", "Aligner à gauche", "alt+a", AlignStartVertical],
  ["centreV", "Centrer verticalement", "alt+h", AlignCenterVertical],
  ["droite", "Aligner à droite", "alt+d", AlignEndVertical],
  ["haut", "Aligner en haut", "alt+w", AlignStartHorizontal],
  ["centreH", "Centrer horizontalement", "alt+v", AlignCenterHorizontal],
  ["bas", "Aligner en bas", "alt+s", AlignEndHorizontal],
];
const REPARTITIONS: [Axe, string, string, Icone][] = [
  ["horizontal", "Répartir horizontalement", "alt+shift+h", AlignHorizontalSpaceAround],
  ["vertical", "Répartir verticalement", "alt+shift+v", AlignVerticalSpaceAround],
];

export const commandesDisposition: Commande<ContexteBoard>[] = [
  ...ALIGNEMENTS.map(([mode, libelle, raccourci, icone]): Commande<ContexteBoard> => ({
    id: `disposition.aligner.${mode}`, libelle, icone, raccourci, categorie: "Disposition", niveau: "ecriture", emplacements: ["flottante", "menu"],
    disponible: (c) => !enLecture(c) && places(c).length > 1,
    executer: (c) => ecrire(c, aligner(places(c), mode), "Alignement"),
  })),
  ...REPARTITIONS.map(([axe, libelle, raccourci, icone]): Commande<ContexteBoard> => ({
    id: `disposition.repartir.${axe}`, libelle, icone, raccourci, categorie: "Disposition", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "espacer distribuer",
    disponible: (c) => !enLecture(c) && places(c).length > 2,
    executer: (c) => ecrire(c, repartir(places(c), axe), "Répartition"),
  })),
];
