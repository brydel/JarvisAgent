import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, Waypoints } from "lucide-react";
import { requete } from "../product/api";
import { SpotlightCard } from "../ui/react-bits/SpotlightCard";
import { estNote, type Graphe } from "./graphe";

type Alimentation = { carte_id: string; lien_id: string; titre: string; texte: string; provenance: string; tronque: boolean };
type Citation = { lien_id: string; reference_id: string; fragment_id: string; titre: string; section: string; extrait: string; citation: string };
type Apercu = { analysable: boolean; contexte: { alimentations: Alimentation[]; references: Citation[]; omis: number } | null };
type Lecture = { id: string; donnees?: Apercu; erreur?: string };

function apercuDemo(modele: Graphe, id: string): Apercu {
  const objet = modele.entites.get(id)?.objet;
  if (!objet || !["note", "texte", "lien", "image", "capture", "pdf", "document", "audio", "video"].includes(objet.type)) {
    return { analysable: false, contexte: null };
  }
  const alimentations = (modele.adjacents.get(id) ?? []).flatMap((r) => {
    if (r.cible !== id || r.style !== "alimente") return [];
    const source = modele.entites.get(r.source);
    if (!source?.objet || !estNote(source.objet) || !source.objet.contenu.trim()) return [];
    return [{ carte_id: source.id, lien_id: r.id, titre: source.titre, texte: source.objet.contenu,
      provenance: "Note du Board · Démo", tronque: false }];
  });
  return { analysable: true, contexte: alimentations.length ? { alimentations, references: [], omis: 0 } : null };
}

export function useContexteCarte(modele: Graphe | null, id: string | undefined, demo: boolean) {
  const [reponse, setReponse] = useState<Lecture | null>(null);
  const objet = id && modele?.entites.get(id)?.objet;
  const carteId = objet ? objet.id : undefined;
  useEffect(() => {
    if (demo || !carteId) return;
    const controle = new AbortController();
    requete<Apercu>("/api/v2/fichiers/" + encodeURIComponent(carteId) + "/contexte", undefined, controle.signal)
      .then((donnees) => { if (!controle.signal.aborted) setReponse({ id: carteId, donnees }); })
      .catch((e: unknown) => {
        if (!controle.signal.aborted) setReponse({ id: carteId, erreur: e instanceof Error ? e.message : "Contexte indisponible." });
      });
    return () => controle.abort();
  }, [carteId, demo, modele]);

  const exemple = useMemo(() => demo && modele && carteId ? apercuDemo(modele, carteId) : undefined, [demo, modele, carteId]);
  const lecture = demo ? (exemple && carteId ? { id: carteId, donnees: exemple } : null)
    : carteId ? (reponse?.id === carteId ? reponse : { id: carteId }) : null;
  const contexte = lecture?.donnees?.contexte;
  const liens = useMemo(() => new Set([
    ...(contexte?.alimentations ?? []).map((a) => a.lien_id),
    ...(contexte?.references ?? []).map((r) => r.lien_id),
  ]), [contexte]);
  return { lecture, liens };
}

export function ContexteCarte({ lecture, demo, choisir, ouvrirReference, actualiser }: {
  lecture: Lecture | null; demo: boolean; choisir: (id: string) => void;
  ouvrirReference: (ref: string, fragment: string) => void; actualiser: () => void;
}) {
  if (!lecture || lecture.donnees?.analysable === false) return null;
  const { contexte } = lecture.donnees ?? {};
  return <section className="mf-contexte" aria-label="Contexte transmis à l’agent">
    <SpotlightCard className="mf-contexte-carte">
      <header><span className="mf-contexte-icone"><Waypoints size={18} aria-hidden /></span>
        <div><h3>Contexte de l’agent</h3><p>{demo ? "Aperçu de démonstration" : "Sources liées pour une analyse de cette carte"}</p></div>
      </header>
      {lecture.erreur && <div className="mf-contexte-etat"><p role="alert">{lecture.erreur}</p>
        <button type="button" className="p-button p-quiet" onClick={actualiser}>Réessayer</button></div>}
      {!lecture.donnees && !lecture.erreur && <p className="mf-contexte-etat" role="status">Chargement des sources…</p>}
      {lecture.donnees && !contexte && <p className="mf-contexte-etat">Aucune source liée à joindre à l’analyse.</p>}
      {contexte && <ul className="mf-contexte-sources">
        {contexte.alimentations.map((a) => <li key={a.lien_id}>
          <details><summary>{a.titre || "Carte du Board"}</summary>
            <blockquote>{a.texte}</blockquote>
            <p>{a.provenance}{a.tronque && " · Extrait tronqué"}</p>
            <button type="button" className="p-button p-quiet" onClick={() => choisir(a.carte_id)}>Ouvrir la source <ArrowUpRight size={14} /></button>
          </details>
        </li>)}
        {contexte.references.map((r) => <li key={r.lien_id + ":" + r.fragment_id}>
          <details><summary>{r.section || r.titre || "Passage cité"}</summary>
            <blockquote>{r.extrait}</blockquote>
            <p>{r.citation}</p>
            <button type="button" className="p-button p-quiet" onClick={() => ouvrirReference(r.reference_id, r.fragment_id)}>
              <BookOpen size={14} /> Ouvrir le passage cité
            </button>
          </details>
        </li>)}
      </ul>}
      {!!contexte?.omis && <p className="mf-contexte-etat">Sources hors du budget de contexte · {contexte.omis}</p>}
    </SpotlightCard>
  </section>;
}
