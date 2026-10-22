// Rendu SÛR d'un texte de note : sous-ensemble Markdown converti en éléments React (aucun innerHTML).
// Gras **x**, italique *x*, souligné __x__, listes « - », liens http(s) ouverts sans référent.
import type { ReactNode } from "react";

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

export function rendreNote(texte: string): ReactNode[] {
  const blocs: ReactNode[] = [];
  let liste: string[] = [];
  const vider = () => {
    if (liste.length) {
      blocs.push(<ul key={`u${blocs.length}`}>{liste.map((l, i) => <li key={i}>{enligne(l, `l${blocs.length}-${i}`)}</li>)}</ul>);
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
      blocs.push(<h5 key={`h${blocs.length}`}>{enligne(titre[1], `h${blocs.length}`)}</h5>);
      continue;
    }
    const m = /^\s*[-*•]\s+(.*)$/.exec(ligne);
    if (m && m[1] !== undefined) {
      liste.push(m[1]);
      continue;
    }
    vider();
    if (ligne.trim()) blocs.push(<p key={`p${blocs.length}`}>{enligne(ligne, `p${blocs.length}`)}</p>);
  }
  vider();
  if (code) blocs.push(<pre key={`c${blocs.length}`}>{code.join("\n")}</pre>);  // bloc jamais fermé
  return blocs;
}
