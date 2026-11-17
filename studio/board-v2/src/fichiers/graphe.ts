import type { EtatBoard, ObjetBoard, StyleLien } from "../types";
import type { GroupeGraphe, SessionGraphe } from "./global-donnees";
import type { Observation, Reference, ReferenceGraphe } from "../references/api";
import { LIBELLE_TYPE } from "../lib/format";
import { idMemoire, titreMemoire, type EntreeMemoire } from "./journal-donnees";
import { estNote, indexerNotes, lireWikiliens, resoudreWiki, titreNote } from "../lib/wikiliens";
export { estNote } from "../lib/wikiliens";

export const TYPES = ["image", "capture", "video", "audio", "pdf", "document", "note", "texte"] as const;
export type TypeFichier = (typeof TYPES)[number];
export const estFichier = (o: ObjetBoard) => TYPES.includes(o.type as TypeFichier);
export type Entite = { id: string; titre: string; type: string; objet?: ObjetBoard; reference?: string; memoire?: EntreeMemoire;
  missionId?: string; sourceRag?: Reference; observation?: Observation; projet?: string;
  sessionId?: string; sessionIds?: string[] };
export type Relation = { id: string; source: string; cible: string; style: StyleLien | "source" | "dossier" | "fichier" | "wikilien" | "memoire" | "causalite"; texte: string; occurrences?: number; idsRegroupes?: string[] };
type EntiteJournal = Entite & { memoire: EntreeMemoire };
export type Graphe = { groupes?: GroupeGraphe[]; sessions?: SessionGraphe[]; racines: Entite[]; fichiers: (Entite & { objet: ObjetBoard })[]; entites: Map<string, Entite>; relations: Relation[]; adjacents: Map<string, Relation[]>; journal: EntiteJournal[]; notes: ReturnType<typeof indexerNotes> };
export const LIBELLES = { defaut: "Relation", inspire: "Inspire", alimente: "Alimente", utilise: "Utilisé par",
  depend: "Dépend de", source: "Référence associée", dossier: "Dans le dossier", fichier: "Même fichier", wikilien: "Wikilien", memoire: "Preuve de mission", causalite: "Événement lié" } as const;
export const titreDe = (o: ObjetBoard) => estNote(o) ? titreNote(o) : o.meta.titre || o.asset?.nom || o.contenu.trim().slice(0, 78) || LIBELLE_TYPE[o.type] || o.type;
export const autre = (r: Relation, id: string) => r.source === id ? r.cible : r.source;
export const tronquer = (s: string, n = 38) => s.length > n ? s.slice(0, n - 1) + "…" : s;
const TYPE_OBSERVATION: Record<Observation["type"], string> = {
  structure: "observation-structure", element: "observation-structure", palette: "observation-style",
  typographie: "observation-style", mouvement: "observation-style", capture: "observation-mesures",
  mesure: "observation-mesures", comparaison: "observation-mesures", lien: "observation-preuves",
  preuve: "observation-preuves", media: "observation-preuves",
};
const MAX_ENTITES = 64;
const MAX_LIENS = 144;

export function construire(board: EtatBoard, entrees: readonly EntreeMemoire[] = [], references: readonly ReferenceGraphe[] = [], sessions?: readonly SessionGraphe[]): Graphe {
  const objets = new Map(board.objets.map((o) => [o.id, o]));
  const fichiers = board.objets.filter(estFichier)
    .sort((a, b) => b.maj - a.maj).map((objet) => ({ id: objet.id, titre: titreDe(objet), type: objet.type, objet }));
  const idsFichiers = new Set(fichiers.map((f) => f.id));
  const entites = new Map<string, Entite>(fichiers.map((f) => [f.id, f]));
  const relations: Relation[] = [];
  const adjacents = new Map<string, Relation[]>();
  const integrer = (id: string) => {
    if (entites.has(id)) return true;
    const objet = objets.get(id);
    if (!objet) return false;
    entites.set(id, { id, titre: titreDe(objet), type: objet.type, objet });
    return true;
  };
  const lier = (r: Relation) => {
    if (r.source === r.cible || !integrer(r.source) || !integrer(r.cible)) return;
    relations.push(r);
    for (const id of [r.source, r.cible]) {
      const voisins = adjacents.get(id) ?? [];
      if (!adjacents.has(id)) adjacents.set(id, voisins);
      voisins.push(r);
    }
  };
  for (const l of board.liens) {
    if (idsFichiers.has(l.source_id) || idsFichiers.has(l.cible_id)) {
      lier({ id: l.id, source: l.source_id, cible: l.cible_id, style: l.style, texte: l.libelle || LIBELLES[l.style] });
    }
  }
  const voisinageDirect = new Set(entites.keys());
  for (const l of board.liens) {
    if (!idsFichiers.has(l.source_id) && !idsFichiers.has(l.cible_id) && (voisinageDirect.has(l.source_id) || voisinageDirect.has(l.cible_id))) {
      lier({ id: l.id, source: l.source_id, cible: l.cible_id, style: l.style, texte: l.libelle || LIBELLES[l.style] });
    }
  }
  const notes = indexerNotes(board.objets);
  const parAsset = new Map<string, string>();
  for (const { objet: o } of fichiers) {
    if (estNote(o)) {
      const cibles = new Set<string>();
      for (const lien of lireWikiliens(o.contenu)) {
        const cible = resoudreWiki(notes, o, lien);
        if (cible) cibles.add(cible);
      }
      for (const cible of cibles) lier({ id: "wiki:" + o.id + ":" + cible, source: o.id, cible, style: "wikilien", texte: LIBELLES.wikilien });
    }
    if (o.parent_id && objets.get(o.parent_id)?.type === "dossier") {
      lier({ id: `dossier:${o.id}`, source: o.id, cible: o.parent_id, style: "dossier", texte: LIBELLES.dossier });
    }
    if (o.meta.reference_id) {
      const ref = o.meta.reference_id;
      if (!entites.has(ref)) entites.set(ref, { id: ref, titre: ref, type: "reference", reference: ref });
      lier({ id: `ref:${o.id}`, source: o.id, cible: ref, style: "source", texte: LIBELLES.source });
    }
    if (o.asset_id) {
      const original = parAsset.get(o.asset_id);
      if (original) lier({ id: `asset:${o.id}`, source: o.id, cible: original, style: "fichier", texte: LIBELLES.fichier });
      else parAsset.set(o.asset_id, o.id);
    }
  }
  const journal = [...new Map(entrees.map((memoire) => [memoire.id, memoire])).values()]
    .map((memoire): EntiteJournal => ({
      id: idMemoire(memoire.id), titre: titreMemoire(memoire), type: "memoire-" + memoire.nature, memoire,
    }));
  if (journal.length) {
    const cartesMissions = new Map<string, ObjetBoard>();
    for (const o of board.objets) {
      if (o.mission_id && (!cartesMissions.has(o.mission_id) || o.type === "mission")) cartesMissions.set(o.mission_id, o);
    }
    for (const e of journal) entites.set(e.id, e);
    for (const e of journal) {
      const { preuve, mission_titre, cause_id } = e.memoire;
      const carte = cartesMissions.get(preuve.mission_id);
      const missionId = carte?.id ?? "journal-mission:" + preuve.mission_id;
      if (carte) integrer(carte.id);
      // La mission reste une preuve navigable même si elle ne possède pas de carte dans ce Board.
      if (!entites.has(missionId)) entites.set(missionId, {
        id: missionId, type: "mission", titre: mission_titre || preuve.mission_id, missionId: preuve.mission_id,
      });
      lier({ id: "mission:" + e.id, source: e.id, cible: missionId, style: "memoire", texte: LIBELLES.memoire });
      if (cause_id && entites.has(idMemoire(cause_id))) {
        lier({ id: "cause:" + e.id, source: idMemoire(cause_id), cible: e.id, style: "causalite", texte: LIBELLES.causalite });
      }
    }
  }
  const sources = new Map<string, ReferenceGraphe>();
  for (const reference of references) {
    if (reference.supprime) continue;
    const precedente = sources.get(reference.id);
    sources.set(reference.id, { ...precedente, ...reference,
      observations: reference.observations ?? precedente?.observations });
  }
  const observations = new Set<string>();
  for (const reference of sources.values()) {
    entites.set(reference.id, { ...entites.get(reference.id), id: reference.id, titre: reference.titre,
      type: "reference", reference: reference.id, sourceRag: reference });
    for (const observation of reference.observations ?? []) {
      if (observation.preuve.reference_id !== reference.id || observations.has(observation.id)) continue;
      observations.add(observation.id);
      entites.set(observation.id, { id: observation.id, titre: observation.titre,
        type: TYPE_OBSERVATION[observation.type] ?? "observation-preuves", reference: reference.id, sourceRag: reference, observation });
      lier({ id: "observation:" + observation.id, source: reference.id, cible: observation.id,
        style: "source", texte: "Observation de la source" });
    }
  }
  const contextes = board.objets.filter((o) => o.type === "mission" || o.type === "dossier");
  for (const objet of contextes) {
    entites.set(objet.id, { ...entites.get(objet.id), id: objet.id, titre: titreDe(objet), type: objet.type,
      objet, ...(objet.mission_id ? { missionId: objet.mission_id } : {}) });
  }
  if (sessions !== undefined) for (const objet of board.objets) integrer(objet.id);
  const liensConnus = new Set(relations.map((r) => r.id));
  for (const lien of board.liens) {
    if (!liensConnus.has(lien.id) && entites.has(lien.source_id) && entites.has(lien.cible_id)) {
      lier({ id: lien.id, source: lien.source_id, cible: lien.cible_id, style: lien.style,
        texte: lien.libelle || LIBELLES[lien.style] });
    }
  }
  const racines = [...new Set([...fichiers.map((f) => f.id), ...journal.map((e) => e.id),
    ...contextes.map((o) => o.id), ...(sessions !== undefined ? board.objets.map((o) => o.id) : []), ...sources.keys(), ...observations])].map((id) => entites.get(id)!);
  const graphe: Graphe = { racines, fichiers, entites, relations, adjacents, journal, notes };
  if (sessions !== undefined) attribuerSessions(graphe, sessions, board.objets);
  return graphe;
}

function attribuerSessions(graphe: Graphe, sessions: readonly SessionGraphe[], objets: readonly ObjetBoard[]) {
  const appartenances = new Map<string, Set<string>>();
  const sessionsConnues = new Map(sessions.map((s) => [s.id, s]));
  const parMission = new Map<string, string[]>();
  const projetsMissions = new Map<string, string>();
  for (const objet of objets) {
    if (objet.mission_id) projetsMissions.set(objet.mission_id, objet.espace);
  }
  for (const e of graphe.entites.values()) {
    e.projet = e.objet?.espace || (e.memoire ? projetsMissions.get(e.memoire.preuve.mission_id) : undefined);
    if (e.missionId || e.objet?.type === "mission" && e.objet.mission_id) {
      const mission = e.missionId || e.objet!.mission_id!;
      const cartes = parMission.get(mission) ?? [];
      cartes.push(e.id);
      parMission.set(mission, cartes);
    }
  }
  const rattacher = (id: string, session: string) => {
    if (!graphe.entites.has(id)) return;
    if (!appartenances.has(id)) appartenances.set(id, new Set());
    appartenances.get(id)!.add(session);
  };
  for (const session of sessionsConnues.values()) {
    for (const id of session.objet_ids) rattacher(id, session.id);
    for (const id of session.evenement_ids) rattacher(idMemoire(id), session.id);
    for (const id of session.mission_ids) {
      if (!parMission.has(id)) {
        const missionId = "journal-mission:" + id;
        const mission: Entite = { id: missionId, titre: "Mission " + id, type: "mission", missionId: id, projet: session.projet };
        graphe.entites.set(missionId, mission);
        graphe.racines.push(mission);
        parMission.set(id, [missionId]);
      }
      for (const carte of parMission.get(id)!) rattacher(carte, session.id);
    }
  }
  for (const [id, ids] of appartenances) {
    const e = graphe.entites.get(id)!;
    e.sessionIds = [...ids].sort();
    if (ids.size === 1) {
      e.sessionId = e.sessionIds[0];
      e.projet ||= sessionsConnues.get(e.sessionId!)?.projet;
    }
  }
  // Une référence reste un hub documentaire unique, même lorsqu’une seule session l’utilise.
  for (const e of graphe.entites.values()) {
    if (!e.reference || e.observation) continue;
    const connues = new Set<string>();
    for (const r of graphe.adjacents.get(e.id) ?? []) {
      const voisin = graphe.entites.get(autre(r, e.id));
      if (voisin?.objet?.meta.reference_id !== e.id) continue;
      for (const session of voisin.sessionIds ?? []) connues.add(session);
    }
    if (connues.size) e.sessionIds = [...connues].sort();
  }
  const groupes: GroupeGraphe[] = [...sessionsConnues.values()].map((session) => ({
    id: session.id, titre: session.titre, projet: session.projet, nature: "session",
    ids: [...graphe.entites.values()].filter((e) => e.sessionId === session.id).map((e) => e.id),
  }));
  const historiques = new Map<string, string[]>();
  for (const e of graphe.entites.values()) {
    if (!e.objet || e.sessionIds?.length) continue;
    const projet = e.objet.espace;
    if (!historiques.has(projet)) historiques.set(projet, []);
    historiques.get(projet)!.push(e.id);
  }
  for (const [projet, ids] of historiques) {
    groupes.push({ id: "hors-session:" + projet, titre: "Sans session · " + projet, projet, ids, nature: "hors_session" });
  }
  graphe.groupes = groupes;
  graphe.sessions = [...sessionsConnues.values()];
}

export function sousGraphe(graphe: Graphe, racines: readonly Entite[], focus: string | null, profondeur: number,
  modeJournal = false, vueUnifiee = false, prioritaire: string | null = null) {
  const idsRacines = new Set(racines.map((f) => f.id));
  const permis = (e?: Entite) => vueUnifiee || !e || (e.memoire ? idsRacines.has(e.id) : modeJournal || !e.objet || !estFichier(e.objet) || idsRacines.has(e.id));
  const retenus = new Set<string>();
  const ajouter = (id: string) => {
    if (retenus.size >= MAX_ENTITES || retenus.has(id)) return false;
    retenus.add(id);
    return true;
  };
  if (vueUnifiee && prioritaire && graphe.entites.has(prioritaire)) ajouter(prioritaire);
  if (focus) {
    ajouter(focus);
    let front = [focus];
    for (let i = 0; i < profondeur && front.length && retenus.size < MAX_ENTITES; i++) {
      front = front.flatMap((id) => (graphe.adjacents.get(id) ?? []).flatMap((r) => {
        const voisin = autre(r, id);
        return permis(graphe.entites.get(voisin)) && ajouter(voisin) ? [voisin] : [];
      }));
    }
  } else {
    // Garder de la place pour les voisins tout en représentant les familles de la mémoire commune.
    const quota = Math.floor(MAX_ENTITES * .66);
    const premiers = vueUnifiee ? equilibrerRacines(racines, quota) : racines.slice(0, quota);
    for (const f of premiers) ajouter(f.id);
    const contexte = (origines: Iterable<string>) => {
      const voisins = Array.from(origines, (origine) => (graphe.adjacents.get(origine) ?? [])
        .map((r) => autre(r, origine)).filter((id) => permis(graphe.entites.get(id))));
      const candidats = vueUnifiee ? entrelacer(voisins, voisins.reduce((n, liste) => n + liste.length, 0)) : voisins.flat();
      for (const id of candidats) ajouter(id);
    };
    contexte(vueUnifiee ? [...retenus] : premiers.map((f) => f.id));
    contexte([...retenus]);
  }
  return { ids: [...retenus], relations: regrouperRelations(graphe.relations.filter((r) => retenus.has(r.source) && retenus.has(r.cible))).slice(0, MAX_LIENS) };
}

function entrelacer<T>(listes: readonly (readonly T[])[], limite: number): T[] {
  const resultat: T[] = [];
  for (let rang = 0; resultat.length < limite; rang++) {
    let ajoute = false;
    for (const liste of listes) {
      if (liste[rang] === undefined || resultat.length >= limite) continue;
      resultat.push(liste[rang]!);
      ajoute = true;
    }
    if (!ajoute) break;
  }
  return resultat;
}

function equilibrerRacines(racines: readonly Entite[], limite: number) {
  const familles = new Map<string, Entite[]>();
  const observations: Entite[] = [];
  for (const e of racines) {
    if (e.observation) { observations.push(e); continue; }
    const famille = e.sessionId ? "session:" + e.sessionId : e.memoire ? "journal" : e.reference ? "reference"
      : e.type === "mission" || e.type === "dossier" ? e.type : e.objet && estNote(e.objet) ? "note" : "fichier";
    if (!familles.has(famille)) familles.set(famille, []);
    familles.get(famille)!.push(e);
  }
  const principaux = entrelacer([...familles.values()], limite);
  return [...principaux, ...observations.slice(0, limite - principaux.length)];
}

export function regrouperRelations(relations: Relation[]) {
  const groupes = new Map<string, Relation>();
  for (const r of relations) {
    const cle = JSON.stringify([r.source, r.cible, r.style, r.texte]);
    const precedent = groupes.get(cle);
    if (precedent) {
      precedent.occurrences = (precedent.occurrences ?? 1) + 1;
      (precedent.idsRegroupes ??= [precedent.id]).push(r.id);
    } else groupes.set(cle, { ...r });
  }
  return [...groupes.values()];
}

type Point = { x: number; y: number };
export type Disposition = "constellation" | "flux";
export function disposer(ids: string[], relations: Relation[], mode: Disposition, centre: string | null): Map<string, Point> {
  const restants = new Set(ids);
  const adjacents = new Map(ids.map((id) => [id, new Set<string>()]));
  for (const r of relations) {
    adjacents.get(r.source)?.add(r.cible);
    adjacents.get(r.cible)?.add(r.source);
  }
  const racines = [...ids].sort((a, b) => (b === centre ? 1 : 0) - (a === centre ? 1 : 0) +
    (a !== centre && b !== centre ? adjacents.get(b)!.size - adjacents.get(a)!.size : 0));
  const positions = new Map<string, Point>();
  let droite = 0;
  const isoles: string[] = [];
  for (const racine of racines) {
    if (!restants.delete(racine)) continue;
    if (!adjacents.get(racine)!.size) { isoles.push(racine); continue; }
    const couches = [[racine]];
    for (let i = 0; i < couches.length; i++) {
      const suite = couches[i]!.flatMap((id) => Array.from(adjacents.get(id)!).filter((v) => restants.delete(v)));
      if (suite.length) couches.push(suite);
    }
    if (mode === "flux") {
      couches.forEach((couche, i) => couche.forEach((id, j) =>
        positions.set(id, { x: droite + 255 * i, y: 108 * (j - (couche.length - 1) / 2) })));
      droite += 255 * couches.length + 80;
    } else {
      const rayons = [0];
      for (const couche of couches.slice(1)) {
        rayons.push(Math.max(rayons.at(-1)! + 156, Math.ceil(couche.length * 188 / (2 * Math.PI))));
      }
      const max = rayons.at(-1)!;
      couches.forEach((couche, i) => couche.forEach((id, j) => {
        const angle = (j + (i % 2) * .12) / couche.length * 2 * Math.PI - Math.PI / 2;
        positions.set(id, { x: droite + max + rayons[i]! * Math.cos(angle), y: rayons[i]! * Math.sin(angle) });
      }));
      droite += 2 * max + 225;
    }
  }
  if (isoles.length) {
    if (!positions.size) droite = 0;
    const colonnes = Math.min(5, Math.ceil(Math.sqrt(isoles.length)));
    isoles.forEach((id, i) => positions.set(id, { x: droite + i % colonnes * 180, y: Math.floor(i / colonnes) * 116 }));
  }
  return positions;
}
