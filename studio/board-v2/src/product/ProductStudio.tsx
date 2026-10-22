import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, CheckCircle2, ChevronRight, Circle, Code2,
  FileText, Fingerprint, GitBranch, Layers3, LockKeyhole, Plus, RefreshCw, ShieldCheck,
  Sparkles, Users, WandSparkles, X } from "lucide-react";
import type { Source, Inspection } from "../api";
import type { ObjetBoard } from "../types";
import { Avatar } from "../components/Avatar";
import { DialogueMission, type DemandeMission } from "../components/DialogueMission";
import { ProductNav } from "./ProductNav";
import { useStudioNavigation } from "./routing";
import { chargerProduit, dateCourte, requete, verifierAgent, type Agent, type Candidate, type Catalogue, type ProductData, type Verification } from "./api";
import "../styles/product.css";

const ETATS: Record<string, string> = { OPEN: "En cours", SUCCEEDED: "Terminée", FAILED: "À examiner", CANCELLED: "Annulée",
  WAITING_APPROVAL: "À valider", WAITING_PROVIDER: "Fournisseur indisponible", QUEUED: "En attente", RUNNING: "En cours",
  LEASED: "Attribuée", REVIEW: "En vérification", proposee: "Proposition", canari: "Essai limité", retiree: "Retirée", promue: "Version stable", refusee: "Refusée", perimee: "À actualiser" };
const message = (e: unknown) => e instanceof Error ? e.message : "Opération indisponible.";
const status = (s: string) => ETATS[s] || s;

export function ProductStudio({ source }: { source: Source }) {
  const { vue, aller } = useStudioNavigation();
  const [data, setData] = useState<ProductData | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState(false);
  const [intention, setIntention] = useState("");
  const composer = (objectif = "") => { setIntention(objectif); setDialog(true); };
  const [notice, setNotice] = useState("");
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const c = new AbortController(); controller.current = c;
    try { const next = await chargerProduit(source, c.signal); if (!c.signal.aborted) { setData(next); setError(""); } }
    catch (e) { if (!c.signal.aborted) setError(message(e)); }
  }, [source]);
  useEffect(() => {
    void refresh();
    const focus = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", focus);
    let timer: number | undefined;
    const events = source.demo ? null : new EventSource("/api/flux");
    if (events) events.onmessage = () => { if (timer === undefined) timer = window.setTimeout(() => { timer = undefined; if (document.visibilityState === "visible") void refresh(); }, 450); };
    return () => { controller.current?.abort(); events?.close(); window.clearTimeout(timer); document.removeEventListener("visibilitychange", focus); };
  }, [source, refresh]);
  useEffect(() => { setSearch(""); }, [vue]);
  useEffect(() => { if (!notice) return; const id = window.setTimeout(() => setNotice(""), 5000); return () => window.clearTimeout(id); }, [notice]);
  const lancer = async (d: DemandeMission) => {
    const id = await source.lancerMission(d, 180, 160);
    aller("board", { carte: id });
  };
  return <div className="product-app">
    <ProductNav recherche={search} setRecherche={["agents", "missions", "fichiers", "connaissances"].includes(vue) ? setSearch : undefined} />
    <main className="product-main" id="contenu-produit">
      {error && <div className="p-error" role="alert"><span>{error}</span><button className="p-button p-quiet" onClick={refresh}><RefreshCw size={15}/>Réessayer</button></div>}
      {!data && !error && <div className="p-loading" role="status"><span className="p-loader"/>Chargement de ton espace...</div>}
      {data && <>
        {vue === "accueil" && <Accueil data={data} demo={source.demo} composer={composer} />}
        {vue === "agents" && <Atelier catalogue={data.catalogue} demo={source.demo} recherche={search} refresh={refresh} notifier={setNotice} />}
        {vue === "missions" && <Missions source={source} objets={data.board.objets} recherche={search} composer={composer}/>}
        {(vue === "fichiers" || vue === "connaissances") && <Bibliotheque objets={data.board.objets} recherche={search} connaissances={vue === "connaissances"}/>}
        {vue === "configuration" && <Configuration catalogue={data.catalogue} demo={source.demo}/>}
        {vue === "analytique" && <Activite catalogue={data.catalogue} demo={source.demo}/>}
      </>}
    </main>
    <DialogueMission initialObjectif={intention} ouvert={dialog} demo={source.demo} fermer={() => setDialog(false)} lancer={lancer}/>
    {notice && <div className="p-feedback" role="status"><CheckCircle2 size={18}/>{notice}</div>}
  </div>;
}

function Accueil({ data, demo, composer }: { data: ProductData; demo: boolean; composer: (objectif?: string) => void }) {
  const { aller } = useStudioNavigation();
  const agents = data.catalogue.agents.slice(0, 4);
  const active = data.catalogue.execution.executants.filter(x => x.actif && !x.revoque).length;
  const choices = [
    { icon: BookOpen, title: "Comprendre un sujet", text: "Rassembler le contexte, poser les bonnes questions.", prompt: "Je souhaite comprendre un sujet. Voici mon objectif : " },
    { icon: Code2, title: "Concevoir un produit", text: "Transformer une idee en brief d'implementation.", prompt: "Je souhaite concevoir un produit. Probleme utilisateur : " },
    { icon: FileText, title: "Préparer une candidature", text: "Comparer une offre a un profil vérifié.", prompt: "Préparer une candidature sans rien envoyer. Offre et profil : " },
  ];
  return <>
    <section className="p-hero">
      <div className="p-hero-copy">
        <div className="p-availability"><span className={active ? "p-dot live" : "p-dot"}/>{demo ? "Explore un espace de démonstration" : active ? `${active} executant${active > 1 ? "s" : ""} disponible${active > 1 ? "s" : ""}` : "Ton espace. Tes outils. Ton rythme."}</div>
        <h1>Une idée.<br/>Toute une équipe.</h1>
        <p className="p-lead">Donne une direction. Rassemble tes ressources.<br/>Construis avec des agents que tu comprends et que tu peux améliorer.</p>
        <div className="p-hero-actions"><button className="p-button p-primary" onClick={() => composer()}><Sparkles size={18}/>Cadrer une mission<ArrowUpRight size={17}/></button>
          <button className="p-button p-quiet" onClick={() => aller("board")}>Ouvrir mon Board<ArrowRight size={17}/></button></div>
        <div className="p-trust"><ShieldCheck size={15}/>Actions sensibles sous ton contrôle<span/><span>Claude + Codex</span></div>
      </div>
      <div className="p-formation" aria-label="Aperçu des rôles de ton équipe">
        <div className="p-formation-grid"/>
        <div className="p-orbit p-orbit-one"/><div className="p-orbit p-orbit-two"/>
        <div className="p-core"><img src="/v2/jarvis-mark.svg" alt=""/><strong>Jarvis</strong><span>Tu donnes la direction</span></div>
        {agents.map((a, i) => <button key={a.nom} className={`p-orbit-agent orbit-${i}`} onClick={() => aller("agents", { agent: a.nom })}>
          <Avatar id={a.nom} role={a.nom} taille={42} titre={a.titre}/><span><strong>{a.court}</strong><small>{a.equipe}</small></span><ArrowUpRight size={15}/></button>)}
        <div className="p-formation-caption"><GitBranch size={14}/>Des rôles spécialisés, pas des sessions permanentes</div>
      </div>
    </section>
    <section className="p-start">
      <div className="p-section-title"><div><h2>Par quoi commence-t-on ?</h2><p>Choisis une intention. Jarvis prépare le cadrage ; aucune action externe n'est déclenchée.</p></div><span className="p-shortcut">À ton rythme</span></div>
      <div className="p-intents">{choices.map(({ icon: Icon, title, text, prompt }) => <button key={title} onClick={() => composer(prompt)}>
        <span className="p-intent-icon"><Icon size={22}/></span><h3>{title}</h3><p>{text}</p><ArrowUpRight className="p-corner" size={19}/></button>)}</div>
    </section>
    <section className="p-workspace-row"><div className="p-workspace-card"><span className="p-workspace-icon"><Layers3 size={25}/></span><div><h3>Ton espace de travail visuel</h3><p>{data.board.objets.length} ressources sur le Board. Images, liens, notes et missions au même endroit.</p></div><button className="p-button p-quiet" onClick={() => aller("board")}>Reprendre<ArrowRight size={16}/></button></div>
      <button className="p-workspace-card p-lab-link" onClick={() => aller("agents")}><span className="p-workspace-icon"><WandSparkles size={24}/></span><div><h3>Fais évoluer ton équipe</h3><p>{data.catalogue.agents.length} roles à découvrir et améliorer.</p></div><ArrowUpRight size={20}/></button></section>
  </>;
}

function Atelier({ catalogue, demo, recherche, refresh, notifier }: { catalogue: Catalogue; demo: boolean; recherche: string; refresh: () => Promise<void>; notifier: (text: string) => void }) {
  const initial = new URLSearchParams(location.search).get("agent");
  const [selected, setSelected] = useState<string | null>(initial);
  const [team, setTeam] = useState("Tous");
  const teams = ["Tous", ...new Set(catalogue.agents.map(a => a.equipe))];
  const filtered = useMemo(() => catalogue.agents.filter(a => (team === "Tous" || a.equipe === team) &&
    `${a.titre} ${a.equipe} ${a.resume}`.toLowerCase().includes(recherche.toLowerCase())), [catalogue.agents, team, recherche]);
  const current = catalogue.agents.find(a => a.nom === selected);
  return <section className="p-page">
    <div className="p-page-heading"><div><div className="p-breadcrumb">Ton équipe / Atelier</div><h1>De bons agents.<br/><span>Encore meilleurs avec toi.</span></h1><p>Explore leurs spécialités. Affine leurs consignes. Compare avant d'adopter.</p></div><span className="p-count"><Users size={18}/>{catalogue.agents.length} rôles disponibles</span></div>
    <div className="p-tabs" role="group" aria-label="Equipes">{teams.map(t => <button key={t} aria-pressed={team === t} onClick={() => setTeam(t)}>{t}</button>)}</div>
    <div className={`p-agent-workspace ${current ? "with-editor" : ""}`}>
      <div className="p-agent-grid">{filtered.map(a => <button key={a.nom} className={`p-agent-card ${a.nom === selected ? "selected" : ""}`} onClick={() => setSelected(a.nom)} aria-pressed={a.nom === selected}>
        <div className="p-agent-top"><Avatar id={a.nom} role={a.nom} taille={68} titre={a.titre}/><span className="p-provider">{a.fournisseur === "auto" ? "Claude / Codex" : a.fournisseur === "claude" ? "Claude Code" : "Codex"}</span></div>
        <span className="p-agent-team">{a.equipe}</span><h2>{a.titre}</h2><p>{a.resume || "Un rôle spécialisé de ton équipe Jarvis."}</p>
        <div className="p-agent-footer"><span><LockKeyhole size={13}/>Niveau {a.niveau}</span><span>{a.candidats.some(c => c.statut === "canari") ? "Essai en cours" : "Découvrir"}<ChevronRight size={15}/></span></div>
      </button>)}{!filtered.length && <EtatVide titre="Aucun agent dans cette sélection" texte="Essaie une autre équipe ou un autre mot-clé."/>}</div>
      {current && <AgentEditor key={`${current.nom}:${current.empreinte}`} agent={current} demo={demo} fermer={() => setSelected(null)} refresh={refresh} notifier={notifier}/>}
    </div>
    <div className="p-footnote"><ShieldCheck size={17}/><span>Un rôle n'est pas un agent en exécution. L'atelier ne change ni ses permissions ni son fournisseur. Les essais utilisent le mécanisme de canari existant.</span></div>
  </section>;
}

function AgentEditor({ agent, demo, fermer, refresh, notifier }: { agent: Agent; demo: boolean; fermer: () => void; refresh: () => Promise<void>; notifier: (text: string) => void }) {
  const { lireBrouillon, garderBrouillon, retirerBrouillon } = useStudioNavigation();
  const restored = useRef(lireBrouillon(agent.nom));
  const [text, setText] = useState(restored.current?.texte ?? agent.corps);
  const [why, setWhy] = useState(restored.current?.pourquoi ?? "");
  const draftBase = restored.current?.base ?? agent.empreinte;
  const remember = (texte: string, pourquoi: string) => {
    if (texte !== agent.corps || pourquoi) garderBrouillon(agent.nom, { texte, pourquoi, base: draftBase });
    else retirerBrouillon(agent.nom);
  };
  const [verification, setVerification] = useState<Verification | null>(null);
  const [verifiedText, setVerifiedText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const dirty = text !== agent.corps;
  const verify = async () => { setBusy(true); setError(""); try { const v = await verifierAgent({ ...agent, empreinte: draftBase }, text, demo); setVerification(v); setVerifiedText(text); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const propose = async () => {
    setBusy(true); setError("");
    try {
      if (demo) { notifier("Démonstration : aucun agent reel n'a été modifié."); return; }
      await requete(`/api/v2/atelier/agents/${encodeURIComponent(agent.nom)}/proposer`, { corps: text, pourquoi: why, base: draftBase });
      retirerBrouillon(agent.nom); setText(agent.corps); setWhy("");
      await refresh(); notifier("Proposition enregistrée. La version stable reste inchangée."); setVerification(null);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  return <aside className="p-editor" aria-label={`Améliorer ${agent.titre}`}>
    <header><div><span className="p-agent-team">Atelier personnel</span><h2>{agent.court}</h2></div><button className="p-icon-button" onClick={fermer} aria-label="Fermer l'editeur"><X size={19}/></button></header>
    <div className="p-editor-content"><div className="p-editor-tip"><WandSparkles size={19}/><p>Décris ce qu'un excellent résultat doit contenir. Conserve les règles existantes ; ajoute des attentes concrètes.</p></div>
      <p className="p-draft-hint">Brouillon conservé pendant la navigation. Non partagé et non activé.</p>
      <label htmlFor="agent-brief">Consignes de travail <span>{text.length.toLocaleString("fr-CA")} / 24 000</span></label>
      <textarea id="agent-brief" maxLength={24000} value={text} onChange={e => { setText(e.target.value); remember(e.target.value, why); setVerification(null); }} spellCheck={false}/>
      <label htmlFor="agent-why">Qu'est-ce que cette version améliore ?</label>
      <input id="agent-why" maxLength={800} value={why} onChange={e => { setWhy(e.target.value); remember(text, e.target.value); }} placeholder="Ex. Exiger les sources et tester les cas limites"/>
      <div className="p-editor-actions"><button className="p-button p-quiet" disabled={!dirty || busy} onClick={() => { setText(agent.corps); setWhy(""); retirerBrouillon(agent.nom); restored.current = undefined; setVerification(null); }}>Rétablir</button><button className="p-button p-primary" disabled={busy || !dirty || text.trim().length < 80} onClick={verify}><ShieldCheck size={16}/>{busy ? "Vérification..." : "Vérifier les consignes"}</button></div>
      {error && <div className="p-error" role="alert">{error}</div>}
      {verification && verifiedText === text && <section className="p-verification"><h3>{verification.valide ? <CheckCircle2 size={18}/> : <ShieldCheck size={18}/>}{verification.valide ? "Règles structurelles respectées" : "Points à corriger"}</h3>
        <p>Ce contrôle n'évalue pas l'intelligence de l'agent et ne consomme aucun appel IA.</p>
        {verification.raisons.map(r => <p key={r} className="p-warning">{r}</p>)}
        <details><summary>Comparer avec la version stable</summary><pre>{verification.diff}</pre></details>
        <button className="p-button p-primary" onClick={propose} disabled={!verification.valide || why.trim().length < 8 || busy}><GitBranch size={16}/>Enregistrer la proposition</button></section>}
      <section className="p-version-list"><h3><GitBranch size={17}/>Versions et essais</h3>{agent.candidats.length ? [...agent.candidats].reverse().map(c => <button key={c.id} className="p-version" onClick={() => setCandidate(c)}><span><strong>{c.id}</strong><small>{c.pourquoi}</small></span><span className="p-status">{status(c.statut)}</span></button>) : <p>Aucune proposition. La version stable est utilisée.</p>}</section>
      <div className="p-editor-proof"><Fingerprint size={14}/>Version stable {agent.empreinte}</div>
    </div>
    {candidate && <CandidateReview candidat={candidate} demo={demo} fermer={() => setCandidate(null)} refresh={refresh} notifier={notifier}/>}
  </aside>;
}

function CandidateReview({ candidat, demo, fermer, refresh, notifier }: { candidat: Candidate; demo: boolean; fermer: () => void; refresh: () => Promise<void>; notifier: (text: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<{ candidat: Candidate; diff: string } | null>(null);
  const [error, setError] = useState(""); const [consent, setConsent] = useState(false); const [busy, setBusy] = useState(false);
  useEffect(() => { ref.current?.showModal(); let alive = true;
    if (!demo) requete<{ candidat: Candidate; diff: string }>(`/api/v2/atelier/candidats/${candidat.id}`).then(d => { if (alive) setDetail(d); }).catch(e => { if (alive) setError(message(e)); });
    return () => { alive = false; }; }, [candidat.id, demo]);
  const decide = async (action: string) => {
    if (!detail) return; setBusy(true); setError("");
    try { await requete(`/api/v2/atelier/candidats/${candidat.id}/decider`, { action, empreinte: detail.candidat.empreinte });
      await refresh(); notifier(action === "essayer" ? "Essai limité autorise. Les prochaines tâches eligibles utiliseront le candidat." : "Candidat retiré. Retour à la version stable."); fermer(); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  return <dialog className="p-review-dialog" ref={ref} onCancel={fermer} aria-labelledby="review-title"><header><div><span className="p-breadcrumb">Comparaison avant décision</span><h2 id="review-title">{candidat.id}</h2></div><button className="p-icon-button" onClick={fermer} aria-label="Fermer"><X size={20}/></button></header>
    <p>Un essai ne remplace pas la version stable. La promotion définitive reste une décision séparée au terminal.</p>
    {error && <div role="alert" className="p-error">{error}</div>}{detail ? <pre>{detail.diff}</pre> : <p>Chargement de la comparaison...</p>}
    {detail?.candidat.statut === "proposee" && <><label className="p-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>J'ai relu le changement et j'autorise un essai sur une partie des prochaines tâches.</label><button className="p-button p-primary" disabled={!consent || busy} onClick={() => decide("essayer")}>Autoriser l'essai limité</button></>}
    {detail && ["proposee", "canari"].includes(detail.candidat.statut) && <button className="p-button p-quiet" disabled={busy} onClick={() => decide("retirer")}>Retirer le candidat</button>}
  </dialog>;
}

function Missions({ source, objets, recherche, composer }: { source: Source; objets: ObjetBoard[]; recherche: string; composer: () => void }) {
  const [inspection, setInspection] = useState<Inspection | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const missions = objets.filter(o => o.mission && `${o.mission.objectif} ${o.mission.statut}`.toLowerCase().includes(recherche.toLowerCase()));
  const inspect = async (id: string) => { setBusy(true); setError(""); try { setInspection(await source.inspection(id)); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  return <section className="p-page"><div className="p-page-heading"><div><div className="p-breadcrumb">Du contexte au résultat</div><h1>Le travail, en clair.</h1><p>Les missions reliées à ton Board. Chaque statut vient du moteur d'exécution.</p></div><button className="p-button p-primary" onClick={() => composer()}><Plus size={17}/>Cadrer une mission</button></div>
    <div className="p-mission-layout"><div className="p-mission-list">{missions.map(o => <button key={o.id} className="p-mission-row" disabled={busy} onClick={() => inspect(o.mission!.id)}>
      <span className="p-mission-symbol">{o.mission!.statut === "SUCCEEDED" ? <CheckCircle2 size={23}/> : <Circle size={23}/>}</span>
      <span className="p-mission-summary"><strong>{o.mission!.objectif}</strong><small>{o.mission!.faites} / {o.mission!.total} tâches terminées<span>{dateCourte(o.mission!.cree)}</span></small></span>
      <span className="p-status">{status(o.mission!.statut)}</span><ChevronRight size={18}/></button>)}
      {!missions.length && <EtatVide titre="La prochaine mission commence avec toi" texte="Rassemble quelques ressources sur le Board, puis prépare un premier objectif."/>}</div>
      <aside className="p-mission-inspector"><h2>Les preuves, pas les promesses.</h2>{error && <p role="alert">{error}</p>}{busy ? <p>Chargement...</p> : inspection ? <><h3>{inspection.objectif}</h3>{inspection.taches.map(t => <div key={t.id} className="p-task"><span className="p-status">{status(t.statut)}</span><p>{t.libelle || t.type}</p><small>{t.raison || `Niveau ${t.niveau}`}</small></div>)}{inspection.artefacts.map(a => <details key={a.id}><summary>{a.factice ? "Resultat factice" : "Resultat"} / {a.fournisseur}</summary><pre>{a.contenu}</pre></details>)}</> : <p>Selectionne une mission pour retrouver ses etapes, les interruptions et les resultats verifies.</p>}</aside></div>
  </section>;
}

function Bibliotheque({ objets, recherche, connaissances }: { objets: ObjetBoard[]; recherche: string; connaissances: boolean }) {
  const { aller } = useStudioNavigation();
  const types = connaissances ? ["note", "texte", "lien", "document"] : ["image", "capture", "audio", "video", "pdf", "document"];
  const filtered = objets.filter(o => types.includes(o.type) && `${o.meta.titre} ${o.contenu} ${o.asset?.nom}`.toLowerCase().includes(recherche.toLowerCase()));
  return <section className="p-page"><div className="p-page-heading"><div><div className="p-breadcrumb">Les ressources de ton espace</div><h1>{connaissances ? "Le contexte fait la difference." : "Chaque ressource a sa place."}</h1><p>{connaissances ? "Notes et liens du Board. Ce repertoire n'est pas encore un moteur RAG." : "Retrouve tes medias et documents sans parcourir tout le canvas."}</p></div><button className="p-button p-primary" onClick={() => aller("board")}><Plus size={17}/>Ajouter sur le Board</button></div>
    <div className="p-library">{filtered.map(o => <button key={o.id} className="p-resource" onClick={() => aller("board", { carte: o.id })}>
      <div className={`p-resource-preview kind-${o.type}`}>{o.type === "image" && (o.asset?.url || o.meta.demo_src) ? <img src={o.asset?.url || o.meta.demo_src} alt="" loading="lazy"/> : <FileText size={38}/>}</div>
      <div><small>{o.type}</small><h3>{o.meta.titre || o.asset?.nom || o.contenu.slice(0, 70) || "Ressource"}</h3><p>{o.meta.description || o.contenu.slice(0, 120) || "Ouvrir dans le Board"}</p></div><ArrowUpRight size={16}/></button>)}</div>
    {!filtered.length && <EtatVide titre="Tout commence par une ressource" texte="Colle une note, un lien ou un fichier dans le Board. Tu le retrouveras ici."/>}
  </section>;
}

function Configuration({ catalogue, demo }: { catalogue: Catalogue; demo: boolean }) {
  return <section className="p-page p-settings"><div className="p-page-heading"><div><div className="p-breadcrumb">Comprendre avant de modifier</div><h1>De la puissance.<br/>Des limites claires.</h1><p>Cette vue expose la configuration. Elle ne change pas silencieusement tes autorisations.</p></div><ShieldCheck size={40} className="p-heading-icon"/></div>
    <div className="p-settings-grid"><section className="p-panel"><h2>Les moteurs de ton équipe</h2>{["claude", "codex"].map(f => { const c = catalogue.execution.connexions.find(c => c.fournisseur === f);
      return <div className="p-provider-row" key={f}><div className={`p-provider-mark ${f}`}>{f === "claude" ? "CL" : "CX"}</div><div><h3>{f === "claude" ? "Claude Code" : "OpenAI Codex"}</h3><p>{demo ? "Etat fictif non mesure" : c ? `${c.mode_auth} / ${c.disponible ? "connexion declaree disponible" : c.raison || "indisponible"}` : "Connexion a declarer sur ton poste"}</p></div><LockKeyhole size={16}/></div>; })}
      <p className="p-caption">Les abonnements restent les moteurs par defaut. Aucun basculement payant n'est ajoute par ce lot.</p></section>
    <section className="p-panel"><h2>Une autonomie explicable</h2><div className="p-setting-line"><span>Plafond d'agents</span><strong>{catalogue.politique.max_agents}</strong></div><div className="p-setting-line"><span>Validation des plans</span><strong>{catalogue.politique.validation_plans}</strong></div><div className="p-setting-line"><span>Arret d'urgence du moteur</span><strong>{catalogue.execution.arret_urgence ? "Active" : "Inactif"}</strong></div><p className="p-caption">La disponibilite d'un abonnement ne garantit ni sa capacite restante ni l'autorisation commerciale d'un SaaS.</p></section>
    <section className="p-panel p-bridge"><span className="p-status">Extension preparee / non branchee au routeur</span><h2>Ton futur modèle open source.</h2><p>Un service separe, local et desactive par defaut. Il ne telecharge aucun modele et ne recoit aucune mission automatiquement.</p><code>services/model_bridge</code><div className="p-caption"><LockKeyhole size={15}/>Activation explicite, jeton dedie, limites de charge et moteur compatible local.</div></section>
    <section className="p-panel"><h2>Les executants</h2>{catalogue.execution.executants.length ? catalogue.execution.executants.map(r => <div className="p-setting-line" key={r.id}><span>{r.nom}</span><span className="p-status">{r.revoque ? "Revoque" : r.actif ? "Recent" : "Hors ligne"}</span></div>) : <p>Aucun executant enrole. L'interface fonctionne, mais elle ne peut pas executer de mission seule.</p>}<code>jarvis mission enroler --fournisseurs claude,codex</code></section></div>
  </section>;
}

function Activite({ catalogue, demo }: { catalogue: Catalogue; demo: boolean }) {
  const tasks = catalogue.execution.taches; const total = Object.values(tasks).reduce((a, b) => a + b, 0);
  return <section className="p-page"><div className="p-page-heading"><div><div className="p-breadcrumb">Observations du moteur</div><h1>Ce qui avance.<br/>Ce qui attend.</h1><p>{demo ? "Mode demo : aucune metrique d'execution reelle." : "Repartition actuelle des taches du moteur. Aucun taux de reussite invente."}</p></div><button className="p-button p-quiet" onClick={() => location.reload()}><RefreshCw size={16}/>Actualiser</button></div>
    <section className="p-panel p-activity-panel"><div className="p-activity-summary"><span>{total}</span><div><h2>Tâches enregistrées</h2><p>Photographie de l'état actuel, pas une mesure historique de performance.</p></div></div>{Object.entries(tasks).map(([name, n]) => <div className="p-distribution" key={name}><span>{status(name)}</span><div><i style={{ width: `${total ? n / total * 100 : 0}%` }}/></div><strong>{n}</strong></div>)}{!total && <EtatVide titre="Pas encore de tâches mesurées" texte="Une fois une mission exécutée, son état apparaîtra ici."/>}</section>
  </section>;
}

function EtatVide({ titre, texte }: { titre: string; texte: string }) {
  return <div className="p-empty"><Layers3 size={29}/><h3>{titre}</h3><p>{texte}</p></div>;
}
