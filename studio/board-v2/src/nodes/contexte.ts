import { createContext, useContext } from "react";
import type { ObjetBoard, Priorite } from "../types";

/** Actions du Board accessibles aux cartes. Références stables (créées une fois) : aucun re-rendu en cascade. */
export interface ActionsBoard {
  modifier(id: string, champs: Partial<Pick<ObjetBoard, "contenu" | "meta" | "priorite">> & { verrouille?: boolean }): void;
  priorite(id: string, p: Priorite): void;
  supprimer(ids: string[]): void;
  dupliquer(ids: string[]): void;
  devant(ids: string[]): void;
  inspecter(id: string): void;
  agrandir(src: string, titre: string): void;
  sortirDuDossier(id: string): void;
  enfants(dossierId: string): ObjetBoard[];
}

export const ContexteActions = createContext<ActionsBoard | null>(null);

export function useActions(): ActionsBoard {
  const a = useContext(ContexteActions);
  if (!a) throw new Error("ContexteActions manquant");
  return a;
}

export const TAILLES: Record<string, { min: [number, number]; defaut: [number, number]; ratio?: boolean }> = {
  image: { min: [220, 170], defaut: [491, 309] },
  lien: { min: [300, 260], defaut: [434, 356] },
  pdf: { min: [280, 260], defaut: [348, 318] },
  document: { min: [280, 200], defaut: [348, 240] },
  note: { min: [260, 200], defaut: [408, 391] },
  texte: { min: [260, 160], defaut: [408, 300] },
  mission: { min: [380, 320], defaut: [452, 362] },
  agents: { min: [280, 240], defaut: [331, 342] },
  audio: { min: [380, 170], defaut: [462, 178] },
  video: { min: [300, 170], defaut: [378, 178] },
  dossier: { min: [300, 140], defaut: [378, 152] },
  capture: { min: [220, 170], defaut: [491, 309] },
};
