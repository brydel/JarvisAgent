// Niveau de détail selon le zoom. Sous 35 %, le texte d'une carte est illisible : elle devient un rectangle titré
// (médias, lecteurs et iframes démontés). Sous 12 %, un simple bloc de couleur, sans poignée ni relation tracée.
//
// Le niveau est calculé UNE fois, dans le canevas (un sélecteur qui rend un entier : il ne déclenche un rendu qu'au
// franchissement d'un seuil), puis distribué aux objets par contexte React. Les objets n'ont donc AUCUN abonnement
// au store de React Flow pour cela : à 2 000 objets visibles, ce sont 2 000 sélecteurs de moins évalués à chaque
// image d'un panoramique.
import { createContext, useContext, useSyncExternalStore } from "react";
import { useStore } from "@xyflow/react";

export const ZOOM_MIN = 0.05;
export const ZOOM_MAX = 8;
export const ZOOM_RESUME = 0.35;
export const ZOOM_BLOC = 0.12;

export type NiveauDetail = 0 | 1 | 2;

export function niveauPour(zoom: number): NiveauDetail {
  return zoom < ZOOM_BLOC ? 2 : zoom < ZOOM_RESUME ? 1 : 0;
}

const choisir = (s: { transform: [number, number, number] }): NiveauDetail => niveauPour(s.transform[2]);

// Export PNG : le détail complet est forcé le temps de la capture, quel que soit le zoom.
let force = false;
const abonnes = new Set<() => void>();
const abonner = (f: () => void) => {
  abonnes.add(f);
  return () => abonnes.delete(f);
};

export function forcerDetail(actif: boolean): void {
  if (force === actif) return;
  force = actif;
  for (const f of abonnes) f();
}

/** À appeler une seule fois, dans le canevas. */
export function useNiveauCalcule(): NiveauDetail {
  const niveau = useStore(choisir);
  const complet = useSyncExternalStore(abonner, () => force);
  return complet ? 0 : niveau;
}

export const ContexteDetail = createContext<NiveauDetail>(0);

/** Niveau de détail courant, pour un objet du canevas. */
export function useNiveauDetail(): NiveauDetail {
  return useContext(ContexteDetail);
}
