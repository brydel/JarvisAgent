// ════════════════════════════════════════════════════════════════════════════════════════════════════════════
// MODE DÉMO — données FICTIVES, isolées de l'état réel. Affichées uniquement avec ?demo=1 et le bandeau « DÉMO ».
// Composition reprise de design/references/JARVIS_BOARD_V2_REFERENCE.png (géométrie mesurée, écran ÷ 0,8).
// Les fichiers (public/demo) sont réels (lecture, forme d'onde, vignettes PDF) ; les missions et agents ne le sont pas.
// ════════════════════════════════════════════════════════════════════════════════════════════════════════════
import type { Asset, EtatBoard, MissionResume, ObjetBoard } from "../types";
import type { Inspection } from "../api";

const T0 = 1_760_000_000;
const D = "/v2/demo/";

function asset(id: string, nom: string, mime: string, famille: Asset["famille"], taille: number,
  meta: Asset["meta"] = {}, vignette?: string): Asset {
  return { id, nom, mime, famille, taille, meta, url: D + nom, vignette_url: vignette ? D + vignette : null };
}

const missionDemo: MissionResume = {
  id: "MI-demo00000001",
  objectif: "Lancer le site web IA",
  statut: "OPEN",
  cree: T0,
  taches: [
    { id: "TA-demo1", type: "recherche", libelle: "Recherche et benchmark", niveau: "L1", statut: "SUCCEEDED", fournisseur_choisi: "claude", fournisseur: "auto", essais: 1, raison: "" },
    { id: "TA-demo2", type: "design", libelle: "Maquettes UI/UX", niveau: "L1", statut: "SUCCEEDED", fournisseur_choisi: "claude", fournisseur: "auto", essais: 1, raison: "" },
    { id: "TA-demo3", type: "developpement", libelle: "Développement", niveau: "L2", statut: "RUNNING", fournisseur_choisi: "codex", fournisseur: "auto", essais: 1, raison: "" },
    { id: "TA-demo4", type: "tests", libelle: "Tests et déploiement", niveau: "L2", statut: "QUEUED", fournisseur_choisi: null, fournisseur: "auto", essais: 0, raison: "" },
  ],
  faites: 2,
  total: 4,
  progression: 50,
  agents: [
    { id: "AT-demo-analyste", nom: "Analyste", role: "Recherche", fournisseur: "claude", issue: null, debut: T0, fin: null, executant: "démo", tache_id: "TA-demo1", statut_tache: "RUNNING" },
    { id: "AT-demo-designer", nom: "Designer", role: "UI/UX", fournisseur: "claude", issue: null, debut: T0, fin: null, executant: "démo", tache_id: "TA-demo2", statut_tache: "RUNNING" },
    { id: "AT-demo-developpeur", nom: "Développeur", role: "Code", fournisseur: "codex", issue: null, debut: T0, fin: null, executant: "démo", tache_id: "TA-demo3", statut_tache: "RUNNING" },
    { id: "AT-demo-redacteur", nom: "Rédacteur", role: "Contenu", fournisseur: "claude", issue: "reussi", debut: T0, fin: T0 + 600, executant: "démo", tache_id: "TA-demo4", statut_tache: "QUEUED" },
  ],
  approbations_en_attente: 1,
};

function objet(o: Partial<ObjetBoard> & Pick<ObjetBoard, "id" | "type" | "x" | "y" | "largeur" | "hauteur">): ObjetBoard {
  return {
    espace: "accueil", contenu: "", z: 1, priorite: "", meta: {}, asset_id: null, asset: null, mission_id: null, mission: null,
    parent_id: null, verrouille: 0, version: 1, cree: T0, maj: T0, commentaires: 0, ...o,
  };
}

export function fixtureDemo(): EtatBoard {
  const montagne = asset("AS-demo-montagne", "montagne.jpg", "image/jpeg", "image", 62_999, { largeur: 1920, hauteur: 1080 });
  const pdf = asset("AS-demo-pdf", "plan-produit.pdf", "application/pdf", "pdf", 1_173);
  const audio = asset("AS-demo-audio", "reunion-ideation.mp3", "audio/mpeg", "audio", 144_866, { duree: 12 });
  const video = asset("AS-demo-video", "presentation-produit.mp4", "video/mp4", "video", 50_470,
    { duree: 6, largeur: 740, hauteur: 340 }, "video-vignette.jpg");
  const objets: ObjetBoard[] = [
    objet({ id: "BO-demo-image", type: "image", x: 168.75, y: 53.75, largeur: 491, hauteur: 309, priorite: "P2", asset: montagne,
      asset_id: montagne.id, meta: { titre: "Inspiration — Design", description: "Paysage montagne" } }),
    objet({ id: "BO-demo-lien", type: "lien", x: 707.5, y: 35, largeur: 434, hauteur: 356, priorite: "P1", contenu: "https://claude.ai",
      meta: { titre: "Claude — IA pour tous vos projets", url: "https://claude.ai", hote: "claude.ai",
        description: "Un assistant IA sûr et performant pour la recherche, l'écriture et le code.",
        tags: ["IA", "Recherche", "Productivité"], demo_src: D + "claude-apercu.jpg", marque: "claude" } }),
    objet({ id: "BO-demo-pdf", type: "pdf", x: 1226, y: 43.75, largeur: 348, hauteur: 318, priorite: "P3", asset: pdf, asset_id: pdf.id,
      meta: { titre: "Plan produit v1.0.pdf", description: "Spécifications du produit, roadmap et maquettes initiales.",
        tags: ["Produit", "Roadmap", "Design"] } }),
    objet({ id: "BO-demo-note", type: "note", x: 182.5, y: 418.75, largeur: 408, hauteur: 391, priorite: "P1",
      contenu: "**Objectif** : créer une plateforme unifiée qui combine IA, gestion de projets et connaissances.\n\n" +
        "- Expérience fluide et moderne\n- Agents spécialisés par domaine\n- Collaboration en temps réel\n- Sécurisé et privé",
      meta: { titre: "Note de recherche", tags: ["Stratégie", "Recherche"] } }),
    objet({ id: "BO-demo-mission", type: "mission", x: 747.5, y: 443.75, largeur: 452, hauteur: 362, z: 2, priorite: "P1",
      mission_id: missionDemo.id, mission: missionDemo,
      meta: { titre: missionDemo.objectif, echeance: "15 janv. 2026", tags: ["SiteWeb", "Lancement", "Produit"],
        description: "Développer et lancer le nouveau site web de Jarvis Studio avec une expérience moderne et alimentée par l'IA." } }),
    objet({ id: "BO-demo-agents", type: "agents", x: 1270, y: 432.5, largeur: 331, hauteur: 342, mission_id: missionDemo.id,
      mission: missionDemo, meta: { titre: "Équipe d'agents" } }),
    objet({ id: "BO-demo-audio", type: "audio", x: 307.5, y: 836.25, largeur: 462, hauteur: 178, priorite: "P3", asset: audio,
      asset_id: audio.id, meta: { titre: "Réunion produit – idéation", demo_src: D + "reunion-ideation.mp3" } }),
    objet({ id: "BO-demo-video", type: "video", x: 795, y: 836.25, largeur: 378, hauteur: 178, priorite: "P2", asset: video,
      asset_id: video.id, meta: { titre: "Présentation produit.mp4" } }),
    objet({ id: "BO-demo-dossier", type: "dossier", x: 1205, y: 860, largeur: 378, hauteur: 152,
      meta: { titre: "Ressources design", demo_vignettes: [D + "ressource-1.jpg", D + "ressource-2.jpg", D + "ressource-3.jpg"],
        demo_elements: 4 } }),
  ];
  // Points d'attache mesurés sur la maquette (côté, position relative le long du côté) : démo seulement.
  const liens = [
    { id: "BL-demo1", source_id: "BO-demo-image", cible_id: "BO-demo-mission", libelle: "Inspire", style: "inspire" as const, cotes: { s: "right", sf: 0.44, t: "left", tf: 0.16, c: 0.5, lt: 0.62 } as const },
    { id: "BL-demo2", source_id: "BO-demo-image", cible_id: "BO-demo-mission", libelle: "", style: "inspire" as const, cotes: { s: "bottom", sf: 0.72, t: "left", tf: 0.16 } as const },
    { id: "BL-demo3", source_id: "BO-demo-note", cible_id: "BO-demo-mission", libelle: "Alimente", style: "alimente" as const, cotes: { s: "right", sf: 0.39, t: "left", tf: 0.57, lt: 0.42 } as const },
    { id: "BL-demo4", source_id: "BO-demo-mission", cible_id: "BO-demo-lien", libelle: "", style: "defaut" as const, cotes: { s: "top", sf: 0.45, t: "bottom", tf: 0.565 } as const },
    { id: "BL-demo5", source_id: "BO-demo-mission", cible_id: "BO-demo-pdf", libelle: "", style: "alimente" as const, cotes: { s: "top", sf: 0.945, t: "bottom", tf: 0.23 } as const },
    { id: "BL-demo6", source_id: "BO-demo-lien", cible_id: "BO-demo-pdf", libelle: "", style: "depend" as const, cotes: { s: "right", sf: 0.22, t: "left", tf: 0.22 } as const },
    { id: "BL-demo7", source_id: "BO-demo-agents", cible_id: "BO-demo-mission", libelle: "", style: "defaut" as const, cotes: { s: "left", sf: 0.45, t: "right", tf: 0.4 } as const },
    { id: "BL-demo8", source_id: "BO-demo-mission", cible_id: "BO-demo-video", libelle: "", style: "defaut" as const, cotes: { s: "bottom", sf: 0.49, t: "top", tf: 0.46 } as const },
    { id: "BL-demo9", source_id: "BO-demo-mission", cible_id: "BO-demo-audio", libelle: "", style: "defaut" as const, cotes: { s: "left", sf: 0.86, t: "top", tf: 0.74 } as const },
    { id: "BL-demo10", source_id: "BO-demo-dossier", cible_id: "BO-demo-mission", libelle: "Utilisé par", style: "utilise" as const, cotes: { s: "top", sf: 0.36, t: "right", tf: 0.68, c: 0.2, lt: 0.22 } as const },
  ];
  return { espace: "accueil", objets, liens };
}

export function inspectionDemo(missionId: string): Inspection {
  const m = missionDemo;
  return {
    id: missionId, objectif: m.objectif, statut: m.statut, source: "démo", demandeur: "démo", cree: T0,
    description: "Développer et lancer le nouveau site web de Jarvis Studio avec une expérience moderne et alimentée par l'IA.",
    tags: ["SiteWeb", "Lancement", "Produit"],
    taches: m.taches.map((t, i) => ({
      ...t, essais_max: 3, tentatives: [],
      approbations: i === 1 ? [{ id: "AP-demo1", statut: "en_attente", demandeur: "Designer (démo)", decide_par: null, cree: Date.now() / 1000 - 7200 }] : [],
    })),
    artefacts: [],
    chronologie: [
      { seq: 3, type: "demo", ts: Date.now() / 1000 - 720, tache_id: null, donnees: { texte: "Designer a ajouté une image", agent: "AT-demo-designer" } },
      { seq: 2, type: "demo", ts: Date.now() / 1000 - 3600, tache_id: null, donnees: { texte: "Analyste a terminé « Recherche et benchmark »", agent: "AT-demo-analyste" } },
      { seq: 1, type: "demo", ts: Date.now() / 1000 - 7200, tache_id: null, donnees: { texte: "Mission créée", agent: "" } },
    ],
  };
}
