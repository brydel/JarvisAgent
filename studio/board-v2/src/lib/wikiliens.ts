import type { ObjetBoard } from "../types";

export type CibleWiki = { id: string; titre: string };
type Note = ObjetBoard & { type: "note" | "texte" };
type IndexNotes = {
  ids: Map<string, Note>;
  titres: Map<string, Note[]>;
  notes: Note[];
};

export function estNote(objet: ObjetBoard): objet is Note {
  return objet.type === "note" || objet.type === "texte";
}

export function titreNote(note: ObjetBoard) {
  return note.meta.titre?.trim() || note.contenu.trim().split(/\r?\n/, 1)[0]?.slice(0, 78) || "Note";
}

const normaliser = (titre: string) => titre.trim().normalize("NFC").toLocaleLowerCase("fr");
const cle = (espace: string, titre: string) => espace + "\0" + normaliser(titre);
const indexParObjets = new WeakMap<readonly ObjetBoard[], IndexNotes>();
const IDENTIFIANT = /^BO-(?:[a-f\d]{12}|demo[\w-]*)$/i;
export const CODE_INLINE = String.raw`(?<!\x60)(\x60{1,8})(?!\x60)[^\r\n]*?(?<!\x60)\1(?!\x60)`;
export const WIKI_INLINE = String.raw`(?<!\\)\[\[([^[\]|\r\n]+?)(?:\|([^[\]|\r\n]+?))?\]\]`;

export function indexerNotes(objets: readonly ObjetBoard[]): IndexNotes {
  const precedent = indexParObjets.get(objets);
  if (precedent) return precedent;
  const notes = objets.filter(estNote);
  const index: IndexNotes = { ids: new Map(), titres: new Map(), notes };
  for (const note of notes) {
    index.ids.set(note.id, note);
    const k = cle(note.espace, titreNote(note));
    const groupe = index.titres.get(k);
    if (groupe) groupe.push(note);
    else index.titres.set(k, [note]);
  }
  indexParObjets.set(objets, index);
  return index;
}

export function resoudreWiki(index: IndexNotes, origine: ObjetBoard, cible: string) {
  const directe = index.ids.get(cible);
  if (directe) return directe.id !== origine.id && directe.espace === origine.espace ? directe.id : undefined;
  // Un identifiant dont la carte a disparu reste un lien manquant, même si une note porte ce nom.
  if (IDENTIFIANT.test(cible)) return undefined;
  const notes = index.titres.get(cle(origine.espace, cible))?.filter((note) => note.id !== origine.id);
  return notes?.length === 1 ? notes[0]?.id : undefined;
}

export function ciblesWiki(objets: readonly ObjetBoard[], origine: ObjetBoard, requete: string): CibleWiki[] {
  const q = normaliser(requete);
  return indexerNotes(objets).notes.filter((note) => note.id !== origine.id && note.espace === origine.espace)
    .map((note) => ({ id: note.id, titre: titreNote(note) }))
    .filter(({ titre }) => normaliser(titre).includes(q))
    .sort((a, b) => Number(normaliser(b.titre).startsWith(q)) - Number(normaliser(a.titre).startsWith(q)) ||
      a.titre.localeCompare(b.titre, "fr") || a.id.localeCompare(b.id))
    .slice(0, 8);
}

export function encoderWiki(cible: CibleWiki) {
  const titre = cible.titre.replace(/[\[\]|\r\n]/g, " ").replace(/\s+/g, " ").trim() || "Note";
  return "[[" + cible.id + "|" + titre + "]]";
}

const WIKI_COMPLET = new RegExp("^" + WIKI_INLINE + "$");

export function analyserWiki(lien: string) {
  const m = WIKI_COMPLET.exec(lien);
  const cible = m?.[1]?.trim();
  return cible ? { cible, texte: m?.[2]?.trim() || cible } : undefined;
}

const JETON_WIKI = new RegExp(CODE_INLINE + "|" + WIKI_INLINE, "g");

export function* lireWikiliens(contenu: string): Generator<string> {
  let code = false;
  for (const ligne of contenu.split("\n")) {
    if (/^\s*\x60\x60\x60/.test(ligne)) {
      code = !code;
      continue;
    }
    if (code) continue;
    for (const m of ligne.matchAll(JETON_WIKI)) {
      const cible = m[2]?.trim();
      if (cible) yield cible;
    }
  }
}
