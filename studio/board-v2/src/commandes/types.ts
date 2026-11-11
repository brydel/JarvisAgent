// Une COMMANDE = une action du Board, déclarée une fois. Les boutons, les raccourcis clavier, les menus contextuels,
// la barre flottante et la palette (Ctrl/⌘+K) passent tous par le registre : même libellé, même raccourci affiché,
// mêmes conditions, même journal d'usage. Aucune dépendance à React ici (icône = simple référence de composant).
import type { ComponentType } from "react";

/** lecture : ne change rien aux données ; ecriture : modifie le Board (annulable) ; sensible : demande confirmation. */
export type Niveau = "lecture" | "ecriture" | "sensible";
export type Categorie = "Outils" | "Édition" | "Disposition" | "Carte" | "Affichage" | "Navigation" | "Ajouter" | "Export";
/** D'où vient l'exécution : appris par le journal (un bouton jamais cliqué mais souvent tapé au clavier…). */
export type Origine = "bouton" | "raccourci" | "palette" | "menu" | "flottante" | "programme";
export type Emplacement = "palette" | "menu" | "flottante";
export type Icone = ComponentType<{ size?: number | string; "aria-hidden"?: boolean }>;

export interface Commande<C> {
  /** identifiant stable « domaine.action » : c'est la clé du journal d'usage */
  id: string;
  libelle: string | ((c: C) => string);
  icone?: Icone;
  /** « mod+k », « shift+1 », « v »… (mod = Ctrl, ou ⌘ sur Mac). Plusieurs raccourcis possibles ; le premier est affiché. */
  raccourci?: string | string[];
  categorie: Categorie;
  niveau: Niveau;
  /** mots de recherche en plus du libellé (palette) */
  motsCles?: string;
  /** où la proposer en plus de la palette (toutes les commandes y sont) */
  emplacements?: Emplacement[];
  /** hors palette : la commande est masquée quand elle n'est pas disponible (défaut : vrai) */
  disponible?(c: C): boolean;
  /** bascule : état courant (aria-pressed, coche dans la palette) */
  actif?(c: C): boolean;
  executer(c: C): void | Promise<void>;
  /** inverse d'une commande qui ne passe pas par les écritures du Board ; si présent, l'exécution est annulable */
  annuler?(c: C): void | Promise<void>;
  /** texte de la demande de confirmation (niveau « sensible ») */
  confirmation?(c: C): string | null;
}

export function libelleDe<C>(cmd: Commande<C>, c: C): string {
  return typeof cmd.libelle === "function" ? cmd.libelle(c) : cmd.libelle;
}

export function raccourcisDe<C>(cmd: Commande<C>): string[] {
  return cmd.raccourci === undefined ? [] : Array.isArray(cmd.raccourci) ? cmd.raccourci : [cmd.raccourci];
}
