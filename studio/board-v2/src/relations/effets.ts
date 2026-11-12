// Ce qu'une relation FAIT. Le serveur applique les effets (lib/jarvis/board_relations.py) et rend, pour chaque
// carte, un résumé calculé (`objet.relations`) : c'est lui que l'interface affiche. Ce module en tire des textes et
// l'état d'une flèche ; il ne décide de rien. Deux exceptions, dites comme telles :
// - `creeraitBoucle` : pré-contrôle local pour griser « Dépend de » avec sa raison (le serveur refuse de toute façon) ;
// - `calculerRelations` : le même calcul que le serveur, pour le mode démo qui n'a pas de serveur.
import type { LienBoard, ObjetBoard, RefCarte, RelationsCarte, StyleLien } from "../types";

export interface EffetRelation {
  /** nom du type, tel qu'il se lit de la source vers la cible */
  nom: string;
  /** verbe court pour l'étiquette de la flèche */
  verbe: string;
  /** ce que choisir ce type change, en une phrase */
  phrase: string;
  /** faux : simple repère visuel */
  effet: boolean;
}

/** Une phrase par type : ce que ça change réellement. « Source » = d'où part la flèche, « cible » = où elle arrive. */
export const EFFETS: Record<StyleLien, EffetRelation> = {
  defaut: { nom: "Relation simple", verbe: "relié à", effet: false,
    phrase: "Simple repère : ne change rien au travail des deux cartes." },
  inspire: { nom: "Inspire", verbe: "inspire", effet: true,
    phrase: "Si la source vient de la bibliothèque de références, ses passages les plus proches sont joints, avec leur citation, au travail de la cible." },
  alimente: { nom: "Alimente", verbe: "alimente", effet: true,
    phrase: "Le livrable (ou le contenu) de la source est joint, comme donnée, au travail de la cible quand il est préparé." },
  utilise: { nom: "Utilisé par", verbe: "utilisé par", effet: false,
    phrase: "Simple repère : note que la cible se sert de la source, sans effet sur leur travail." },
  depend: { nom: "Dépend de", verbe: "dépend de", effet: true,
    phrase: "La source est bloquée tant que la cible n'est pas terminée : son lancement est refusé et ses tâches attendent." },
};

/** La même phrase, avec les deux cartes nommées : ce que choisir ce type changerait pour CETTE flèche. */
export function phraseConcrete(style: StyleLien, source: string, cible: string): string {
  const s = `« ${source} »`, c = `« ${cible} »`;
  if (style === "depend") return `${s} sera bloquée tant que ${c} n'est pas terminée : son lancement sera refusé.`;
  if (style === "alimente") return `Le livrable (ou le contenu) de ${s} sera joint, comme donnée, au travail de ${c}.`;
  if (style === "inspire") return `Si ${s} vient de la bibliothèque de références, ses passages seront joints, avec citation, au travail de ${c}.`;
  return EFFETS[style].phrase;
}

export type EtatFleche =
  /** dépendance non terminée : la source ne peut pas démarrer */
  | "bloquante"
  /** dépendance terminée : la source est libre */
  | "debloquee"
  /** dépendance vers une carte qui n'est pas un travail suivi : sans effet */
  | "non_suivie"
  /** quelque chose est joint au travail de la cible */
  | "jointe"
  /** rien à joindre pour l'instant (pas encore de livrable, source sans matière, source hors bibliothèque) */
  | "inerte"
  /** type sans effet, ou résumé du serveur pas encore reçu */
  | "neutre";

export interface LectureFleche {
  etat: EtatFleche;
  /** libellé par défaut de l'étiquette quand l'humain n'a rien écrit */
  libelle: string;
  /** phrase complète (info-bulle, lecteur d'écran) */
  detail: string;
}

const dans = <T extends { lien_id: string }>(liste: T[] | undefined, id: string): T | undefined => liste?.find((x) => x.lien_id === id);

/** Ce que cette flèche fait EN CE MOMENT, lu dans les résumés calculés par le serveur sur ses deux cartes. */
export function lireFleche(lien: LienBoard, source?: ObjetBoard, cible?: ObjetBoard): LectureFleche {
  const e = EFFETS[lien.style] ?? EFFETS.defaut;
  if (lien.style === "depend") {
    const d = dans(source?.relations?.dependances, lien.id);
    if (!d) return { etat: "neutre", libelle: e.nom, detail: e.phrase };
    if (!d.suivi) return { etat: "non_suivie", libelle: "dépend de (sans effet)", detail: `« ${d.titre} » n'est ni une mission ni une tâche : cette dépendance ne bloque rien.` };
    if (d.termine) return { etat: "debloquee", libelle: "débloquée", detail: `« ${d.titre} » est ${d.etat} : cette dépendance ne bloque plus.` };
    return { etat: "bloquante", libelle: "bloque", detail: `Bloquante : « ${d.titre} » est ${d.etat}. La carte au départ de la flèche ne peut pas démarrer.` };
  }
  if (lien.style === "alimente") {
    const a = dans(cible?.relations?.alimentee_par, lien.id);
    if (!a) return { etat: "neutre", libelle: e.nom, detail: e.phrase };
    if (a.sorte === "livrable") return { etat: "jointe", libelle: "alimente · livrable", detail: `Le livrable de « ${a.titre} » sera joint au travail de la cible.` };
    if (a.sorte === "contenu") return { etat: "jointe", libelle: "alimente · contenu", detail: `Le contenu de « ${a.titre} » sera joint au travail de la cible.` };
    if (a.sorte === "reference") return { etat: "jointe", libelle: "alimente · citations", detail: `Les passages de la référence « ${a.titre} » seront joints, avec leur citation.` };
    if (a.sorte === "en_attente") return { etat: "inerte", libelle: "alimente · rien encore", detail: `« ${a.titre} » n'a pas encore rendu de livrable : rien n'est joint pour l'instant.` };
    return { etat: "inerte", libelle: "alimente (sans effet)", detail: `« ${a.titre} » n'apporte aucun contenu (objet de tableau blanc, dossier ou équipe).` };
  }
  if (lien.style === "inspire") {
    const i = dans(cible?.relations?.inspiree_par, lien.id);
    if (!i) return { etat: "neutre", libelle: e.nom, detail: e.phrase };
    return i.effet
      ? { etat: "jointe", libelle: "inspire · citations", detail: `Les passages de la référence « ${i.titre} » seront joints, avec leur citation.` }
      : { etat: "inerte", libelle: "inspire (repère)", detail: `« ${i.titre} » ne vient pas de la bibliothèque de références : rien n'est joint.` };
  }
  return { etat: "neutre", libelle: e.nom, detail: e.phrase };
}

export interface LigneRelation {
  sorte: "bloquee" | "attend" | "alimentee" | "citee" | "debloque" | "libere";
  /** « Bloquée par », « Alimentée par »… */
  verbe: string;
  carte: RefCarte;
  /** précision courte après le titre (« en cours », « livrable ») */
  precision: string;
}

const SORTES_MATIERE: Record<string, string> = { livrable: "livrable", contenu: "contenu", reference: "citations", en_attente: "rien encore", aucun: "sans effet" };

/** Les lignes qu'une carte affiche : bloquée par X, alimentée par Y, cite Z, débloquera W. Rien d'inventé : chaque
 *  ligne vient d'une entrée du résumé du serveur. Seulement ce qui a un effet EN CE MOMENT : une relation qui ne
 *  joint rien (pas encore de livrable, source sans matière) ou une dépendance déjà levée ne prend pas de place sur
 *  la carte — sa flèche le dit (étiquette « débloquée », info-bulle). `tout` les ajoute (panneau, tests). */
export function lignesRelations(r: RelationsCarte | undefined, tout = false): LigneRelation[] {
  if (!r) return [];
  const lignes: LigneRelation[] = [];
  for (const b of r.bloquee_par) lignes.push({ sorte: "bloquee", verbe: "Bloquée par", carte: b, precision: b.etat });
  for (const a of r.alimentee_par) {
    if (tout || a.sorte === "livrable" || a.sorte === "contenu" || a.sorte === "reference") lignes.push({ sorte: "alimentee", verbe: "Alimentée par", carte: a, precision: SORTES_MATIERE[a.sorte] ?? "" });
  }
  for (const i of r.inspiree_par) if (i.effet) lignes.push({ sorte: "citee", verbe: "Cite", carte: i, precision: "référence" });
  for (const d of r.debloque) {
    if (d.attend) lignes.push({ sorte: "debloque", verbe: "Débloquera", carte: d, precision: "" });
    else if (tout) lignes.push({ sorte: "libere", verbe: "A débloqué", carte: d, precision: "" });
  }
  return lignes;
}

/** Une flèche garde son étiquette visible quand elle FAIT quelque chose en ce moment (bloque, a débloqué, joint). */
export function etiquetteParlante(etat: EtatFleche): boolean {
  return etat === "bloquante" || etat === "debloquee" || etat === "jointe";
}

/** Libellé écrit par l'humain, s'il ajoute quelque chose à ce que l'effet dit déjà (« Alimente » + « alimente · contenu » = redite). */
export function libelleUtile(libelle: string, lecture: LectureFleche, nomDuType: string): string {
  const l = libelle.trim().toLowerCase();
  return !l || l === nomDuType.toLowerCase() || lecture.libelle.toLowerCase().startsWith(l) || lecture.libelle.toLowerCase().includes(`· ${l}`) ? "" : libelle.trim();
}

/** Phrase « bloquée par « A » (en cours), « B » (en échec) » pour une info-bulle ou la raison d'une commande. */
export function phraseBlocage(r: RelationsCarte | undefined): string | null {
  if (!r?.bloquee || !r.bloquee_par.length) return null;
  const noms = r.bloquee_par.slice(0, 3).map((b) => `« ${b.titre} » (${b.etat})`).join(", ");
  return `Bloquée par ${noms}${r.bloquee_par.length > 3 ? ` et ${r.bloquee_par.length - 3} ${r.bloquee_par.length - 3 > 1 ? "autres" : "autre"}` : ""}`;
}

/** Trajet de la boucle que fermerait la dépendance source → cible (« la source dépend de la cible »), ou null.
 *  `sauf` : relation en cours de modification. Même parcours que le serveur (`verifier_cycle`). */
export function creeraitBoucle(liens: readonly LienBoard[], source: string, cible: string, sauf?: string): string[] | null {
  const suivants = new Map<string, string[]>();
  for (const l of liens) {
    if (l.style !== "depend" || l.id === sauf) continue;
    suivants.set(l.source_id, [...(suivants.get(l.source_id) ?? []), l.cible_id]);
  }
  const venuDe = new Map<string, string | null>([[cible, null]]);
  const file = [cible];
  while (file.length) {
    const courant = file.shift()!;
    if (courant === source) {
      const retour = [source];
      while (venuDe.get(retour[retour.length - 1]!) != null) retour.push(venuDe.get(retour[retour.length - 1]!)!);
      return [source, ...retour.reverse()];
    }
    for (const s of suivants.get(courant) ?? []) {
      if (!venuDe.has(s)) {
        venuDe.set(s, courant);
        file.push(s);
      }
    }
  }
  return null;
}

/* ---------------------------------------------------------------- mode démo ------------------------------- */
const TABLEAU = new Set(["adhesif", "texte_libre", "forme", "trait", "cadre", "fleche"]);
const ETATS_MISSION: Record<string, string> = { SUCCEEDED: "terminée", FAILED: "en échec", CANCELLED: "annulée", EXPIRED: "expirée" };

const titreDe = (o: ObjetBoard): string => (o.meta.titre || o.mission?.objectif || o.contenu.trim().split("\n")[0] || o.type).slice(0, 80);

function etatPrerequis(o: ObjetBoard): { suivi: boolean; termine: boolean; etat: string } {
  if (o.type === "mission" && o.mission_id) {
    const statut = o.mission?.statut ?? "";
    return { suivi: true, termine: statut === "SUCCEEDED", etat: ETATS_MISSION[statut] ?? "en cours" };
  }
  if (o.type === "tache") {
    const statut = typeof o.meta.statut === "string" ? o.meta.statut : "";
    if (o.meta.verdict === "corrections") return { suivi: true, termine: false, etat: "corrections demandées" };
    return { suivi: true, termine: statut === "terminé", etat: statut === "terminé" ? "terminée" : statut || "en cours" };
  }
  if (typeof o.meta.livrable_de === "string" && o.meta.livrable_de) return { suivi: true, termine: true, etat: "livrable rendu" };
  return { suivi: false, termine: false, etat: "non suivie" };
}

function sorteMatiere(o: ObjetBoard): RelationsCarte["alimentee_par"][number]["sorte"] {
  if (o.meta.reference_id) return "reference";
  if (TABLEAU.has(o.type) || o.type === "agents" || o.type === "dossier" || o.type === "plan") return "aucun";
  if (o.type === "mission") return o.artefacts?.some((a) => a.revue === "acceptee") ? "livrable" : "en_attente";
  return o.meta.livrable_de ? "livrable" : "contenu";
}

/** Résumé par carte, calculé comme le fait le serveur (`board_relations.resumes`). Sert au mode démo et aux tests. */
export function calculerRelations(objets: readonly ObjetBoard[], liens: readonly LienBoard[]): Map<string, RelationsCarte> {
  const parId = new Map(objets.map((o) => [o.id, o]));
  const sortie = new Map<string, RelationsCarte>();
  const de = (id: string): RelationsCarte => {
    let r = sortie.get(id);
    if (!r) {
      r = { bloquee: false, bloquee_par: [], dependances: [], debloque: [], alimentee_par: [], alimente: [], inspiree_par: [] };
      sortie.set(id, r);
    }
    return r;
  };
  const fiche = (o: ObjetBoard, l: LienBoard): RefCarte => ({ id: o.id, titre: titreDe(o), type: o.type, lien_id: l.id });
  for (const l of liens) {
    const s = parId.get(l.source_id), t = parId.get(l.cible_id);
    if (!s || !t) continue;
    if (l.style === "depend") {
      const e = etatPrerequis(t);
      de(s.id).dependances.push({ ...fiche(t, l), ...e });
      if (e.suivi && !e.termine) {
        de(s.id).bloquee_par.push({ ...fiche(t, l), etat: e.etat });
        de(s.id).bloquee = true;
      }
      if (e.suivi) de(t.id).debloque.push({ ...fiche(s, l), attend: !e.termine });
    } else if (l.style === "alimente") {
      de(t.id).alimentee_par.push({ ...fiche(s, l), sorte: sorteMatiere(s) });
      de(s.id).alimente.push(fiche(t, l));
    } else if (l.style === "inspire") {
      const ref = typeof s.meta.reference_id === "string" ? s.meta.reference_id : null;
      de(t.id).inspiree_par.push({ ...fiche(s, l), reference_id: ref, effet: Boolean(ref) });
    }
  }
  return sortie;
}
