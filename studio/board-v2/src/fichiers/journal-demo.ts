import type { Inspection } from "../api";
import type { EntreeMemoire } from "./journal-donnees";

const DATE = 1760004000;
const MISSION = "MI-demo00000001";
const TACHE = "TA-demo3";
const ANCIENNE_TENTATIVE = "AT-demo-integration-echec";
const NOUVELLE_TENTATIVE = "AT-demo-integration-reprise";

export const journalDemo: EntreeMemoire[] = [
  { id: "demo-106", nature: "reprise", titre: "Intégration React · Nouvelle tentative",
    detail: "L’intégration reprend avec une maquette corrigée.", date: DATE + 1800, factice: true, cause_id: "demo-104",
    preuve: { mission_id: MISSION, tache_id: TACHE, tentative_id: NOUVELLE_TENTATIVE, sequence: 106 } },
  { id: "demo-105", nature: "frustration", titre: "Intégration React · Frustration déclarée",
    detail: "L’agent signale avoir répété deux vérifications parce que le point de référence a changé.", date: DATE + 1600,
    auteur: "Agent d’intégration (démo)", factice: true,
    preuve: { mission_id: MISSION, tache_id: TACHE, tentative_id: ANCIENNE_TENTATIVE, sequence: 105 } },
  { id: "demo-104", nature: "echec", titre: "Intégration React · Tentative échouée",
    detail: "La maquette et les critères de validation ne correspondaient plus.", date: DATE + 1350, factice: true,
    cause_id: "demo-103", preuve: { mission_id: MISSION, tache_id: TACHE, tentative_id: ANCIENNE_TENTATIVE, sequence: 104 } },
  { id: "demo-103", nature: "blocage", titre: "Intégration React · Maquette à vérifier",
    detail: "L’intégration attend une maquette de référence.", date: DATE + 1200, factice: true,
    preuve: { mission_id: MISSION, tache_id: TACHE, tentative_id: ANCIENNE_TENTATIVE, sequence: 103 } },
];

const TYPES = { reprise: "tache_louee", frustration: "frustration_declaree", echec: "tache_echec", blocage: "tache_etat" } as const;
export const chronologieJournalDemo: Inspection["chronologie"] = journalDemo.map((e) => ({
  seq: e.preuve.sequence,
  type: TYPES[e.nature as keyof typeof TYPES],
  ts: e.date,
  tache_id: e.preuve.tache_id || null,
  donnees: { texte: e.detail, factice: true, tentative_id: e.preuve.tentative_id, ...(e.auteur ? { auteur: e.auteur } : {}) },
}));

export const tentativesJournalDemo: Inspection["taches"][number]["tentatives"] = [
  { id: ANCIENNE_TENTATIVE, executant_nom: "Agent d’intégration (démo)", fournisseur: "codex",
    debut: DATE + 900, fin: DATE + 1650, issue: "echec" },
  { id: NOUVELLE_TENTATIVE, executant_nom: "Agent d’intégration (démo)", fournisseur: "codex",
    debut: DATE + 1800, fin: null, issue: null },
];
