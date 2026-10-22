import type { Source } from "../api";
import type { EtatBoard } from "../types";

export interface Candidate {
  id: string; role: string; statut: string; ts: number; pourquoi: string; base: string; empreinte: string; pct: number;
}
export interface Agent {
  nom: string; titre: string; court: string; equipe: string; sigle: string; fournisseur: string;
  niveau: number; resume: string; corps: string; empreinte: string; candidats: Candidate[];
}
export interface Catalogue {
  agents: Agent[];
  execution: {
    executants: { id: string; nom: string; actif: boolean; revoque: boolean; fournisseurs: string[] }[];
    connexions: { fournisseur: string; mode_auth: string; disponible: boolean; payant: boolean; raison: string }[];
    taches: Record<string, number>; arret_urgence: boolean; budget_inference_centimes: number;
  };
  politique: { max_agents: number; validation_plans: string; fournisseurs_defaut: string[]; model_bridge: string; portee: string };
}
export interface Verification { valide: boolean; raisons: string[]; diff: string; empreinte: string; base: string; qualite_modele: null }
export interface ProductData { catalogue: Catalogue; board: EtatBoard }
export async function requete<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { credentials: "same-origin", signal,
    ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" }, body: JSON.stringify(body) }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erreur || `Le serveur a repondu ${r.status}.`);
  return data as T;
}
// Exemples explicitement fictifs : aucune session, mesure ou inference simulee n'est declaree reelle.
export function catalogueDemo(): Catalogue {
  const roles = [
    ["architecte", "Architecte systèmes", "Architecture", "Conception", "AR", "claude", "Transforme une ambition en décisions techniques solides."],
    ["frontend", "Ingénieur interface", "Interface", "Fabrication", "UI", "codex", "Donne vie aux interfaces rapides, accessibles et soignées."],
    ["recherche", "Analyste recherche", "Recherche", "Veille", "RE", "claude", "Relie les sources, compare les faits et explicite les incertitudes."],
    ["design", "Designer produit", "Design", "Conception", "DS", "claude", "Transforme les usages en interactions simples et mémorables."],
    ["qa", "Ingénieur qualité", "Qualité", "Qualité", "QA", "codex", "Cherche les régressions avant qu'elles atteignent ton produit."],
    ["backend", "Ingénieur backend", "Backend", "Fabrication", "BE", "codex", "Construit les contrats, la persistance et la reprise après panne."],
  ];
  return {
    agents: roles.map(([nom, titre, court, equipe, sigle, fournisseur, resume]) => ({
      nom: nom!, titre: titre!, court: court!, equipe: equipe!, sigle: sigle!, fournisseur: fournisseur!, resume: resume!, niveau: 2,
      corps: `Tu es ${titre}. ${resume}\n\nTravaille dans le perimetre autorise. Explique tes choix, conserve les sources et verifie tes resultats. Ne modifie jamais les permissions ni les secrets. Demande une validation pour les actions sensibles.`,
      empreinte: `demo-${nom}`, candidats: [],
    })),
    execution: { executants: [], connexions: [], taches: {}, arret_urgence: false, budget_inference_centimes: 0 },
    politique: { max_agents: 3, validation_plans: "humain", fournisseurs_defaut: ["claude", "codex"], model_bridge: "desactive", portee: "demo" },
  };
}
export async function chargerProduit(source: Source, signal?: AbortSignal): Promise<ProductData> {
  const [catalogue, board] = await Promise.all([
    source.demo ? Promise.resolve(catalogueDemo()) : requete<Catalogue>("/api/v2/atelier", undefined, signal),
    source.charger(),
  ]);
  return { catalogue, board };
}
export function dateCourte(ts: number) {
  return new Intl.DateTimeFormat("fr-CA", { day: "numeric", month: "short" }).format(ts * 1000);
}
export function verifierAgent(agent: Agent, corps: string, demo: boolean): Promise<Verification> {
  if (demo) return Promise.resolve({ valide: corps.trim().length >= 80 && corps !== agent.corps,
    raisons: corps.trim().length < 80 ? ["Ajoute des consignes plus précises (80 caractères minimum)."] : corps === agent.corps ? ["Les consignes n'ont pas change."] : [],
    diff: `--- Version de démonstration\n+++ Ton brouillon\n\n${corps}`, empreinte: "demo-preview", base: agent.empreinte, qualite_modele: null });
  return requete(`/api/v2/atelier/agents/${encodeURIComponent(agent.nom)}/verifier`, { corps, base: agent.empreinte });
}
