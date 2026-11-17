import { ArrowUpRight, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { urlStudio, useStudioNavigation } from "../product/routing";
import { SpotlightCard } from "../ui/react-bits/SpotlightCard";
import { destinationPreuve, idMemoire, NATURES_MEMOIRE, titreMemoire, type EntreeMemoire, type NatureMemoire } from "./journal-donnees";
import type { useJournalMemoire } from "./useJournalMemoire";
import "./journal-memoire.css";

const dates = new Intl.DateTimeFormat("fr-CA", { dateStyle: "medium", timeStyle: "short" });

export function CommandesJournal({ journal, demo, filtrer }: {
  journal: ReturnType<typeof useJournalMemoire>; demo: boolean; filtrer: (n: NatureMemoire | "") => void;
}) {
  return <div className="jm-commandes">
    <label className="jm-filtre">
      <span className="sr-only">Type d’événement</span>
      <select className="champ" value={journal.nature} onChange={(e) => filtrer(e.target.value as NatureMemoire | "")}>
        <option value="">Tous les événements</option>
        {Object.entries(NATURES_MEMOIRE).map(([id, nom]) => <option key={id} value={id}>{nom}</option>)}
      </select>
    </label>
    {!demo && <button type="button" className="p-button p-quiet" onClick={journal.actualiser} disabled={journal.charge}>
      <RefreshCw size={15} />Actualiser le journal
    </button>}
  </div>;
}

export function ListeJournal({ journal, entrees, demo, recherche, selection, choisir }: {
  journal: ReturnType<typeof useJournalMemoire>; entrees: EntreeMemoire[]; demo: boolean;
  recherche: string; selection?: string; choisir: (id: string) => void;
}) {
  return <section className="jm-liste" aria-labelledby="jm-titre">
    <header className="jm-entete"><h2 id="jm-titre">Journal des agents</h2>{demo && <span className="mf-indice">Démo</span>}</header>
    {journal.charge && <p className="p-loading" role="status">Chargement du journal…</p>}
    {journal.erreur && <div className="p-error" role="alert">{journal.erreur}
      <button type="button" className="p-button p-quiet" onClick={journal.reessayer}>Réessayer</button></div>}
    {!journal.charge && !journal.erreur && <>{entrees.length > 0 ? <ul>
      {entrees.map((e) => <li key={e.id}>
        <SpotlightCard as="button" type="button" className="jm-entree"
          aria-pressed={selection === idMemoire(e.id)} onClick={() => choisir(idMemoire(e.id))}>
          <span className="jm-point" data-nature={e.nature} aria-hidden="true" />
          <span><strong>{titreMemoire(e)}</strong><small>{NATURES_MEMOIRE[e.nature]}{e.factice && !demo ? " · Exécution factice" : ""}</small></span>
          <time dateTime={new Date(e.date * 1000).toISOString()}>{dates.format(e.date * 1000)}</time>
        </SpotlightCard>
      </li>)}
    </ul> : <p className="mf-apercu-message">{recherche ? "Aucun résultat sur cette page." : "Aucun événement de ce type dans ce projet."}</p>}
    {(journal.precedent || journal.suivant) && <nav className="mf-pagination" aria-label="Pagination du journal">
      <button className="p-icon-button" type="button" aria-label="Événements plus récents" disabled={!journal.precedent} onClick={journal.precedent}>
        <ChevronLeft size={17} />
      </button>
      <span>Page {journal.page}</span>
      <button className="p-icon-button" type="button" aria-label="Événements plus anciens" disabled={!journal.suivant} onClick={journal.suivant}>
        <ChevronRight size={17} />
      </button>
    </nav>}</>}
  </section>;
}

export function FicheEntreeJournal({ entree, demo }: { entree: EntreeMemoire; demo: boolean }) {
  const { aller } = useStudioNavigation();
  const destination = destinationPreuve(entree.preuve);
  return <section className="jm-preuve" aria-label="Détail et preuve de l’événement">
    <div className="jm-entete">
      <time dateTime={new Date(entree.date * 1000).toISOString()}>{dates.format(entree.date * 1000)}</time>
      {(demo || entree.factice) && <span className="mf-indice">{demo ? "Démo" : "Exécution factice"}</span>}
    </div>
    {entree.detail && <p>{entree.detail}</p>}
    {entree.auteur && <p className="jm-declaration">Déclaré par {entree.auteur}</p>}
    <a className="p-button p-quiet" href={urlStudio("missions", destination).href} onClick={(e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault(); aller("missions", destination);
    }}><ArrowUpRight size={15} />Voir la preuve</a>
  </section>;
}
