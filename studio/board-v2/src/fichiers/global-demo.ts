import { SourceDemo, type Source } from "../api";
import type { EtatBoard, ObjetBoard } from "../types";
import { journalDemo } from "./journal-demo";
import type { PageGrapheGlobal, SessionGraphe } from "./global-donnees";

const PROJET_CAMPAGNE = "Campagne de lancement";
const PROJET_ACCUEIL = "Refonte de l'accueil";
const DATE = 1_760_004_000;
const projetsDemo = new WeakMap<Source, Map<string, Source>>();
let navigationDemo: Map<string, Source> | undefined;

function sourcesDemo(source: Source) {
  let projets = projetsDemo.get(source);
  if (projets) return projets;
  const base: ObjetBoard = {
    id: "BO-demo-campagne-note", type: "note", espace: PROJET_CAMPAGNE, contenu: "",
    x: 80, y: 80, largeur: 408, hauteur: 260, z: 1, priorite: "", meta: {},
    asset_id: null, asset: null, mission_id: null, mission: null, parent_id: null,
    verrouille: 0, version: 1, cree: DATE, maj: DATE, commentaires: 0,
  };
  const campagne: EtatBoard = {
    espace: PROJET_CAMPAGNE,
    objets: [
      { ...base, contenu: "Préparer une campagne avec la référence Atelier Lumière et les critères de la refonte.",
        meta: { titre: "Brief de campagne", reference_id: "RF-demo00000001" } },
      { ...base, id: "BO-demo-campagne-redaction", y: 400,
        contenu: "Les messages de la campagne suivent [[BO-demo-campagne-note|Brief de campagne]].",
        meta: { titre: "Messages de lancement" } },
      { ...base, id: "BO-demo-campagne-preuve", type: "document", y: 720,
        contenu: "Validation éditoriale de démonstration. Le guide visuel est partagé avec la refonte.",
        meta: { titre: "Relecture des messages", reference_id: "RF-demo00000001" } },
    ],
    liens: [
      { id: "BL-demo-campagne-redaction", source_id: "BO-demo-campagne-note", cible_id: "BO-demo-campagne-redaction",
        libelle: "Contexte éditorial", style: "alimente" },
      { id: "BL-demo-campagne-relecture", source_id: "BO-demo-campagne-redaction", cible_id: "BO-demo-campagne-preuve",
        libelle: "À relire", style: "utilise" },
    ],
  };
  projets = new Map([[source.espace, source]]);
  if (source.espace !== PROJET_CAMPAGNE) projets.set(PROJET_CAMPAGNE, new SourceDemo(campagne, PROJET_CAMPAGNE));
  else projets.set(PROJET_ACCUEIL, new SourceDemo());
  for (const adaptateur of projets.values()) projetsDemo.set(adaptateur, projets);
  return projets;
}

export function sourceProjetDemo(source: Source, projet: string): Source {
  if (!source.demo) return source;
  const nom = projet === "accueil" ? PROJET_ACCUEIL : projet;
  const projets = sourcesDemo(source);
  let adaptateur = projets.get(nom);
  if (!adaptateur) {
    adaptateur = new SourceDemo({ espace: nom, objets: [], liens: [] }, nom);
    projets.set(nom, adaptateur);
    projetsDemo.set(adaptateur, projets);
  }
  return adaptateur;
}

export function creerSourceDemo(espace = "accueil"): Source {
  if (!navigationDemo) navigationDemo = sourcesDemo(new SourceDemo());
  const origine = navigationDemo.get(PROJET_ACCUEIL)!;
  return sourceProjetDemo(origine, espace);
}

export async function grapheGlobalDemo(source: Source): Promise<PageGrapheGlobal> {
  const courant = await source.charger();
  const origine = source.espace;
  const snapshots = await Promise.all([...sourcesDemo(source)].map(async ([nom, adaptateur]) => {
    const b = await adaptateur.charger();
    return { ...b, espace: nom };
  }));
  const principal = { ...courant, espace: origine };
  const boards = [principal, ...snapshots.filter((b) => b.espace !== origine)];
  const objets = boards.flatMap((b) => b.objets.map((o) => ({
    ...o, espace: b.espace,
    meta: o.id === "BO-demo-note" ? { ...o.meta, reference_id: "RF-demo00000001" } : o.meta,
  })));
  const projetAccueil = objets.find((o) => o.id === "BO-demo-note")?.espace ?? PROJET_ACCUEIL;
  const disponibles = new Set(objets.map((o) => o.id));
  const membres = (ids: string[]) => ids.filter((id) => disponibles.has(id));
  const sessions: SessionGraphe[] = [
    { id: "AT-demo-integration-echec", titre: "Intégration React · Première tentative", projet: projetAccueil, projets: [projetAccueil],
      origine: "tentative", statut: "échec", debut: DATE, fin: DATE + 1350,
      objet_ids: membres(["BO-demo-note", "BO-demo-image", "BO-demo-pdf"]),
      mission_ids: ["MI-demo00000001"], evenement_ids: ["demo-103", "demo-104", "demo-105"] },
    { id: "AT-demo-integration-reprise", titre: "Intégration React · Reprise", projet: projetAccueil, projets: [projetAccueil],
      origine: "tentative", statut: "en cours", debut: DATE + 1800, fin: null,
      objet_ids: membres(["BO-demo-decisions", "BO-demo-video", "BO-demo-audio"]),
      mission_ids: ["MI-demo00000001"], evenement_ids: ["demo-106"] },
    { id: "AR-demo-campagne-redaction", titre: "Campagne · Rédaction", projet: PROJET_CAMPAGNE, projets: [PROJET_CAMPAGNE],
      origine: "runtime", statut: "terminée", debut: DATE + 200, fin: DATE + 900,
      objet_ids: membres(["BO-demo-campagne-note", "BO-demo-campagne-redaction"]), mission_ids: [], evenement_ids: [] },
    { id: "AR-demo-campagne-relecture", titre: "Campagne · Relecture", projet: PROJET_CAMPAGNE, projets: [PROJET_CAMPAGNE],
      origine: "runtime", statut: "en cours", debut: DATE + 1000, fin: null,
      objet_ids: membres(["BO-demo-campagne-preuve"]), mission_ids: [], evenement_ids: [] },
  ];
  const liens = boards.flatMap((b) => b.liens);
  const entrees = structuredClone(journalDemo);
  return {
    page: 1, limite: 100, objets, liens, entrees, sessions,
    projets: boards.map((b) => ({ nom: b.espace, objets: b.objets.length })),
    couverture: {
      objets: { charges: objets.length, total: objets.length }, liens: { charges: liens.length, total: liens.length },
      sessions: { charges: sessions.length, total: sessions.length }, entrees: { charges: entrees.length, total: entrees.length },
    },
    suivant: null, avertissements: [], cle_disposition: "demo-graphe-global-v1",
  };
}
