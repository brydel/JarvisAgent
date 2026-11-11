export interface Jetons {
  themes: { nuit: Record<string, string>; jour: Record<string, string> };
  contraste: { paires: { texte: string; fonds: string[]; min: number }[] };
  layout: {
    zoom: { min: number; max: number; "detail-resume": number; "detail-bloc": number };
    toolbar: { x: number; width: number; itemHeight: number };
    "canvas-safe-area": { top: number; right: number; bottom: number; left: number; $description: string };
  };
}
export const CHEMIN_JETONS: string;
export const CHEMIN_CSS: string;
export function lireJetons(): Jetons;
export function cssDesThemes(themes: Jetons["themes"]): string;
export function luminance(hex: string): number;
export function contraste(a: string, b: string): number;
export function lireCssThemes(): string;
export function lireFeuille(nom: string): string;
export function feuillesDuProduit(): { chemin: string; css: string }[];
export function sourcesInterface(): { chemin: string; code: string }[];
