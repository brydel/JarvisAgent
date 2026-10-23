import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, Bot, Check, CircleHelp, Clock3, KeyRound, LoaderCircle, Mail, Pause, Play, Plus, RefreshCw, ShieldCheck, Square, X } from "lucide-react";
import type { Source } from "../api";
import "../styles/runtime.css";

interface ConfigurationModele {
  provider: "openai_responses"; model: string; api_key_env: string;
  max_output_tokens: number; timeout_s: number; max_turns: number;
  auth?: { configuree: boolean; mode: string }; inference_verifiee?: boolean;
}
interface VerificationModele { authentification: string; modele: string; inference: string; preuve: string }
interface Mandat {
  id: string; owner: string; project: string; tools: string[]; destinations: string[];
  expires_at: number; max_cost_cents: number; max_actions: number;
  used_actions: number; used_cost_cents: number; revoked_at: number | null;
}
interface Outil { id: string; nom: string; disponible: boolean }
interface Run {
  id: string; status: string; created_at: number; updated_at: number;
  agent: { id: string; role: string; model: string; tools: string[]; budget: { max_tokens: number; max_cost_cents: number; max_duration_s: number } };
  tache: { objective: string; project: string; acceptance: string[]; mandate_id: string };
  tours: number; max_tours: number; usage: { input_tokens: number; output_tokens: number; reserved_cost_cents: number };
  resultat: string; preuves: string[]; raison: string; factice: boolean;
  trace: { sequence: number; type: string; ts: number; donnees: Record<string, unknown> }[];
  evaluation: { commentaire?: string; accepte?: boolean; preuves?: string[] } | null;
}
interface OAuth {
  id: string; nom: string; provider: string; scopes: string[]; redirect_uri: string;
  client_id_configure: boolean; client_secret_configure: boolean; etat: string;
  adresse_expediteur?: string;
  expires_at?: number; actualise_at?: number;
}
type Onglet = "missions" | "modele" | "mandats" | "courriel";
const ETATS: Record<string, string> = {
  planned: "Prête à démarrer", running: "En cours", paused: "En pause", blocked: "Bloquée",
  awaiting_review: "À vérifier", succeeded: "Vérifiée", failed: "Échouée", cancelled: "Annulée",
  configuree: "À connecter", connectee: "Connectée", expiree: "Expirée", revoquee: "Révoquée",
};
const SCOPES = [
  { id: "https://www.googleapis.com/auth/gmail.readonly", nom: "Lire les courriels" },
  { id: "https://www.googleapis.com/auth/gmail.compose", nom: "Préparer des brouillons" },
  { id: "https://www.googleapis.com/auth/gmail.send", nom: "Envoyer des courriels" },
];
const MODELE_VIDE: ConfigurationModele = { provider: "openai_responses", model: "", api_key_env: "JARVIS_OPENAI_API_KEY", max_output_tokens: 4096, timeout_s: 90, max_turns: 12 };
const lignes = (texte: string) => texte.split("\n").map(s => s.trim()).filter(Boolean);
const date = (ts: number) => new Date(ts * 1000).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const actif = (m: Mandat) => m.revoked_at === null && m.expires_at > Date.now() / 1000 && m.used_actions < m.max_actions;

async function api<T>(url: string, init?: RequestInit, timeoutMs = 25000): Promise<T> {
  const signal = init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs);
  const r = await fetch(url, { credentials: "same-origin", ...init, signal });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.erreur || `Service indisponible (${r.status})`);
  return data as T;
}
const post = <T,>(url: string, corps: unknown = {}, timeoutMs = 25000) => api<T>(url, {
  method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" }, body: JSON.stringify(corps),
}, timeoutMs);
const formulaireModele = (c: ConfigurationModele | null): ConfigurationModele => c ? {
  provider: c.provider, model: c.model, api_key_env: c.api_key_env,
  max_output_tokens: c.max_output_tokens, timeout_s: c.timeout_s, max_turns: c.max_turns,
} : MODELE_VIDE;

function ModeleForm({ configuration, sauver, verifier, verification, enCours }: {
  configuration: ConfigurationModele | null; sauver: (c: ConfigurationModele) => Promise<void>;
  verifier: () => Promise<void>; verification: VerificationModele | null; enCours: boolean;
}) {
  const [form, setForm] = useState(formulaireModele(configuration));
  useEffect(() => setForm(formulaireModele(configuration)), [configuration]);
  const modifie = <K extends keyof ConfigurationModele>(cle: K, valeur: ConfigurationModele[K]) => setForm(c => ({ ...c, [cle]: valeur }));
  const valide = !!form.model.trim() && /^[A-Z_][A-Z0-9_]{0,99}$/.test(form.api_key_env) && form.max_output_tokens > 0 && form.timeout_s > 0 && form.max_turns > 0;
  return <>
    <div className="runtime-intro"><h3>Le modèle de tes agents</h3><p>Indique le modèle de ton compte et la variable du serveur qui contient sa clé. Une vérification de disponibilité ne lance aucune inférence.</p></div>
    <form className="runtime-form" aria-label="Configuration du modèle" onSubmit={e => { e.preventDefault(); void sauver(form); }}>
      <label>Identifiant du modèle<input required autoComplete="off" value={form.model} maxLength={200} onChange={e => modifie("model", e.target.value)} placeholder="Identifiant exact disponible sur ton compte"/></label>
      <label>Variable contenant la clé API<input required value={form.api_key_env} maxLength={100} pattern="[A-Z_][A-Z0-9_]*" onChange={e => modifie("api_key_env", e.target.value)} autoComplete="off"/></label>
      <p className="runtime-aide"><KeyRound size={15}/><span>Le nom de variable suffit. La clé reste sur le serveur ; ne la colle pas ici.</span></p>
      <div className="runtime-grille trois"><label>Sortie maximale par tour<input type="number" min={1} max={32768} required value={form.max_output_tokens} onChange={e => modifie("max_output_tokens", Number(e.target.value))}/></label>
        <label>Délai d'appel, en secondes<input type="number" min={1} max={120} required value={form.timeout_s} onChange={e => modifie("timeout_s", Number(e.target.value))}/></label>
        <label>Tours maximum<input type="number" min={1} max={64} required value={form.max_turns} onChange={e => modifie("max_turns", Number(e.target.value))}/></label></div>
      <footer><button type="submit" className="bouton primaire" disabled={!valide || enCours}>Enregistrer le modèle</button>
        <button type="button" className="bouton" disabled={!configuration || enCours} onClick={() => void verifier()}><ShieldCheck size={14}/>Vérifier la disponibilité</button></footer>
    </form>
    {configuration && <div className="runtime-info"><h4>Configuration enregistrée</h4><dl><dt>Modèle</dt><dd>{configuration.model}</dd><dt>Clé sur le serveur</dt><dd>{configuration.auth?.configuree ? "Disponible" : "Variable manquante"}</dd><dt>Inférence</dt><dd>Non vérifiée par ce contrôle</dd></dl></div>}
    {verification && <div className="runtime-info" role="status"><h4>Dernière vérification</h4><p>{verification.preuve}</p><dl><dt>Authentification</dt><dd>{verification.authentification === "verifiee" ? "Vérifiée" : "Non vérifiée"}</dd><dt>Modèle</dt><dd>{verification.modele === "verifie" ? "Disponible" : "Non vérifié"}</dd></dl></div>}
  </>;
}

/** Une mission outillée conserve son propre état et attend une revue après la réponse finale. */
export function RuntimeAgents({ source }: { source: Source }) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const [ouvert, setOuvert] = useState(false);
  const [onglet, setOnglet] = useState<Onglet>("missions");
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [action, setAction] = useState("");
  const [actualisation, setActualisation] = useState(0);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selection, setSelection] = useState("");
  const [detail, setDetail] = useState<Run | null>(null);
  const [configuration, setConfiguration] = useState<ConfigurationModele | null>(null);
  const [verification, setVerification] = useState<VerificationModele | null>(null);
  const [mandats, setMandats] = useState<Mandat[]>([]);
  const [outils, setOutils] = useState<Outil[]>([]);
  const [oauth, setOauth] = useState<OAuth[]>([]);
  const [nouvelleMission, setNouvelleMission] = useState(false);
  const [objectif, setObjectif] = useState("");
  const [projet, setProjet] = useState(source.espace);
  const [acceptation, setAcceptation] = useState("");
  const [mandatId, setMandatId] = useState("");
  const [selectionOutils, setSelectionOutils] = useState<string[]>([]);
  const [maxTours, setMaxTours] = useState(8);
  const [maxTokens, setMaxTokens] = useState(12000);
  const [maxCout, setMaxCout] = useState(100);
  const [maxDuree, setMaxDuree] = useState(600);
  const [coutTour, setCoutTour] = useState(1);
  const [commentaire, setCommentaire] = useState("");
  const [preuves, setPreuves] = useState("");
  const [nouveauMandat, setNouveauMandat] = useState(false);
  const [mandatProjet, setMandatProjet] = useState(source.espace);
  const [mandatOutils, setMandatOutils] = useState<string[]>(["model.openai_responses.inference"]);
  const [destinations, setDestinations] = useState("api.openai.com");
  const [mandatDuree, setMandatDuree] = useState(60);
  const [mandatCout, setMandatCout] = useState(100);
  const [mandatActions, setMandatActions] = useState(32);
  const [nouvelOAuth, setNouvelOAuth] = useState(false);
  const [oauthId, setOauthId] = useState("");
  const [oauthNom, setOauthNom] = useState("");
  const [clientId, setClientId] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [adresseExpediteur, setAdresseExpediteur] = useState("");
  const [redirectUri, setRedirectUri] = useState(() => `${location.origin}/api/v2/oauth/callback`);
  const [scopes, setScopes] = useState<string[]>([SCOPES[0]!.id]);
  const [lienAutorisation, setLienAutorisation] = useState<{ nom: string; url: string } | null>(null);
  const demandeMission = useRef<{ empreinte: string; agentId: string; tacheId: string } | null>(null);
  const versionDetail = useRef(0);
  const selectionRef = useRef(selection); selectionRef.current = selection;
  useEffect(() => { if (configuration) setMaxTours(avant => Math.min(avant, configuration.max_turns, 32)); }, [configuration?.max_turns]);

  useEffect(() => {
    const d = dialog.current;
    if (ouvert && d && !d.open) d.showModal();
    else if (!ouvert && d?.open) d.close();
  }, [ouvert]);
  useEffect(() => {
    if (!ouvert || source.demo) return;
    const c = new AbortController();
    let timer: number | undefined;
    setChargement(true);
    const charger = async () => {
      try {
        if (onglet === "missions") {
          const [r, m, o, conf] = await Promise.all([
            api<{ runs: Run[] }>("/api/v2/runtime", { signal: c.signal }),
            api<{ mandats: Mandat[] }>("/api/v2/os/mandats", { signal: c.signal }),
            api<{ outils: Outil[] }>("/api/v2/outils", { signal: c.signal }),
            api<{ configuration: ConfigurationModele | null }>("/api/v2/modeles-runtime", { signal: c.signal }),
          ]);
          if (!c.signal.aborted) {
            setRuns(r.runs); setMandats(m.mandats); setOutils(o.outils); setConfiguration(conf.configuration);
            setSelection(avant => avant || r.runs[0]?.id || "");
          }
        } else if (onglet === "modele") {
          const r = await api<{ configuration: ConfigurationModele | null; verification?: VerificationModele | null }>("/api/v2/modeles-runtime", { signal: c.signal });
          if (!c.signal.aborted) { setConfiguration(r.configuration); setVerification(r.verification || null); }
        } else if (onglet === "mandats") {
          const [m, o] = await Promise.all([api<{ mandats: Mandat[] }>("/api/v2/os/mandats", { signal: c.signal }), api<{ outils: Outil[] }>("/api/v2/outils", { signal: c.signal })]);
          if (!c.signal.aborted) { setMandats(m.mandats); setOutils(o.outils); }
        } else {
          const r = await api<{ connexions: OAuth[] }>("/api/v2/oauth", { signal: c.signal });
          if (!c.signal.aborted) setOauth(r.connexions);
        }
        if (!c.signal.aborted) setErreur("");
      } catch (e) { if (!c.signal.aborted) setErreur(e instanceof Error ? e.message : "Lecture impossible"); }
      finally {
        if (!c.signal.aborted) {
          setChargement(false);
          if (onglet === "missions" || onglet === "courriel") timer = window.setTimeout(charger, 4000);
        }
      }
    };
    void charger();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [ouvert, onglet, source.demo, actualisation]);
  useEffect(() => {
    if (!ouvert || onglet !== "missions" || !selection || nouvelleMission) return;
    const c = new AbortController();
    const version = ++versionDetail.current;
    let timer: number | undefined;
    setDetail(null);
    const charger = async () => {
      try {
        const r = await api<Run>(`/api/v2/runtime/${encodeURIComponent(selection)}`, { signal: c.signal });
        if (!c.signal.aborted && versionDetail.current === version) setDetail(r);
      } catch (e) { if (!c.signal.aborted) setErreur(e instanceof Error ? e.message : "Mission indisponible"); }
      finally { if (!c.signal.aborted) timer = window.setTimeout(charger, 2500); }
    };
    void charger();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [ouvert, onglet, selection, nouvelleMission, actualisation]);

  const agir = async <T,>(nom: string, travail: () => Promise<T>, ensuite?: (r: T) => void, message = "Modification enregistrée.") => {
    if (action) return;
    setAction(nom); setErreur(""); setConfirmation("");
    try {
      const r = await travail(); ensuite?.(r); setConfirmation(message); setActualisation(n => n + 1);
    } catch (e) { setErreur(e instanceof Error ? e.message : "Opération impossible"); }
    finally { setAction(""); }
  };
  const changerOnglet = (t: Onglet) => { setOnglet(t); setErreur(""); setConfirmation(""); };
  const mandat = mandats.find(m => m.id === mandatId);
  const mandatsAdmis = mandats.filter(m => actif(m) && m.project === projet && m.tools.includes("model.openai_responses.inference") && m.destinations.includes("api.openai.com"));
  const outilsAdmis = outils.filter(o => o.disponible && mandat?.tools.includes(o.id));
  const valideMission = !!objectif.trim() && !!projet.trim() && lignes(acceptation).length > 0 && !!configuration?.model && !!configuration.auth?.configuree && mandatsAdmis.some(m => m.id === mandatId)
    && selectionOutils.every(o => outilsAdmis.some(a => a.id === o)) && maxTokens >= 1 && maxCout >= 0 && maxDuree >= 1 && maxTours >= 1 && maxTours <= Math.min(configuration.max_turns, 32) && coutTour >= 0;
  const creerMission = async () => {
    if (!valideMission || !configuration) return;
    const parametres = { objectif, projet, acceptation, mandatId, selectionOutils, maxTokens, maxCout, maxDuree, maxTours, coutTour, modele: configuration.model };
    const empreinte = JSON.stringify(parametres);
    if (demandeMission.current?.empreinte !== empreinte) {
      const suffixe = crypto.randomUUID().replaceAll("-", "");
      demandeMission.current = { empreinte, agentId: `AG-${suffixe}`, tacheId: `TK-${suffixe}` };
    }
    const { agentId, tacheId } = demandeMission.current!;
    const corps = {
      agent: { version: 1, id: agentId, role: "generaliste", profile: "outille", provider: "openai_responses", model: configuration.model,
        tools: selectionOutils, required_capabilities: [], budget: { max_tokens: maxTokens, max_cost_cents: maxCout, max_duration_s: maxDuree }, delegation: { max_depth: 0, max_children: 0 } },
      tache: { version: 1, id: tacheId, agent_id: agentId, objective: objectif.trim(), project: projet.trim(), depends_on: [], inputs: [],
        acceptance: lignes(acceptation), required_tools: selectionOutils, mandate_id: mandatId, execution_engine: "local", max_attempts: 1 },
      configuration_modele: { provider: configuration.provider, model: configuration.model, api_key_env: configuration.api_key_env,
        max_output_tokens: configuration.max_output_tokens, timeout_s: configuration.timeout_s, max_turns: configuration.max_turns },
      max_tours: maxTours, reserve_model_cents: coutTour, max_model_output_tokens: Math.min(configuration.max_output_tokens, 32000),
      operation_id: "creation:" + tacheId,
    };
    await agir("creer-mission", () => post<Run>("/api/v2/runtime", corps), r => {
      setSelection(r.id); setDetail(r); setNouvelleMission(false); setObjectif(""); setAcceptation(""); demandeMission.current = null;
    }, "Mission créée. Tu peux maintenant la démarrer.");
  };
  const commande = (nom: string) => {
    if (!detail) return;
    const runId = detail.id;
    void agir(nom, () => post<Run>(`/api/v2/runtime/${encodeURIComponent(runId)}/${nom}`), r => {
      if (selectionRef.current === runId && r.id) setDetail(r);
    }, nom === "executer" ? "Exécution demandée. Son état s'actualise ici." : "État de la mission mis à jour.");
  };
  const evaluer = (accepte: boolean) => {
    if (!detail || !commentaire.trim() || (accepte && !lignes(preuves).length)) return;
    void agir("evaluer", () => post<Run>(`/api/v2/runtime/${encodeURIComponent(detail.id)}/evaluer`, { accepte, preuves: lignes(preuves), commentaire: commentaire.trim() }), r => {
      setDetail(r); setCommentaire(""); setPreuves("");
    }, accepte ? "Résultat vérifié et accepté." : "Relecture enregistrée.");
  };
  const creerMandat = () => void agir("creer-mandat", () => post<Mandat>("/api/v2/os/mandats", {
    version: 1, owner: "proprietaire", project: mandatProjet.trim(), tools: mandatOutils, destinations: lignes(destinations),
    expires_at: Date.now() / 1000 + mandatDuree * 60, max_cost_cents: mandatCout, max_actions: mandatActions,
  }), m => { setMandats(avant => [...avant, m]); setNouveauMandat(false); setMandatId(m.id); }, "Mandat enregistré avec le périmètre choisi.");
  const connecterOAuth = (c: OAuth) => void agir("oauth-commencer", () => post<{ authorization_url: string }>(`/api/v2/oauth/${encodeURIComponent(c.id)}/commencer`), r => {
    const u = new URL(r.authorization_url);
    if (u.protocol !== "https:" || u.hostname !== "accounts.google.com" || u.username || u.password) throw new Error("Adresse d'autorisation inattendue.");
    setLienAutorisation({ nom: c.nom, url: r.authorization_url });
  }, "Autorisation prête. Continue dans ton compte Google.");
  const sauvegarderOAuth = () => void agir("oauth-configurer", () => post<OAuth>("/api/v2/oauth", {
    id: oauthId.trim(), nom: oauthNom.trim(), provider: "google_gmail", client_id: clientId.trim(),
    ...(secretEnv ? { client_secret_env: secretEnv } : {}), redirect_uri: redirectUri.trim(), scopes,
    ...(adresseExpediteur ? { adresse_expediteur: adresseExpediteur.trim() } : {}),
  }), c => { setOauth(avant => [...avant.filter(x => x.id !== c.id), c]); setNouvelOAuth(false); setClientId(""); }, "Application Gmail enregistrée. Tu peux autoriser la connexion.");
  if (source.demo) return null;

  return <>
    <button type="button" className="runtime-ouvrir" title="Missions outillées" aria-haspopup="dialog" onClick={() => setOuvert(true)}><Bot size={18}/><span>Missions outillées</span></button>
    <dialog ref={dialog} className="runtime-dialog" aria-labelledby={`${id}-titre`} onClose={() => setOuvert(false)}>
      {ouvert && <div className="runtime-coque">
        <header className="runtime-entete"><span className="runtime-embleme"><Bot size={23}/></span><div><p>Donner un objectif, suivre les preuves</p><h2 id={`${id}-titre`}>Missions outillées</h2></div>
          <button type="button" className="icone-bouton" aria-label="Actualiser les missions outillées" disabled={!!action} onClick={() => setActualisation(n => n + 1)}><RefreshCw size={17}/></button>
          <button type="button" className="icone-bouton" aria-label="Fermer les missions outillées" onClick={() => setOuvert(false)}><X size={20}/></button></header>
        <div className="runtime-onglets" role="tablist" aria-label="Pilotage des missions outillées">
          {([ ["missions", "Missions", Bot], ["modele", "Modèle", KeyRound], ["mandats", "Mandats", ShieldCheck], ["courriel", "Courriel", Mail] ] as const).map(([cle, texte, Icone]) =>
            <button key={cle} type="button" role="tab" id={`${id}-${cle}`} aria-controls={`${id}-panneau`} aria-selected={onglet === cle} disabled={!!action} onClick={() => changerOnglet(cle)}><Icone size={16}/>{texte}</button>)}
        </div>
        <main className="runtime-contenu" role="tabpanel" id={`${id}-panneau`} aria-labelledby={`${id}-${onglet}`}>
          {erreur && <p className="runtime-erreur" role="alert">{erreur}</p>}
          {confirmation && <p className="runtime-confirmation" role="status"><Check size={15}/>{confirmation}</p>}
          {chargement && <p className="runtime-attente" role="status"><LoaderCircle size={16}/>Lecture de l'installation…</p>}
          {onglet === "modele" && <ModeleForm configuration={configuration} verification={verification} enCours={!!action}
            sauver={async c => { await agir("modele", () => post<{ configuration: ConfigurationModele }>("/api/v2/modeles-runtime", c), r => setConfiguration(r.configuration), "Configuration du modèle enregistrée."); }}
            verifier={async () => { await agir("verifier-modele", () => post<VerificationModele>("/api/v2/modeles-runtime/verifier", {}, 125000), setVerification, "Vérification terminée, sans inférence."); }}/>} 
          {onglet === "missions" && <>
            <div className="runtime-intro avec-action"><div><h3>Des actions suivies jusqu'à leur vérification</h3><p>Chaque mission utilise un modèle configuré, les outils choisis et un mandat. La réponse finale attend ta relecture.</p></div>
              <button type="button" className="bouton primaire" disabled={!!action} onClick={() => { setNouvelleMission(!nouvelleMission); setErreur(""); setConfirmation(""); }}><Plus size={15}/>{nouvelleMission ? "Fermer le formulaire" : "Nouvelle mission outillée"}</button></div>
            {!configuration?.model && !chargement && <div className="runtime-prealable"><KeyRound size={19}/><div><strong>Configure d'abord un modèle</strong><p>Son identifiant et une clé disponible sur le serveur sont nécessaires pour exécuter une mission.</p></div><button type="button" className="bouton" onClick={() => changerOnglet("modele")}>Configurer le modèle</button></div>}
            {nouvelleMission && <form className="runtime-form" aria-label="Nouvelle mission outillée" onSubmit={e => { e.preventDefault(); void creerMission(); }}>
              <label>Objectif de la mission<textarea required rows={3} value={objectif} maxLength={8000} onChange={e => setObjectif(e.target.value)} placeholder="Quel résultat concret veux-tu obtenir ?"/></label>
              <div className="runtime-grille"><label>Projet<input required value={projet} maxLength={200} onChange={e => { setProjet(e.target.value); setMandatId(""); setSelectionOutils([]); }}/></label>
                <label>Mandat existant<select required value={mandatId} onChange={e => { setMandatId(e.target.value); setSelectionOutils([]); }}><option value="">Choisir un mandat</option>{mandatsAdmis.map(m => <option key={m.id} value={m.id}>{m.id} · {m.max_actions - m.used_actions} actions restantes</option>)}</select></label></div>
              {!mandatsAdmis.length && <p className="runtime-aide"><ShieldCheck size={15}/><span>Aucun mandat actif pour ce projet et le modèle. <button type="button" className="runtime-lien" onClick={() => { setMandatProjet(projet); setNouveauMandat(true); changerOnglet("mandats"); }}>Créer un mandat</button></span></p>}
              <label>Critères de réussite, un par ligne<textarea required rows={3} value={acceptation} maxLength={8000} onChange={e => setAcceptation(e.target.value)} placeholder="Ce qui permettra de vérifier le résultat"/></label>
              <fieldset className="runtime-outils"><legend>Outils accessibles à cette mission</legend>{outilsAdmis.length ? outilsAdmis.map(o => <label key={o.id}><input type="checkbox" checked={selectionOutils.includes(o.id)} onChange={e => setSelectionOutils(avant => e.target.checked ? [...avant, o.id] : avant.filter(x => x !== o.id))}/><span>{o.nom}<small>{o.id}</small></span></label>) : <p>Choisis un mandat pour voir les outils qu'il autorise.</p>}</fieldset>
              <div className="runtime-grille trois"><label>Plafond de jetons<input type="number" min={1} max={10000000} required value={maxTokens} onChange={e => setMaxTokens(Number(e.target.value))}/></label><label>Budget réservé, en centimes<input type="number" min={0} max={1000000} required value={maxCout} onChange={e => setMaxCout(Number(e.target.value))}/></label><label>Durée maximale, en secondes<input type="number" min={1} max={86400} required value={maxDuree} onChange={e => setMaxDuree(Number(e.target.value))}/></label></div>
              <div className="runtime-grille"><label>Tours maximum<input type="number" min={1} max={Math.min(configuration?.max_turns || 32, 32)} required value={maxTours} onChange={e => setMaxTours(Number(e.target.value))}/></label><label>Réservation par appel du modèle, en centimes<input type="number" min={0} max={1000000} required value={coutTour} onChange={e => setCoutTour(Number(e.target.value))}/></label></div>
              <p className="runtime-aide"><CircleHelp size={15}/><span>Ces réservations bornent le travail autorisé dans Jarvis. Vérifie aussi les limites de facturation de ton fournisseur.</span></p>
              <footer><button type="button" className="bouton" disabled={!!action} onClick={() => setNouvelleMission(false)}>Annuler</button><button type="submit" className="bouton primaire" disabled={!valideMission || !!action}>Créer la mission</button></footer>
            </form>}
            {!nouvelleMission && <div className="runtime-travail"><aside className="runtime-liste" aria-label="Missions outillées enregistrées">{!runs.length && !chargement && <div className="runtime-vide"><Bot size={30}/><h4>La prochaine mission commence ici</h4><p>Aucune exécution outillée enregistrée.</p></div>}{runs.map(r => <button type="button" key={r.id} aria-pressed={selection === r.id} onClick={() => { setSelection(r.id); setCommentaire(""); setPreuves(""); setErreur(""); setConfirmation(""); }}><span className={`runtime-etat ${r.status}`}>{ETATS[r.status] || r.status}</span><strong>{r.tache.objective}</strong><small>{r.tache.project} · {date(r.created_at)}</small></button>)}</aside>
              {detail && <section className="runtime-detail" aria-label="Détail de la mission outillée"><header><span className={`runtime-etat ${detail.status}`}>{ETATS[detail.status] || detail.status}</span>{detail.factice && <span className="runtime-etat factice">Fournisseur de test</span>}<h3>{detail.tache.objective}</h3><p>{detail.tache.project} · {detail.agent.model}</p></header>
                <div className="runtime-mesures"><div><span>Tours</span><strong>{detail.tours} / {detail.max_tours}</strong></div><div><span>Jetons utilisés</span><strong>{detail.usage.input_tokens + detail.usage.output_tokens}</strong></div><div><span>Réservé</span><strong>{detail.usage.reserved_cost_cents} c</strong></div></div>
                <div className="runtime-commandes">{detail.status === "planned" && <button type="button" className="bouton primaire" disabled={!!action} onClick={() => commande("executer")}><Play size={14}/>Démarrer la mission</button>}
                  {detail.status === "running" && <button type="button" className="bouton" disabled={!!action} onClick={() => commande("pause")}><Pause size={14}/>Mettre en pause</button>}
                  {detail.status === "paused" && <button type="button" className="bouton primaire" disabled={!!action} onClick={() => commande("reprendre")}><Play size={14}/>Reprendre</button>}
                  {!["succeeded", "failed", "cancelled"].includes(detail.status) && <button type="button" className="bouton runtime-arreter" disabled={!!action} onClick={() => commande("annuler")}><Square size={13}/>Arrêter la mission</button>}</div>
                {detail.raison && <p className={`runtime-raison ${detail.status}`} role={detail.status === "blocked" || detail.status === "failed" ? "alert" : undefined}>{detail.raison}</p>}
                <h4>Ce qui doit être vérifié</h4><ul className="runtime-criteres">{detail.tache.acceptance.map((a, i) => <li key={i}>{a}</li>)}</ul>
                {detail.resultat && <><h4>Résultat proposé</h4><pre className="runtime-resultat">{detail.resultat}</pre></>}
                {!!detail.preuves.length && <details className="runtime-references"><summary>Références produites par l'exécution</summary><ul>{detail.preuves.map((p, i) => <li key={i}><code>{p}</code></li>)}</ul></details>}
                {detail.status === "awaiting_review" && <form className="runtime-form runtime-revue" aria-label="Vérifier le résultat" onSubmit={e => { e.preventDefault(); evaluer(true); }}><h4>Ta relecture</h4><p>Compare le résultat aux critères avant de décider.</p><label>Commentaire de vérification<textarea required rows={3} maxLength={8000} value={commentaire} onChange={e => setCommentaire(e.target.value)}/></label><label>Preuves de vérification, une par ligne<textarea rows={2} maxLength={5000} value={preuves} onChange={e => setPreuves(e.target.value)} placeholder="Rapport, source consultée ou artefact vérifié"/></label><footer><button type="button" className="bouton" disabled={!commentaire.trim() || !!action} onClick={() => evaluer(false)}>Refuser le résultat</button><button type="submit" className="bouton primaire" disabled={!commentaire.trim() || !lignes(preuves).length || !!action}>Valider les preuves</button></footer></form>}
                {detail.evaluation?.commentaire && <div className="runtime-info"><h4>Relecture enregistrée</h4><p>{detail.evaluation.commentaire}</p></div>}
                {!!detail.trace.length && <details className="runtime-trace"><summary><Clock3 size={14}/>Historique de l'exécution</summary><ol>{detail.trace.map(e => <li key={e.sequence}><time>{date(e.ts)}</time><span>{e.type.replaceAll("_", " ")}</span>{typeof e.donnees.outil === "string" && <code>{e.donnees.outil}</code>}</li>)}</ol></details>}
              </section>}
            </div>}
          </>}
          {onglet === "mandats" && <>
            <div className="runtime-intro avec-action"><div><h3>Ce que l'usine peut faire pour toi</h3><p>Définis le projet, les outils, les destinations et une durée. Les agents utilisent ce périmètre sans te redemander chaque action.</p></div><button type="button" className="bouton primaire" disabled={!!action} onClick={() => setNouveauMandat(!nouveauMandat)}><Plus size={14}/>{nouveauMandat ? "Fermer le formulaire" : "Nouveau mandat"}</button></div>
            {nouveauMandat && <form className="runtime-form" aria-label="Nouveau mandat" onSubmit={e => { e.preventDefault(); creerMandat(); }}><label>Projet du mandat<input required value={mandatProjet} maxLength={200} onChange={e => setMandatProjet(e.target.value)}/></label>
              <fieldset className="runtime-outils"><legend>Outils autorisés</legend>{[{ id: "model.openai_responses.inference", nom: "Appeler le modèle OpenAI", disponible: true }, ...outils].map(o => <label key={o.id}><input type="checkbox" checked={mandatOutils.includes(o.id)} onChange={e => setMandatOutils(avant => e.target.checked ? [...avant, o.id] : avant.filter(x => x !== o.id))}/><span>{o.nom}<small>{o.id}</small></span></label>)}</fieldset>
              <label>Destinations exactes, une par ligne<textarea rows={3} maxLength={5000} value={destinations} onChange={e => setDestinations(e.target.value)} placeholder="api.openai.com"/></label>
              <div className="runtime-grille trois"><label>Durée, en minutes<input type="number" min={1} max={10080} required value={mandatDuree} onChange={e => setMandatDuree(Number(e.target.value))}/></label><label>Budget maximal, en centimes<input type="number" min={0} max={1000000} required value={mandatCout} onChange={e => setMandatCout(Number(e.target.value))}/></label><label>Nombre maximal d'actions<input type="number" min={1} max={100000} required value={mandatActions} onChange={e => setMandatActions(Number(e.target.value))}/></label></div>
              <footer><button type="submit" className="bouton primaire" disabled={!mandatProjet.trim() || !mandatOutils.length || !!action}>Créer ce mandat</button></footer></form>}
            <div className="runtime-cartes">{mandats.map(m => <article key={m.id}><header><ShieldCheck size={18}/><h4>{m.project}</h4><span className={`runtime-etat ${actif(m) ? "succeeded" : "cancelled"}`}>{m.revoked_at !== null ? "Révoqué" : m.expires_at <= Date.now() / 1000 ? "Expiré" : "Actif"}</span></header><code>{m.id}</code><p>{m.tools.join(", ")}</p><dl><dt>Destinations</dt><dd>{m.destinations.join(", ") || "Actions locales"}</dd><dt>Actions restantes</dt><dd>{m.max_actions - m.used_actions}</dd><dt>Expiration</dt><dd>{date(m.expires_at)}</dd></dl>{m.revoked_at === null && <button type="button" className="bouton runtime-arreter" disabled={!!action} onClick={() => void agir("revoquer-mandat", () => post(`/api/v2/os/mandats/${encodeURIComponent(m.id)}/revoquer`), undefined, "Mandat révoqué.")}>Révoquer ce mandat</button>}</article>)}</div>
            {!mandats.length && !chargement && <div className="runtime-vide"><ShieldCheck size={30}/><h4>Aucun mandat enregistré</h4><p>Un mandat donne à tes agents un périmètre explicite pour agir.</p></div>}
          </>}
          {onglet === "courriel" && <>
            <div className="runtime-intro avec-action"><div><h3>Relier ton compte Gmail</h3><p>Choisis les permissions, puis autorise la connexion dans ton compte Google. Les envois demandent également un mandat avec des destinataires précis.</p></div><button type="button" className="bouton primaire" disabled={!!action} onClick={() => setNouvelOAuth(!nouvelOAuth)}><Plus size={14}/>{nouvelOAuth ? "Fermer le formulaire" : "Configurer Gmail"}</button></div>
            {nouvelOAuth && <form className="runtime-form" aria-label="Configurer Gmail" onSubmit={e => { e.preventDefault(); sauvegarderOAuth(); }}><div className="runtime-grille"><label>Nom de la connexion Gmail<input required maxLength={120} value={oauthNom} onChange={e => setOauthNom(e.target.value)} placeholder="Mon compte Gmail"/></label><label>Identifiant de connexion Gmail<input required pattern="[a-z][a-z0-9_-]{0,39}" maxLength={40} value={oauthId} onChange={e => setOauthId(e.target.value)} placeholder="gmail-personnel"/></label></div>
              <label>Identifiant client Google<input required value={clientId} maxLength={500} onChange={e => setClientId(e.target.value)} autoComplete="off" placeholder="Identifiant de ton application OAuth Google"/></label>
              <label>Variable du secret client, si nécessaire<input value={secretEnv} pattern="[A-Z_][A-Z0-9_]*" maxLength={100} onChange={e => setSecretEnv(e.target.value)} autoComplete="off" placeholder="JARVIS_GOOGLE_CLIENT_SECRET"/></label>
              <label>Adresse expéditrice Gmail<input type="email" value={adresseExpediteur} maxLength={254} onChange={e => setAdresseExpediteur(e.target.value)} autoComplete="off" placeholder="Adresse de ton compte ou alias vérifié"/></label>
              <p className="runtime-aide">L'adresse expéditrice est nécessaire pour les brouillons et les envois ; la lecture seule peut la laisser vide.</p>
              <label>Adresse de retour enregistrée dans Google<input type="url" required value={redirectUri} maxLength={2048} onChange={e => setRedirectUri(e.target.value)}/></label>
              <fieldset className="runtime-outils"><legend>Permissions demandées à Google</legend>{SCOPES.map(s => <label key={s.id}><input type="checkbox" checked={scopes.includes(s.id)} onChange={e => setScopes(avant => e.target.checked ? [...avant, s.id] : avant.filter(x => x !== s.id))}/><span>{s.nom}</span></label>)}</fieldset>
              <p className="runtime-aide"><KeyRound size={15}/><span>Le secret client reste dans sa variable sur le serveur. Les jetons Google sont conservés côté service et ne sont pas transmis aux agents.</span></p><footer><button type="submit" className="bouton primaire" disabled={!oauthNom.trim() || !oauthId.trim() || !clientId.trim() || !scopes.length || !!action}>Enregistrer l'application Gmail</button></footer></form>}
            {lienAutorisation && <div className="runtime-autorisation" role="status"><Mail size={22}/><div><strong>{lienAutorisation.nom} : autorisation en attente</strong><p>Connecte ton compte et accepte les permissions choisies. Reviens ensuite dans ce panneau.</p></div><a className="bouton primaire" href={lienAutorisation.url} target="_blank" rel="noreferrer noopener">Continuer dans Google<ArrowUpRight size={15}/></a></div>}
            <div className="runtime-cartes">{oauth.map(c => <article key={c.id}><header><Mail size={18}/><h4>{c.nom}</h4><span className={`runtime-etat ${c.etat}`}>{ETATS[c.etat] || c.etat}</span></header><p>{c.scopes.map(s => SCOPES.find(x => x.id === s)?.nom || s).join(" · ")}</p><dl><dt>Application Google</dt><dd>{c.client_id_configure ? "Configurée" : "Manquante"}</dd><dt>Expéditeur</dt><dd>{c.adresse_expediteur || "Lecture seule"}</dd><dt>Retour</dt><dd>{c.redirect_uri}</dd>{c.expires_at && <><dt>Expiration</dt><dd>{date(c.expires_at)}</dd></>}</dl><footer>{c.etat !== "revoquee" && <><button type="button" className="bouton primaire" disabled={!!action || !c.client_id_configure} onClick={() => connecterOAuth(c)}>{c.etat === "connectee" ? "Renouveler l'autorisation" : "Autoriser dans Google"}</button><button type="button" className="bouton runtime-arreter" disabled={!!action} onClick={() => void agir("oauth-revoquer", () => post(`/api/v2/oauth/${encodeURIComponent(c.id)}/revoquer`), () => setLienAutorisation(null), "Connexion Gmail révoquée.")}>Révoquer Gmail</button></>}</footer></article>)}</div>
            {!oauth.length && !chargement && <div className="runtime-vide"><Mail size={30}/><h4>Aucun compte Gmail connecté</h4><p>Configure ton application Google pour commencer l'autorisation.</p></div>}
          </>}
        </main>
      </div>}
    </dialog>
  </>;
}
