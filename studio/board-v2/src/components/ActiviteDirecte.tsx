import { useEffect, useState } from "react";
import { Activity, ChevronDown, ChevronUp, Terminal } from "lucide-react";
import type { Source } from "../api";
import "../styles/activite.css";

interface Session {
  id: string; project: string; worktree: string; status: string; kind: string;
  elapsed: number; title: string; session: string; window: string;
}
interface Tache {
  id: string; mission_id: string; type: string; statut: string; raison: string; fournisseur: string | null;
  debut: number | null; executant: string | null; objectif: string; objet_id: string | null; bail_perime: boolean;
}
interface Activite {
  ts: number; sessions: Session[] | null; sessions_erreur: string; taches: Tache[];
  demon: boolean; executant_actif: boolean;
}
const ETATS: Record<string, string> = {
  working: "Travaille", waiting: "Attend une réponse", done: "Terminé", silent: "Silencieux", idle: "Inactif",
  untracked: "Actif, statut non suivi", LEASED: "Attribuée", RUNNING: "En cours", REVIEW: "En vérification",
  QUEUED: "En file", WAITING_APPROVAL: "Attend ton accord", WAITING_PROVIDER: "Attend un fournisseur",
  RETRY_SCHEDULED: "Nouvel essai prévu", CREATED: "Créée", VALIDATED: "Validée",
};

async function lire<T>(url: string, signal: AbortSignal): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin", signal: AbortSignal.any([signal, AbortSignal.timeout(25000)]) });
  const data = await r.json();
  if (!r.ok) throw new Error(data.erreur || `Observation indisponible (${r.status})`);
  return data as T;
}

/** Lecture périodique indépendante du SSE : les sessions tmux ne publient pas d'événements de mission. */
export function ActiviteDirecte({ source, inspecter }: { source: Source; inspecter: (id: string) => void }) {
  const [ouvert, setOuvert] = useState(true);
  const [etat, setEtat] = useState<Activite | null>(null);
  const [erreur, setErreur] = useState("");
  const [session, setSession] = useState("");
  const [apercu, setApercu] = useState("");
  const [erreurApercu, setErreurApercu] = useState("");
  const espace = encodeURIComponent(source.espace);
  useEffect(() => {
    if (source.demo) return;
    const c = new AbortController();
    let timer: number | undefined;
    setEtat(null); setErreur(""); setSession("");
    const observer = async () => {
      try {
        const e = await lire<Activite>(`/api/v2/activite?espace=${espace}`, c.signal);
        if (!c.signal.aborted) { setEtat(e); setErreur(""); }
      } catch (e) {
        if (!c.signal.aborted) setErreur(e instanceof Error ? e.message : "Observation indisponible");
      } finally {
        // Un seul appel en vol ; une réponse lente ne crée pas une avalanche de processus workmux.
        if (!c.signal.aborted) timer = window.setTimeout(observer, 5000);
      }
    };
    void observer();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [source, espace]);
  useEffect(() => {
    if (!session || !ouvert) return;
    const c = new AbortController();
    let timer: number | undefined;
    setApercu(""); setErreurApercu("");
    const capturer = async () => {
      try {
        const r = await lire<{ texte: string }>(`/api/v2/activite/${session}/apercu?espace=${espace}`, c.signal);
        if (!c.signal.aborted) { setApercu(r.texte); setErreurApercu(""); }
      } catch (e) {
        if (!c.signal.aborted) setErreurApercu(e instanceof Error ? e.message : "Aperçu indisponible");
      } finally { if (!c.signal.aborted) timer = window.setTimeout(capturer, 5000); }
    };
    void capturer();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [session, espace, ouvert]);
  useEffect(() => {
    if (etat?.sessions && !etat.sessions.some(s => s.id === session)) setSession("");
  }, [etat, session]);
  if (source.demo) return null;
  const actifs = etat?.sessions?.filter(s => ["working", "waiting", "untracked", "silent"].includes(s.status)).length ?? 0;
  const selection = etat?.sessions?.find(s => s.id === session);
  return <section className="activite-directe" aria-label="Travail en direct">
    <button type="button" className="activite-titre" aria-expanded={ouvert} aria-controls="travail-observe" onClick={() => setOuvert(!ouvert)}>
      <Activity size={17}/><strong>Travail en direct</strong>
      <span>{etat ? `${etat.sessions === null ? "Sessions indisponibles" : `${actifs} session(s) active(s)`} · ${etat.taches.length} tâche(s) en cours ou en attente` : "Observation…"}</span>
      {ouvert ? <ChevronUp size={17}/> : <ChevronDown size={17}/>}
    </button>
    {ouvert && <div id="travail-observe" className="activite-contenu">
      <div className="activite-liste">
        <p className="activite-meta">{source.espace === "accueil" ? "Tous les projets du poste" : `Projet : ${source.espace}`} · actualisation toutes les 5 s
          {etat && <> · démon {etat.demon ? "actif" : "sans battement récent"}</>}</p>
        {erreur && <p role="alert">Observation interrompue : {erreur}. Les données précédentes peuvent être périmées.</p>}
        {etat?.sessions_erreur && <p role="alert">Sessions non observables : {etat.sessions_erreur}</p>}
        {etat && !etat.executant_actif && etat.taches.length > 0 && <p role="status">Aucun exécutant de missions n'a donné signe de vie récemment. Vérifie le démon et l'enrôlement.</p>}
        {etat?.sessions?.map(s => <button type="button" key={s.id} className="activite-session" aria-pressed={session === s.id} onClick={() => setSession(s.id)}>
          <Terminal size={15}/><span><b>{s.project} / {s.worktree}</b><small>{s.kind || "Agent"} · {ETATS[s.status] || s.status} · {s.session}/{s.window}</small>{s.title && <small>{s.title}</small>}</span>
        </button>)}
        {etat?.taches.map(t => <div key={t.id} className="activite-tache">
          <b>{t.objectif}</b><span>{t.type} · {ETATS[t.statut] || t.statut} · {t.fournisseur || "fournisseur à attribuer"}
            {t.debut !== null && ` · depuis ${Math.max(0, Math.floor((etat.ts - t.debut) / 60))} min`}</span>
          {t.bail_perime && <strong>Bail expiré : reprise à vérifier</strong>}
          {t.raison && <small>{t.raison}</small>}
          {t.objet_id && <button type="button" onClick={() => inspecter(t.objet_id!)}>Voir la carte liée</button>}
        </div>)}
        {etat && etat.sessions !== null && !etat.sessions.length && !etat.taches.length && <p>Aucun travail observé dans cet espace.</p>}
      </div>
      <div className="activite-apercu" aria-label="Sortie de la session">
        {selection ? <><strong>{selection.project} / {selection.worktree}</strong>
          {erreurApercu && <p role="alert">{erreurApercu} — l'ancienne sortie peut être périmée.</p>}
          <pre>{apercu || (erreurApercu ? "" : "Capture en cours…")}</pre></>
          : <p>Sélectionne une session pour voir sa sortie terminal. Pour les missions, le statut vient du moteur ; le contenu du modèle est disponible à la remise du résultat.</p>}
      </div>
    </div>}
  </section>;
}
