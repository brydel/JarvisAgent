// Bibliothèque de références : types et appels à /api/v2/references (lib/jarvis/references_api.py).
// En mode démo, tout vient de ./demo (données fictives, aucune requête).
import { dateCourte } from "../lib/format";
import { requete } from "../product/api";
import { chercherDemo, listerDemo, voirDemo } from "./demo";

export type Statut = "en_attente" | "capture" | "indexation" | "prete" | "echec";
export interface Couleur { hex: string; part: number }
export interface Fichier { asset_id: string; url: string; sha256: string; largeur: number; hauteur: number }
export interface Zone { y: number; hauteur: number; x?: number; largeur?: number; largeur_element?: number }
export const GENRES = { site: "Site", composant: "Composant", effet: "Effet", image: "Image", video: "Vidéo", skill: "Skill",
  document: "Document", texte: "Texte", audio: "Audio", pdf: "PDF", lien: "Lien", carte: "Carte du Board" } as const;
export type Genre = keyof typeof GENRES;
export interface Reference {
  id: string; type: Genre; recapturable?: boolean; source: string; url: string; titre: string; description: string;
  collection: string; etiquettes: string[]; statut: Statut; raison: string; supprime: boolean; cree: number; maj: number;
  capture_le: number | null; vignette_url: string | null; palette: Couleur[]; polices: Record<string, string>; fragments?: number;
}
export interface Section { titre: string; niveau: number; zone: (Zone & { asset_id?: string; largeur?: number }) | null; caracteres: number; extrait: string }
export interface Lien { url: string; texte: string; externe: boolean; zone: string }
export interface Structure {
  entete: boolean; navigation: number; principal: boolean; pied: boolean; sections: string[]; images: number; boutons: number;
  formulaires: number; hauteur_page: number; heros: { titre: string; appel_action: string; visible_d_emblee: boolean } | null;
}
export interface ElementReleve {
  role: string; nom: string; largeur: number; hauteur: number; affichage: string; espacement: string;
  rayon: string; police: string; taille: string; alignement?: string; colonnes?: string;
  selecteur?: string; parent_selecteur?: string; x?: number; y?: number; couleur?: string; fond?: string;
  padding?: string; interligne?: string; graisse?: string; position?: string;
}
export interface Releve {
  mesures: Record<string, number>;
  elements: ElementReleve[];
  mouvements: { nature: string; duree: string; courbe: string; propriete: string }[];
  echantillon?: { examines: number; limite: number; tronque: boolean };
  tokens?: Partial<Record<"espacement" | "rayon" | "typographie" | "couleur", { valeur: string; occurrences: number }[]>>;
}
export type TypeObservation = "capture" | "structure" | "palette" | "typographie" | "lien" | "mesure" | "element" | "mouvement" | "preuve" | "media" | "comparaison";
export interface Observation {
  id: string; type: TypeObservation; titre: string; texte: string; ecran?: "bureau" | "mobile";
  preuve: { reference_id: string; capture_le: number | null; asset_id?: string; capture_url?: string; zone?: Zone | null };
  nature: "donnee_non_fiable";
  element?: Partial<ElementReleve>;
}
export interface ReferenceGraphe extends Reference { observations?: Observation[] }
export interface PageGrapheReferences { references: ReferenceGraphe[]; total: number; page: number; limite: number }
export interface Fiche extends Reference {
  observations?: Observation[];
  releve?: Partial<Record<"bureau" | "mobile", Releve>>;
  perimetre?: { type?: "element" | "page"; mobile_erreur?: string };
  fichiers: Partial<Record<"bureau_vue" | "bureau_page" | "mobile_vue" | "mobile_page", Fichier>>;
  sections: Section[]; couleurs_css: Record<string, string>; polices_declarees: string[]; structure: Structure | null;
  liens: Lien[]; langue: string; tronquee: boolean; empreinte: string;
  index: { fragments: number; vecteurs: number; modele: string; dimension: number; version_index: number };
  avertissement: string;
}
export interface Facette { nom: string; n: number }
export interface Moteur { mots: "fts5" | "python"; vecteurs: boolean; modele: string; fragments_vectorises: number; capture: boolean }
export interface Liste { references: Reference[]; total: number; collections: Facette[]; etiquettes: Facette[]; moteur: Moteur }
export interface Passage {
  fragment_id: string; reference_id: string; score: number; rangs: { mots: number | null; vecteurs: number | null };
  section: string; section_surlignages?: [number, number][]; position: number; extrait: { texte: string; surlignages: [number, number][] };
  citation: { reference_id: string; titre: string; url: string; type: string; collection: string; section: string;
    capture_le: number | null; capture_url: string | null; vignette_url: string | null; zone: Zone | null; lien: string; observation_id?: string };
}
export interface Recherche { question: string; mode: "bm25" | "hybride"; vecteurs: string; moteur_mots: string; resultats: Passage[]; avertissement: string }
export interface Filtres { collection: string | null; etiquette: string | null }

const params = (valeurs: Record<string, string | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(valeurs)) if (v !== null && v !== undefined) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};

export function lister(demo: boolean, f: Filtres, signal?: AbortSignal): Promise<Liste> {
  if (demo) return Promise.resolve(listerDemo(f));
  return requete<Liste>(`/api/v2/references${params({ collection: f.collection, etiquette: f.etiquette })}`, undefined, signal);
}
export async function chargerGraphe(demo: boolean, page: number, signal?: AbortSignal): Promise<PageGrapheReferences> {
  if (demo) {
    const liste = listerDemo({ collection: null, etiquette: null });
    const limite = 8;
    const references = await Promise.all(liste.references.slice((page - 1) * limite, page * limite).map((r) => voirDemo(r.id)));
    return { references, total: liste.total, page, limite };
  }
  return requete<PageGrapheReferences>(`/api/v2/references/graphe${params({ page: String(page) })}`, undefined, signal);
}

export function voir(demo: boolean, id: string, signal?: AbortSignal): Promise<Fiche> {
  if (demo) return voirDemo(id);
  return requete<Fiche>(`/api/v2/references/${encodeURIComponent(id)}`, undefined, signal);
}
export function lireFragment(id: string, signal: AbortSignal) {
  return requete<{ reference_id: string; section: string; texte: string; titre: string }>(
    `/api/v2/references/fragments/${encodeURIComponent(id)}`, undefined, signal);
}
export function chercher(demo: boolean, q: string, f: Filtres, signal?: AbortSignal): Promise<Recherche> {
  if (demo) return Promise.resolve(chercherDemo(q, f));
  return requete<Recherche>(`/api/v2/references/recherche${params({ q, collection: f.collection, etiquette: f.etiquette, n: "12" })}`, undefined, signal);
}
export interface Ajout { url?: string; texte?: string; titre?: string; collection: string; etiquettes: string[] }
export const ajouter = (a: Ajout) => requete<Fiche & { deja?: boolean }>("/api/v2/references", a);
export const supprimer = (id: string, restaurer = false) => requete<{ id: string }>(`/api/v2/references/${id}/supprimer`, restaurer ? { restaurer: true } : {});
export const recapturer = (id: string) => requete<Fiche>(`/api/v2/references/${id}/reindexer`, { recapturer: true });
export const reindexer = (id: string) => requete<{ fragments: number; vecteurs: number; etat_vecteurs: string }>(`/api/v2/references/${id}/reindexer`, {});
export const poser = (id: string, espace: string) => requete<{ objet_id: string; espace: string }>(`/api/v2/references/${id}/poser`, { espace, x: 160, y: 140 });

export const EN_COURS: Statut[] = ["en_attente", "capture", "indexation"];
export const LIBELLES: Record<Statut, string> = { en_attente: "En attente", capture: "Capture en cours", indexation: "Indexation", prete: "Prête", echec: "Échec" };
export function hote(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}
export function dateCapture(ts: number | null): string {
  return ts ? dateCourte(ts) : "date inconnue";
}
/** Citation prête à coller : titre, section, source, date — et les identifiants pour la retrouver. */
export function citation(p: Passage): string {
  const c = p.citation;
  const section = c.section ? `, section « ${c.section} »` : "";
  return `« ${p.extrait.texte.replace(/\s+/g, " ").trim()} » — ${c.titre}${section}${c.url ? `, ${c.url}` : ""} (capturé le ${dateCapture(c.capture_le)}) [${p.reference_id}#${p.fragment_id}]`;
}
/** Texte lisible sur une couleur de palette (contraste suffisant, sans dépendance). */
export function encreSur(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const [r, v, b] = [n >> 16, (n >> 8) & 255, n & 255].map((x) => { const c = x / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r! + 0.7152 * v! + 0.0722 * b! > 0.32 ? "#0B0E15" : "#F3F5FF";
}
