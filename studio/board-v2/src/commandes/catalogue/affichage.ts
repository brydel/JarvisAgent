// Affichage : thème, plein écran, zen, concentration sur un cadre, présentation (cadres = diapositives), zoom.
import { ChevronLeft, ChevronRight, Focus, Grid3x3, Magnet, Map as IconeCarte, Maximize, Maximize2, Minimize2, Moon, MousePointer2, PanelTopClose, Presentation, Sun, SunMoon, X, ZoomIn, ZoomOut } from "lucide-react";
import type { Theme } from "../../etat/ui";
import { ordreDeLecture } from "../../outils/disposition";
import { boiteDe } from "../../outils/espace";
import { englobante } from "../../outils/geometrie";
import type { ObjetBoard } from "../../types";
import { deType, type ContexteBoard } from "../contexte";
import type { Commande, Icone } from "../types";

/** Cadres du Board dans l'ordre de lecture : ce sont les diapositives de la présentation. */
export function diapositives(objets: readonly ObjetBoard[]): ObjetBoard[] {
  return ordreDeLecture(objets.filter((o) => o.type === "cadre" && !o.parent_id).map((o) => ({ ...boiteDe(o), objet: o }))).map((c) => c.objet);
}

function montrer(c: ContexteBoard, index: number): void {
  const cadres = diapositives(c.b.objets());
  if (!cadres.length) return;
  const i = Math.max(0, Math.min(cadres.length - 1, index));
  c.b.ui.definir({ presentation: i, focus: cadres[i]!.id, outil: "selection", menu: null, edition: null });
  c.b.selectionner([]);
  c.b.cadrer(boiteDe(cadres[i]!), MARGE_DIAPOSITIVE);
}

/** Marge autour d'une diapositive (part de l'écran). Le canevas la recadre aussi quand la fenêtre change de taille
 *  (entrée en plein écran, barres masquées). */
export const MARGE_DIAPOSITIVE = 0.04;

const THEMES: [Theme, string, Icone, string][] = [
  ["nuit", "Thème nuit", Moon, "sombre dark"], ["jour", "Thème jour", Sun, "clair light"], ["auto", "Thème automatique (système)", SunMoon, "préférence système"],
];

export const commandesAffichage: Commande<ContexteBoard>[] = [
  /* ---- Échap : la première commande disponible gagne (présentation, concentration, zen, outil, sélection) ---- */
  { id: "presentation.quitter", libelle: "Quitter la présentation", icone: X, raccourci: "echap", categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.ui.presentation !== null,
    executer: (c) => {
      c.b.ui.definir({ presentation: null, focus: null });
      void c.b.pleinEcran(false);
    } },
  { id: "affichage.concentration.quitter", libelle: "Quitter le mode concentration", icone: X, raccourci: "echap", categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.ui.focus !== null && c.ui.presentation === null, executer: (c) => c.b.ui.definir({ focus: null }) },
  { id: "affichage.zen.quitter", libelle: "Quitter le mode zen", icone: X, raccourci: "echap", categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.ui.zen && c.ui.outil === "selection" && !c.selection.length, executer: (c) => c.b.ui.definir({ zen: false }) },
  { id: "outil.revenir", libelle: "Revenir à l'outil de sélection", icone: MousePointer2, raccourci: "echap", categorie: "Outils", niveau: "lecture",
    disponible: (c) => c.ui.outil !== "selection" || c.ui.liaison !== null, executer: (c) => c.b.ui.definir({ outil: "selection", liaison: null }) },
  { id: "edition.deselectionner", libelle: "Tout désélectionner", raccourci: "echap", categorie: "Édition", niveau: "lecture",
    disponible: (c) => c.selection.length > 0, executer: (c) => c.b.selectionner([]) },

  ...THEMES.map(([theme, libelle, icone, motsCles]): Commande<ContexteBoard> => ({
    id: `affichage.theme.${theme}`, libelle, icone, categorie: "Affichage", niveau: "lecture", motsCles: `${motsCles} couleurs apparence`,
    actif: (c) => c.ui.theme === theme, executer: (c) => c.b.ui.definir({ theme }),
  })),
  { id: "affichage.theme.basculer", libelle: "Basculer jour / nuit", icone: SunMoon, raccourci: "shift+d", categorie: "Affichage", niveau: "lecture",
    motsCles: "thème sombre clair",
    executer: (c) => c.b.ui.definir({ theme: document.documentElement.dataset.theme === "jour" ? "nuit" : "jour" }) },
  { id: "affichage.pleinEcran", libelle: (c) => (c.ui.pleinEcran ? "Quitter le plein écran" : "Plein écran"), icone: Maximize2, raccourci: "shift+f",
    categorie: "Affichage", niveau: "lecture", actif: (c) => c.ui.pleinEcran, executer: (c) => c.b.pleinEcran(!c.ui.pleinEcran) },
  { id: "affichage.zen", libelle: (c) => (c.ui.zen ? "Quitter le mode zen" : "Mode zen (masquer l'interface)"), icone: PanelTopClose, raccourci: "mod+.",
    categorie: "Affichage", niveau: "lecture", motsCles: "sans distraction", actif: (c) => c.ui.zen,
    disponible: (c) => c.ui.presentation === null, executer: (c) => c.b.ui.definir({ zen: !c.ui.zen }) },
  { id: "affichage.minicarte", libelle: (c) => (c.ui.minicarte ? "Masquer la minicarte" : "Afficher la minicarte"), icone: IconeCarte, raccourci: "shift+m",
    categorie: "Affichage", niveau: "lecture", actif: (c) => c.ui.minicarte, executer: (c) => c.b.ui.definir({ minicarte: !c.ui.minicarte }) },
  { id: "affichage.grille", libelle: "Magnétisme de la grille", icone: Grid3x3, raccourci: "shift+g", categorie: "Affichage", niveau: "lecture",
    motsCles: "accroche aimant", actif: (c) => c.ui.grille, executer: (c) => c.b.ui.definir({ grille: !c.ui.grille }) },
  { id: "affichage.guides", libelle: "Guides magnétiques d'alignement", icone: Magnet, raccourci: "shift+a", categorie: "Affichage", niveau: "lecture",
    motsCles: "accroche aimant lignes", actif: (c) => c.ui.guides, executer: (c) => c.b.ui.definir({ guides: !c.ui.guides }) },

  { id: "vue.ajuster", libelle: "Ajuster à la vue", icone: Maximize, raccourci: "shift+1", categorie: "Navigation", niveau: "lecture",
    motsCles: "tout voir zoom", executer: (c) => c.b.ajuster() },
  { id: "vue.selection", libelle: "Zoomer sur la sélection", icone: Focus, raccourci: "shift+2", categorie: "Navigation", niveau: "lecture",
    disponible: (c) => c.selection.length > 0, executer: (c) => c.b.cadrer(englobante(c.selection.map(boiteDe))!, 0.2) },
  { id: "vue.cent", libelle: "Zoom à 100 %", raccourci: "shift+0", categorie: "Navigation", niveau: "lecture", executer: (c) => c.b.zoomA(1) },
  { id: "vue.zoomAvant", libelle: "Zoom avant", icone: ZoomIn, raccourci: ["mod+=", "+"], categorie: "Navigation", niveau: "lecture", executer: (c) => c.b.zoomer(1.25) },
  { id: "vue.zoomArriere", libelle: "Zoom arrière", icone: ZoomOut, raccourci: ["mod+-", "-"], categorie: "Navigation", niveau: "lecture", executer: (c) => c.b.zoomer(0.8) },

  { id: "affichage.concentration", libelle: "Se concentrer sur ce cadre", icone: Minimize2, raccourci: "shift+c", categorie: "Affichage", niveau: "lecture",
    emplacements: ["flottante", "menu"], motsCles: "focus estomper le reste",
    disponible: (c) => Boolean(deType(c, "cadre")) && c.ui.presentation === null,
    executer: (c) => {
      const cadre = deType(c, "cadre")!;
      c.b.ui.definir({ focus: cadre.id });
      c.b.cadrer(boiteDe(cadre), 0.08);
    } },
  { id: "presentation.demarrer", libelle: "Présenter (les cadres deviennent des diapositives)", icone: Presentation, raccourci: "shift+p",
    categorie: "Affichage", niveau: "lecture", emplacements: ["flottante", "menu"], motsCles: "diaporama slides",
    disponible: (c) => c.ui.presentation === null && c.b.objets().some((o) => o.type === "cadre"),
    executer: (c) => {
      const cadres = diapositives(c.b.objets());
      const depart = deType(c, "cadre");
      void c.b.pleinEcran(true);
      montrer(c, depart ? Math.max(0, cadres.findIndex((x) => x.id === depart.id)) : 0);
    } },
  { id: "presentation.suivante", libelle: "Diapositive suivante", icone: ChevronRight, raccourci: ["droite", "bas", "espace", "entree"], categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.ui.presentation !== null, executer: (c) => montrer(c, (c.ui.presentation ?? 0) + 1) },
  { id: "presentation.precedente", libelle: "Diapositive précédente", icone: ChevronLeft, raccourci: ["gauche", "haut"], categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.ui.presentation !== null, executer: (c) => montrer(c, (c.ui.presentation ?? 0) - 1) },
];
