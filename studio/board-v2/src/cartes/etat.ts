// Ce qu'une carte sait dire d'elle-même À PARTIR DES DONNÉES RÉELLES : son état (bloquée, en attente de toi,
// périmée) et sa provenance (qui l'a posée, quel modèle a produit le livrable, quand, quelle version, combien de
// sources). Rien n'est inventé : une information absente des données n'est pas affichée. Fonctions pures, testées.
import type { ObjetBoard } from "../types";

export type SorteEtat = "bloquee" | "attente" | "perimee";
export interface EtatCarte {
  sorte: SorteEtat;
  /** libellé court affiché sur la carte */
  texte: string;
  /** d'où vient ce constat (info-bulle) */
  raison: string;
}

const ECHECS = new Set(["FAILED", "CANCELLED", "EXPIRED"]);

/** États visibles d'une carte, du plus urgent au moins urgent. */
export function etatsCarte(o: ObjetBoard): EtatCarte[] {
  const etats: EtatCarte[] = [];
  // la carte « équipe » partage la mission de sa carte mission : c'est celle-ci qui porte l'état, pas les deux
  const m = o.type === "agents" ? undefined : o.mission;
  const statutTravail = typeof o.meta.statut === "string" ? o.meta.statut : "";

  // en attente de l'humain : une approbation, un plan à valider, des propositions sans réponse, une relecture demandée
  if (m && m.approbations_en_attente > 0) {
    etats.push({ sorte: "attente", texte: "Attend ta décision", raison: `${m.approbations_en_attente} approbation${m.approbations_en_attente > 1 ? "s" : ""} en attente sur cette mission` });
  } else if (o.type === "plan" && statutTravail === "en_attente") {
    etats.push({ sorte: "attente", texte: "Plan à valider", raison: "Le chef attend ta validation de ce plan" });
  } else if (o.meta.propositions?.some((p) => p.statut === "proposee")) {
    const n = o.meta.propositions.filter((p) => p.statut === "proposee").length;
    etats.push({ sorte: "attente", texte: "Attend ta décision", raison: `${n} action${n > 1 ? "s" : ""} proposée${n > 1 ? "s" : ""} par Jarvis, sans réponse` });
  }
  if (o.meta.relecture && Number.isFinite(o.meta.relecture.demandee)) {
    etats.push({ sorte: "attente", texte: "Relecture demandée", raison: "Tu as demandé une relecture de ce livrable ; aucun agent n'est lancé par cette demande" });
  }

  // bloquée : une tâche de la mission a échoué ou attend un exécutant, ou le chef a marqué la carte de travail
  const echec = m?.taches.find((t) => ECHECS.has(t.statut));
  const sansExecutant = m?.taches.find((t) => t.statut === "WAITING_PROVIDER");
  if (m && (ECHECS.has(m.statut) || echec)) {
    etats.push({ sorte: "bloquee", texte: "Bloquée", raison: echec?.raison ? `Tâche en échec : ${echec.raison}` : "Une tâche de cette mission a échoué" });
  } else if (sansExecutant) {
    etats.push({ sorte: "bloquee", texte: "Sans exécutant", raison: sansExecutant.raison || "Aucun exécutant disponible pour cette tâche" });
  } else if ((o.type === "tache" || o.type === "plan") && /bloqu|échec|echec|refus/i.test(statutTravail)) {
    etats.push({ sorte: "bloquee", texte: "Bloquée", raison: `Statut déclaré par le chef : ${statutTravail}` });
  }

  // périmée : le texte a été modifié APRÈS le lancement de l'analyse dont la carte affiche le résultat
  const derniereEdition = o.meta.historique?.[0]?.ts;
  if (m && o.meta.jarvis_resume && typeof derniereEdition === "number" && derniereEdition > m.cree) {
    etats.push({ sorte: "perimee", texte: "Analyse périmée", raison: "Le texte a changé depuis l'analyse de Jarvis : relance « Analyser avec Jarvis »" });
  }
  return etats;
}

export interface Provenance {
  /** « Toi », « Jarvis (chef) », « Telegram »… ; absent si le serveur ne l'a pas enregistré */
  auteur?: string;
  /** vrai si l'auteur est un agent */
  agent: boolean;
  /** modèle ou fournisseur qui a produit le dernier livrable de la carte, s'il est connu */
  modele?: string;
  /** horodatage (s) de la dernière modification, sinon de la création */
  date?: number;
  modifiee: boolean;
  version: number;
  /** nombre de relations entrantes (cartes sources) */
  sources: number;
}

const AUTEURS: Record<string, [string, boolean]> = {
  studio: ["Toi", false], "studio:humain": ["Toi", false], test: ["Toi", false], cli: ["Toi (terminal)", false],
  chef: ["Jarvis (chef)", true], jarvis: ["Jarvis (chef)", true], telegram: ["Telegram", false], apercu: ["Aperçu de lien", true],
};

/** Provenance d'une carte ; null s'il n'y a rien de plus à dire que « créée par toi, jamais modifiée ». */
export function provenance(o: ObjetBoard, sources = 0): Provenance | null {
  const brut = typeof o.meta.source === "string" && o.meta.source ? o.meta.source : o.auteur ?? "";
  const connu = AUTEURS[brut] ?? (brut.startsWith("executant") || brut.startsWith("agent") ? [brut, true] as [string, boolean] : undefined);
  const dernier = o.artefacts?.length ? o.artefacts[o.artefacts.length - 1] : undefined;
  const modele = dernier?.fournisseur
    || (typeof o.meta.modele === "string" && o.meta.modele) || (typeof o.meta.agent === "string" && o.meta.agent) || undefined;
  const modifiee = o.version > 1;
  const p: Provenance = {
    auteur: connu?.[0] ?? (brut || undefined), agent: connu?.[1] ?? false, modele: modele || undefined,
    date: o.maj || o.cree || undefined, modifiee, version: o.version, sources,
  };
  const banal = !p.agent && !p.modele && !sources && !modifiee && (!p.auteur || p.auteur === "Toi");
  return banal ? null : p;
}

/** Carte qui porte un livrable : produit par une mission, ou posée comme livrable d'une autre carte. */
export function estLivrable(o: ObjetBoard): boolean {
  return Boolean(o.artefacts?.length) || typeof o.meta.livrable_de === "string";
}

const VIDES = new Set(["les", "des", "une", "pour", "avec", "dans", "sur", "the", "and", "que", "qui", "est", "aux", "par", "pas", "plus", "note", "carte"]);

function mots(o: ObjetBoard): Set<string> {
  const texte = [o.meta.titre, o.meta.description, o.meta.hote, o.asset?.nom, o.contenu.slice(0, 2000), ...(o.meta.tags ?? [])].join(" ");
  return new Set(texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().split(/[^a-z0-9]+/).filter((m) => m.length > 2 && !VIDES.has(m)));
}

/** Cartes proches d'une carte : mots en commun (titre, description, étiquettes, texte, site). Calcul LOCAL, sans
 *  modèle : c'est une proximité de vocabulaire, pas une compréhension. Rend les `max` meilleures, score > 0. */
export function cartesProches(source: ObjetBoard, objets: readonly ObjetBoard[], max = 6): { objet: ObjetBoard; communs: string[] }[] {
  const ref = mots(source);
  if (!ref.size) return [];
  const sorties: { objet: ObjetBoard; communs: string[]; score: number }[] = [];
  for (const o of objets) {
    if (o.id === source.id || o.parent_id || ["trait", "forme", "fleche", "cadre", "agents"].includes(o.type)) continue;
    const m = mots(o);
    const communs = [...ref].filter((x) => m.has(x));
    if (communs.length) sorties.push({ objet: o, communs, score: communs.length / Math.sqrt(ref.size * Math.max(1, m.size)) });
  }
  return sorties.sort((a, b) => b.score - a.score).slice(0, max).map(({ objet, communs }) => ({ objet, communs }));
}
