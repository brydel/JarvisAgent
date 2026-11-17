import { useEffect, useMemo, useState, type Ref } from "react";
import { ArrowUpRight, BookOpen, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { dateCapture, GENRES, type Fiche, type Observation, type Reference, type TypeObservation } from "../references/api";
import "./graphe-references.css";

const TAILLE = 24;
const GROUPES = { structure: "Structure et composants", style: "Style et mouvement",
  mesures: "Capture et mesures", preuves: "Sources et preuves" } as const;
type Groupe = keyof typeof GROUPES;
const TYPES: Record<TypeObservation, Groupe> = {
  structure: "structure", element: "structure", palette: "style", typographie: "style", mouvement: "style",
  capture: "mesures", mesure: "mesures", comparaison: "mesures", lien: "preuves", preuve: "preuves", media: "preuves",
};

type Props = {
  refInspecteur: Ref<HTMLElement>;
  referenceId: string;
  reference?: Reference & { observations?: readonly Observation[] };
  fiche?: Fiche;
  observation?: Observation;
  charge: boolean;
  erreur?: string;
  choisir: (id: string) => void;
  ouvrir: (observation?: string) => void;
  reessayer: () => void;
};

export function InspecteurReferences({ refInspecteur, referenceId, reference, fiche, observation, charge, erreur,
  choisir, ouvrir, reessayer }: Props) {
  const [groupe, setGroupe] = useState<Groupe | null>(null);
  const [page, setPage] = useState(1);
  const source = fiche ?? reference;
  const parGroupe = useMemo(() => {
    const classes = new Map<Groupe, Observation[]>();
    for (const obs of fiche?.observations ?? reference?.observations ?? []) {
      const cle = TYPES[obs.type] ?? "preuves";
      if (!classes.has(cle)) classes.set(cle, []);
      classes.get(cle)!.push(obs);
    }
    return classes;
  }, [fiche, reference]);
  useEffect(() => {
    setGroupe(observation ? TYPES[observation.type] : null);
    setPage(1);
  }, [observation?.id]);
  const famille = groupe ?? (observation ? TYPES[observation.type] : null);
  const observations = famille ? parGroupe.get(famille) ?? [] : [...parGroupe.values()].flat();
  const totalPages = Math.max(1, Math.ceil(observations.length / TAILLE));
  const cible = observation ? observations.findIndex((o) => o.id === observation.id) : -1;
  const courante = Math.min(cible >= 0 && page === 1 ? Math.floor(cible / TAILLE) + 1 : page, totalPages);
  const passages = fiche?.index.fragments ?? reference?.fragments;
  return <aside ref={refInspecteur} tabIndex={-1} className="mf-inspecteur rfg-inspection" aria-label="Inspecteur des sources RAG">
    <header className="mf-inspect-entete"><span className="mf-miniature"><BookOpen size={20} aria-hidden /></span>
      <div><p>{source ? GENRES[source.type] : "Référence"}</p><h2>{source?.titre || referenceId}</h2></div></header>
    {source?.description && <p className="mf-description">{source.description}</p>}
    <p className="rfg-meta">{passages === undefined ? "Index en cours de lecture" : passages + (passages === 1 ? " passage indexé" : " passages indexés")}
      {source?.collection && " · " + source.collection}</p>
    <button type="button" className="p-button p-quiet" onClick={() => ouvrir()}>Ouvrir la référence <ArrowUpRight size={14} /></button>
    {charge && <p className="rfg-meta" role="status">Lecture de la source…</p>}
    {erreur && <p className="p-error" role="alert">{erreur}<button type="button" className="p-button p-quiet" onClick={reessayer}>
      <RefreshCw size={14} />Réessayer</button></p>}
    {observation && <section className="rfg-preuve" aria-label="Preuve de l’observation">
      <h3>{observation.titre}</h3><p>{observation.texte}</p>
      <small>Relevé le {dateCapture(observation.preuve.capture_le)} · {observation.id}</small>
      <button type="button" className="p-button p-quiet" onClick={() => ouvrir(observation.id)}>
        Voir l’observation dans la source <ArrowUpRight size={14} />
      </button>
    </section>}
    {parGroupe.size > 0 && <section className="rfg-observations" aria-label="Observations de la source">
      <h3>Observations reliées</h3>
      <ul className="rfg-liste rfg-categories" aria-label="Catégories d’observation">
        {[...parGroupe].map(([g, entrees]) => <li key={g}>
          <button type="button" aria-pressed={famille === g} onClick={() => { setGroupe(famille === g ? null : g); setPage(1); }}>
            {GROUPES[g]} <span>{entrees.length}</span>
          </button>
        </li>)}
      </ul>
      <section aria-label="Observations de la catégorie">
        <ul className="rfg-liste">{observations.slice((courante - 1) * TAILLE, courante * TAILLE).map((o) => <li key={o.id}>
          <button type="button" aria-pressed={o.id === observation?.id} onClick={() => choisir(o.id)}>{o.titre}</button>
        </li>)}</ul>
        {totalPages > 1 && <nav className="rfg-pagination" aria-label="Pages d’observations">
          <button type="button" className="p-icon-button" aria-label="Page précédente" disabled={courante <= 1} onClick={() => setPage(courante - 1)}>
            <ChevronLeft size={17} /></button>
          <span>{courante} / {totalPages}</span>
          <button type="button" className="p-icon-button" aria-label="Page suivante" disabled={courante >= totalPages} onClick={() => setPage(courante + 1)}>
            <ChevronRight size={17} /></button>
        </nav>}
      </section>
    </section>}
    {!charge && !parGroupe.size && <p className="rfg-meta">Cette référence conserve ses passages textuels. Une capture enrichira ses observations.</p>}
  </aside>;
}
