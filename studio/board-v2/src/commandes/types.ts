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
  /** la commande peut s'exécuter dans ce contexte (défaut : vrai) */
  disponible?(c: C): boolean;
  /** POURQUOI elle ne peut pas s'exécuter, en une phrase destinée à l'utilisateur ; null si elle est simplement hors
   *  sujet. N'est consultée que si `disponible` est faux. C'est la seule source des raisons affichées : info-bulle
   *  d'un bouton grisé, ligne grisée de la palette et du menu contextuel, message d'un raccourci refusé. */
  raison?(c: C): string | null;
  /** la commande concerne ce qui est visé même quand elle n'est pas exécutable : menu contextuel et barre flottante
   *  la montrent alors grisée, avec sa raison, au lieu de la cacher (défaut : faux) */
  concerne?(c: C): boolean;
  /** bascule : état courant (aria-pressed, coche dans la palette) */
  actif?(c: C): boolean;
  executer(c: C): void | Promise<void>;
  /** inverse d'une commande qui ne passe pas par les écritures du Board ; si présent, l'exécution est annulable */
  annuler?(c: C): void | Promise<void>;
  /** texte de la demande de confirmation (niveau « sensible ») */
  confirmation?(c: C): string | null;
}

/** État d'une commande dans un contexte : exécutable, ou non avec la phrase qui dit pourquoi (null : hors sujet). */
export interface EtatCommande {
  disponible: boolean;
  raison: string | null;
  /** à montrer grisée là où elle est proposée (menu, barre flottante) */
  concerne: boolean;
}

export function etatDe<C>(cmd: Commande<C>, c: C): EtatCommande {
  if (cmd.disponible?.(c) ?? true) return { disponible: true, raison: null, concerne: true };
  const raison = cmd.raison?.(c) ?? null;
  return { disponible: false, raison, concerne: Boolean(raison) && Boolean(cmd.concerne?.(c)) };
}

export function libelleDe<C>(cmd: Commande<C>, c: C): string {
  return typeof cmd.libelle === "function" ? cmd.libelle(c) : cmd.libelle;
}

export function raccourcisDe<C>(cmd: Commande<C>): string[] {
  return cmd.raccourci === undefined ? [] : Array.isArray(cmd.raccourci) ? cmd.raccourci : [cmd.raccourci];
}
