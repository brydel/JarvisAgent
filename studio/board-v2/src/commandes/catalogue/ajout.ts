// Ajouter au Board : note, lien, fichiers, dossier, presse-papiers, mission. Mêmes actions que la barre d'ajout.
import { ClipboardPaste, File, Folder, Image as IconeImage, Link2, Mic, NotebookPen, Sparkles, Upload, Video } from "lucide-react";
import { enLecture, type ContexteBoard } from "../contexte";
import type { Commande, Icone } from "../types";

const FICHIERS: [string, string, Icone, string][] = [
  ["importer", "Importer des fichiers", Upload, "image/*,audio/*,video/*,application/pdf"],
  ["image", "Ajouter une image", IconeImage, "image/png,image/jpeg,image/webp,image/gif"],
  ["video", "Ajouter une vidéo", Video, "video/*"],
  ["audio", "Ajouter un audio", Mic, "audio/*"],
  ["document", "Ajouter un document PDF", File, "application/pdf"],
];

export const commandesAjout: Commande<ContexteBoard>[] = [
  { id: "ajouter.note", libelle: "Ajouter une note", icone: NotebookPen, raccourci: "shift+n", categorie: "Ajouter", niveau: "ecriture", emplacements: ["menu"],
    motsCles: "carte texte markdown",
    disponible: (c) => !enLecture(c) && !c.lien && c.selection.length === 0,
    executer: async (c) => {
      const p = c.point ?? c.b.centreVue();
      await c.b.creer({ type: "note", contenu: "Nouvelle note", x: Math.round(p.x), y: Math.round(p.y), largeur: 408, hauteur: 320, meta: { titre: "Note" }, analyser: false });
    } },
  { id: "ajouter.lien", libelle: "Ajouter un lien", icone: Link2, categorie: "Ajouter", niveau: "ecriture", motsCles: "url adresse site",
    disponible: (c) => !enLecture(c), executer: (c) => c.b.saisirLien() },
  ...FICHIERS.map(([cle, libelle, icone, accept]): Commande<ContexteBoard> => ({
    id: `ajouter.${cle}`, libelle, icone, categorie: "Ajouter", niveau: "ecriture", motsCles: "fichier téléverser",
    disponible: (c) => !enLecture(c), executer: (c) => c.b.choisirFichiers(accept),
  })),
  { id: "ajouter.dossier", libelle: "Ajouter un dossier", icone: Folder, categorie: "Ajouter", niveau: "ecriture", motsCles: "ranger",
    disponible: (c) => !enLecture(c),
    executer: async (c) => {
      const p = c.point ?? c.b.centreVue();
      await c.b.creer({ type: "dossier", x: Math.round(p.x), y: Math.round(p.y), largeur: 378, hauteur: 152, meta: { titre: "Nouveau dossier" } });
      c.b.toast("Dossier créé : glisse des cartes dessus pour les y ranger");
    } },
  { id: "ajouter.pressePapiers", libelle: "Coller le presse-papiers", icone: ClipboardPaste, categorie: "Ajouter", niveau: "ecriture",
    motsCles: "image texte lien", disponible: (c) => !enLecture(c), executer: (c) => c.b.collerPressePapiers() },
  { id: "mission.lancer", libelle: "Lancer une mission…", icone: Sparkles, raccourci: "mod+shift+m", categorie: "Ajouter", niveau: "ecriture",
    motsCles: "agent objectif travail", disponible: (c) => !enLecture(c), executer: (c) => c.b.ouvrirMission() },
];
