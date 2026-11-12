import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, RefreshCw, X } from "lucide-react";
import type { Source, Inspection } from "../api";
import type { ObjetBoard, StyleLien } from "../types";
import { Avatar } from "../components/Avatar";
import { MENTION_DEMO, duree, extension, taille } from "../lib/format";
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
        {vue === "analytique" && <Activite catalogue={data.catalogue} demo={source.demo} composer={composer}/>}
      </>}
    </main>
    <DialogueMission initialObjectif={intention} ouvert={dialog} demo={source.demo} fermer={() => setDialog(false)} lancer={lancer}/>
    {notice && <div className="p-feedback" role="status"><CheckCircle2 size={16} strokeWidth={1.5}/>{notice}</div>}
  </div>;
}

/** Objets du tableau blanc : dessinés sur le plan, mais ce ne sont pas des cartes (ils ne sont pas comptés comme telles). */
const TABLEAU = new Set(["adhesif", "texte_libre", "forme", "trait", "fleche", "cadre"]);
const estCarte = (o: ObjetBoard) => Boolean(TYPES_PLAN[o.type]) && !TABLEAU.has(o.type);
const nomDe = (o: ObjetBoard) => String(o.mission?.objectif || o.meta.titre || o.asset?.nom || o.contenu || "").slice(0, 90);

function Accueil({ data, demo, composer }: { data: ProductData; demo: boolean; composer: (objectif?: string) => void }) {
  const { aller } = useStudioNavigation();
  const active = data.catalogue.execution.executants.filter(x => x.actif && !x.revoque).length;
  // on compte ce que le plan dessine comme carte : les formes et les traits du tableau blanc n'en sont pas
  const cartes = data.board.objets.filter(estCarte).length;
  const relations = data.board.liens.length;
  const modifie = Math.max(0, ...data.board.objets.map(o => o.maj));
  const vide = !data.board.objets.some(o => TYPES_PLAN[o.type] || TABLEAU.has(o.type));
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
      <div className="p-formation" aria-label="Plan de situation de ton Board">
        <div className="p-plan-tete"><strong>Ton Board</strong>{!vide && <span className="tab-num">{pluriel(cartes, "carte")} · {pluriel(relations, "relation")}</span>}</div>
        {vide ? <div className="p-plan p-plan-vide"><h2>Pose ta première note</h2>
          <p>Colle un texte, un lien ou un fichier sur le canevas. Le plan de ton Board s'affichera ici, avec ses relations et l'avancement de ta mission.</p>
          <button className="p-button" onClick={() => aller("board")}>Ouvrir le Board</button></div>
          : <><PlanBoard board={data.board} ouvrir={() => aller("board")}/><ListeBoard board={data.board} ouvrir={() => aller("board")}/></>}
        <div className="p-plan-pied">
          {demo ? <p className="mention-demo">{MENTION_DEMO}</p>
            : <p className="p-plan-meta tab-num">{active ? pluriel(active, "exécutant") + (active > 1 ? " disponibles" : " disponible") : "Aucun exécutant actif"}{modifie > 0 && <><span aria-hidden>·</span><span>modifié le {dateCourte(modifie)}</span></>}</p>}
          <Legende board={data.board}/>
        </div>
      </div>
    </section>
    <section className="p-start">
      <div className="p-section-title"><div><h2>Intentions de départ</h2><p>Choisis-en une : Jarvis prépare le cadrage, rien n'est envoyé</p></div></div>
      <div className="p-intents">{choices.map(({ title, text, prompt }) => <button key={title} onClick={() => composer(prompt)}>
        <h3>{title}</h3><p>{text}</p></button>)}</div>
    </section>
    <section className="p-workspace-row"><div className="p-workspace-card"><div><h3>L'atelier des agents</h3><p>{pluriel(data.catalogue.agents.length, "rôle")} à lire, corriger et comparer avant d'adopter</p></div>
      <button className="p-button p-quiet" onClick={() => aller("agents")}>Ouvrir l'atelier</button></div></section>
  </>;
}

const TYPES_PLAN: Record<string, string> = { note: "Note", texte: "Texte", lien: "Lien", image: "Image", video: "Vidéo", audio: "Audio", pdf: "PDF", document: "Document", capture: "Capture",
  mission: "Mission", agents: "Équipe", dossier: "Dossier", plan: "Plan", tache: "Tâche" };
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
 *  type, la jauge de la mission. Les cartes sont posées en pourcentage : le texte garde sa taille à toutes les largeurs.
 *  Le tableau blanc y figure sans étiquette : cadres en pointillé, adhésifs dans leur couleur, formes et traits en filet. */
function PlanBoard({ board, ouvrir }: { board: ProductData["board"]; ouvrir: () => void }) {
  const objets = board.objets.filter(o => TYPES_PLAN[o.type] || TABLEAU.has(o.type)).sort((a, b) => Number(b.type === "cadre") - Number(a.type === "cadre") || a.z - b.z).slice(0, 80);
  const marge = 24;
  let x0 = Math.min(...objets.map(o => o.x)) - marge, y0 = Math.min(...objets.map(o => o.y)) - marge;
  let l = Math.max(...objets.map(o => o.x + o.largeur)) + marge - x0, h = Math.max(...objets.map(o => o.y + o.hauteur)) + marge - y0;
  // proportions bornées : un Board très large ou très haut reste lisible, centré dans son cadre
  const ratio = Math.min(2.2, Math.max(1.3, l / h));
  if (l / h < ratio) { x0 -= (h * ratio - l) / 2; l = h * ratio; } else { y0 -= (l / ratio - h) / 2; h = l / ratio; }
  const parId = new Map(objets.map(o => [o.id, o]));
  const pct = (v: number, total: number) => `${(v / total * 100).toFixed(3)}%`;
  const nCartes = objets.filter(estCarte).length;
  return <button className="p-plan" style={{ aspectRatio: `${l.toFixed(0)} / ${h.toFixed(0)}` }} onClick={ouvrir}
    aria-label={`Ouvrir le Board : ${pluriel(nCartes, "carte")}, ${pluriel(board.liens.length, "relation")}`}>
    <svg viewBox={`${x0} ${y0} ${l} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      {objets.filter(o => o.type === "trait" || o.type === "fleche").map(o =>
        <line key={o.id} className="p-plan-trace" x1={o.x} y1={o.y + o.hauteur} x2={o.x + o.largeur} y2={o.y}/>)}
      {board.liens.map(lien => {
        const s = parId.get(lien.source_id), c = parId.get(lien.cible_id);
        if (!s || !c) return null;
        const t = TRAITS_PLAN[lien.style] ?? TRAITS_PLAN.defaut;
        return <line key={lien.id} x1={s.x + s.largeur / 2} y1={s.y + s.hauteur / 2} x2={c.x + c.largeur / 2} y2={c.y + c.hauteur / 2}
          stroke={t.couleur} strokeDasharray={t.tirets} strokeLinecap={t.tirets ? "round" : undefined}/>;
      })}
    </svg>
    {objets.filter(o => o.type !== "trait" && o.type !== "fleche").map(o => {
      const place = { left: pct(o.x - x0, l), top: pct(o.y - y0, h), width: pct(o.largeur, l), height: pct(o.hauteur, h) };
      if (o.type === "cadre") return <span key={o.id} className="p-plan-cadre" aria-hidden="true" style={place}>{o.meta.titre && <span>{String(o.meta.titre).slice(0, 40)}</span>}</span>;
      if (o.type === "forme") return <span key={o.id} className={`p-plan-forme${o.meta.forme === "ellipse" ? " ellipse" : ""}`} aria-hidden="true" style={place}/>;
      if (o.type === "adhesif") return <span key={o.id} className="p-plan-adhesif" aria-hidden="true" style={{ ...place, background: `var(--adhesif-${typeof o.meta.couleur === "string" && o.meta.couleur ? o.meta.couleur : "jaune"})` }}>{o.contenu.slice(0, 60)}</span>;
      if (o.type === "texte_libre") return <span key={o.id} className="p-plan-texte" aria-hidden="true" style={place}>{o.contenu.slice(0, 60)}</span>;
      const image = o.type === "image" ? o.asset?.url || o.meta.demo_src : undefined;
      const nom = nomDe(o);
      return <span key={o.id} className={`p-plan-carte type-${o.type}${image ? " a-image" : ""}`} aria-hidden="true" style={place}>
        {image && <img src={image} alt="" loading="lazy"/>}
        <span className="p-plan-type">{TYPES_PLAN[o.type]}{o.priorite ? ` · ${o.priorite}` : ""}</span>
        {nom && <span className="p-plan-nom">{nom}</span>}
        {o.type === "mission" && o.mission && <Avancement m={o.mission}/>}
      </span>;
    })}
  </button>;
}

function Avancement({ m }: { m: NonNullable<ObjetBoard["mission"]> }) {
  return <span className="p-plan-avancement">
    <span className="p-plan-jauge"><i style={{ width: `${Math.max(0, Math.min(100, m.progression))}%` }}/></span>
    <span className="tab-num">{m.faites} / {m.total}</span></span>;
}

/** Petit écran : le plan réduit ne dirait plus rien. La mission d'abord, avec son titre et sa jauge, puis les cartes en lignes. */
function ListeBoard({ board, ouvrir }: { board: ProductData["board"]; ouvrir: () => void }) {
  const cartes = board.objets.filter(estCarte);
  const mission = cartes.find(o => o.type === "mission" && o.mission);
  const autres = cartes.filter(o => o !== mission && o.type !== "agents").sort((a, b) => Number(Boolean(b.priorite)) - Number(Boolean(a.priorite)) || b.maj - a.maj);
  return <button className="p-plan-liste" onClick={ouvrir} aria-label={`Ouvrir le Board : ${pluriel(cartes.length, "carte")}, ${pluriel(board.liens.length, "relation")}`}>
    {mission && <span className="p-plan-une"><span className="p-plan-type">Mission{mission.priorite ? ` · ${mission.priorite}` : ""}</span>
      <span className="p-plan-nom">{nomDe(mission)}</span><Avancement m={mission.mission!}/></span>}
    {autres.slice(0, 4).map(o => <span key={o.id} className="p-plan-ligne"><span className="p-plan-type">{TYPES_PLAN[o.type]}</span><span className="p-plan-nom">{nomDe(o) || "Sans titre"}</span></span>)}
    {autres.length > 4 && <span className="p-plan-ligne p-plan-reste tab-num">+ {pluriel(autres.length - 4, "autre carte").replace("autre cartes", "autres cartes")}</span>}
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
        <p>Contrôle de structure, sans appel à un modèle</p>
        {verification.raisons.map(r => <p key={r} className="p-warning">{r}</p>)}
        <details><summary>Comparer avec la version stable</summary><pre>{verification.diff}</pre></details>
        <button className="p-button p-primary" onClick={propose} disabled={!verification.valide || why.trim().length < 8 || busy}>Enregistrer la proposition</button></section>}
      <section className="p-version-list"><h3>Versions et essais</h3>{agent.candidats.length ? [...agent.candidats].reverse().map(c => <button key={c.id} className="p-version" onClick={() => setCandidate(c)}><span><strong>{c.id}</strong><small>{c.pourquoi}</small></span><Statut etat={c.statut}/></button>) : <p>Aucune proposition. La version stable est utilisée.</p>}</section>
      <p className="p-editor-proof tab-num">Version stable<span aria-hidden>·</span><span>{agent.empreinte}</span></p>
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
    <div className={`p-mission-layout${missions.length ? "" : " sans-detail"}`}><div className="p-mission-list">{missions.map(o => <button key={o.id} className={`p-mission-row ${inspection?.id === o.mission!.id ? "selected" : ""}`} disabled={busy} onClick={() => inspect(o.mission!.id)}>
      <span className="p-mission-summary"><strong>{o.mission!.objectif}</strong><small className="tab-num">{o.mission!.faites} / {o.mission!.total} tâches terminées<span aria-hidden>·</span><span>{dateCourte(o.mission!.cree)}</span></small></span>
      <Statut etat={o.mission!.statut}/></button>)}
      {!missions.length && <EtatVide titre="Aucune mission" texte="Rassemble quelques ressources sur le Board, puis prépare un premier objectif" action={recherche ? undefined : ["Cadrer une mission", () => composer()]}/>}</div>
      {missions.length > 0 && <aside className="p-mission-inspector"><h2>Détail de la mission</h2>{error && <p role="alert">{error}</p>}{busy ? <p>Chargement</p> : inspection ? <><h3>{inspection.objectif}</h3>
        <p className="credit">{origine && <>{origine}<span aria-hidden>·</span></>}<span>{dateCourte(inspection.cree)}</span></p>
        {inspection.taches.map(t => <div key={t.id} className="p-task"><p>{t.libelle || t.type}</p><Statut etat={t.statut}/><small>{t.raison || `Niveau ${t.niveau}`}</small></div>)}{inspection.artefacts.map(a => <details key={a.id}><summary>{a.factice ? "Résultat factice" : "Résultat"} · {a.fournisseur}</summary><pre>{a.contenu}</pre></details>)}</> : <p>Sélectionne une mission pour retrouver ses étapes, ses interruptions et ses résultats vérifiés</p>}</aside>}</div>
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
        <span className="p-resource-texte"><h3>{o.meta.titre || o.asset?.nom || o.contenu.slice(0, 70) || "Ressource"}</h3><p className={o.meta.description || o.contenu ? undefined : "tab-num"}>{o.meta.description || o.contenu.slice(0, 120) || metaFichier(o)}</p></span>
        <small className="tab-num">{TYPES_FICHIER[o.type] ?? o.type}{o.auteur && <><span aria-hidden>·</span>par {o.auteur}</>}<span aria-hidden>·</span>{dateCourte(o.maj)}</small>
        <span className="p-resource-preview">{image && <img src={image} alt="" loading="lazy"/>}</span></button>; })}</div>
    {!filtered.length && <EtatVide titre="Aucun fichier" texte="Colle une note, un lien ou un fichier dans le Board. Tu le retrouveras ici."/>}
  </section>;
}

/** Sous-titre d'un fichier sans description : son format, sa durée ou ses dimensions, sa taille. Jamais un libellé d'action. */
function metaFichier(o: ObjetBoard): string {
  const a = o.asset;
  if (!a) return TYPES_FICHIER[o.type] ?? o.type;
  const mesure = a.meta.duree ? duree(a.meta.duree) : a.meta.largeur && a.meta.hauteur ? `${a.meta.largeur} × ${a.meta.hauteur}` : "";
  return [extension(a.mime, a.nom), mesure, taille(a.taille)].filter(Boolean).join(" · ");
}

const VALIDATIONS: Record<string, string> = { humain: "Humaine", humaine: "Humaine", auto: "Automatique", automatique: "Automatique" };

function Configuration({ catalogue, demo }: { catalogue: Catalogue; demo: boolean }) {
  return <section className="p-page p-colonne p-settings"><div className="p-page-heading"><div><h1>Configuration</h1><p>Moteurs, autonomie et exécutants de cette installation, en lecture seule</p></div></div>
    <div className="p-settings-grid"><section className="p-panel"><div className="p-panel-tete"><h2>Moteurs</h2><p className="p-caption">Claude Code et Codex passent par tes abonnements</p></div>
      <div className="p-panel-corps">{["claude", "codex"].map(f => { const c = catalogue.execution.connexions.find(c => c.fournisseur === f);
        return <div className="p-setting-line" key={f}><span>{f === "claude" ? "Claude Code" : "OpenAI Codex"}</span><small>{demo ? "Démonstration, état non mesuré" : c ? `${c.mode_auth} · ${c.disponible ? "connexion déclarée disponible" : c.raison || "indisponible"}` : "Connexion à déclarer sur ton poste"}</small></div>; })}</div></section>
    <section className="p-panel"><div className="p-panel-tete"><h2>Autonomie</h2><p className="p-caption">Limites appliquées aux agents</p></div>
      <div className="p-panel-corps"><div className="p-setting-line"><span>Plafond d'agents</span><strong className="tab-num">{catalogue.politique.max_agents}</strong></div><div className="p-setting-line"><span>Validation des plans</span><strong>{VALIDATIONS[catalogue.politique.validation_plans] ?? catalogue.politique.validation_plans}</strong></div><div className="p-setting-line"><span>Arrêt d'urgence du moteur</span><strong>{catalogue.execution.arret_urgence ? "Activé" : "Inactif"}</strong></div></div></section>
    <section className="p-panel p-bridge"><div className="p-panel-tete"><h2>Modèle open source local</h2><p className="p-caption">Activation explicite, jeton dédié, limites de charge et moteur compatible local</p></div>
      <div className="p-panel-corps"><div className="p-setting-line"><span>Service séparé</span><Statut>Préparé, non activé</Statut></div><p>Service local, à activer toi-même. Tant qu'il est éteint, aucune mission ne lui est confiée.</p><code>services/model_bridge</code></div></section>
    <section className="p-panel"><div className="p-panel-tete"><h2>Exécutants</h2></div>
      <div className="p-panel-corps">{catalogue.execution.executants.length ? catalogue.execution.executants.map(r => <div className="p-setting-line" key={r.id}><span>{r.nom}</span><span className="p-status" data-ton={r.revoque ? "echec" : r.actif ? "ok" : undefined}>{r.revoque ? "Révoqué" : r.actif ? "Récent" : "Hors ligne"}</span></div>) : <p>Aucun exécutant enrôlé : les missions restent en file tant qu'aucun poste ne les prend</p>}<code>jarvis mission enroler --fournisseurs claude,codex</code></div></section></div>
  </section>;
}

function Activite({ catalogue, demo, composer }: { catalogue: Catalogue; demo: boolean; composer: () => void }) {
  const tasks = Object.entries(catalogue.execution.taches).sort((a, b) => b[1] - a[1]); const total = tasks.reduce((a, [, n]) => a + n, 0);
  return <section className="p-page p-colonne"><div className="p-page-heading"><div><h1>Activité</h1><p>État des tâches à l'instant</p>{demo && <p className="mention-demo">{MENTION_DEMO}</p>}</div>
    <button className="p-button p-quiet" onClick={() => location.reload()}><RefreshCw size={16} strokeWidth={1.5}/>Actualiser</button></div>
    <section className="p-activity-panel">{total > 0 && <div className="p-activity-summary"><span className="tab-num">{total}</span><div><h2>{total > 1 ? "Tâches enregistrées" : "Tâche enregistrée"}</h2><p>Réparties par état, la plus fréquente en tête</p></div></div>}
      {tasks.map(([name, n], i) => <div className={`p-distribution ${i === 0 && n > 0 ? "en-tete" : ""}`} key={name}><span>{status(name)}</span><div><i style={{ width: `${total ? n / total * 100 : 0}%` }}/></div><strong className="tab-num">{n}</strong></div>)}
      {!total && <EtatVide titre="Aucune tâche pour l'instant" texte="Dès qu'une mission est lancée, ses tâches se répartissent ici par état" action={["Cadrer une mission", composer]}/>}</section>
  </section>;
}

function EtatVide({ titre, texte, action }: { titre: string; texte: string; action?: [string, () => void] }) {
  return <div className="p-empty"><h3>{titre}</h3><p>{texte}</p>{action && <button className="p-button" onClick={action[1]}>{action[0]}</button>}</div>;
}
