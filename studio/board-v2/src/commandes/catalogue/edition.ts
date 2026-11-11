// Édition : annuler / rétablir, presse-papiers, dupliquer, supprimer, verrouiller, ordre, grouper, encadrer.
import { ArrowDownToLine, ArrowUpToLine, ClipboardPaste, Copy, CopyPlus, FolderInput, Frame, Lock, LockOpen, Redo2, Scissors, SquareDashedMousePointer, Trash2, Undo2 } from "lucide-react";
import { boiteDe } from "../../outils/espace";
import { englobante } from "../../outils/geometrie";
import { enLecture, ids, raisonLecture, raisonSelection, type ContexteBoard } from "../contexte";
import type { Commande } from "../types";

const avecSelection = (c: ContexteBoard) => c.selection.length > 0 && !enLecture(c);
/** les cartes de mission et d'équipe représentent un travail réel : on ne les recopie pas */
const copiables = (c: ContexteBoard) => c.selection.filter((o) => o.type !== "mission" && o.type !== "agents").map((o) => o.id);
const RAISON_TRAVAIL = "Une carte de mission ou d'équipe représente un travail réel : elle ne se copie pas";
const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? "s" : ""}`;

export const commandesEdition: Commande<ContexteBoard>[] = [
  { id: "edition.annuler", libelle: "Annuler", icone: Undo2, raccourci: "mod+z", categorie: "Édition", niveau: "ecriture",
    disponible: (c) => !enLecture(c) && c.b.historique().annuler !== null, concerne: () => true,
    raison: (c) => raisonLecture(c) ?? "Rien à annuler : aucun geste n'a encore été fait sur ce Board", executer: (c) => c.b.annuler() },
  { id: "edition.retablir", libelle: "Rétablir", icone: Redo2, raccourci: ["mod+shift+z", "mod+y"], categorie: "Édition", niveau: "ecriture",
    disponible: (c) => !enLecture(c) && c.b.historique().refaire !== null, concerne: () => true,
    raison: (c) => raisonLecture(c) ?? "Rien à rétablir : aucun geste n'a été annulé", executer: (c) => c.b.retablir() },
  { id: "edition.copier", libelle: "Copier", icone: Copy, raccourci: "mod+c", categorie: "Édition", niveau: "lecture", emplacements: ["menu"],
    disponible: (c) => c.selection.length > 0, raison: () => "Sélectionne d'abord ce que tu veux copier", executer: (c) => c.b.copier(ids(c)) },
  { id: "edition.couper", libelle: "Couper", icone: Scissors, raccourci: "mod+x", categorie: "Édition", niveau: "ecriture", emplacements: ["menu"],
    disponible: (c) => avecSelection(c) && copiables(c).length === c.selection.length,
    concerne: (c) => c.selection.length > 0, raison: (c) => raisonSelection(c) ?? RAISON_TRAVAIL.replace("copie", "coupe"),
    executer: async (c) => {
      c.b.copier(ids(c));
      await c.b.supprimer(ids(c));
    } },
  { id: "edition.coller", libelle: "Coller ici", icone: ClipboardPaste, categorie: "Édition", niveau: "ecriture", emplacements: ["menu"],
    motsCles: "presse-papiers ctrl v",
    disponible: (c) => !enLecture(c) && !c.lien && c.b.peutColler(), concerne: (c) => !c.lien && c.selection.length === 0,
    raison: (c) => raisonLecture(c) ?? (c.lien ? null : "Presse-papiers du Board vide : copie d'abord un objet (Ctrl+C)"),
    executer: (c) => c.b.coller(c.point) },
  { id: "edition.dupliquer", libelle: "Dupliquer", icone: CopyPlus, raccourci: "mod+d", categorie: "Édition", niveau: "ecriture", emplacements: ["menu", "flottante"],
    disponible: (c) => avecSelection(c) && copiables(c).length > 0,
    concerne: (c) => c.selection.length > 0, raison: (c) => raisonSelection(c) ?? RAISON_TRAVAIL.replace("copie", "duplique"),
    executer: async (c) => { c.b.selectionner(await c.b.dupliquer(copiables(c))); } },
  { id: "edition.supprimer", libelle: "Supprimer", icone: Trash2, raccourci: ["suppr", "retour"], categorie: "Édition", niveau: "ecriture",
    emplacements: ["menu", "flottante"], disponible: avecSelection, raison: raisonSelection,
    confirmation: (c) => (c.selection.length >= 10 ? `Supprimer ${c.selection.length} objets ? (Ctrl+Z pour annuler)` : null),
    executer: (c) => c.b.supprimer(ids(c)) },
  { id: "edition.toutSelectionner", libelle: "Tout sélectionner", icone: SquareDashedMousePointer, raccourci: "mod+a", categorie: "Édition", niveau: "lecture",
    disponible: (c) => !enLecture(c), raison: raisonLecture, executer: (c) => c.b.selectionner(c.b.visibles()) },
  { id: "edition.verrouiller", libelle: (c) => (c.selection.every((o) => o.verrouille) ? "Déverrouiller" : "Verrouiller"), icone: Lock,
    raccourci: "mod+shift+l", categorie: "Édition", niveau: "ecriture", emplacements: ["menu", "flottante"], motsCles: "figer bloquer la position",
    disponible: avecSelection, raison: raisonSelection,
    executer: (c) => {
      const verrouille = !c.selection.every((o) => o.verrouille);
      return c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { verrouille } })), verrouille ? "Verrouillage" : "Déverrouillage");
    } },
  { id: "edition.devant", libelle: "Amener devant", icone: ArrowUpToLine, raccourci: "]", categorie: "Édition", niveau: "ecriture", emplacements: ["menu", "flottante"],
    disponible: avecSelection, raison: raisonSelection,
    executer: (c) => {
      const max = c.b.objets().reduce((m, o) => Math.max(m, o.z), 0);
      return c.b.modifier(c.selection.map((o, i) => ({ id: o.id, champs: { z: max + 1 + i } })), "Amener devant");
    } },
  { id: "edition.derriere", libelle: "Envoyer derrière", icone: ArrowDownToLine, raccourci: "[", categorie: "Édition", niveau: "ecriture", emplacements: ["menu"],
    disponible: avecSelection, raison: raisonSelection,
    executer: (c) => {
      const min = c.b.objets().reduce((m, o) => Math.min(m, o.z), 0);
      return c.b.modifier(c.selection.map((o, i) => ({ id: o.id, champs: { z: min - c.selection.length + i } })), "Envoyer derrière");
    } },
  { id: "edition.grouper", libelle: "Grouper dans un dossier", icone: FolderInput, raccourci: "mod+g", categorie: "Édition", niveau: "ecriture",
    emplacements: ["menu", "flottante"], motsCles: "ranger regrouper",
    disponible: (c) => c.selection.length > 1 && !enLecture(c) && c.selection.every((o) => o.type !== "dossier"),
    concerne: (c) => c.selection.length > 1,
    raison: (c) => raisonLecture(c) ?? (c.selection.length < 2 ? "Sélectionne au moins deux cartes à ranger ensemble" : "Un dossier ne se range pas dans un autre dossier : retire-le de la sélection"),
    executer: (c) => c.b.grouper("Groupe", async () => {
      const zone = englobante(c.selection.map(boiteDe))!;
      const dossier = await c.b.creer({ type: "dossier", x: zone.x, y: zone.y - 200, largeur: 378, hauteur: 152, meta: { titre: "Groupe" } }, "Groupe");
      await c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { parent_id: dossier } })), "Groupe");
      c.b.toast(`${pluriel(c.selection.length, "carte")} rangée${c.selection.length > 1 ? "s" : ""} dans un dossier`);
    }) },
  { id: "edition.encadrer", libelle: "Encadrer la sélection", icone: Frame, raccourci: "mod+shift+g", categorie: "Édition", niveau: "ecriture",
    emplacements: ["menu", "flottante"], motsCles: "cadre section diapositive",
    disponible: (c) => c.selection.length > 0 && !enLecture(c) && c.selection.every((o) => o.type !== "cadre"),
    raison: (c) => raisonSelection(c) ?? "Un cadre ne s'encadre pas : retire-le de la sélection",
    executer: async (c) => {
      const zone = englobante(c.selection.map(boiteDe))!;
      const marge = 48;
      const id = await c.b.creer({ type: "cadre", x: Math.round(zone.x - marge), y: Math.round(zone.y - marge - 24),
        largeur: Math.round(zone.largeur + 2 * marge), hauteur: Math.round(zone.hauteur + 2 * marge + 24), meta: { titre: "Cadre" }, analyser: false }, "Cadre");
      c.b.selectionner([id]);
    } },
  { id: "edition.deverrouillerTout", libelle: "Déverrouiller tout le Board", icone: LockOpen, categorie: "Édition", niveau: "ecriture",
    disponible: (c) => !enLecture(c) && c.b.objets().some((o) => o.verrouille),
    raison: (c) => raisonLecture(c) ?? "Aucun objet n'est verrouillé sur ce Board",
    executer: (c) => c.b.modifier(c.b.objets().filter((o) => o.verrouille).map((o) => ({ id: o.id, champs: { verrouille: false } })), "Déverrouillage") },
];
