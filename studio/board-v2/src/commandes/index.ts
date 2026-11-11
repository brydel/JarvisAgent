// Le registre du Board : toutes les commandes, déclarées une fois. Voir types.ts pour le contrat.
import { Command, Download, Search } from "lucide-react";
import { commandesAffichage } from "./catalogue/affichage";
import { commandesAjout } from "./catalogue/ajout";
import { commandesCartes } from "./catalogue/cartes";
import { commandesDisposition } from "./catalogue/disposition";
import { commandesEdition } from "./catalogue/edition";
import { commandesNavigation } from "./catalogue/navigation";
import { commandesOutils } from "./catalogue/outils";
import type { ContexteBoard } from "./contexte";
import { JournalUsage } from "./journal";
import { Registre, type OptionsRegistre } from "./registre";

export type RegistreBoard = Registre<ContexteBoard>;

/** Enregistre un texte comme fichier téléchargé (journal d'usage). */
function telecharger(nom: string, contenu: string, type: string) {
  const url = URL.createObjectURL(new Blob([contenu], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nom;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function creerRegistreBoard(options: OptionsRegistre<ContexteBoard> = {}): RegistreBoard {
  const registre = new Registre<ContexteBoard>({ journal: new JournalUsage(), ...options });
  return registre.declarer([
    { id: "palette.ouvrir", libelle: "Palette de commandes", icone: Command, raccourci: ["mod+k", "mod+shift+p"], categorie: "Navigation", niveau: "lecture",
      motsCles: "chercher une action", executer: (c) => c.b.ui.definir({ palette: !c.ui.palette, menu: null }) },
    { id: "navigation.rechercher", libelle: "Rechercher dans le Board", icone: Search, raccourci: ["/", "mod+f"], categorie: "Navigation", niveau: "lecture",
      motsCles: "filtrer trouver une carte", disponible: (c) => c.ui.presentation === null && !c.ui.zen,
      raison: (c) => (c.ui.presentation !== null ? "La recherche est masquée pendant la présentation" : "La recherche est masquée en mode zen : quitte-le avec Ctrl+."),
      executer: () => document.querySelector<HTMLInputElement>(".topbar input[type='search']")?.focus() },
    { id: "menu.ouvrir", libelle: "Ouvrir le menu contextuel", raccourci: ["shift+f10", "contextmenu"], categorie: "Navigation", niveau: "lecture",
      motsCles: "clic droit actions", disponible: (c) => c.ui.presentation === null, raison: () => "Aucun menu pendant la présentation",
      // au clavier : le menu s'ouvre au centre du canevas, sur la sélection en cours
      executer: (c) => {
        const r = document.querySelector(".canevas")?.getBoundingClientRect();
        if (r) c.b.ui.definir({ menu: { x: r.left + r.width / 2 - 120, y: r.top + r.height / 3, cible: c.selection[0]?.id, point: c.b.centreVue() } });
      } },
    // Échap suit l'ordre de déclaration : affichage (présentation, concentration, zen, outil, sélection) d'abord
    ...commandesAffichage,
    ...commandesOutils,
    ...commandesEdition,
    ...commandesDisposition,
    ...commandesCartes,
    ...commandesAjout,
    ...commandesNavigation,
    { id: "export.journal", libelle: "Exporter mon journal d'usage des commandes (JSON)", icone: Download, categorie: "Export", niveau: "lecture",
      motsCles: "préférences statistiques apprentissage",
      executer: () => telecharger("jarvis-board-commandes.json", JSON.stringify(registre.journal.exporter(), null, 1), "application/json") },
  ]);
}

export * from "./types";
export type { ContexteBoard, ServicesBoard } from "./contexte";
