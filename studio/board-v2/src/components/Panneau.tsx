import { memo, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, CircleDashed, Copy, FileText, Folder, Image as IconeImage, Link2, Loader, Music, Play, Plus, ShieldCheck, Target, Users, Video, X } from "lucide-react";
import type { Approbation, Evenement, ObjetBoard, Priorite, ReglagesBoard } from "../types";
import type { Inspection, Source } from "../api";
import { ilya, libelleTache, taille } from "../lib/format";
import { rendreNote } from "../lib/markdown";
import { Avatar } from "./Avatar";
import { statutAgent } from "../nodes/CartesVivantes";
import { etatJarvis } from "../nodes/CardShell";
import { CONTEXTUALISABLES } from "../nodes/contexte";
import { LigneCredit } from "../cartes/Provenance";
import { provenance } from "../cartes/etat";

type Onglet = "details" | "activite" | "commentaires";
const NIVEAUX: Record<string, string> = { P1: "Élevée", P2: "Moyenne", P3: "Basse" };

export function decrireEvenement(e: Evenement | Inspection["chronologie"][number]): string {
  const d = e.donnees as Record<string, string | boolean | string[] | undefined>;
  switch (e.type) {
    case "demo": return String(d.texte ?? "");
    case "board_objet": return `Objet ${d.type ?? ""} ajouté au Board`;
    case "board_maj": return `Objet modifié (${(d.champs as string[] | undefined)?.join(", ") ?? ""})`;
    case "board_supprime": return "Suppression sur le Board";
    case "board_restaure": return "Restauration sur le Board";
    case "board_lien": return "Relation créée";
    case "board_fichier": return `Fichier ${d.famille ?? ""} téléversé`;
    case "board_commentaire": return "Commentaire ajouté";
    case "board_propositions": return `Jarvis a contextualisé l'élément (${d.n ?? 0} ${Number(d.n) > 1 ? "actions proposées" : "action proposée"}${Number(d.liens) ? `, ${d.liens} ${Number(d.liens) > 1 ? "liens" : "lien"}` : ""})`;
    case "outils": return `Outils : ${((d.outils as unknown as { outil: string; detail: string }[]) ?? []).map((o) => `${o.outil} ${o.detail}`).join(" · ")}`;
    case "reglages_board": return "Réglages du chef modifiés";
    case "board_proposition": return `Proposition ${d.decision === "lancer" ? "lancée" : "écartée"}`;
    case "tache_creee": return "Tâche créée";
    case "mission_creee": return `Mission créée (${d.source ?? ""})`;
    case "mission_etat": return `Mission ${String(d.vers ?? "").toLowerCase()}`;
    case "tache_etat": return `Tâche : ${d.de} → ${d.vers}${d.raison ? ` — ${d.raison}` : ""}`;
    case "artefact": return `Livrable reçu de ${d.fournisseur}${d.factice ? " (factice)" : ""}`;
    case "approbation": return `Approbation ${d.decision} par ${d.par}`;
    case "resultat_perime": return "Résultat périmé refusé";
    default: return e.type.replace(/_/g, " ");
  }
}

const NOMS_TYPES: Record<string, string> = { note: "Note", texte: "Texte", mission: "Mission", image: "Image", capture: "Capture", lien: "Lien", audio: "Audio",
  video: "Vidéo", pdf: "PDF", document: "Document", dossier: "Dossier", agents: "Équipe d'agents", plan: "Plan", tache: "Tâche" };

/** La rubrique de la carte : une icône au trait et le nom du type, au-dessus du titre. */
function Rubrique({ type }: { type: string }) {
  const I = type === "mission" ? Target : type === "image" || type === "capture" ? IconeImage : type === "lien" ? Link2 : type === "audio" ? Music
    : type === "video" ? Video : type === "dossier" ? Folder : type === "agents" ? Users : FileText;
  return <span className="p-rubrique"><I size={16} aria-hidden />{NOMS_TYPES[type] ?? type.charAt(0).toUpperCase() + type.slice(1)}</span>;
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
  reglages?: ReglagesBoard;
  regler: (v: Partial<ReglagesBoard>) => Promise<void>;
}

export const Panneau = memo(function Panneau({ source, objet, objets, evenements, approbations, tick, priorite, modifierMeta, decider, contextualiser, deciderProposition, reglages, regler }: Props) {
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
        {([["details", "Détails"], ["activite", "Activité"], ["commentaires", "Commentaires"]] as [Onglet, string][]).map(([k, nom]) => (
          <button key={k} role="tab" aria-selected={onglet === k} onClick={() => setOnglet(k)}>{nom}
            {k === "commentaires" && comms.length > 0 && <span className="compte">{comms.length}</span>}</button>
        ))}
      </div>
      <div className="panneau-corps">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={`${onglet}-${objet?.id ?? "aucun"}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
            {onglet === "details" && (objet
              ? <>
                  <SectionJarvis objet={objet} contextualiser={contextualiser} deciderProposition={deciderProposition} />
                  <Details objet={objet} insp={insp} approbations={approbations} demo={source.demo} activite={activite}
                    priorite={priorite} modifierMeta={modifierMeta} decider={decider} voirTout={() => setOnglet("activite")} />
                </>
              : <><ReglagesJarvis reglages={reglages} regler={regler} /><Apercu objets={objets} approbations={approbations} activite={activite} /></>)}
            {onglet === "activite" && (
              <div className="section">
                {activite.length ? <ListeActivite activite={activite} /> : <p className="vide">Aucune activité enregistrée pour l'instant</p>}
              </div>
            )}
            {onglet === "commentaires" && (
              <div className="section fil-commentaires">
                {!objet && <p className="vide">Sélectionne une carte pour lire ou écrire ses commentaires</p>}
                {comms.map((c) => <div key={c.id} className="commentaire"><div className="qui">{c.auteur} · {ilya(c.cree)}</div>{c.texte}</div>)}
                {objet && (
                  <form onSubmit={async (e) => {
                    e.preventDefault();
                    if (!brouillon.trim()) return;
                    await source.commenter(objet.id, brouillon.trim());
                    setBrouillon("");
                    setComms(await source.commentaires(objet.id));
                  }}>
                    <textarea className="champ zone-commentaire" placeholder="Commentaire" value={brouillon}
                      onChange={(e) => setBrouillon(e.target.value)} maxLength={4000} aria-label="Nouveau commentaire" />
                    <div className="ligne-actions">
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

/** Ce que le chef a le droit de faire seul. Les actions L2/L3 attendent toujours ton accord, quel que soit le réglage. */
function ReglagesJarvis({ reglages, regler }: { reglages?: ReglagesBoard; regler: (v: Partial<ReglagesBoard>) => Promise<void> }) {
  if (!reglages) return null;
  const ligne = (cle: keyof ReglagesBoard, titre: string, aide: string) => (
    <label className="interrupteur">
      <input type="checkbox" role="switch" checked={reglages[cle]} onChange={(e) => regler({ [cle]: e.target.checked })} />
      <span className="piste" aria-hidden />
      <span><b>{titre}</b><small>{aide}</small></span>
    </label>
  );
  return (
    <section className="section section-jarvis" aria-label="Autonomie de Jarvis">
      <div className="tete"><h4>Autonomie de Jarvis</h4></div>
      {ligne("auto_analyse", "Analyser ce que je dépose", "Résumé, contexte, liens vers les autres cartes du projet")}
      {ligne("actions_auto", "Lancer seul les actions sans risque", "Une action L1 par élément (rédiger, résumer, comparer). Rien d'externe.")}
      <p className="vide">Envoyer, publier, postuler ou modifier tes fichiers attend toujours ton accord</p>
    </section>
  );
}

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
      <div className="tete"><h4>Jarvis</h4>
        {e?.etat !== "analyse" && (
          <button type="button" className="lien-texte" onClick={() => contextualiser(objet.id)}>{e ? "Relancer l'analyse" : "Analyser avec Jarvis"}</button>
        )}</div>
      {!e && <p className="vide">Pas encore analysé</p>}
      {e && e.etat !== "pret" && <p className={`vide etat-${e.etat}`}>{e.etat === "analyse" ? <Loader size={16} className="tourne" /> : null}{e.texte}</p>}
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
                  <Play size={16} />{p.niveau === "L1" ? "Lancer" : "Préparer"}</button>
                <button type="button" className="bouton" aria-label={`Écarter « ${p.titre} »`} disabled={occupe !== null}
                  onClick={async () => { setOccupe(i); await deciderProposition(objet, i, "ecarter"); setOccupe(null); }}><X size={16} />Écarter</button>
              </div>
            ) : <span className="meta-carte">{p.statut === "lancee" ? (p.par?.startsWith("jarvis") ? "Lancée par Jarvis" : "Lancée") : "Écartée"}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Dernier livrable accepté par la revue (sinon le dernier reçu, signalé) : le texte réel, jamais un résumé inventé. */
function Livrable({ artefacts }: { artefacts: Inspection["artefacts"] }) {
  const [tout, setTout] = useState(false);
  const [copie, setCopie] = useState(false);
  const a = [...artefacts].reverse().find((x) => x.revue === "acceptee") ?? artefacts[artefacts.length - 1];
  if (!a) return null;
  const long = a.contenu.length > 900;
  return (
    <section className="section section-livrable" aria-label="Livrable">
      <div className="tete"><h4><FileText size={16} />Livrable</h4>
        <p className="credit points"><b>{a.fournisseur}</b>{a.factice && a.fournisseur !== "factice" ? <span>factice</span> : null}{a.revue !== "acceptee" ? <span>refusé par la revue</span> : null}</p></div>
      <div className={`livrable-texte${long && !tout ? " replie" : ""}`}>{rendreNote(a.contenu)}</div>
      <div className="livrable-actions">
        {long && <button type="button" className="lien-texte" onClick={() => setTout((v) => !v)}>{tout ? "Réduire" : "Tout afficher"}</button>}
        <button type="button" className="bouton" onClick={async () => {
          await navigator.clipboard?.writeText(a.contenu).catch(() => undefined);
          setCopie(true);
          window.setTimeout(() => setCopie(false), 1500);
        }}><Copy size={16} />{copie ? "Copié" : "Copier"}</button>
      </div>
    </section>
  );
}

function ListeActivite({ activite, max }: { activite: { cle: string; texte: string; ts: number; agent?: string }[]; max?: number }) {
  return (
    <ul className="activite">
      {activite.slice(0, max).map((a) => (
        <li key={a.cle}>
          {a.agent ? <Avatar id={a.agent} role={a.agent} taille={32} /> : <span className="sans-agent"><CircleDashed size={16} /></span>}
          <span>{a.texte.split(" ").map((m, i) => (i === 0 && a.agent ? <b key={i}>{m} </b> : `${m} `))}</span>
          <span className="quand">{ilya(a.ts)}</span>
        </li>
      ))}
    </ul>
  );
}

function Apercu({ objets, approbations, activite }: { objets: ObjetBoard[]; approbations: Approbation[]; activite: { cle: string; texte: string; ts: number }[] }) {
  return (
    <>
      <div className="section">
        <div className="tete"><h4>Board</h4><span className="compte">{objets.length} carte{objets.length > 1 ? "s" : ""}</span></div>
        <p className="vide">Sélectionne une carte pour voir ses détails, son activité et ses commentaires</p>
      </div>
      <div className="section">
        <div className="tete"><h4><ShieldCheck size={16} />Approbations</h4>{approbations.length > 0 && <span className="compte-attente">{approbations.length} en attente</span>}</div>
        {approbations.length ? approbations.map((a) => <div key={a.id} className="ligne-approbation"><span className="niveau">{a.niveau}</span>{a.type.replace(/_/g, " ")}<span className="compte">{a.tache_id}</span></div>)
          : <p className="vide">Rien à décider</p>}
      </div>
      <div className="section"><div className="tete"><h4>Activité récente</h4></div>
        {activite.length ? <ListeActivite activite={activite} max={6} /> : <p className="vide">Pas encore d'activité</p>}</div>
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
    ? (insp?.taches ?? []).flatMap((t) => t.approbations.filter((a) => a.statut === "en_attente").map((a) => ({ id: a.id, titre: libelleTache(t), cree: a.cree })))
    : approbations.filter((a) => a.mission_id === objet.mission_id).map((a) => ({ id: a.id, titre: `${a.niveau} · ${a.type.replace(/_/g, " ")}`, cree: a.cree }));
  const encours = m?.taches.some((t) => ["LEASED", "RUNNING", "REVIEW"].includes(t.statut));
  const credit = provenance(objet);
  const description = objet.meta.description ?? insp?.description
    // un élément analysé garde sa propre description : l'objectif de la mission d'analyse n'en est pas une
    // à défaut, le début du texte de la carte, sans ses marques de mise en forme
    ?? (objet.type === "mission" ? m?.objectif : objet.contenu?.slice(0, 280).replace(/\*\*|__|^#+\s*/gm, "").replace(/\s*\n+- /g, " · ").replace(/\n+/g, " ") || objet.asset?.nom);
  return (
    <>
      <div className="section">
        <div className="p-entete">
          <Rubrique type={objet.type} />
          <h3>{objet.meta.titre || m?.objectif || objet.asset?.nom || NOMS_TYPES[objet.type] || objet.type}</h3>
          {credit && <LigneCredit p={credit} />}
        </div>
        <dl className="grille-details">
          {m && <><dt>Statut</dt><dd className={`p-statut${encours ? " en-cours" : ""}`}>{encours ? <Loader size={16} className="tourne" /> : m.statut === "SUCCEEDED" ? <Check size={16} /> : null}
            {m.statut === "SUCCEEDED" ? "Réussie" : m.statut === "FAILED" ? "Échouée" : encours ? "En cours" : "En file"}</dd></>}
          {!m && objet.asset && <><dt>Taille</dt><dd className="chiffre">{taille(objet.asset.taille)}</dd></>}
          <dt>Priorité</dt>
          <dd><span className="choix-priorite">
            {objet.priorite ? <span className={`badge-p ${objet.priorite} doux`}>{objet.priorite}</span> : null}
            <span>{NIVEAUX[objet.priorite] ?? "Aucune"}</span>
            <select className="nodrag" aria-label="Priorité" value={objet.priorite} onChange={(e) => priorite(objet.id, e.target.value as Priorite)}>
              <option value="">Aucune</option><option value="P1">P1 Élevée</option><option value="P2">P2 Moyenne</option><option value="P3">P3 Basse</option>
            </select>
          </span></dd>
          {Boolean(objet.meta.echeance) && <><dt>Échéance</dt><dd className="chiffre">{String(objet.meta.echeance)}</dd></>}
          <dt>Propriétaire</dt><dd>Toi</dd>
        </dl>
        {m && (
          <div className="p-progression" aria-label={`${m.faites} sur ${m.total} tâche${m.total > 1 ? "s" : ""}`}>
            Progression<div className="barre"><span style={{ transform: `scaleX(${m.progression / 100})` }} /></div><output>{m.progression}%</output>
          </div>
        )}
        {Boolean(description) && <div className="p-description">Description<p>{String(description)}</p></div>}
        <div className="tags">
          {tags.map((t) => <span key={t} className="tag">#{t}</span>)}
          {nouveauTag === null ? (
            <button type="button" className="ajout-tag" aria-label="Ajouter une étiquette" onClick={() => setNouveauTag("")}><Plus size={16} /></button>
          ) : (
            <input className="champ champ-tag" autoFocus value={nouveauTag} aria-label="Nouvelle étiquette" maxLength={30}
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
          <div className="tete"><h4>Tâches</h4><span className="compte">{insp.taches.filter((t) => t.statut === "SUCCEEDED").length}/{insp.taches.length}</span></div>
          <ul className="liste-taches">
            {insp.taches.map((t) => {
              const e = t.statut === "SUCCEEDED" ? "faite" : ["LEASED", "RUNNING", "REVIEW"].includes(t.statut) ? "encours" : "";
              return <li key={t.id} className={e === "faite" ? "faite" : ""} title={t.raison}>
                <span className={`case ${e}`}>{e === "faite" && <Check size={12} className="trait-fort" />}</span>{libelleTache(t)}
                <span className="niveau">{t.niveau}</span></li>;
            })}
          </ul>
        </div>
      )}
      {insp && <Livrable artefacts={insp.artefacts} />}
      {m && (
        <div className="section ligne-agents">Agents assignés
          <span className="pile">
            {m.agents.length ? m.agents.slice(0, 5).map((a) => <Avatar key={a.id} id={a.id} role={a.role} taille={32} statut={statutAgent(a)} titre={`${a.nom ?? a.executant ?? ""} ${a.fournisseur}`} />)
              : <span className="vide">Aucun pour l'instant</span>}
          </span>
        </div>
      )}
      {(m || enAttente.length > 0) && (
        <div className="section">
          <div className="tete"><h4><ShieldCheck size={16} />Approbations</h4>
            {enAttente.length > 0 && <span className="compte-attente">{enAttente.length} en attente</span>}</div>
          {enAttente.length ? enAttente.map((a) => (
            <div key={a.id} className="approbation">
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
          )) : <p className="vide">Aucune décision attendue de ta part</p>}
        </div>
      )}
      <div className="section">
        <div className="tete"><h4>Activité récente</h4><button type="button" className="lien-texte" onClick={voirTout}>Voir tout</button></div>
        {activite.length ? <ListeActivite activite={activite} max={3} /> : <p className="vide">Pas encore d'activité</p>}
      </div>
    </>
  );
}
