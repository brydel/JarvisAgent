// Contrats de données du Board V2 — miroir de lib/jarvis/board.py (objets, relations, fichiers, missions).

export type Priorite = "" | "P1" | "P2" | "P3";
export type TypeObjet =
  | "note" | "texte" | "lien" | "image" | "video" | "audio" | "pdf" | "document" | "capture"
  | "mission" | "agents" | "dossier" | "plan" | "tache"
  // tableau blanc (lib/jarvis/board_tableau.py) : apparence dans meta, bornée par le serveur
  | "adhesif" | "texte_libre" | "forme" | "trait" | "cadre" | "fleche";

/** Ancre d'une extrémité de flèche : position normalisée (0..1) sur la boîte de l'objet visé. */
export interface AncreFleche {
  id: string;
  nx: number;
  ny: number;
}

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
  /** outils déclarés par l'exécutant pour cette tentative (copie isolée, lecture web, Read…) */
  outils?: { outil: string; detail: string }[];
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
  /** écrits par le moteur seul (contextualisation par le chef) */
  jarvis_resume?: string;
  propositions?: Proposition[];
  jarvis_mission?: string;
  /** démo : URL locale d'un fichier de démonstration */
  demo_src?: string;
  demo_vignette?: string;
  demo_pages?: string[];
  /** tableau blanc — noms de jetons de couleur (jamais une couleur CSS) */
  couleur?: string;
  fond?: string;
  trait?: string;
  epaisseur?: number;
  taille_police?: number;
  forme?: "rectangle" | "ellipse" | "losange";
  /** trait : triplets (x, y, pression %) relatifs à la boîte ; flèche : [x1, y1, x2, y2] normalisés sur la boîte */
  points?: number[];
  boite?: [number, number];
  outil?: "crayon" | "surligneur";
  pointes?: "fin" | "deux" | "aucune";
  ancres?: { de?: AncreFleche; vers?: AncreFleche };
  libelle?: string;
  /** demande de relecture posée par l'humain sur un livrable (aucun agent n'est lancé par cette demande) */
  relecture?: { demandee: number; par: string };
  source?: string;
  compact?: boolean;
  [cle: string]: unknown;
}

/** Action proposée par le chef : rien n'est exécuté sans « Lancer », et une action L2/L3 n'est que préparée. */
export interface Proposition {
  titre: string;
  pourquoi: string;
  niveau: "L1" | "L2" | "L3";
  statut: "proposee" | "lancee" | "ecartee";
  mission_id?: string;
  /** « jarvis:auto » quand le chef l'a lancée seul */
  par?: string;
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
  /** qui a posé l'objet : « studio » (toi), « chef », « telegram »… tel qu'enregistré par le serveur */
  auteur?: string;
  artefacts?: { id: string; fournisseur: string; factice: number; revue: string; contenu: string }[];
}

export type StyleLien = "defaut" | "inspire" | "alimente" | "utilise" | "depend";

export interface LienBoard {
  id: string;
  source_id: string;
  cible_id: string;
  libelle: string;
  style: StyleLien;
  /** « jarvis » : relation posée par le chef (retirable comme les autres) */
  auteur?: string;
  /** version serveur (détection de conflit) ; absente en démo et sur les anciennes réponses */
  version?: number;
  espace?: string;
  /** ancrages explicites (démo) ; sinon le lien part du bord le plus proche */
  cotes?: { s: CoteLien; sf: number; t: CoteLien; tf: number; c?: number; lt?: number };
}
export type CoteLien = "top" | "right" | "bottom" | "left";

export interface ReglagesBoard {
  auto_analyse: boolean;
  actions_auto: boolean;
}

export interface EtatBoard {
  espace: string;
  objets: ObjetBoard[];
  liens: LienBoard[];
  reglages?: ReglagesBoard;
  /** numéro du dernier événement du journal au moment de la lecture : le flux reprend à partir de là */
  curseur?: number;
}

/** Lecture ciblée (GET /api/v2/objets?ids=…) : quelques objets et les relations qui les touchent. */
export interface DeltaBoard {
  espace: string;
  objets: ObjetBoard[];
  liens: LienBoard[];
  /** identifiants demandés qui n'existent plus dans ce Board (supprimés, déplacés ailleurs, inconnus) */
  absents: { objets: string[]; liens: string[] };
  curseur?: number;
  reglages?: ReglagesBoard;
}

export interface EspaceBoard {
  nom: string;
  objets: number;
  projet: boolean;
  description: string;
}

export interface Evenement {
  seq: number;
  type: string;
  mission_id: string | null;
  tache_id: string | null;
  ts: number;
  donnees: Record<string, unknown>;
  /** flux filtré : numéro de l'événement précédent envoyé sur CE flux (continuité vérifiée par le client) */
  prec?: number;
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
  /** nombre de relations entrantes (cartes sources), pour le pied « provenance » */
  sources: number;
}
