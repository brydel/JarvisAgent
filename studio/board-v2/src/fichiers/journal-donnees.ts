export const NATURES_MEMOIRE = {
  blocage: "Blocage",
  echec: "Échec",
  refus: "Refus de revue",
  reprise: "Reprise",
  resolution: "Résolution",
  frustration: "Frustration déclarée",
} as const;

export type NatureMemoire = keyof typeof NATURES_MEMOIRE;

export type PreuveMemoire = {
  mission_id: string;
  tache_id?: string | null;
  tentative_id?: string | null;
  sequence: number;
};

export type EntreeMemoire = {
  id: string;
  nature: NatureMemoire;
  titre: string;
  detail: string;
  date: number;
  factice: boolean;
  auteur?: string | null;
  mission_titre?: string | null;
  preuve: PreuveMemoire;
  cause_id?: string | null;
};

export type PageMemoire = { entrees: EntreeMemoire[]; avant: string | null };
export const idMemoire = (id: string) => "journal:" + id;
export const titreMemoire = (e: EntreeMemoire) => e.mission_titre ? e.mission_titre + " · " + e.titre : e.titre;

export function destinationPreuve({ mission_id, tache_id, tentative_id, sequence }: PreuveMemoire): Record<string, string> {
  return {
    mission: mission_id,
    evenement: String(sequence),
    ...(tache_id ? { etape: tache_id } : {}),
    ...(tentative_id ? { tentative: tentative_id } : {}),
  };
}
