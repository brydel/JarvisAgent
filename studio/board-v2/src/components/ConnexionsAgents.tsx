import { useEffect, useId, useRef, useState } from "react";
import { Activity, Check, CircleHelp, Link2, LoaderCircle, PlugZap, Plus, RefreshCw, ShieldCheck, Unplug, X } from "lucide-react";
import type { Source } from "../api";
import "../styles/connexions.css";

interface OutilMcp { name: string; description: string; inputSchema: unknown; autorise: boolean }
interface Connexion {
  id: string; nom: string; type: string; active: boolean; hote: string;
  auth: { mode: string; configuree: boolean }; outils_autorises: string[]; outils: OutilMcp[];
  etat: string; created_at: number; verified_at: number | null;
  stdio?: { executable: string; env: unknown };
}
interface Capacite { id: string; etat: string; available: boolean; scope: string; preuve: string; version?: string }
interface Operation { operation_id: string; project: string; tool: string; status: string; created_at: number; updated_at: number; mandat_id: string; erreur?: string | null }
type Onglet = "connexions" | "operations" | "capacites";
const ETATS: Record<string, string> = {
  revoquee: "Révoquée", decouverte_verifiee: "Découverte vérifiée", configuree_non_verifiee: "À vérifier",
  prepared: "Préparée", in_progress: "En cours", succeeded: "Réussie", failed: "Échouée", unknown: "Résultat inconnu",
  absent: "Absent", configure: "Configuré", authentifie: "Authentifié", verifie: "Vérifié", inconnu: "Non vérifié", degrade: "Dégradé",
};

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const signal = init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(25000)]) : AbortSignal.timeout(25000);
  const r = await fetch(url, { credentials: "same-origin", ...init, signal });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erreur || `Intégrations indisponibles (${r.status})`);
  return data as T;
}
const post = <T,>(url: string, corps: unknown) => api<T>(url, {
  method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" }, body: JSON.stringify(corps),
});
function date(ts: number | null) {
  return ts === null ? "Pas encore vérifiée" : new Date(ts * 1000).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
function adresseValide(url: string) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && (!u.port || u.port === "443") && !u.username && !u.password && !u.search && !u.hash;
  } catch { return false; }
}

/** Les formulaires administrent des références de connexion ; les secrets restent sur le serveur. */
export function ConnexionsAgents({ source }: { source: Source }) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const [ouvert, setOuvert] = useState(false);
  const [onglet, setOnglet] = useState<Onglet>("connexions");
  const [connexions, setConnexions] = useState<Connexion[]>([]);
  const [capacites, setCapacites] = useState<Capacite[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [outilsChoisis, setOutilsChoisis] = useState<Record<string, string[]>>({});
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [actualisation, setActualisation] = useState(0);
  const [action, setAction] = useState("");
  const [ajout, setAjout] = useState(false);
  const [identifiant, setIdentifiant] = useState("");
  const [nom, setNom] = useState("");
  const [url, setUrl] = useState("");
  const [variable, setVariable] = useState("");
  const [transport, setTransport] = useState<"mcp_http" | "mcp_stdio">("mcp_http");
  const [commande, setCommande] = useState("");
  const [argumentsProcessus, setArgumentsProcessus] = useState("");
  const [variablesProcessus, setVariablesProcessus] = useState("");
  const [dossierProcessus, setDossierProcessus] = useState("");
  const [ceProjet, setCeProjet] = useState(false);

  useEffect(() => {
    const d = dialog.current;
    if (ouvert && d && !d.open) d.showModal();
    else if (!ouvert && d?.open) { d.close(); setUrl(""); }
  }, [ouvert]);
  useEffect(() => {
    if (!ouvert || source.demo) return;
    const c = new AbortController();
    let timer: number | undefined;
    setErreur(""); setChargement(true);
    const charger = async () => {
      try {
        if (onglet === "connexions") {
          const r = await api<{ connexions: Connexion[] }>("/api/v2/connexions", { signal: c.signal });
          if (!c.signal.aborted) {
            setConnexions(r.connexions);
            setOutilsChoisis(Object.fromEntries(r.connexions.map(c => [c.id, c.outils_autorises])));
          }
        } else if (onglet === "capacites") {
          const r = await api<{ capacites: Capacite[] }>("/api/v2/os/capacites", { signal: c.signal });
          if (!c.signal.aborted) setCapacites(r.capacites);
        } else {
          const r = await api<{ operations: Operation[] }>(`/api/v2/outils/operations${ceProjet ? `?projet=${encodeURIComponent(source.espace)}` : ""}`, { signal: c.signal });
          if (!c.signal.aborted) setOperations(r.operations);
        }
        if (!c.signal.aborted) setErreur("");
      } catch (e) { if (!c.signal.aborted) setErreur(e instanceof Error ? e.message : "Lecture impossible"); }
      finally {
        if (!c.signal.aborted) {
          setChargement(false);
          if (onglet === "operations") timer = window.setTimeout(charger, 7000);
        }
      }
    };
    void charger();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [ouvert, source.demo, source.espace, onglet, ceProjet, actualisation]);

  const administrer = async (connexionId: string, commande: "decouvrir" | "revoquer" | "outils", corps = {}) => {
    if (action) return;
    setAction(`${connexionId}:${commande}`); setErreur(""); setConfirmation("");
    try {
      const r = await post<Connexion>(`/api/v2/connexions/${encodeURIComponent(connexionId)}/${commande}`, corps);
      setConnexions(avant => avant.map(c => c.id === connexionId ? r : c));
      setOutilsChoisis(avant => ({ ...avant, [r.id]: r.outils_autorises }));
      setConfirmation(commande === "decouvrir" ? "Connexion vérifiée et outils découverts." : commande === "revoquer" ? "Connexion révoquée." : "Sélection des outils enregistrée.");
    } catch (e) { setErreur(e instanceof Error ? e.message : "Action impossible"); }
    finally { setAction(""); }
  };
  const argumentsLocaux = argumentsProcessus.split("\n").map(v => v.trim()).filter(Boolean);
  const nomsVariables = variablesProcessus.split("\n").map(v => v.trim()).filter(Boolean);
  const cheminAbsolu = (v: string) => v.startsWith("/") && !/[\r\n\x00]/.test(v);
  const valide = /^[a-z][a-z0-9_-]{0,39}$/.test(identifiant) && !!nom.trim() && (transport === "mcp_http"
    ? adresseValide(url) && (!variable || /^[A-Z_][A-Z0-9_]*$/.test(variable))
    : cheminAbsolu(commande) && (!dossierProcessus || cheminAbsolu(dossierProcessus)) && argumentsLocaux.length <= 64 && nomsVariables.every(v => /^[A-Z_][A-Z0-9_]*$/.test(v)));
  const connecter = async () => {
    if (action || !valide) return;
    setAction("ajout"); setErreur(""); setConfirmation("");
    try {
      const r = await post<Connexion>("/api/v2/connexions", { id: identifiant, nom: nom.trim(), type: transport,
        ...(transport === "mcp_http" ? { url, ...(variable ? { token_env: variable } : {}) }
          : { command: commande, args: argumentsLocaux, env_allowlist: nomsVariables, ...(dossierProcessus ? { cwd: dossierProcessus } : {}) }),
        outils_autorises: [] });
      setConnexions(avant => [...avant.filter(c => c.id !== r.id), r]);
      setOutilsChoisis(avant => ({ ...avant, [r.id]: [] }));
      setAjout(false); setIdentifiant(""); setNom(""); setUrl(""); setVariable(""); setCommande(""); setArgumentsProcessus(""); setVariablesProcessus(""); setDossierProcessus("");
      setConfirmation("Connexion enregistrée. Découvre ses outils pour vérifier le serveur.");
    } catch (e) { setErreur(e instanceof Error ? e.message : "Connexion non enregistrée"); }
    finally { setAction(""); }
  };
  if (source.demo) return null;
  return <>
    <button type="button" className="integrations-ouvrir" aria-haspopup="dialog" title="Intégrations" onClick={() => setOuvert(true)}><PlugZap size={17}/><span>Intégrations</span></button>
    <dialog ref={dialog} className="integrations-dialog" aria-labelledby={`${id}-titre`} onClose={() => setOuvert(false)}>
      {ouvert && <div className="integrations-coque">
        <header className="integrations-entete"><span className="integrations-embleme"><PlugZap size={22}/></span><div><p>Relier l'usine à ses outils</p><h2 id={`${id}-titre`}>Intégrations</h2></div>
          <button type="button" className="icone-bouton" aria-label="Actualiser les intégrations" disabled={!!action} onClick={() => setActualisation(n => n + 1)}><RefreshCw size={17}/></button>
          <button type="button" className="icone-bouton" aria-label="Fermer les intégrations" onClick={() => setOuvert(false)}><X size={20}/></button></header>
        <div className="integrations-onglets" role="tablist" aria-label="Informations des intégrations">
          {([ ["connexions", "Connexions", Link2], ["operations", "Activité des outils", Activity], ["capacites", "Capacités", ShieldCheck] ] as const).map(([cle, libelle, Icone]) =>
            <button key={cle} type="button" role="tab" id={`${id}-${cle}`} aria-controls={`${id}-panneau`} aria-selected={onglet === cle} disabled={!!action} onClick={() => { setOnglet(cle); setConfirmation(""); }}><Icone size={16}/>{libelle}</button>)}
        </div>
        <div className="integrations-contenu" role="tabpanel" id={`${id}-panneau`} aria-labelledby={`${id}-${onglet}`}>
          {erreur && <p className="integrations-erreur" role="alert">{erreur}</p>}
          {confirmation && <p className="integrations-confirmation" role="status"><Check size={15}/>{confirmation}</p>}
          {chargement && <p className="integrations-attente" role="status"><LoaderCircle size={16}/>Lecture de l'installation…</p>}
          {onglet === "connexions" && <>
            <div className="integrations-intro"><div><h3>Connexions de l'usine</h3><p>Ajoute un serveur MCP, découvre ses outils, puis choisis ceux que tes agents pourront demander.</p></div>
              <button type="button" className="bouton primaire" disabled={!!action} onClick={() => setAjout(!ajout)}><Plus size={15}/>{ajout ? "Fermer le formulaire" : "Connecter un serveur MCP"}</button></div>
            {ajout && <form className="integrations-formulaire" aria-label="Connecter un serveur MCP" onSubmit={e => { e.preventDefault(); void connecter(); }}>
              <label>Transport du serveur MCP<select value={transport} onChange={e => setTransport(e.target.value as "mcp_http" | "mcp_stdio")}><option value="mcp_http">Serveur HTTPS distant</option><option value="mcp_stdio">Processus local, stdio</option></select></label>
              <div className="integrations-champs"><label>Nom de la connexion<input required value={nom} maxLength={120} onChange={e => setNom(e.target.value)} placeholder="Mon espace de recherche"/></label>
                <label>Identifiant<input required value={identifiant} maxLength={40} pattern="[a-z][a-z0-9_-]{0,39}" onChange={e => setIdentifiant(e.target.value)} placeholder="recherche"/></label></div>
              {transport === "mcp_http" && <><label>Adresse HTTPS du serveur MCP<input type="url" required value={url} maxLength={2048} onChange={e => setUrl(e.target.value)} placeholder="https://mcp.example.org/mcp" autoComplete="off"/></label>
              {url && !adresseValide(url) && <p className="integrations-erreur">Utilise une adresse HTTPS sur le port 443, sans identifiants, paramètres ni fragment.</p>}
              <label>Variable d'authentification, facultative<input value={variable} onChange={e => setVariable(e.target.value)} pattern="[A-Z_][A-Z0-9_]*" maxLength={100} placeholder="JARVIS_MCP_TOKEN" autoComplete="off"/></label>
              <p className="integrations-aide"><CircleHelp size={15}/><span>Indique uniquement le nom d'une variable disponible sur le serveur Jarvis. Sa valeur secrète reste sur le serveur.</span></p></>}
              {transport === "mcp_stdio" && <><label>Exécutable local, chemin absolu<input required value={commande} maxLength={2048} onChange={e => setCommande(e.target.value)} placeholder="/chemin/vers/le-serveur-mcp" autoComplete="off"/></label>
                <label>Arguments, un par ligne<textarea value={argumentsProcessus} rows={3} maxLength={16000} onChange={e => setArgumentsProcessus(e.target.value)} placeholder="Chaque ligne devient un argument distinct"/></label>
                <label>Variables à transmettre, noms uniquement<textarea value={variablesProcessus} rows={2} maxLength={3000} onChange={e => setVariablesProcessus(e.target.value)} placeholder="JARVIS_SERVICE_TOKEN"/></label>
                <label>Dossier de travail, facultatif<input value={dossierProcessus} maxLength={2048} onChange={e => setDossierProcessus(e.target.value)} placeholder="/chemin/du/dossier" autoComplete="off"/></label>
                <p className="integrations-aide"><CircleHelp size={15}/><span>La découverte lancera cet exécutable sur le serveur Jarvis. Seuls les noms de variables choisis seront transmis ; aucune commande shell n'est construite.</span></p></>}
              <footer><button type="button" className="bouton" disabled={!!action} onClick={() => setAjout(false)}>Annuler</button><button type="submit" className="bouton primaire" disabled={!valide || !!action}>{action === "ajout" ? "Enregistrement…" : "Enregistrer la connexion"}</button></footer>
            </form>}
            {!chargement && !connexions.length && !erreur && <div className="integrations-vide"><PlugZap size={32}/><h3>Le prochain outil commence ici</h3><p>Aucun serveur MCP n'est encore connecté à cette installation.</p></div>}
            <div className="integrations-liste">{connexions.map(c => {
              const choix = outilsChoisis[c.id] ?? c.outils_autorises;
              const modifie = [...choix].sort().join("\0") !== [...c.outils_autorises].sort().join("\0");
              return <article className={`integration-carte${c.active ? "" : " revoquee"}`} key={c.id}>
                <header><span className="integration-icone"><Link2 size={19}/></span><div><h4>{c.nom}</h4><p>{c.hote}</p></div><span className={`integration-etat ${c.etat}`}>{ETATS[c.etat] || c.etat}</span></header>
                <dl><div><dt>Authentification</dt><dd>{c.auth.mode === "processus_local" ? "Processus local" : c.auth.mode === "aucune" ? "Sans authentification" : c.auth.configuree ? "Variable disponible" : "Variable manquante"}</dd></div><div><dt>Dernière découverte</dt><dd>{date(c.verified_at)}</dd></div>{c.stdio && <div><dt>Exécutable</dt><dd>{c.stdio.executable}</dd></div>}</dl>
                {c.outils.length > 0 && <fieldset className="integration-outils"><legend>Outils accessibles aux agents</legend>{c.outils.map(o => <div key={o.name}>
                  <label><input type="checkbox" disabled={!c.active || !!action} checked={choix.includes(o.name)} onChange={e => setOutilsChoisis(avant => ({ ...avant, [c.id]: e.target.checked ? [...choix, o.name] : choix.filter(n => n !== o.name) }))}/><span><strong>{o.name}</strong>{o.description && <small>{o.description}</small>}</span></label>
                  <details><summary>Schéma d'entrée</summary><pre>{JSON.stringify(o.inputSchema, null, 2)}</pre></details>
                </div>)}</fieldset>}
                {!c.outils.length && c.active && <p className="integration-note">La découverte vérifie la connexion et récupère les outils réellement proposés.</p>}
                {c.outils.length > 0 && <p className="integration-note">Chaque exécution exige aussi un mandat couvrant l'outil, le projet et la destination.</p>}
                <footer>{c.active && <><button type="button" className="bouton" disabled={!!action} onClick={() => void administrer(c.id, "decouvrir")}><RefreshCw size={14}/>{action === `${c.id}:decouvrir` ? "Découverte…" : "Découvrir les outils"}</button>
                  {modifie && <button type="button" className="bouton primaire" disabled={!!action} onClick={() => void administrer(c.id, "outils", { outils_autorises: choix })}>Enregistrer les outils</button>}
                  <button type="button" className="bouton integration-revoquer" disabled={!!action} onClick={() => void administrer(c.id, "revoquer")}><Unplug size={14}/>Révoquer</button></>}</footer>
              </article>;
            })}</div>
          </>}
          {onglet === "operations" && <><div className="integrations-intro"><div><h3>Activité réelle des outils</h3><p>Les opérations enregistrées et leur résultat connu. Actualisation toutes les 7 secondes.</p></div><label className="integrations-filtre"><input type="checkbox" checked={ceProjet} onChange={e => setCeProjet(e.target.checked)}/>Ce Board seulement</label></div>
            {!chargement && !operations.length && !erreur && <div className="integrations-vide"><Activity size={30}/><h3>Aucune opération observée</h3><p>Les appels exécutés par la passerelle apparaîtront ici.</p></div>}
            <div className="integrations-operations">{operations.map(o => <article key={o.operation_id}><header><strong>{o.tool}</strong><span className={`integration-etat ${o.status}`}>{ETATS[o.status] || o.status}</span></header><p>{o.project || "Sans projet"} · {date(o.updated_at)}</p><dl><dt>Opération</dt><dd>{o.operation_id}</dd><dt>Mandat</dt><dd>{o.mandat_id}</dd></dl>{o.erreur && <p className="integrations-erreur">{o.erreur}</p>}</article>)}</div>
          </>}
          {onglet === "capacites" && <><div className="integrations-intro"><div><h3>Ce que l'installation a vérifié</h3><p>Chaque état est accompagné de sa preuve. Aucun appel de modèle n'est effectué par ce diagnostic.</p></div></div>
            <div className="integrations-capacites">{capacites.map(c => <article key={c.id}><header><strong>{c.id}</strong><span className={`integration-etat ${c.etat}`}>{ETATS[c.etat] || c.etat}</span></header><p>{c.preuve}</p><small>{c.scope}{c.version && ` · version ${c.version}`}</small></article>)}</div>
          </>}
        </div>
      </div>}
    </dialog>
  </>;
}
