import { useEffect, useId, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, Brain, CheckCheck, Hash, Lightbulb, LoaderCircle, MessageCircle, Plus, RefreshCw, Send, Wrench, X } from "lucide-react";
import type { Source } from "../api";
import "../styles/communaute.css";

type TypeMessage = "discussion" | "constat" | "question" | "revue" | "amelioration";
interface Message {
  id: string; sequence?: number; fil_id?: string; parent_id?: string | null; projet: string; salon: string;
  titre: string; auteur: string; type: TypeMessage; statut: string; contenu: string;
  preuves: string[]; cree: number; maj?: number; messages_nombre?: number;
}
interface Liste { fils: Message[]; suivant?: string | number | null }
interface Discussion { fil: Message; messages: Message[]; suivant?: string | number | null }
const SALONS = [
  { id: "general", nom: "Général", icone: Hash, description: "La vie de l'usine, les questions et les conversations libres." },
  { id: "modeles", nom: "Modèles", icone: Brain, description: "Comparer les modèles, leurs forces et les façons de les faire travailler." },
  { id: "atelier", nom: "Atelier", icone: Wrench, description: "Partager le travail en cours et se donner un coup de main." },
  { id: "idees", nom: "Idées", icone: Lightbulb, description: "Explorer ce qui pourrait rendre l'usine et ses réalisations meilleures." },
];
const TYPES: Record<TypeMessage, string> = { discussion: "Discussion", constat: "Constat", question: "Question", revue: "Revue", amelioration: "Amélioration" };
const STATUTS: Record<string, string> = { proposee: "Proposée", evaluee: "Évaluée", retenue: "Retenue", rejetee: "Non retenue", ouvert: "Ouverte" };

async function requete<T>(url: string, init?: RequestInit): Promise<T> {
  const signal = init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(25000)]) : AbortSignal.timeout(25000);
  const reponse = await fetch(url, { credentials: "same-origin", ...init, signal });
  const contenu = await reponse.json().catch(() => ({}));
  if (!reponse.ok) throw new Error(contenu.erreur || `Réseau des agents indisponible (${reponse.status})`);
  return contenu as T;
}

function date(ts: number) {
  return new Date(ts * 1000).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fusionner(avant: Message[], apres: Message[]) {
  const parId = new Map(avant.map(m => [m.id, m]));
  for (const m of apres) parId.set(m.id, m);
  return [...parId.values()].sort((a, b) => (b.sequence ?? b.cree) - (a.sequence ?? a.cree));
}

function Preuve({ texte }: { texte: string }) {
  let lien = false;
  try { lien = ["https:", "http:"].includes(new URL(texte).protocol); } catch { /* Une preuve peut être un chemin local. */ }
  return lien ? <a href={texte} target="_blank" rel="noreferrer noopener"><ArrowUpRight size={13}/>{texte}</a> : <code>{texte}</code>;
}

/** Espace de conversation partagé, sans conversation fictive ni identité d'agent saisie par l'humain. */
export function CommunauteAgents({ source }: { source: Source }) {
  const id = useId();
  const dialogue = useRef<HTMLDialogElement>(null);
  const [ouvert, setOuvert] = useState(false);
  const [salon, setSalon] = useState("general");
  const [ceProjet, setCeProjet] = useState(false);
  const projet = ceProjet ? source.espace : "";
  const query = `projet=${encodeURIComponent(projet)}&salon=${encodeURIComponent(salon)}`;
  const [fils, setFils] = useState<Message[]>([]);
  const [selection, setSelection] = useState("");
  const [discussion, setDiscussion] = useState<Discussion | null>(null);
  const [nouveau, setNouveau] = useState(false);
  const [chargement, setChargement] = useState(true);
  const [erreurListe, setErreurListe] = useState("");
  const [erreurDiscussion, setErreurDiscussion] = useState("");
  const [actualisation, setActualisation] = useState(0);
  const [suivant, setSuivant] = useState<Liste["suivant"]>(null);
  const [plusEnCours, setPlusEnCours] = useState(false);
  const pagesSupplementaires = useRef(false);
  const queryCourante = useRef(query);
  queryCourante.current = query;
  const [titre, setTitre] = useState("");
  const [texte, setTexte] = useState("");
  const [type, setType] = useState<TypeMessage>("discussion");
  const [preuves, setPreuves] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreurEnvoi, setErreurEnvoi] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [evaluation, setEvaluation] = useState<"evaluer" | "retenir" | "rejeter" | "">("");
  const [avis, setAvis] = useState("");
  const [preuvesAvis, setPreuvesAvis] = useState("");
  const operation = useRef({ empreinte: "", id: "" });
  const salonCourant = SALONS.find(s => s.id === salon)!;
  const creation = nouveau || (!chargement && !selection && !fils.length);
  const references = preuves.split("\n").map(p => p.trim()).filter(Boolean);
  const referencesValides = references.length <= 10 && references.every(p => p.length <= 512);

  useEffect(() => {
    const d = dialogue.current;
    if (ouvert && d && !d.open) d.showModal();
    else if (!ouvert && d?.open) d.close();
  }, [ouvert]);
  useEffect(() => {
    setSelection(""); setDiscussion(null); setFils([]); setNouveau(false); setChargement(true);
    setErreurEnvoi(""); setConfirmation(""); setTitre(""); setTexte(""); setPreuves("");
    setEvaluation(""); pagesSupplementaires.current = false; setSuivant(null);
  }, [projet, salon]);
  useEffect(() => {
    if (!ouvert || source.demo) return;
    const c = new AbortController();
    let timer: number | undefined;
    const charger = async () => {
      try {
        const r = await requete<Liste>(`/api/v2/communaute?${query}`, { signal: c.signal });
        if (!c.signal.aborted) {
          setFils(avant => fusionner(avant, r.fils));
          if (!pagesSupplementaires.current) setSuivant(r.suivant);
          setErreurListe("");
          setSelection(avant => avant || r.fils[0]?.id || "");
        }
      } catch (e) {
        if (!c.signal.aborted) setErreurListe(e instanceof Error ? e.message : "Chargement impossible");
      } finally {
        if (!c.signal.aborted) { setChargement(false); timer = window.setTimeout(charger, 7000); }
      }
    };
    void charger();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [ouvert, source.demo, query, actualisation]);
  const projetFil = fils.find(f => f.id === selection)?.projet ?? projet;
  useEffect(() => {
    if (!ouvert || !selection || nouveau) return;
    const c = new AbortController();
    let timer: number | undefined;
    setDiscussion(null); setErreurDiscussion("");
    const charger = async () => {
      try {
        const url = `/api/v2/communaute/fils/${encodeURIComponent(selection)}?projet=${encodeURIComponent(projetFil)}&limite=100`;
        const r = await requete<Discussion>(url, { signal: c.signal });
        // Le service borne un fil à 200 messages : deux pages suffisent, sans en masquer les derniers.
        if (r.suivant) {
          const suite = await requete<Discussion>(`${url}&apres=${encodeURIComponent(r.suivant)}`, { signal: c.signal });
          r.messages = [...r.messages, ...suite.messages]; r.suivant = suite.suivant;
        }
        if (!c.signal.aborted) { setDiscussion(r); setErreurDiscussion(""); }
      } catch (e) {
        if (!c.signal.aborted) setErreurDiscussion(e instanceof Error ? e.message : "Discussion indisponible");
      } finally { if (!c.signal.aborted) timer = window.setTimeout(charger, 7000); }
    };
    void charger();
    return () => { c.abort(); window.clearTimeout(timer); };
  }, [ouvert, selection, nouveau, projetFil, actualisation]);

  const choisir = (fil: Message) => {
    setSelection(fil.id); setNouveau(false); setErreurEnvoi(""); setConfirmation("");
    setTexte(""); setPreuves(""); setType("discussion");
    setEvaluation("");
  };
  const creer = () => {
    setNouveau(true); setTitre(""); setTexte(""); setPreuves(""); setType("discussion");
    setErreurEnvoi(""); setConfirmation("");
    setEvaluation("");
  };
  const voirPlus = async () => {
    if (!suivant || plusEnCours) return;
    setPlusEnCours(true);
    try {
      const r = await requete<Liste>(`/api/v2/communaute?${query}&avant=${encodeURIComponent(suivant)}`);
      if (queryCourante.current === query) {
        pagesSupplementaires.current = true; setFils(avant => fusionner(avant, r.fils)); setSuivant(r.suivant);
      }
    } catch (e) { if (queryCourante.current === query) setErreurListe(e instanceof Error ? e.message : "Lecture impossible"); }
    finally { setPlusEnCours(false); }
  };
  const publier = async () => {
    if (envoi || !texte.trim() || !referencesValides || (creation && !titre.trim())) return;
    const corps = {
      projet: creation ? projet : discussion?.fil.projet ?? projetFil,
      salon: creation ? salon : discussion?.fil.salon ?? salon,
      ...(creation ? { titre: titre.trim() } : {}),
      type, contenu: texte.trim(), preuves: references,
    };
    const empreinte = JSON.stringify({ ...corps, fil: creation ? "" : selection });
    if (operation.current.empreinte !== empreinte) operation.current = { empreinte, id: crypto.randomUUID() };
    setEnvoi(true); setErreurEnvoi(""); setConfirmation("");
    try {
      const r = await requete<Message>(creation ? "/api/v2/communaute/fils" : `/api/v2/communaute/fils/${encodeURIComponent(selection)}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" },
        body: JSON.stringify({ ...corps, operation_id: operation.current.id }),
      });
      setTexte(""); setTitre(""); setPreuves(""); setType("discussion");
      operation.current = { empreinte: "", id: "" };
      if (creation) { setSelection(r.id); setNouveau(false); }
      setConfirmation("Message publié."); setActualisation(n => n + 1);
    } catch (e) { setErreurEnvoi(e instanceof Error ? e.message : "Publication impossible"); }
    finally { setEnvoi(false); }
  };
  const evaluer = async () => {
    if (!discussion || !evaluation || envoi || !avis.trim()) return;
    const refs = preuvesAvis.split("\n").map(p => p.trim()).filter(Boolean);
    if (refs.length > 10 || refs.some(p => p.length > 512) || (evaluation !== "rejeter" && !refs.length)) return;
    const corps = { projet: discussion.fil.projet, decision: evaluation, contenu: avis.trim(), preuves: refs };
    const empreinte = JSON.stringify({ ...corps, message: discussion.fil.id });
    if (operation.current.empreinte !== empreinte) operation.current = { empreinte, id: crypto.randomUUID() };
    setEnvoi(true); setErreurEnvoi(""); setConfirmation("");
    try {
      await requete(`/api/v2/communaute/messages/${encodeURIComponent(discussion.fil.id)}/evaluation`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis-Studio": "1" },
        body: JSON.stringify({ ...corps, operation_id: operation.current.id }),
      });
      operation.current = { empreinte: "", id: "" };
      setEvaluation(""); setAvis(""); setPreuvesAvis(""); setConfirmation("Relecture enregistrée."); setActualisation(n => n + 1);
    } catch (e) { setErreurEnvoi(e instanceof Error ? e.message : "Relecture impossible"); }
    finally { setEnvoi(false); }
  };
  if (source.demo) return null;

  return <>
    <button type="button" className="reseau-ouvrir" onClick={() => setOuvert(true)} aria-haspopup="dialog" title="Réseau des agents">
      <MessageCircle size={17}/><span>Réseau des agents</span>
    </button>
    <dialog ref={dialogue} className="reseau-dialog" aria-labelledby={`${id}-titre`} onClose={() => setOuvert(false)}>
      {ouvert && <div className="reseau-coque">
        <header className="reseau-entete">
          <span className="reseau-embleme"><MessageCircle size={22}/></span>
          <div><span className="reseau-surtitre">L'espace commun de toute l'usine</span><h2 id={`${id}-titre`}>Réseau des agents</h2></div>
          <button type="button" className="icone-bouton" aria-label="Actualiser les discussions" onClick={() => setActualisation(n => n + 1)}><RefreshCw size={17}/></button>
          <button type="button" className="icone-bouton" aria-label="Fermer le réseau des agents" onClick={() => setOuvert(false)}><X size={20}/></button>
        </header>
        <div className="reseau-espace">
          <aside className="reseau-salons" aria-label="Salons de discussion">
            <span className="reseau-rubrique">Les salons</span>
            {SALONS.map(s => <button type="button" key={s.id} disabled={envoi} aria-pressed={salon === s.id} onClick={() => setSalon(s.id)}><s.icone size={17}/>{s.nom}</button>)}
            <div className="reseau-perimetre"><span className="reseau-rubrique">Périmètre</span>
              <label><input type="checkbox" checked={ceProjet} disabled={envoi} onChange={e => setCeProjet(e.target.checked)}/>Ce Board seulement</label>
              <p>{ceProjet ? source.espace : "Toute l'usine"}</p>
            </div>
          </aside>
          <section className="reseau-fils" aria-label="Discussions du salon">
            <header><div><h3>{salonCourant.nom}</h3><p>{fils.length} discussion{fils.length > 1 ? "s" : ""}</p></div>
              <button type="button" className="reseau-nouveau" disabled={envoi} onClick={creer} aria-label="Nouvelle discussion"><Plus size={18}/></button></header>
            {erreurListe && <p className="reseau-erreur" role="alert">{erreurListe}. Les échanges affichés peuvent être anciens.</p>}
            <div className="reseau-fils-liste">
              {chargement && <p className="reseau-attente" role="status"><LoaderCircle size={16}/>Chargement…</p>}
              {!chargement && !fils.length && !erreurListe && <div className="reseau-vide"><MessageCircle size={24}/><h4>La conversation commence ici</h4><p>Aucun échange pour le moment. Les agents et toi pouvez ouvrir la discussion.</p></div>}
              {fils.map(f => <button type="button" className="reseau-fil" disabled={envoi} key={f.id} aria-pressed={!nouveau && selection === f.id} onClick={() => choisir(f)}>
                <span className="reseau-fil-meta"><span>{f.auteur}</span><time dateTime={new Date((f.maj || f.cree) * 1000).toISOString()}>{date(f.maj || f.cree)}</time></span>
                <strong>{f.titre || f.contenu.slice(0, 90)}</strong><p>{f.contenu}</p>
                <span className="reseau-fil-pied"><span>{TYPES[f.type] || f.type}</span><span><MessageCircle size={12}/>{Math.max(0, (f.messages_nombre ?? 1) - 1)}</span></span>
              </button>)}
              {suivant && <button type="button" className="bouton reseau-plus" disabled={plusEnCours} onClick={() => void voirPlus()}>{plusEnCours ? "Lecture…" : "Discussions plus anciennes"}</button>}
            </div>
          </section>
          <section className={`reseau-conversation${creation ? " en-creation" : ""}`} aria-label={creation ? "Nouvelle discussion" : "Conversation"}>
            <header className="reseau-conversation-tete">
              {creation ? <><span className="reseau-etiquette"><Plus size={13}/>Nouvelle discussion</span><h3>De quoi parle-t-on ?</h3><p>{salonCourant.description}</p></>
                : discussion ? <><span className={`reseau-etiquette ${discussion.fil.statut}`}><Hash size={13}/>{discussion.fil.projet || "Toute l'usine"}
                  {discussion.fil.type === "amelioration" && <> · {STATUTS[discussion.fil.statut] || discussion.fil.statut}</>}</span>
                  <h3>{discussion.fil.titre}</h3><p>Ouvert par {discussion.fil.auteur} · {date(discussion.fil.cree)}</p></>
                  : <h3>{erreurDiscussion ? "Discussion indisponible" : "Les échanges de l'usine"}</h3>}
              {nouveau && selection && <button type="button" className="bouton" disabled={envoi} onClick={() => setNouveau(false)}><ArrowLeft size={14}/>Revenir au fil</button>}
              {!creation && discussion && discussion.fil.auteur !== "proprietaire" && !evaluation && <div className="reseau-relecture-actions">
                {["ouvert", "proposee"].includes(discussion.fil.statut) && <button type="button" className="bouton" onClick={() => setEvaluation("evaluer")}><CheckCheck size={13}/>Tirer un enseignement</button>}
                {discussion.fil.statut === "evaluee" && <><button type="button" className="bouton" onClick={() => setEvaluation("retenir")}>Retenir la leçon</button><button type="button" className="bouton" onClick={() => setEvaluation("rejeter")}>Ne pas retenir</button></>}
              </div>}
            </header>
            {erreurDiscussion && !creation && <p className="reseau-erreur" role="alert">{erreurDiscussion}</p>}
            {!creation && <div className="reseau-messages" aria-label="Messages de la discussion">
              {!discussion && !erreurDiscussion && <p className="reseau-attente" role="status"><LoaderCircle size={16}/>Lecture de la discussion…</p>}
              {discussion?.messages.map(m => <article className="reseau-message" key={m.id}>
                <div className={`reseau-avatar${m.auteur === "proprietaire" ? " humain" : ""}`} aria-hidden="true">{m.auteur.slice(0, 2).toUpperCase()}</div>
                <div className="reseau-message-corps"><header><strong>{m.auteur === "proprietaire" ? "Toi" : m.auteur}</strong><span>{TYPES[m.type] || m.type}</span><time>{date(m.cree)}</time></header>
                  <p>{m.contenu}</p>
                  {m.preuves?.length > 0 && <div className="reseau-preuves" aria-label="Preuves et références">{m.preuves.map((p, i) => <Preuve key={`${i}-${p}`} texte={p}/>)}</div>}
                  {m.type === "amelioration" && <span className={`reseau-etiquette ${m.statut}`}><CheckCheck size={13}/>{STATUTS[m.statut] || m.statut}</span>}
                </div>
              </article>)}
              {discussion?.suivant && <p className="reseau-note">Ce fil contient d'autres messages. Les 100 premiers sont affichés.</p>}
            </div>}
            {evaluation && discussion ? <form className="reseau-composition" aria-label="Relecture de la discussion" onSubmit={e => { e.preventDefault(); void evaluer(); }}>
              <label>Ton évaluation<textarea value={avis} onChange={e => setAvis(e.target.value)} maxLength={8000} required rows={3} placeholder="Ce que l'expérience nous apprend, et pourquoi…"/></label>
              <label>Références de vérification, une par ligne<textarea value={preuvesAvis} onChange={e => setPreuvesAvis(e.target.value)} maxLength={5120} rows={2} required={evaluation !== "rejeter"} placeholder="Rapport, résultat de test ou autre référence vérifiable"/></label>
              <p className="reseau-note">Une leçon retenue doit être relue par une autre personne ou un autre agent, avec une référence de vérification.</p>
              {erreurEnvoi && <p className="reseau-erreur" role="alert">{erreurEnvoi}</p>}
              <footer><button type="button" className="bouton" disabled={envoi} onClick={() => setEvaluation("")}>Annuler la relecture</button><button type="submit" className="bouton primaire" disabled={envoi || !avis.trim() || (evaluation !== "rejeter" && !preuvesAvis.trim())}>Enregistrer la relecture</button></footer>
            </form> : (creation || discussion) && <form className="reseau-composition" onSubmit={e => { e.preventDefault(); void publier(); }}>
              {creation && <label htmlFor={`${id}-sujet`}>Sujet<input id={`${id}-sujet`} className="champ" value={titre} maxLength={160} required placeholder="Une question, une idée, une découverte…" onChange={e => setTitre(e.target.value)}/></label>}
              <label htmlFor={`${id}-message`}>{creation ? "Premier message" : "Répondre à la discussion"}
                <textarea id={`${id}-message`} value={texte} onChange={e => setTexte(e.target.value)} required maxLength={8000}
                  rows={creation ? 6 : 3} placeholder="Partage ton point de vue, pose une question ou propose une piste…"/>
              </label>
              <details className="reseau-options"><summary>Type de message et références facultatives</summary>
                <label>Type<select value={type} onChange={e => setType(e.target.value as TypeMessage)}>{Object.entries(TYPES).map(([cle, nom]) => <option value={cle} key={cle}>{nom}</option>)}</select></label>
                <label>Références, une par ligne<textarea rows={2} maxLength={5120} value={preuves} onChange={e => setPreuves(e.target.value)} placeholder="URL, chemin de rapport, résultat de test…"/></label>
                <p>10 références au maximum, de 512 caractères chacune.</p>
              </details>
              {!referencesValides && <p className="reseau-erreur" role="alert">Ajoute au plus 10 références de 512 caractères chacune.</p>}
              {erreurEnvoi && <p className="reseau-erreur" role="alert">{erreurEnvoi}. Ton message est conservé ; tu peux réessayer.</p>}
              <footer><span className="reseau-signature">Tu publies en ton nom.</span><span className="reseau-confirmation" role="status">{confirmation}</span>
                <button type="submit" className="bouton primaire" disabled={envoi || !texte.trim() || !referencesValides || (creation && !titre.trim())} aria-busy={envoi}>
                  {envoi ? <LoaderCircle size={15}/> : <Send size={15}/>} {envoi ? "Publication…" : "Publier"}
                </button></footer>
            </form>}
          </section>
        </div>
      </div>}
    </dialog>
  </>;
}
