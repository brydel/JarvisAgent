export interface Jetons {
  direction: Record<string, string>;
  themes: { nuit: Record<string, string>; jour: Record<string, string> };
  synonymes: { roles: Record<string, string>; herites: Record<string, string> };
  contraste: { paires: { texte: string; fonds: string[]; min: number }[] };
  fixes: Record<string, Record<string, string>>;
  layout: {
    reference: { width: number; height: number; canvasZoom: number };
    topbar: { height: number };
    subbar: { height: number };
    panel: { width: number };
    zoom: { min: number; max: number; "detail-resume": number; "detail-bloc": number };
    toolbar: { x: number; width: number; itemHeight: number };
    "canvas-safe-area": { top: number; right: number; bottom: number; left: number; $description: string };
  };
}
export const CHEMIN_JETONS: string;
export const CHEMIN_CSS: string;
export const CHEMIN_FIXES: string;
export const CHEMIN_PLANCHE: string;
export const SEUIL_MOBILE: number;
export function lireJetons(): Jetons;
export function synonymes(jetons: Jetons): Record<string, string>;
export function themeResolu(jetons: Jetons, theme: "nuit" | "jour"): Record<string, string>;
export function cssDesThemes(jetons: Jetons): string;
export function cssDesFixes(jetons: Jetons): string;
export function nomsFixes(jetons: Jetons): string[];
export function nomsConnus(jetons: Jetons): string[];
export function fichiersGeneres(jetons?: Jetons): { chemin: string; contenu: string }[];
export function luminance(hex: string): number;
export function contraste(a: string, b: string): number;
export function lireFichier(chemin: string): string;
export function lireCssThemes(): string;
export function lireFeuille(nom: string): string;
export function lireDuProjet(relatif: string): string;
export function feuillesDuProduit(): { chemin: string; css: string }[];
export function sourcesInterface(): { chemin: string; code: string }[];
export function usage(jetons?: Jetons): Record<string, number>;
