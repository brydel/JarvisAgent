// Ce qu'une commande du Board reçoit : la sélection (résolue), la carte visée par un menu contextuel, l'état
// d'interface, et les SERVICES du Board (écritures annulables, vue, dialogues). Les commandes ne touchent ni au
// réseau ni à React : elles appellent ces services, ce qui les rend testables avec un double (catalogue.test.ts).
import type { Modification, NouvelObjet } from "../api";
import type { EtatUi, StoreUi } from "../etat/ui";
import type { Boite, Point } from "../outils/geometrie";
import type { LienBoard, ObjetBoard, Relecture, StyleLien } from "../types";

export interface OptionsToast {
  erreur?: boolean;
  action?: { nom: string; faire: () => void };
}

export interface ServicesBoard {
  demo: boolean;
  ui: StoreUi;
  /* ---- lecture ---- */
  objet(id: string): ObjetBoard | undefined;
  objets(): readonly ObjetBoard[];
  liens(): readonly LienBoard[];
  /** identifiants des objets affichés dans le canevas (ni filtrés, ni rangés dans un dossier) */
  visibles(): string[];
  /* ---- écritures (optimistes, versionnées, annulables) ---- */
  /** modifie des objets ; l'inverse est calculé depuis l'état courant. Une entrée d'historique par appel. */
  modifier(mods: Modification[], libelle: string): Promise<void>;
  creer(o: NouvelObjet, libelle?: string): Promise<string>;
  supprimer(ids: string[]): Promise<void>;
  dupliquer(ids: string[], decalage?: Point): Promise<string[]>;
  lier(source: string, cible: string, style?: StyleLien): Promise<string | null>;
  modifierLien(id: string, champs: { libelle?: string; style?: StyleLien }): Promise<void>;
  supprimerLien(id: string): Promise<void>;
  commenter(id: string, texte: string): Promise<void>;
  /** regroupe les écritures de `f` en un seul pas d'annulation */
  grouper<T>(libelle: string, f: () => Promise<T>): Promise<T>;
  annuler(): Promise<void>;
  retablir(): Promise<void>;
  /** libellé du prochain « annuler » et du prochain « rétablir » (null : rien à faire) */
  historique(): { annuler: string | null; refaire: string | null };
  /** « Faire relire » : demande, retrait ou verdict, enregistrés dans la file du serveur. Aucun agent n'est lancé. */
  relire(id: string, action: "demander" | "annuler" | "rendre", options?: { verdict?: "pret" | "corrections"; avis?: string }): Promise<Relecture | null>;
  /* ---- presse-papiers ---- */
  copier(ids: string[]): void;
  coller(ou?: Point): Promise<void>;
  peutColler(): boolean;
  /* ---- sélection et vue ---- */
  selectionner(ids: string[]): void;
  inspecter(id: string): void;
  /** sélectionne la carte et l'amène dans la vue (navigation depuis « bloquée par X », « alimentée par Y »…) */
  allerA(id: string): void;
  ajuster(): void;
  zoomer(facteur: number): void;
  zoomA(niveau: number): void;
  cadrer(zone: Boite, marge?: number): void;
  /** amène la zone dans la vue si elle est hors champ, sans changer le zoom */
  montrer(zone: Boite): void;
  centreVue(): Point;
  /* ---- dialogues et ingestion ---- */
  toast(texte: string, options?: OptionsToast): void;
  ouvrirMission(): void;
  saisirLien(): void;
  choisirFichiers(accept: string): void;
  collerPressePapiers(): Promise<void>;
  contextualiser(id: string): void;
  exporterPng(ids: string[], nom: string): Promise<void>;
  pleinEcran(actif: boolean): Promise<void>;
}

export interface ContexteBoard {
  /** objets sélectionnés ; si un menu contextuel vise une carte hors sélection, c'est elle seule */
  selection: ObjetBoard[];
  /** relation visée par le menu contextuel */
  lien?: LienBoard;
  /** point du canevas visé (menu contextuel) */
  point?: Point;
  ui: EtatUi;
  b: ServicesBoard;
}

/* Aides de disponibilité, partagées par le catalogue */
export const ids = (c: ContexteBoard): string[] => c.selection.map((o) => o.id);
export const un = (c: ContexteBoard): ObjetBoard | undefined => (c.selection.length === 1 ? c.selection[0] : undefined);
export const deType = (c: ContexteBoard, ...types: string[]): ObjetBoard | undefined => {
  const o = un(c);
  return o && types.includes(o.type) ? o : undefined;
};
/** mode présentation ou zen : les commandes d'écriture au clavier sont suspendues */
export const enLecture = (c: ContexteBoard): boolean => c.ui.presentation !== null;

/* Raisons d'indisponibilité partagées (une phrase, adressée à l'utilisateur). */
export const RAISON_LECTURE = "Rien ne se modifie pendant la présentation : quitte-la avec Échap";
export const RAISON_SELECTION = "Sélectionne d'abord un objet du Board";
export const RAISON_UNE_CARTE = "Sélectionne une seule carte";
export const raisonLecture = (c: ContexteBoard): string | null => (enLecture(c) ? RAISON_LECTURE : null);
/** écriture sur la sélection : présentation en cours, puis sélection vide */
export const raisonSelection = (c: ContexteBoard): string | null => raisonLecture(c) ?? (c.selection.length ? null : RAISON_SELECTION);
