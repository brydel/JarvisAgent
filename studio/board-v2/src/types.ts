// Contrats de données du Board V2 — miroir de lib/jarvis/board.py (objets, relations, fichiers, missions).

export type Priorite = "" | "P1" | "P2" | "P3";
export type TypeObjet =
  | "note" | "texte" | "lien" | "image" | "video" | "audio" | "pdf" | "document" | "capture"
  | "mission" | "agents" | "dossier";

export interface Asset {
  id: string;
  mime: string;
  taille: number;
  nom: string;
  famille: "image" | "audio" | "video" | "pdf" | null;
  meta: { largeur?: number; hauteur?: number; duree?: number; codec_video?: string; codec_audio?: string };
  url: string;
  vignette_url: string | null;
}

export interface TacheResume {
  id: string;
  type: string;
  niveau: string;
  statut: string;
  fournisseur_choisi: string | null;
  fournisseur: string;
  essais: number;
  raison: string;
  /** démo seulement : libellé lisible d'une étape */
  libelle?: string;
}

export interface AgentResume {
  id: string;
  tache_id: string;
  fournisseur: string;
  issue: string | null;
  debut: number;
  fin: number | null;
  executant: string | null;
  role: string;
  statut_tache: string;
  /** démo seulement */
  nom?: string;
}

export interface MissionResume {
  id: string;
  objectif: string;
  statut: string;
  cree: number;
  taches: TacheResume[];
  faites: number;
  total: number;
  progression: number;
  agents: AgentResume[];
  approbations_en_attente: number;
}

export interface MetaObjet {
  titre?: string;
  description?: string;
  tags?: string[];
  url?: string;
  hote?: string;
  site?: string;
  apercu_image?: Asset | null;
  favicon?: Asset | null;
  apercu_erreur?: string;
  historique?: { ts: number; extrait: string }[];
  /** démo : URL locale d'un fichier de démonstration */
  demo_src?: string;
  demo_vignette?: string;
  demo_pages?: string[];
  [cle: string]: unknown;
}

export interface ObjetBoard {
  id: string;
  type: TypeObjet;
  espace: string;
  contenu: string;
  x: number;
  y: number;
  largeur: number;
  hauteur: number;
  z: number;
  priorite: Priorite;
  meta: MetaObjet;
  asset_id: string | null;
  asset?: Asset | null;
  mission_id: string | null;
  mission?: MissionResume | null;
  parent_id: string | null;
  verrouille: number;
  version: number;
  cree: number;
  maj: number;
  commentaires?: number;
  artefacts?: { id: string; fournisseur: string; factice: number; revue: string; contenu: string }[];
}

export type StyleLien = "defaut" | "inspire" | "alimente" | "utilise" | "depend";

export interface LienBoard {
  id: string;
  source_id: string;
  cible_id: string;
  libelle: string;
  style: StyleLien;
  /** ancrages explicites (démo) ; sinon le lien part du bord le plus proche */
  cotes?: { s: CoteLien; sf: number; t: CoteLien; tf: number; c?: number; lt?: number };
}
export type CoteLien = "top" | "right" | "bottom" | "left";

export interface EtatBoard {
  espace: string;
  objets: ObjetBoard[];
  liens: LienBoard[];
}

export interface Evenement {
  seq: number;
  type: string;
  mission_id: string | null;
  tache_id: string | null;
  ts: number;
  donnees: Record<string, unknown>;
}

export interface Approbation {
  id: string;
  tache_id: string;
  mission_id: string;
  niveau: string;
  type: string;
  travail: string;
  demandeur: string;
  cree: number;
}

/** Données passées à chaque nœud React Flow (références stables : le nœud ne recopie pas le graphe). */
export interface DonneesNoeud extends Record<string, unknown> {
  objet: ObjetBoard;
  demo: boolean;
}
