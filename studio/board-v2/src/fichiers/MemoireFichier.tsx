import { useEffect, useState } from "react";
import { ArrowUpRight, BookOpen, Copy, Database, Search } from "lucide-react";
import { extraireTextePdf } from "../lib/pdf";
import { requete } from "../product/api";
import type { Entite } from "./graphe";

type Extrait = { reference_id: string; fragment_id: string; section: string; titre: string; extrait: string; citation: string };
type Memoire = { reference_id: string | null; passages: Extrait[] };

export function MemoireFichier({ entite, demo, indexee, ouvrir, signaler }: {
  entite: Entite; demo: boolean; indexee: () => void; ouvrir: (ref: string, fragment?: string) => void; signaler: (texte: string) => void;
}) {
  const [donnees, setDonnees] = useState<Memoire | null>(null);
  const [question, setQuestion] = useState("");
  const [erreur, setErreur] = useState("");
  const [occupe, setOccupe] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (demo) return;
    const controle = new AbortController();
    const url = `/api/v2/fichiers/${entite.id}/memoire?q=${encodeURIComponent(question.trim())}`;
    const timer = window.setTimeout(() => {
      requete<Memoire>(url, undefined, controle.signal).then((r) => {
        if (!controle.signal.aborted) { setDonnees(r); setErreur(""); }
      }).catch((e: Error) => { if (!controle.signal.aborted) setErreur(e.message); });
    }, question ? 180 : 0);
    return () => { window.clearTimeout(timer); controle.abort(); };
  }, [entite.id, question, demo, version]);
  const indexer = async () => {
    setOccupe(true); setErreur("");
    try {
      const asset = entite.objet?.asset;
      const pdf = asset?.mime === "application/pdf";
      const texte_pdf = pdf ? await extraireTextePdf(asset.url).catch(() => "") : "";
      const r = await requete<{ texte_pdf: boolean }>(`/api/v2/fichiers/${entite.id}/indexer`, { texte_pdf });
      setVersion((v) => v + 1); indexee();
      signaler(pdf && !r.texte_pdf ? "Fiche indexée. Aucun texte exploitable dans le PDF." : "Fichier indexé dans Références.");
    } catch (e) { setErreur(e instanceof Error ? e.message : "Indexation indisponible."); }
    finally { setOccupe(false); }
  };
  return <section className="mf-memoire" aria-label="Index de la mémoire">
    <div className="mf-partie-entete"><h3><Database size={16} />Mémoire Jarvis</h3>
      {donnees?.reference_id && <span className="mf-indice">Indexé</span>}</div>
    {demo ? <p className="mf-apercu-message">En mode local, indexe ce fichier pour retrouver et citer ses passages.</p> : <>
      {erreur && <p className="p-error" role="alert">{erreur}</p>}
      {!donnees && !erreur && <p className="mf-apercu-message" role="status">Lecture de l’index…</p>}
      {donnees && !donnees.reference_id && <>
        <p className="mf-apercu-message">Ajoute son contenu à l’index de Références pour que Jarvis puisse le retrouver.</p>
        <button type="button" className="p-button p-quiet" disabled={occupe} onClick={() => void indexer()}><BookOpen size={16} />{occupe ? "Indexation…" : "Indexer le fichier"}</button>
      </>}
      {donnees?.reference_id && <>
        <label className="mf-recherche-extraits"><Search size={15} /><input type="search" placeholder="Chercher dans ce fichier"
          aria-label="Chercher dans les passages indexés" value={question} maxLength={180} onChange={(e) => setQuestion(e.target.value)} /></label>
        <ul className="mf-extraits">{donnees.passages.map((p) => <li key={p.fragment_id}>
          <button type="button" className="mf-extrait-lien" onClick={() => ouvrir(p.reference_id, p.fragment_id)}>{p.section || p.titre || "Extrait"} <ArrowUpRight size={14} /></button>
          <blockquote>{p.extrait}</blockquote>
          <button type="button" className="p-button p-quiet" onClick={() => void navigator.clipboard.writeText(`« ${p.extrait} »\n${p.citation}`)
            .then(() => signaler("Citation copiée."), () => signaler("Copie indisponible."))}><Copy size={14} />Copier la citation</button>
        </li>)}</ul>
        {!donnees.passages.length && <p className="mf-apercu-message">{question.trim() ? "Aucun passage correspondant." : "Aucun extrait textuel disponible."}</p>}
        <button type="button" className="p-button p-quiet" onClick={() => ouvrir(donnees.reference_id!)}>Ouvrir dans Références <ArrowUpRight size={15} /></button>
      </>}
    </>}
  </section>;
}
