// État d'interface du Board (outil courant, thème, modes d'affichage, style de dessin) dans un petit store externe :
// les commandes le lisent et l'écrivent sans React, les composants s'y abonnent par SÉLECTEUR (un bouton ne se
// re-rend que si SA valeur change). Les préférences sont mémorisées sur ce poste (localStorage).
import { useSyncExternalStore } from "react";

export type IdOutil = "selection" | "main" | "adhesif" | "texte" | "rectangle" | "ellipse" | "losange" | "fleche"
  | "crayon" | "surligneur" | "gomme" | "cadre" | "lasso";
export type Theme = "nuit" | "jour" | "auto";
export type NomCouleur = "" | "neutre" | "indigo" | "violet" | "rose" | "orange" | "jaune" | "vert" | "cyan" | "gris";
export const COULEURS: NomCouleur[] = ["neutre", "indigo", "violet", "rose", "orange", "jaune", "vert", "cyan", "gris"];

export interface MenuOuvert {
  /** position écran */
  x: number;
  y: number;
  /** carte visée (clic droit sur une carte) ; sinon le canevas */
  cible?: string;
  /** relation visée (clic droit sur une flèche de relation) */
  lien?: string;
  /** position dans le canevas (pour « coller ici », « ajouter ici ») */
  point: { x: number; y: number };
}

export interface Preferences {
  theme: Theme;
  minicarte: boolean;
  /** accroche sur la grille (20 px) */
  grille: boolean;
  /** guides magnétiques d'alignement entre objets */
  guides: boolean;
  /** style des prochains objets dessinés */
  couleur: NomCouleur;
  epaisseur: number;
}

export interface EtatUi extends Preferences {
  outil: IdOutil;
  /** interface masquée (mode zen) */
  zen: boolean;
  /** mode présentation : index du cadre affiché, ou null */
  presentation: number | null;
  /** mode concentration : identifiant du cadre mis en avant, ou null */
  focus: string | null;
  /** objet dont le texte est en cours d'édition (surcouche non transformée), ou null */
  edition: string | null;
  palette: boolean;
  menu: MenuOuvert | null;
  pleinEcran: boolean;
  /** carte en attente de sa cible pour « Relier à… » */
  liaison: string | null;
  /** objets survolés par la gomme pendant le geste */
  aEffacer: ReadonlySet<string>;
}

const CLE = "jarvis.board.preferences.v1";
const DEFAUT: Preferences = { theme: "nuit", minicarte: true, grille: false, guides: true, couleur: "indigo", epaisseur: 6 };
const VIDE: ReadonlySet<string> = new Set();

function lirePreferences(): Preferences {
  try {
    const p = JSON.parse(localStorage.getItem(CLE) ?? "{}") as Partial<Preferences>;
    return {
      theme: p.theme === "jour" || p.theme === "auto" || p.theme === "nuit" ? p.theme : DEFAUT.theme,
      minicarte: typeof p.minicarte === "boolean" ? p.minicarte : DEFAUT.minicarte,
      grille: typeof p.grille === "boolean" ? p.grille : DEFAUT.grille,
      guides: typeof p.guides === "boolean" ? p.guides : DEFAUT.guides,
      couleur: COULEURS.includes(p.couleur as NomCouleur) ? (p.couleur as NomCouleur) : DEFAUT.couleur,
      epaisseur: typeof p.epaisseur === "number" && p.epaisseur >= 1 && p.epaisseur <= 64 ? p.epaisseur : DEFAUT.epaisseur,
    };
  } catch {
    return { ...DEFAUT };
  }
}

export class StoreUi {
  private etat: EtatUi;
  private abonnes = new Set<() => void>();

  constructor(preferences: Preferences = lirePreferences()) {
    this.etat = { ...preferences, outil: "selection", zen: false, presentation: null, focus: null, edition: null, palette: false,
      menu: null, pleinEcran: false, liaison: null, aEffacer: VIDE };
  }

  lire = (): EtatUi => this.etat;

  abonner = (f: () => void): (() => void) => {
    this.abonnes.add(f);
    return () => this.abonnes.delete(f);
  };

  definir(changements: Partial<EtatUi>): void {
    let change = false;
    for (const k of Object.keys(changements) as (keyof EtatUi)[]) {
      if (this.etat[k] !== changements[k]) change = true;
    }
    if (!change) return;
    this.etat = { ...this.etat, ...changements };
    if (["theme", "minicarte", "grille", "guides", "couleur", "epaisseur"].some((k) => k in changements)) this.memoriser();
    for (const f of this.abonnes) f();
  }

  private memoriser() {
    const { theme, minicarte, grille, guides, couleur, epaisseur } = this.etat;
    try {
      localStorage.setItem(CLE, JSON.stringify({ theme, minicarte, grille, guides, couleur, epaisseur } satisfies Preferences));
    } catch {
      // stockage refusé : la préférence vaut pour cette session
    }
  }
}

/** Un seul Board par page : store partagé par les commandes, la barre d'outils et le canevas. */
export const ui = new StoreUi();

export function useUi<T>(selecteur: (e: EtatUi) => T): T {
  return useSyncExternalStore(ui.abonner, () => selecteur(ui.lire()));
}

/* ---------------------------------------------------------------- thème ------------------------------------ */
const CLAIR = "(prefers-color-scheme: light)";

/** Thème effectif : « auto » suit la préférence du système. */
export function resoudreTheme(theme: Theme, systemeClair: boolean): "nuit" | "jour" {
  return theme === "auto" ? (systemeClair ? "jour" : "nuit") : theme;
}

/** Pose `data-theme` sur la racine et suit la préférence système tant que le thème est « auto ». Branché une fois
 *  pour TOUT le produit (App.tsx) : accueil, missions, agents, références, dialogues et Board partagent le thème. */
export function brancherTheme(store: StoreUi = ui): () => void {
  const media = typeof matchMedia === "function" ? matchMedia(CLAIR) : null;
  const appliquer = () => {
    document.documentElement.dataset.theme = resoudreTheme(store.lire().theme, Boolean(media?.matches));
  };
  appliquer();
  const fin = store.abonner(appliquer);
  media?.addEventListener("change", appliquer);
  return () => {
    fin();
    media?.removeEventListener("change", appliquer);
  };
}
