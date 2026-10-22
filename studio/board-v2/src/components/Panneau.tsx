import { memo, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Calendar, Check, CircleDashed, FileText, Image as IconeImage, Link2, Loader, MoreHorizontal, Music, Play, Plus, ShieldCheck, Sparkles, Star, Target, Video, X } from "lucide-react";
import type { Approbation, Evenement, ObjetBoard, Priorite } from "../types";
import type { Inspection, Source } from "../api";
import { ilya, libelleTache, taille } from "../lib/format";
import { Avatar } from "./Avatar";
import { statutAgent } from "../nodes/CartesVivantes";
import { etatJarvis } from "../nodes/CardShell";
import { CONTEXTUALISABLES } from "../nodes/contexte";

type Onglet = "details" | "activite" | "commentaires";
const NIVEAUX: Record<string, string> = { P1: "Élevée", P2: "Moyenne", P3: "Basse" };

export function decrireEvenement(e: Evenement | Inspection["chronologie"][number]): string {
  const d = e.donnees as Record<string, string | boolean | string[] | undefined>;
  switch (e.type) {
    case "demo": return String(d.texte ?? "");
    case "board_objet": return `Objet ${d.type ?? ""} ajouté au Board`;
    case "board_maj": return `Objet modifié (${(d.champs as string[] | undefined)?.join(", ") ?? ""})`;
    case "board_supprime": return "Objet(s) supprimé(s)";
    case "board_restaure": return "Objet(s) restauré(s)";
    case "board_lien": return "Relation créée";
    case "board_fichier": return `Fichier ${d.famille ?? ""} téléversé`;
    case "board_commentaire": return "Commentaire ajouté";
    case "board_propositions": return `Jarvis a contextualisé l'élément (${d.n ?? 0} action(s) proposée(s))`;
    case "board_proposition": return `Proposition ${d.decision === "lancer" ? "lancée" : "écartée"}`;
    case "mission_creee": return `Mission créée (${d.source ?? ""})`;
    case "mission_etat": return `Mission ${String(d.vers ?? "").toLowerCase()}`;
    case "tache_etat": return `Tâche : ${d.de} → ${d.vers}${d.raison ? ` — ${d.raison}` : ""}`;
    case "artefact": return `Livrable reçu de ${d.fournisseur}${d.factice ? " (factice)" : ""}`;
    case "approbation": return `Approbation ${d.decision} par ${d.par}`;
    case "resultat_perime": return "Résultat périmé refusé";
    default: return e.type.replace(/_/g, " ");
  }
}

function IconeType({ type }: { type: string }) {
  const I = type === "mission" ? Target : type === "image" ? IconeImage : type === "lien" ? Link2 : type === "audio" ? Music
    : type === "video" ? Video : FileText;
  return <span className="icone-mission" style={type === "mission" ? undefined : { background: "#1B2133", color: "#9DB0FF" }}><I size={22} /></span>;
}

interface Props {
  source: Source;
  objet: ObjetBoard | null;
  objets: ObjetBoard[];
  evenements: Evenement[];
  approbations: Approbation[];
  tick: number;
  priorite: (id: string, p: Priorite) => void;
  modifierMeta: (o: ObjetBoard, meta: ObjetBoard["meta"]) => void;
  decider: (id: string, accord: boolean) => Promise<void>;
  contextualiser: (id: string) => void;
  deciderProposition: (o: ObjetBoard, index: number, decision: "lancer" | "ecarter") => Promise<void>;
}

export const Panneau = memo(function Panneau({ source, objet, objets, evenements, approbations, tick, priorite, modifierMeta, decider, contextualiser, deciderProposition }: Props) {
  const [onglet, setOnglet] = useState<Onglet>("details");
  const [insp, setInsp] = useState<Inspection | null>(null);
  const [comms, setComms] = useState<{ id: string; auteur: string; texte: string; cree: number }[]>([]);
  const [brouillon, setBrouillon] = useState("");
  const missionId = objet?.mission_id ?? null;

  useEffect(() => {
    let annule = false;
    if (!missionId) {
      setInsp(null);
      return;
    }
    source.inspection(missionId).then((r) => !annule && setInsp(r)).catch(() => !annule && setInsp(null));
    return () => {
      annule = true;
    };
  }, [source, missionId, tick]);
  useEffect(() => {
    let annule = false;
    if (!objet) {
      setComms([]);
      return;
    }
    source.commentaires(objet.id).then((c) => !annule && setComms(c)).catch(() => undefined);
    return () => {
      annule = true;
    };
  }, [source, objet?.id, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const activite: { cle: string; texte: string; ts: number; agent?: string }[] = insp
    ? [...insp.chronologie].sort((a, b) => b.ts - a.ts).map((e) => ({ cle: `${e.seq}`, texte: decrireEvenement(e), ts: e.ts, agent: (e.donnees.agent as string) || undefined }))
    : evenements.filter((e) => !objet || e.donnees.objet_id === objet.id || (objet.mission_id && e.mission_id === objet.mission_id))
      .slice(-40).reverse().map((e) => ({ cle: `${e.seq}`, texte: decrireEvenement(e), ts: e.ts }));

  return (
    <aside className="panneau" aria-label="Panneau contextuel">
      <div className="onglets" role="tablist">
        {([["details", "Détails"], ["activite", "Activité"], ["commentaires", `Commentaires (${comms.length})`]] as [Onglet, string][]).map(([k, nom]) => (
          <button key={k} role="tab" aria-selected={onglet === k} onClick={() => setOnglet(k)}>{nom}</button>
        ))}
      </div>
      <div className="panneau-corps">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={`${onglet}-${objet?.id ?? "aucun"}`} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}>
            {onglet === "details" && (objet
              ? <>
                  <SectionJarvis objet={objet} contextualiser={contextualiser} deciderProposition={deciderProposition} />
                  <Details objet={objet} insp={insp} approbations={approbations} demo={source.demo} activite={activite}
                    priorite={priorite} modifierMeta={modifierMeta} decider={decider} voirTout={() => setOnglet("activite")} />
                </>
              : <Apercu objets={objets} approbations={approbations} activite={activite} />)}
            {onglet === "activite" && (
              <div className="section">
                {activite.length ? <ListeActivite activite={activite} /> : <p className="vide">Aucune activité enregistrée pour l'instant.</p>}
              </div>
            )}
            {onglet === "commentaires" && (
              <div className="section" style={{ display: "grid", gap: 10 }}>
                {!objet && <p className="vide">Sélectionne une carte pour lire ou écrire ses commentaires.</p>}
                {comms.map((c) => <div key={c.id} className="commentaire"><div className="qui">{c.auteur} · {ilya(c.cree)}</div>{c.texte}</div>)}
                {objet && (
                  <form onSubmit={async (e) => {
                    e.preventDefault();
                    if (!brouillon.trim()) return;
                    await source.commenter(objet.id, brouillon.trim());
                    setBrouillon("");
                    setComms(await source.commentaires(objet.id));
                  }}>
                    <textarea className="champ" style={{ height: 80, paddingTop: 8 }} placeholder="Écrire un commentaire…" value={brouillon}
                      onChange={(e) => setBrouillon(e.target.value)} maxLength={4000} aria-label="Nouveau commentaire" />
                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button className="bouton primaire" disabled={!brouillon.trim()}>Commenter</button>
                    </div>
                  </form>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </aside>
  );
});

/** Lecture du chef : résumé et actions proposées. « Lancer » prépare (mission L1) ; l'humain garde l'étape externe. */
function SectionJarvis({ objet, contextualiser, deciderProposition }: {
  objet: ObjetBoard; contextualiser: (id: string) => void;
  deciderProposition: (o: ObjetBoard, index: number, decision: "lancer" | "ecarter") => Promise<void>;
}) {
  const [occupe, setOccupe] = useState<number | null>(null);
  if (!CONTEXTUALISABLES.has(objet.type)) return null;
  const e = etatJarvis(objet);
  const props = objet.meta.propositions ?? [];
  return (
    <section className="section section-jarvis" aria-label="Actions proposées par Jarvis">
      <div className="tete"><h4><Sparkles size={17} /> Jarvis</h4>
        {e?.etat !== "analyse" && (
          <button type="button" className="lien-texte" onClick={() => contextualiser(objet.id)}>{e ? "Relancer l'analyse" : "Analyser avec Jarvis"}</button>
        )}</div>
      {!e && <p className="vide">Pas encore analysé.</p>}
      {e && e.etat !== "pret" && <p className={`vide etat-${e.etat}`}>{e.etat === "analyse" ? <Loader size={14} className="tourne" /> : null} {e.texte}</p>}
      {objet.meta.jarvis_resume && <p className="resume-jarvis">{objet.meta.jarvis_resume}</p>}
      {props.length > 0 && <h5 className="sous-titre">Actions proposées par Jarvis</h5>}
      <ul className="propositions">
        {props.map((p, i) => (
          <li key={i} className={p.statut}>
            <div className="prop-texte">
              <span className={`niveau ${p.niveau}`} title={p.niveau === "L1" ? "Sans effet externe" : "Jarvis prépare seulement : l'étape externe reste la tienne"}>{p.niveau}</span>
              <b>{p.titre}</b>
              {p.pourquoi && <span className="pourquoi">{p.pourquoi}</span>}
            </div>
            {p.statut === "proposee" ? (
              <div className="prop-actions">
                <button type="button" className="bouton primaire" disabled={occupe !== null}
                  aria-label={`${p.niveau === "L1" ? "Lancer" : "Préparer"} « ${p.titre} »`}
                  onClick={async () => { setOccupe(i); await deciderProposition(objet, i, "lancer"); setOccupe(null); }}>
                  <Play size={13} /> {p.niveau === "L1" ? "Lancer" : "Préparer"}</button>
                <button type="button" className="bouton" aria-label={`Écarter « ${p.titre} »`} disabled={occupe !== null}
                  onClick={async () => { setOccupe(i); await deciderProposition(objet, i, "ecarter"); setOccupe(null); }}><X size={13} /> Écarter</button>
              </div>
            ) : <span className="meta-carte">{p.statut === "lancee" ? "Lancée" : "Écartée"}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ListeActivite({ activite, max }: { activite: { cle: string; texte: string; ts: number; agent?: string }[]; max?: number }) {
  return (
    <ul className="activite">
      {activite.slice(0, max).map((a) => (
        <li key={a.cle}>
          {a.agent ? <Avatar id={a.agent} role={a.agent} taille={34} point /> : <span className="bouton-rond" style={{ width: 34, height: 34 }}><CircleDashed size={16} /></span>}
          <span>{a.texte.split(" ").map((m, i) => (i === 0 && a.agent ? <b key={i}>{m} </b> : `${m} `))}</span>
          <span className="tab-num" style={{ whiteSpace: "nowrap" }}>{ilya(a.ts)}</span>
        </li>
      ))}
    </ul>
  );
}

function Apercu({ objets, approbations, activite }: { objets: ObjetBoard[]; approbations: Approbation[]; activite: { cle: string; texte: string; ts: number }[] }) {
  return (
    <>
      <div className="section">
        <h4>Board</h4>
        <p className="vide" style={{ marginTop: 6 }}>{objets.length} carte(s). Sélectionne une carte pour voir ses détails, son activité et ses commentaires.</p>
      </div>
      <div className="section">
        <div className="tete"><h4><ShieldCheck size={17} /> Approbations</h4>{approbations.length > 0 && <span className="compte-attente">{approbations.length} en attente</span>}</div>
        {approbations.length ? approbations.map((a) => <div key={a.id} className="meta-carte" style={{ fontSize: 13 }}>{a.niveau} · {a.type} ({a.tache_id})</div>)
          : <p className="vide">Rien à décider.</p>}
      </div>
      <div className="section"><div className="tete"><h4>Activité récente</h4></div>
        {activite.length ? <ListeActivite activite={activite} max={6} /> : <p className="vide">Pas encore d'activité.</p>}</div>
    </>
  );
}

function Details({ objet, insp, approbations, demo, activite, priorite, modifierMeta, decider, voirTout }: {
  objet: ObjetBoard; insp: Inspection | null; approbations: Approbation[]; demo: boolean;
  activite: { cle: string; texte: string; ts: number; agent?: string }[];
  priorite: (id: string, p: Priorite) => void; modifierMeta: (o: ObjetBoard, meta: ObjetBoard["meta"]) => void;
  decider: (id: string, accord: boolean) => Promise<void>; voirTout: () => void;
}) {
  const m = objet.mission;
  const [nouveauTag, setNouveauTag] = useState<string | null>(null);
  const [decides, setDecides] = useState<Record<string, string>>({});
  const tags = (objet.meta.tags ?? insp?.tags ?? []) as string[];
  const enAttente = demo
    ? (insp?.taches ?? []).flatMap((t) => t.approbations.filter((a) => a.statut === "en_attente").map((a) => ({ id: a.id, titre: "Maquettes UI finales", cree: a.cree })))
    : approbations.filter((a) => a.mission_id === objet.mission_id).map((a) => ({ id: a.id, titre: `${a.niveau} · ${a.type}`, cree: a.cree }));
  const encours = m?.taches.some((t) => ["LEASED", "RUNNING", "REVIEW"].includes(t.statut));
  return (
    <>
      <div className="section">
        <div className="p-entete">
          <IconeType type={objet.type} />
          <div style={{ minWidth: 0 }}>
            <h3>{objet.meta.titre || m?.objectif || objet.asset?.nom || objet.type}</h3>
            <span className="etiquette-type" style={{ height: 22, fontSize: 11 }}>{objet.type === "mission" ? <>✳ MISSION</> : objet.type.toUpperCase()}</span>
          </div>
          <span className="actions"><Star size={18} /><MoreHorizontal size={18} style={{ marginLeft: 14 }} /></span>
        </div>
        <dl className="grille-details">
          {m ? (
            <dd style={{ gridRow: "span 3", alignSelf: "start" }}>
              <span className="select-statut">{encours ? <Loader size={15} /> : <Check size={15} />}
                {m.statut === "SUCCEEDED" ? "Réussie" : m.statut === "FAILED" ? "Échouée" : encours ? "En cours" : "En file"}</span>
            </dd>
          ) : <dd style={{ gridRow: "span 3", alignSelf: "start" }} className="meta-carte">{objet.asset ? taille(objet.asset.taille) : ""}</dd>}
          <dt style={{ display: "contents" }} />
          <div style={{ display: "grid", gridTemplateColumns: "86px 1fr", gap: "12px 6px", gridRow: "span 3", whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--text-secondary)" }}>Priorité</span>
            <span className="choix-priorite">
              {objet.priorite ? <span className={`badge-p ${objet.priorite} doux`}>{objet.priorite}</span> : null}
              <span>{NIVEAUX[objet.priorite] ?? "Aucune"}</span>
              <select className="nodrag" aria-label="Priorité" value={objet.priorite} onChange={(e) => priorite(objet.id, e.target.value as Priorite)}>
                <option value="">Aucune</option><option value="P1">P1 Élevée</option><option value="P2">P2 Moyenne</option><option value="P3">P3 Basse</option>
              </select>
            </span>
            <span style={{ color: "var(--text-secondary)" }}>Échéance</span>
            <span><Calendar size={14} style={{ verticalAlign: -2, marginRight: 6 }} />{String(objet.meta.echeance ?? "—")}</span>
            <span style={{ color: "var(--text-secondary)" }}>Propriétaire</span>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="profil-avatar" style={{ width: 24, height: 24, fontSize: 11 }}>J</span>Vous</span>
          </div>
        </dl>
        {m && (
          <div className="p-progression" aria-label={`${m.faites} tâche(s) faite(s) sur ${m.total}`}>
            Progression<div className="barre"><span style={{ width: `${m.progression}%` }} /></div><output className="tab-num">{m.progression}%</output>
          </div>
        )}
        <div className="p-description">Description
          <p>{String(objet.meta.description ?? insp?.description
            // un élément analysé garde sa propre description : l'objectif de la mission d'analyse n'en est pas une
            ?? (objet.type === "mission" ? m?.objectif : objet.contenu?.slice(0, 280) || objet.asset?.nom) ?? "—")}</p>
        </div>
        <div className="tags">
          {tags.map((t, i) => <span key={t} className={`tag c${i % 3}`}>#{t}</span>)}
          {nouveauTag === null ? (
            <button type="button" className="bouton-rond" style={{ width: 26, height: 26 }} aria-label="Ajouter une étiquette" onClick={() => setNouveauTag("")}><Plus size={14} /></button>
          ) : (
            <input className="champ" style={{ width: 120, height: 26 }} autoFocus value={nouveauTag} aria-label="Nouvelle étiquette" maxLength={30}
              onChange={(e) => setNouveauTag(e.target.value.replace(/[#\s]/g, ""))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && nouveauTag) {
                  modifierMeta(objet, { ...objet.meta, tags: [...tags, nouveauTag].slice(0, 12) });
                  setNouveauTag(null);
                }
                if (e.key === "Escape") setNouveauTag(null);
              }} onBlur={() => setNouveauTag(null)} />
          )}
        </div>
      </div>
      {insp && (
        <div className="section">
          <div className="tete"><h4>Tâches ({insp.taches.filter((t) => t.statut === "SUCCEEDED").length}/{insp.taches.length})</h4>
            <button type="button" className="bouton" style={{ height: 28, color: "var(--brand-indigo-soft)" }} disabled title="La délégation de sous-tâches arrive avec le compilateur de missions (M4)"><Plus size={14} /> Ajouter</button></div>
          <ul className="liste-taches">
            {insp.taches.map((t) => {
              const e = t.statut === "SUCCEEDED" ? "faite" : ["LEASED", "RUNNING", "REVIEW"].includes(t.statut) ? "encours" : "";
              return <li key={t.id} className={e === "faite" ? "faite" : ""} title={t.raison}>
                <span className={`case ${e}`}>{e === "faite" && <Check size={12} strokeWidth={3} />}</span>{libelleTache(t)}
                <span className="meta-carte" style={{ marginLeft: "auto", fontSize: 11 }}>{t.niveau}</span></li>;
            })}
          </ul>
        </div>
      )}
      {m && (
        <div className="section ligne-agents">Agents assignés
          <span className="pile">
            {m.agents.length ? m.agents.slice(0, 5).map((a) => <Avatar key={a.id} id={a.id} role={a.role} taille={32} statut={statutAgent(a)} titre={`${a.nom ?? a.executant ?? ""} ${a.fournisseur}`} />)
              : <span className="vide">aucun pour l'instant</span>}
            <button type="button" className="bouton-rond" aria-label="Affecter un agent" disabled title="L'affectation passe par l'ordonnanceur"><Plus size={15} /></button>
          </span>
        </div>
      )}
      {(m || enAttente.length > 0) && (
        <div className="section">
          <div className="tete"><h4><ShieldCheck size={17} /> Approbations</h4>
            {enAttente.length > 0 && <span className="compte-attente">{enAttente.length} en attente</span>}</div>
          {enAttente.length ? enAttente.map((a) => (
            <div key={a.id} className="approbation">
              <span className="icone"><FileText size={13} /></span>
              <div><div className="titre">{a.titre}</div><div className="quand">{ilya(a.cree)}</div></div>
              <div className="actions">
                {decides[a.id] ? <span className="meta-carte">{decides[a.id]}</span> : (
                  <>
                    <button type="button" className="bouton succes" onClick={async () => { await decider(a.id, true); setDecides((d) => ({ ...d, [a.id]: demo ? "Approuvée (démo)" : "Approuvée" })); }}>Approuver</button>
                    <button type="button" className="bouton danger" onClick={async () => { await decider(a.id, false); setDecides((d) => ({ ...d, [a.id]: demo ? "Refusée (démo)" : "Refusée" })); }}>Refuser</button>
                  </>
                )}
              </div>
            </div>
          )) : <p className="vide">Aucune décision attendue de ta part.</p>}
        </div>
      )}
      <div className="section">
        <div className="tete"><h4>Activité récente</h4><button type="button" className="lien-texte" onClick={voirTout}>Voir tout</button></div>
        {activite.length ? <ListeActivite activite={activite} max={3} /> : <p className="vide">Pas encore d'activité.</p>}
      </div>
    </>
  );
}
