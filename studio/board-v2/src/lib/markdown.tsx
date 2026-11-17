// Rendu SÛR d'un texte de note : sous-ensemble Markdown converti en éléments React (aucun innerHTML).
// Gras **x**, italique *x*, souligné __x__, listes « - », liens http(s) ouverts sans référent.
import type { ReactNode } from "react";
import { analyserWiki, CODE_INLINE, WIKI_INLINE } from "./wikiliens";
import "./wikiliens.css";

const JETONS = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|https?:\/\/[^\s)]+)/g;

function enligne(texte: string, cle: string): ReactNode[] {
  return texte.split(JETONS).filter(Boolean).map((m, i) => {
    const k = `${cle}-${i}`;
    if (m.startsWith("**") && m.endsWith("**")) return <strong key={k}>{m.slice(2, -2)}</strong>;
    if (m.startsWith("__") && m.endsWith("__")) return <u key={k}>{m.slice(2, -2)}</u>;
    if (m.startsWith("*") && m.endsWith("*") && m.length > 2) return <em key={k}>{m.slice(1, -1)}</em>;
    if (/^https?:\/\//.test(m)) return <a key={k} href={m} target="_blank" rel="noopener noreferrer nofollow">{m}</a>;
    return m;
  });
}

export type NavigationWiki = { resoudre(cible: string): string | undefined; ouvrir(id: string): void };

const JETONS_WIKI = new RegExp(CODE_INLINE + "|" + WIKI_INLINE + "|" + JETONS.source, "g");

function enligneWiki(texte: string, cle: string, wiki: NavigationWiki): ReactNode[] {
  const parties: ReactNode[] = [];
  let dernier = 0;
  for (const m of texte.matchAll(JETONS_WIKI)) {
    const extrait = m[0];
    const k = cle + "-" + m.index;
    if (m.index > dernier) parties.push(texte.slice(dernier, m.index));
    dernier = m.index + extrait.length;
    const lien = analyserWiki(extrait);
    if (lien) {
      const id = wiki.resoudre(lien.cible);
      parties.push(id ? <button key={k} type="button" className="wiki-lien nodrag"
        onDoubleClick={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); wiki.ouvrir(id); }}>{lien.texte}</button>
        : <span className="wiki-lien-manquant" key={k} title="Note introuvable ou titre ambigu">{lien.texte}</span>);
    } else if (m[1]) parties.push(<code key={k}>{extrait.slice(m[1].length, -m[1].length)}</code>);
    else if (extrait.startsWith("**")) parties.push(<strong key={k}>{enligneWiki(extrait.slice(2, -2), k, wiki)}</strong>);
    else if (extrait.startsWith("__")) parties.push(<u key={k}>{enligneWiki(extrait.slice(2, -2), k, wiki)}</u>);
    else if (extrait.startsWith("*")) parties.push(<em key={k}>{enligneWiki(extrait.slice(1, -1), k, wiki)}</em>);
    else parties.push(...enligne(extrait, k));
  }
  if (dernier < texte.length) parties.push(texte.slice(dernier));
  return parties;
}

export function rendreNote(texte: string, wiki?: NavigationWiki): ReactNode[] {
  const ligneRendue = (texte: string, cle: string) => wiki ? enligneWiki(texte, cle, wiki) : enligne(texte, cle);
  const blocs: ReactNode[] = [];
  let liste: string[] = [];
  const vider = () => {
    if (liste.length) {
      blocs.push(<ul key={`u${blocs.length}`}>{liste.map((l, i) => <li key={i}>{ligneRendue(l, `l${blocs.length}-${i}`)}</li>)}</ul>);
      liste = [];
    }
  };
  let code: string[] | null = null;  // bloc ``` en cours : rendu tel quel
  for (const ligne of texte.split("\n")) {
    if (/^\s*```/.test(ligne)) {
      vider();
      if (code) {
        blocs.push(<pre key={`c${blocs.length}`}>{code.join("\n")}</pre>);
        code = null;
      } else code = [];
      continue;
    }
    if (code) {
      code.push(ligne);
      continue;
    }
    const titre = /^\s*#{1,4}\s+(.*)$/.exec(ligne);
    if (titre && titre[1] !== undefined) {
      vider();
      blocs.push(<h5 key={`h${blocs.length}`}>{ligneRendue(titre[1], `h${blocs.length}`)}</h5>);
      continue;
    }
    const m = /^\s*[-*•]\s+(.*)$/.exec(ligne);
    if (m && m[1] !== undefined) {
      liste.push(m[1]);
      continue;
    }
    vider();
    if (ligne.trim()) blocs.push(<p key={`p${blocs.length}`}>{ligneRendue(ligne, `p${blocs.length}`)}</p>);
  }
  vider();
  if (code) blocs.push(<pre key={`c${blocs.length}`}>{code.join("\n")}</pre>);  // bloc jamais fermé
  return blocs;
}
