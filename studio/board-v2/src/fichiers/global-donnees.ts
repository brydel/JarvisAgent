import type { LienBoard, ObjetBoard } from "../types";
import type { EntreeMemoire } from "./journal-donnees";

export type SessionGraphe = {
  id: string;
  titre: string;
  projet: string;
  projets: string[];
  origine: "tentative" | "runtime" | "workmux";
  statut: string;
  debut: number | null;
  fin: number | null;
  objet_ids: string[];
  mission_ids: string[];
  evenement_ids: string[];
};

export type GroupeGraphe = {
  id: string;
  titre: string;
  projet?: string;
  ids: string[];
  nature: "session" | "hors_session";
};

export type CouvertureGlobale = Record<"objets" | "liens" | "sessions" | "entrees", { charges: number; total: number }>;

export type PageGrapheGlobal = {
  page: number;
  limite: number;
  objets: ObjetBoard[];
  liens: LienBoard[];
  entrees: EntreeMemoire[];
  sessions: SessionGraphe[];
  projets: { nom: string; objets: number }[];
  couverture: CouvertureGlobale;
  suivant: number | null;
  avertissements: string[];
  cle_disposition: string;
};
