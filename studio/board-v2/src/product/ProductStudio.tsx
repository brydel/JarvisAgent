import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, RefreshCw, X } from "lucide-react";
import type { Source, Inspection } from "../api";
import type { ObjetBoard, StyleLien } from "../types";
import { Avatar } from "../components/Avatar";
import { DialogueMission, type DemandeMission } from "../components/DialogueMission";
import { ProductNav } from "./ProductNav";
import { useStudioNavigation } from "./routing";
import { chargerProduit, dateCourte, requete, verifierAgent, type Agent, type Candidate, type Catalogue, type ProductData, type Verification } from "./api";
import "../styles/product.css";

const ETATS: Record<string, string> = { OPEN: "En cours", SUCCEEDED: "Terminée", FAILED: "À examiner", CANCELLED: "Annulée",
  WAITING_APPROVAL: "À valider", WAITING_PROVIDER: "Fournisseur indisponible", QUEUED: "En attente", RUNNING: "En cours",
  LEASED: "Attribuée", REVIEW: "En vérification", proposee: "Proposition", canari: "Essai limité", retiree: "Retirée", promue: "Version stable", refusee: "Refusée", perimee: "À actualiser" };
const message = (e: unknown) => e instanceof Error ? e.message : "Opération indisponible";
const status = (s: string) => ETATS[s] || s;
/** Le point d'un statut porte son sens : vert = abouti, ambre = t'attend, rouge = à examiner, encre = en cours, gris = au repos. */
const TONS: Record<string, string> = { SUCCEEDED: "ok", promue: "ok", FAILED: "echec", refusee: "echec", WAITING_APPROVAL: "attente", WAITING_PROVIDER: "attente",
  perimee: "attente", OPEN: "cours", RUNNING: "cours", LEASED: "cours", REVIEW: "cours", canari: "cours" };
function Statut({ etat, children }: { etat?: string; children?: string }) {
  return <span className="p-status" data-ton={etat ? TONS[etat] : undefined}>{children ?? status(etat ?? "")}</span>;
}
const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? "s" : ""}`;

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
    const events = source.demo ? null : new EventSource("/api/flux?apres=fin");
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
      {error && <div className="p-error" role="alert"><span>{error}</span><button className="p-button p-quiet" onClick={refresh}><RefreshCw size={16} strokeWidth={1.5}/>Réessayer</button></div>}
      {!data && !error && <div className="p-loading" role="status">Chargement</div>}
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
    {notice && <div className="p-feedback" role="status"><CheckCircle2 size={16} strokeWidth={1.5}/>{notice}</div>}
  </div>;
}

function Accueil({ data, demo, composer }: { data: ProductData; demo: boolean; composer: (objectif?: string) => void }) {
  const { aller } = useStudioNavigation();
  const agents = data.catalogue.agents.slice(0, 4);
  const active = data.catalogue.execution.executants.filter(x => x.actif && !x.revoque).length;
  const cartes = data.board.objets.length;
  const relations = data.board.liens.length;
  const modifie = Math.max(0, ...data.board.objets.map(o => o.maj));
  const choices = [
    { title: "Comprendre un sujet", text: "Rassembler le contexte et poser les bonnes questions avant de lancer quoi que ce soit", prompt: "Je souhaite comprendre un sujet. Voici mon objectif : " },
    { title: "Concevoir un produit", text: "Transformer une idée en brief d'implémentation, tâche par tâche", prompt: "Je souhaite concevoir un produit. Problème utilisateur : " },
    { title: "Préparer une candidature", text: "Comparer une offre à un profil vérifié, sans rien envoyer", prompt: "Préparer une candidature sans rien envoyer. Offre et profil : " },
  ];
  return <>
    <section className="p-hero">
      <div className="p-hero-copy">
        <h1>Cadre une mission sur le Board, tes agents la mènent</h1>
        <p className="p-lead">Rassemble notes, liens et fichiers sur le canevas, relie-les par des flèches, puis confie la mission à des rôles que tu peux lire et corriger. Envoyer, publier ou modifier tes fichiers attend toujours ton accord, avec Claude Code comme avec Codex.</p>
        <div className="p-hero-actions"><button className="p-button p-primary" onClick={() => composer()}>Cadrer une mission</button>
          <button className="p-button p-quiet" onClick={() => aller("board")}>Ouvrir mon Board</button></div>
      </div>
      <div className="p-formation" aria-label="Plan de situation de ton Board et rôles de ton équipe">
        <div className="p-plan-tete"><strong>Ton Board</strong><span className="tab-num">{pluriel(cartes, "carte")} · {pluriel(relations, "relation")}</span></div>
        <PlanBoard board={data.board} ouvrir={() => aller("board")}/>
        <div className="p-plan-pied">
          <p className="credit">{demo ? "Espace de démonstration" : active ? `${pluriel(active, "exécutant")} disponible${active > 1 ? "s" : ""}` : "Aucun exécutant actif"}
            <span aria-hidden>·</span><span>{demo ? "données fictives" : modifie ? `modifié le ${dateCourte(modifie)}` : "aucune carte"}</span></p>
          <Legende board={data.board}/>
        </div>
        <p className="p-formation-caption">Des rôles spécialisés, pas des sessions permanentes</p>
        <ul className="p-roles">{agents.map((a) => <li key={a.nom}><button className="p-orbit-agent" onClick={() => aller("agents", { agent: a.nom })}>
          <Avatar id={a.nom} role={a.nom} taille={32} titre={a.titre}/><span><strong>{a.court}</strong><small>{a.equipe}</small></span></button></li>)}</ul>
      </div>
    </section>
    <section className="p-start">
      <div className="p-section-title"><div><h2>Par quoi commence-t-on ?</h2><p>Choisis une intention. Jarvis prépare le cadrage ; aucune action externe n'est déclenchée.</p></div></div>
      <div className="p-intents">{choices.map(({ title, text, prompt }) => <button key={title} onClick={() => composer(prompt)}>
        <h3>{title}</h3><p>{text}</p></button>)}</div>
    </section>
    <section className="p-workspace-row"><div className="p-workspace-card"><div><h3>Ton Board</h3><p>{pluriel(cartes, "carte")} sur le canevas : images, liens, notes et missions au même endroit</p></div><button className="p-button p-quiet" onClick={() => aller("board")}>Reprendre</button></div>
      <button className="p-workspace-card p-lab-link" onClick={() => aller("agents")}><div><h3>L'atelier des agents</h3><p>{pluriel(data.catalogue.agents.length, "rôle")} à lire, corriger et comparer avant d'adopter</p></div></button></section>
  </>;
}

const TYPES_PLAN: Record<string, string> = { note: "Note", texte: "Texte", lien: "Lien", image: "Image", video: "Vidéo", audio: "Audio", pdf: "PDF", document: "Document", capture: "Capture",
  mission: "Mission", agents: "Équipe", dossier: "Dossier", plan: "Plan", tache: "Tâche", adhesif: "Adhésif", cadre: "Cadre" };
/** Même couleur et même tracé que sur le Board (edges/RelationEdge) : le type d'une relation se lit aussi sans la couleur. */
const TRAITS_PLAN: Record<StyleLien, { couleur: string; tirets?: string; nom: string }> = {
  defaut: { couleur: "var(--edge-default)", nom: "Relation simple" },
  inspire: { couleur: "var(--edge-inspire)", tirets: "1 5", nom: "Inspire" },
  alimente: { couleur: "var(--edge-alimente)", nom: "Alimente" },
  utilise: { couleur: "var(--edge-utilise)", tirets: "5 5", nom: "Utilisé par" },
  depend: { couleur: "var(--edge-depend)", tirets: "9 4 2 4", nom: "Dépend de" },
};
const ORDRE_TRAITS: StyleLien[] = ["alimente", "inspire", "depend", "utilise", "defaut"];

/** Plan de situation du Board : les vraies cartes à leur vraie place, les relations dans la couleur et le tracé de leur
 *  type, la jauge de la mission. Les cartes sont posées en pourcentage : le texte garde sa taille à toutes les largeurs. */
function PlanBoard({ board, ouvrir }: { board: ProductData["board"]; ouvrir: () => void }) {
  const cartes = board.objets.filter(o => TYPES_PLAN[o.type]).sort((a, b) => a.z - b.z).slice(0, 60);
  if (!cartes.length) return <button className="p-plan p-plan-vide" onClick={ouvrir}>Aucune carte sur le Board</button>;
  const marge = 24;
  let x0 = Math.min(...cartes.map(o => o.x)) - marge, y0 = Math.min(...cartes.map(o => o.y)) - marge;
  let l = Math.max(...cartes.map(o => o.x + o.largeur)) + marge - x0, h = Math.max(...cartes.map(o => o.y + o.hauteur)) + marge - y0;
  // proportions bornées : un Board très large ou très haut reste lisible, centré dans son cadre
  const ratio = Math.min(2.2, Math.max(1.3, l / h));
  if (l / h < ratio) { x0 -= (h * ratio - l) / 2; l = h * ratio; } else { y0 -= (l / ratio - h) / 2; h = l / ratio; }
  const parId = new Map(cartes.map(o => [o.id, o]));
  const pct = (v: number, total: number) => `${(v / total * 100).toFixed(3)}%`;
  return <button className="p-plan" style={{ aspectRatio: `${l.toFixed(0)} / ${h.toFixed(0)}` }} onClick={ouvrir}
    aria-label={`Ouvrir le Board : ${pluriel(cartes.length, "carte")}, ${pluriel(board.liens.length, "relation")}`}>
    <svg viewBox={`${x0} ${y0} ${l} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      {board.liens.map(lien => {
        const s = parId.get(lien.source_id), c = parId.get(lien.cible_id);
        if (!s || !c) return null;
        const t = TRAITS_PLAN[lien.style] ?? TRAITS_PLAN.defaut;
        return <line key={lien.id} x1={s.x + s.largeur / 2} y1={s.y + s.hauteur / 2} x2={c.x + c.largeur / 2} y2={c.y + c.hauteur / 2}
          stroke={t.couleur} strokeDasharray={t.tirets} strokeLinecap={t.tirets ? "round" : undefined}/>;
      })}
    </svg>
    {cartes.map(o => {
      const image = o.type === "image" ? o.asset?.url || o.meta.demo_src : undefined;
      const nom = String(o.meta.titre || o.asset?.nom || o.contenu || "").slice(0, 90);
      return <span key={o.id} className={`p-plan-carte type-${o.type}${image ? " a-image" : ""}`} aria-hidden="true"
        style={{ left: pct(o.x - x0, l), top: pct(o.y - y0, h), width: pct(o.largeur, l), height: pct(o.hauteur, h) }}>
        {image && <img src={image} alt="" loading="lazy"/>}
        <span className="p-plan-type">{TYPES_PLAN[o.type]}{o.priorite ? ` · ${o.priorite}` : ""}</span>
        {nom && <span className="p-plan-nom">{nom}</span>}
        {o.type === "mission" && o.mission && <span className="p-plan-avancement">
          <span className="p-plan-jauge"><i style={{ width: `${Math.max(0, Math.min(100, o.mission.progression))}%` }}/></span>
          <span className="tab-num">{o.mission.faites} / {o.mission.total}</span></span>}
      </span>;
    })}
  </button>;
}

/** Légende du plan : seulement les types de relation présents sur ce Board. */
function Legende({ board }: { board: ProductData["board"] }) {
  const presents = ORDRE_TRAITS.filter(s => board.liens.some(lien => lien.style === s));
  if (!presents.length) return null;
  return <ul className="p-plan-legende" aria-label="Types de relation">{presents.map(s => <li key={s}>
    <svg width="20" height="8" viewBox="0 0 20 8" aria-hidden="true"><line x1="1" y1="4" x2="19" y2="4" stroke={TRAITS_PLAN[s].couleur} strokeDasharray={TRAITS_PLAN[s].tirets} strokeLinecap={TRAITS_PLAN[s].tirets ? "round" : undefined}/></svg>
    {TRAITS_PLAN[s].nom}</li>)}</ul>;
}

const MOTEURS: Record<string, string> = { auto: "Claude / Codex", claude: "Claude Code", codex: "Codex" };

function Atelier({ catalogue, demo, recherche, refresh, notifier }: { catalogue: Catalogue; demo: boolean; recherche: string; refresh: () => Promise<void>; notifier: (text: string) => void }) {
  const initial = new URLSearchParams(location.search).get("agent");
  const [selected, setSelected] = useState<string | null>(initial);
  const [team, setTeam] = useState("Tous");
  const teams = ["Tous", ...new Set(catalogue.agents.map(a => a.equipe))];
  const filtered = useMemo(() => catalogue.agents.filter(a => (team === "Tous" || a.equipe === team) &&
    `${a.titre} ${a.equipe} ${a.resume}`.toLowerCase().includes(recherche.toLowerCase())), [catalogue.agents, team, recherche]);
  const current = catalogue.agents.find(a => a.nom === selected);
  return <section className="p-page">
    <div className="p-page-heading"><div><h1>Agents</h1><p>Lis les consignes de chaque rôle, corrige-les et compare avant d'adopter</p></div><span className="p-count tab-num">{pluriel(catalogue.agents.length, "rôle")}</span></div>
    <div className="p-tabs" role="group" aria-label="Équipes">{teams.map(t => <button key={t} aria-pressed={team === t} onClick={() => setTeam(t)}>{t}</button>)}</div>
    <div className={`p-agent-workspace ${current ? "with-editor" : ""}`}>
      <div className="p-agent-grid">{filtered.map(a => <button key={a.nom} className={`p-agent-card ${a.nom === selected ? "selected" : ""}`} onClick={() => setSelected(a.nom)} aria-pressed={a.nom === selected}>
        <Avatar id={a.nom} role={a.nom} taille={40} titre={a.titre}/>
        <span className="p-agent-nom"><h2>{a.titre}</h2><p>{a.resume || "Un rôle spécialisé de ton équipe Jarvis"}</p></span>
        <span className="p-agent-meta"><span className="p-agent-team">{a.equipe}</span><span className="p-provider">{MOTEURS[a.fournisseur] ?? "Codex"}</span>
          <span className="p-agent-niveau tab-num">Niveau {a.niveau}</span>{a.candidats.some(c => c.statut === "canari") && <Statut etat="canari">Essai en cours</Statut>}</span>
      </button>)}{!filtered.length && <EtatVide titre="Aucun agent dans cette sélection" texte="Essaie une autre équipe ou un autre mot-clé"/>}</div>
      {current && <AgentEditor key={`${current.nom}:${current.empreinte}`} agent={current} demo={demo} fermer={() => setSelected(null)} refresh={refresh} notifier={notifier}/>}
    </div>
    <p className="p-footnote">Un rôle n'est pas un agent en exécution. L'atelier ne change ni ses permissions ni son fournisseur. Un essai ne porte que sur une partie des prochaines tâches.</p>
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
      if (demo) { notifier("Démonstration : aucun agent réel n'a été modifié"); return; }
      await requete(`/api/v2/atelier/agents/${encodeURIComponent(agent.nom)}/proposer`, { corps: text, pourquoi: why, base: draftBase });
      retirerBrouillon(agent.nom); setText(agent.corps); setWhy("");
      await refresh(); notifier("Proposition enregistrée. La version stable reste inchangée."); setVerification(null);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  return <aside className="p-editor" aria-label={`Améliorer ${agent.titre}`}>
    <header><div><span className="p-agent-team">Atelier personnel</span><h2>{agent.court}</h2></div><button className="p-icon-button" onClick={fermer} aria-label="Fermer l'éditeur"><X size={16} strokeWidth={1.5}/></button></header>
    <div className="p-editor-content"><p className="p-editor-tip">Décris ce qu'un excellent résultat doit contenir. Conserve les règles existantes ; ajoute des attentes concrètes.</p>
      <p className="p-draft-hint">Brouillon conservé pendant la navigation. Non partagé et non activé.</p>
      <label htmlFor="agent-brief">Consignes de travail <span className="tab-num">{text.length.toLocaleString("fr-CA")} / 24 000</span></label>
      <textarea id="agent-brief" maxLength={24000} value={text} onChange={e => { setText(e.target.value); remember(e.target.value, why); setVerification(null); }} spellCheck={false}/>
      <label htmlFor="agent-why">Qu'est-ce que cette version améliore ?</label>
      <input id="agent-why" maxLength={800} value={why} onChange={e => { setWhy(e.target.value); remember(text, e.target.value); }} placeholder="Ex. Exiger les sources et tester les cas limites"/>
      <div className="p-editor-actions"><button className="p-button p-quiet" disabled={!dirty || busy} onClick={() => { setText(agent.corps); setWhy(""); retirerBrouillon(agent.nom); restored.current = undefined; setVerification(null); }}>Rétablir</button><button className="p-button p-primary" disabled={busy || !dirty || text.trim().length < 80} onClick={verify}>{busy ? "Vérification" : "Vérifier les consignes"}</button></div>
      {error && <div className="p-error" role="alert">{error}</div>}
      {verification && verifiedText === text && <section className={`p-verification ${verification.valide ? "est-valide" : ""}`}><h3>{verification.valide ? "Règles structurelles respectées" : "Points à corriger"}</h3>
        <p>Ce contrôle n'évalue pas l'intelligence de l'agent et ne consomme aucun appel IA.</p>
        {verification.raisons.map(r => <p key={r} className="p-warning">{r}</p>)}
        <details><summary>Comparer avec la version stable</summary><pre>{verification.diff}</pre></details>
        <button className="p-button p-primary" onClick={propose} disabled={!verification.valide || why.trim().length < 8 || busy}>Enregistrer la proposition</button></section>}
      <section className="p-version-list"><h3>Versions et essais</h3>{agent.candidats.length ? [...agent.candidats].reverse().map(c => <button key={c.id} className="p-version" onClick={() => setCandidate(c)}><span><strong>{c.id}</strong><small>{c.pourquoi}</small></span><Statut etat={c.statut}/></button>) : <p>Aucune proposition. La version stable est utilisée.</p>}</section>
      <p className="credit p-editor-proof">Version stable<span>{agent.empreinte}</span></p>
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
      await refresh(); notifier(action === "essayer" ? "Essai limité autorisé. Les prochaines tâches éligibles utiliseront le candidat." : "Candidat retiré. Retour à la version stable."); fermer(); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  return <dialog className="p-review-dialog" ref={ref} onCancel={fermer} aria-labelledby="review-title"><header><div><span className="p-agent-team">Comparaison avant décision</span><h2 id="review-title">{candidat.id}</h2></div><button className="p-icon-button" onClick={fermer} aria-label="Fermer"><X size={16} strokeWidth={1.5}/></button></header>
    <p>Un essai ne remplace pas la version stable. La promotion définitive reste une décision séparée au terminal.</p>
    {error && <div role="alert" className="p-error">{error}</div>}{detail ? <pre>{detail.diff}</pre> : <p>Chargement de la comparaison</p>}
    {detail?.candidat.statut === "proposee" && <><label className="p-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/>J'ai relu le changement et j'autorise un essai sur une partie des prochaines tâches.</label><button className="p-button p-primary" disabled={!consent || busy} onClick={() => decide("essayer")}>Autoriser l'essai limité</button></>}
    {detail && ["proposee", "canari"].includes(detail.candidat.statut) && <button className="p-button p-quiet" disabled={busy} onClick={() => decide("retirer")}>Retirer le candidat</button>}
  </dialog>;
}

function Missions({ source, objets, recherche, composer }: { source: Source; objets: ObjetBoard[]; recherche: string; composer: () => void }) {
  const [inspection, setInspection] = useState<Inspection | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  // une ligne par mission : la carte Mission et sa carte Équipe portent la même mission
  const vues = new Set<string>();
  const missions = [...objets].sort((a, b) => Number(b.type === "mission") - Number(a.type === "mission")).filter(o => o.mission && !vues.has(o.mission.id) && Boolean(vues.add(o.mission.id)))
    .filter(o => `${o.mission!.objectif} ${o.mission!.statut}`.toLowerCase().includes(recherche.toLowerCase()));
  const inspect = async (id: string) => { setBusy(true); setError(""); try { setInspection(await source.inspection(id)); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const origine = inspection ? [...new Set([inspection.demandeur, inspection.source].filter(Boolean))].join(" · ") : "";
  return <section className="p-page"><div className="p-page-heading"><div><h1>Missions</h1><p>Les missions reliées à ton Board. Chaque statut vient du moteur d'exécution.</p></div><button className="p-button p-primary" onClick={() => composer()}>Cadrer une mission</button></div>
    <div className="p-mission-layout"><div className="p-mission-list">{missions.map(o => <button key={o.id} className={`p-mission-row ${inspection?.id === o.mission!.id ? "selected" : ""}`} disabled={busy} onClick={() => inspect(o.mission!.id)}>
      <span className="p-mission-summary"><strong>{o.mission!.objectif}</strong><small className="tab-num">{o.mission!.faites} / {o.mission!.total} tâches terminées<span aria-hidden>·</span><span>{dateCourte(o.mission!.cree)}</span></small></span>
      <Statut etat={o.mission!.statut}/></button>)}
      {!missions.length && <EtatVide titre="Aucune mission" texte="Rassemble quelques ressources sur le Board, puis prépare un premier objectif"/>}</div>
      <aside className="p-mission-inspector"><h2>Détail de la mission</h2>{error && <p role="alert">{error}</p>}{busy ? <p>Chargement</p> : inspection ? <><h3>{inspection.objectif}</h3>
        <p className="credit">{origine && <>{origine}<span aria-hidden>·</span></>}<span>{dateCourte(inspection.cree)}</span></p>
        {inspection.taches.map(t => <div key={t.id} className="p-task"><p>{t.libelle || t.type}</p><Statut etat={t.statut}/><small>{t.raison || `Niveau ${t.niveau}`}</small></div>)}{inspection.artefacts.map(a => <details key={a.id}><summary>{a.factice ? "Résultat factice" : "Résultat"} · {a.fournisseur}</summary><pre>{a.contenu}</pre></details>)}</> : <p>Sélectionne une mission pour retrouver ses étapes, ses interruptions et ses résultats vérifiés</p>}</aside></div>
  </section>;
}

const TYPES_FICHIER: Record<string, string> = { image: "Image", capture: "Capture", audio: "Audio", video: "Vidéo", pdf: "PDF", document: "Document", note: "Note", texte: "Texte", lien: "Lien" };

function Bibliotheque({ objets, recherche, connaissances }: { objets: ObjetBoard[]; recherche: string; connaissances: boolean }) {
  const { aller } = useStudioNavigation();
  const types = connaissances ? ["note", "texte", "lien", "document"] : ["image", "capture", "audio", "video", "pdf", "document"];
  const filtered = objets.filter(o => types.includes(o.type) && `${o.meta.titre} ${o.contenu} ${o.asset?.nom}`.toLowerCase().includes(recherche.toLowerCase()));
  return <section className="p-page"><div className="p-page-heading"><div><h1>{connaissances ? "Notes et liens" : "Fichiers"}</h1><p>{connaissances ? "Les notes et les liens posés sur ton Board" : "Retrouve tes médias et documents sans parcourir tout le canevas"}</p></div><button className="p-button p-primary" onClick={() => aller("board")}>Ajouter sur le Board</button></div>
    <div className="p-library">{filtered.map(o => { const image = o.type === "image" ? o.asset?.url || o.meta.demo_src : undefined;
      return <button key={o.id} className="p-resource" onClick={() => aller("board", { carte: o.id })}>
        <span className="p-resource-texte"><h3>{o.meta.titre || o.asset?.nom || o.contenu.slice(0, 70) || "Ressource"}</h3><p>{o.meta.description || o.contenu.slice(0, 120) || "Ouvrir dans le Board"}</p></span>
        <small className="tab-num">{TYPES_FICHIER[o.type] ?? o.type}{o.auteur && <><span aria-hidden>·</span>par {o.auteur}</>}<span aria-hidden>·</span>{dateCourte(o.maj)}</small>
        <span className="p-resource-preview">{image && <img src={image} alt="" loading="lazy"/>}</span></button>; })}</div>
    {!filtered.length && <EtatVide titre="Aucun fichier" texte="Colle une note, un lien ou un fichier dans le Board. Tu le retrouveras ici."/>}
  </section>;
}

const VALIDATIONS: Record<string, string> = { humain: "Humaine", humaine: "Humaine", auto: "Automatique", automatique: "Automatique" };

function Configuration({ catalogue, demo }: { catalogue: Catalogue; demo: boolean }) {
  return <section className="p-page p-settings"><div className="p-page-heading"><div><h1>Configuration</h1><p>Cette vue expose la configuration. Elle ne change pas silencieusement tes autorisations.</p></div></div>
    <div className="p-settings-grid"><section className="p-panel"><div className="p-panel-tete"><h2>Moteurs</h2><p className="p-caption">Les abonnements restent les moteurs par défaut. Aucun basculement payant n'est ajouté.</p></div>
      <div className="p-panel-corps">{["claude", "codex"].map(f => { const c = catalogue.execution.connexions.find(c => c.fournisseur === f);
        return <div className="p-setting-line" key={f}><span>{f === "claude" ? "Claude Code" : "OpenAI Codex"}</span><small>{demo ? "État fictif, non mesuré" : c ? `${c.mode_auth} · ${c.disponible ? "connexion déclarée disponible" : c.raison || "indisponible"}` : "Connexion à déclarer sur ton poste"}</small></div>; })}</div></section>
    <section className="p-panel"><div className="p-panel-tete"><h2>Autonomie</h2><p className="p-caption">La disponibilité d'un abonnement ne garantit ni sa capacité restante ni l'autorisation commerciale d'un SaaS</p></div>
      <div className="p-panel-corps"><div className="p-setting-line"><span>Plafond d'agents</span><strong className="tab-num">{catalogue.politique.max_agents}</strong></div><div className="p-setting-line"><span>Validation des plans</span><strong>{VALIDATIONS[catalogue.politique.validation_plans] ?? catalogue.politique.validation_plans}</strong></div><div className="p-setting-line"><span>Arrêt d'urgence du moteur</span><strong>{catalogue.execution.arret_urgence ? "Activé" : "Inactif"}</strong></div></div></section>
    <section className="p-panel p-bridge"><div className="p-panel-tete"><h2>Modèle open source local</h2><p className="p-caption">Activation explicite, jeton dédié, limites de charge et moteur compatible local</p></div>
      <div className="p-panel-corps"><div className="p-setting-line"><span>Service séparé</span><Statut>Préparé, non activé</Statut></div><p>Un service séparé, local et désactivé par défaut. Il ne télécharge aucun modèle et ne reçoit aucune mission automatiquement.</p><code>services/model_bridge</code></div></section>
    <section className="p-panel"><div className="p-panel-tete"><h2>Exécutants</h2></div>
      <div className="p-panel-corps">{catalogue.execution.executants.length ? catalogue.execution.executants.map(r => <div className="p-setting-line" key={r.id}><span>{r.nom}</span><span className="p-status" data-ton={r.revoque ? "echec" : r.actif ? "ok" : undefined}>{r.revoque ? "Révoqué" : r.actif ? "Récent" : "Hors ligne"}</span></div>) : <p>Aucun exécutant enrôlé. L'interface fonctionne, mais elle ne peut pas exécuter de mission seule.</p>}<code>jarvis mission enroler --fournisseurs claude,codex</code></div></section></div>
  </section>;
}

function Activite({ catalogue, demo }: { catalogue: Catalogue; demo: boolean }) {
  const tasks = Object.entries(catalogue.execution.taches).sort((a, b) => b[1] - a[1]); const total = tasks.reduce((a, [, n]) => a + n, 0);
  return <section className="p-page"><div className="p-page-heading"><div><h1>Activité</h1><p>{demo ? "Mode démo : aucune métrique d'exécution réelle" : "Répartition actuelle des tâches du moteur"}</p></div><button className="p-button p-quiet" onClick={() => location.reload()}><RefreshCw size={16} strokeWidth={1.5}/>Actualiser</button></div>
    <section className="p-activity-panel"><div className="p-activity-summary"><span className="tab-num">{total}</span><div><h2>Tâches enregistrées</h2><p>Photographie de l'état actuel, pas une mesure historique de performance</p></div></div>{tasks.map(([name, n], i) => <div className={`p-distribution ${i === 0 && n > 0 ? "en-tete" : ""}`} key={name}><span>{status(name)}</span><div><i style={{ width: `${total ? n / total * 100 : 0}%` }}/></div><strong className="tab-num">{n}</strong></div>)}{!total && <EtatVide titre="Pas encore de tâches mesurées" texte="Une fois une mission exécutée, son état apparaîtra ici"/>}</section>
  </section>;
}

function EtatVide({ titre, texte }: { titre: string; texte: string }) {
  return <div className="p-empty"><h3>{titre}</h3><p>{texte}</p></div>;
}
