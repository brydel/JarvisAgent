import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import { Bold, Calendar, Check, FileText, Italic, List, Loader, MoreHorizontal, Target, Underline, Users, Wrench, X } from "lucide-react";
import type { AgentResume, DonneesNoeud, MissionResume } from "../types";
import { libelleTache } from "../lib/format";
import { rendreNote } from "../lib/markdown";
import { Avatar, type StatutAgent } from "../components/Avatar";
import { CardShell, Tags } from "./CardShell";
import { useActions } from "./contexte";

type P = NodeProps<Node<DonneesNoeud>>;

/* ---------------------------------------------------------------- note ------------------------------------- */
export const NoteNode = memo(function NoteNode({ data, selected }: P) {
  const o = data.objet;
  const a = useActions();
  const [edition, setEdition] = useState(false);
  const [texte, setTexte] = useState(o.contenu);
  const zone = useRef<HTMLTextAreaElement>(null);
  const minuterie = useRef<number>(0);
  useEffect(() => {
    if (!edition) setTexte(o.contenu);
  }, [o.contenu, edition]);
  const enregistrer = useCallback((valeur: string) => {
    window.clearTimeout(minuterie.current);
    minuterie.current = window.setTimeout(() => {
      if (valeur === o.contenu) return;
      const historique = [{ ts: Date.now() / 1000, extrait: o.contenu.slice(0, 400) }, ...(o.meta.historique ?? [])].slice(0, 5);
      a.modifier(o.id, { contenu: valeur, meta: { ...o.meta, historique } });
    }, 600);
  }, [a, o.contenu, o.id, o.meta]);
  useEffect(() => () => window.clearTimeout(minuterie.current), []);
  const entourer = (avant: string, apres = avant) => {
    const z = zone.current;
    if (!edition || !z) {
      setEdition(true);
      return;
    }
    const { selectionStart: d, selectionEnd: f, value } = z;
    const v = value.slice(0, d) + avant + value.slice(d, f) + apres + value.slice(f);
    setTexte(v);
    enregistrer(v);
    requestAnimationFrame(() => z.setSelectionRange(d + avant.length, f + avant.length));
  };
  const terminer = () => {
    setEdition(false);
    window.clearTimeout(minuterie.current);
    if (texte !== o.contenu) {
      const historique = [{ ts: Date.now() / 1000, extrait: o.contenu.slice(0, 400) }, ...(o.meta.historique ?? [])].slice(0, 5);
      a.modifier(o.id, { contenu: texte, meta: { ...o.meta, historique } });
    }
  };
  return (
    <CardShell objet={o} selected={selected} classe="c-note">
      <div className="entete">
        <FileText size={24} />
        <div className="titre-carte">{o.meta.titre || "Note"}</div>
      </div>
      <div className="barre-format nodrag" role="toolbar" aria-label="Mise en forme">
        <button type="button" aria-label="Gras" onClick={() => entourer("**")}><Bold size={17} /></button>
        <button type="button" aria-label="Italique" onClick={() => entourer("*")}><Italic size={17} /></button>
        <button type="button" aria-label="Souligné" onClick={() => entourer("__")}><Underline size={17} /></button>
        <button type="button" aria-label="Liste" onClick={() => entourer("\n- ", "")}><List size={17} /></button>
        <button type="button" aria-label="Modifier le texte" onClick={() => (edition ? terminer() : setEdition(true))}>
          {edition ? <Check size={17} /> : <MoreHorizontal size={17} />}
        </button>
      </div>
      {edition ? (
        <textarea ref={zone} className="nodrag nowheel nopan" value={texte} autoFocus aria-label="Texte de la note" maxLength={50000}
          onChange={(e) => {
            setTexte(e.target.value);
            enregistrer(e.target.value);
          }}
          onBlur={terminer} onKeyDown={(e) => e.key === "Escape" && terminer()} />
      ) : (
        <div className="texte" onDoubleClick={() => setEdition(true)}>{rendreNote(o.contenu)}</div>
      )}
      <Tags tags={o.meta.tags} max={2} />
    </CardShell>
  );
});

/* ---------------------------------------------------------------- mission ---------------------------------- */
function statutMission(m: MissionResume): { classe: string; libelle: string } {
  if (m.statut === "SUCCEEDED") return { classe: "reussie", libelle: "Réussie" };
  if (m.statut === "FAILED") return { classe: "echouee", libelle: "Échouée" };
  if (m.statut === "CANCELLED") return { classe: "echouee", libelle: "Annulée" };
  if (m.taches.some((t) => ["LEASED", "RUNNING", "REVIEW"].includes(t.statut))) return { classe: "en-cours", libelle: "En cours" };
  if (m.approbations_en_attente) return { classe: "attente", libelle: "Attend ton accord" };
  return { classe: "attente", libelle: "En file" };
}

export function statutAgent(a: AgentResume): StatutAgent {
  if (a.issue === "reussi") return "termine";
  if (a.issue && a.issue !== "reussi") return "echec";
  return "actif";
}

export const MissionNode = memo(function MissionNode({ data, selected }: P) {
  const o = data.objet;
  const m = o.mission;
  const a = useActions();
  if (!m) {
    return (
      <CardShell objet={o} selected={selected} classe="c-mission" entete={false}>
        <div className="contenu"><h3>Mission introuvable</h3><p className="meta-carte">La mission liée n'existe plus.</p></div>
      </CardShell>
    );
  }
  const s = statutMission(m);
  const agents = m.agents;
  return (
    <CardShell objet={o} selected={selected} classe="c-mission" entete={false}>
      <div className="contenu" onDoubleClick={() => a.inspecter(o.id)}>
        <div className="ligne1">
          <span className="icone-mission"><Target size={26} /></span>
          <span className="etiquette-type">MISSION</span>
          <span className={`statut-pill ${s.classe}`}>
            {s.classe === "en-cours" ? <Loader size={17} className="tourne" /> : s.classe === "reussie" ? <Check size={17} /> : null}
            {s.libelle}
          </span>
        </div>
        <h3>{o.meta.titre || m.objectif}</h3>
        <div className="progression" aria-label={`Progression : ${m.faites} tâche(s) sur ${m.total}`}>
          <div className="barre"><span style={{ transform: `scaleX(${m.progression / 100})` }} /></div>
          <output className="tab-num">{m.progression}%</output>
        </div>
        <ul className="etapes">
          {m.taches.slice(0, 4).map((t) => {
            const etat = t.statut === "SUCCEEDED" ? "faite" : ["LEASED", "RUNNING", "REVIEW"].includes(t.statut) ? "encours"
              : ["FAILED", "CANCELLED", "EXPIRED"].includes(t.statut) ? "echec" : "attente";
            return (
              <li key={t.id} className={etat === "encours" ? "encours" : ""}>
                <span className={`coche ${etat}`}>{etat === "faite" ? <Check size={15} strokeWidth={3} /> : etat === "echec" ? <X size={14} /> : null}</span>
                {libelleTache(t)}
              </li>
            );
          })}
          {m.taches.length > 4 && <li className="meta-carte">+ {m.taches.length - 4} autres tâches</li>}
        </ul>
        <OutilsAgents agents={agents} />
        <div className="bas">
          <Calendar size={19} />
          {o.meta.echeance ? <>Échéance <span className="date">{String(o.meta.echeance)}</span></> : <span>Sans échéance</span>}
          <span className="pile-avatars">
            {agents.slice(0, 2).map((ag) => (
              <Avatar key={ag.id} id={ag.id} role={ag.nom ?? (NOMS_ROLES[ag.role]?.[0] ?? ag.role)} taille={40} titre={`${ag.nom ?? NOMS_ROLES[ag.role]?.[0] ?? ag.executant ?? "agent"} — ${ag.fournisseur}`} />
            ))}
            {agents.length > 2 && <span className="plus tab-num">+{agents.length - 2}</span>}
          </span>
        </div>
      </div>
    </CardShell>
  );
});

/** Dernière action réelle de l'équipe (outils déclarés par l'exécutant) : ce qui a été lu ou utilisé. */
function OutilsAgents({ agents }: { agents: AgentResume[] }) {
  const ag = agents.find((x) => x.outils?.length);
  if (!ag) return null;
  const [nom] = NOMS_ROLES[ag.role] ?? [ag.role];
  return (
    <p className="outils-mission" title={ag.outils!.map((x) => `${x.outil} ${x.detail}`).join(" · ")}>
      <Wrench size={13} /> <b>{nom}</b> {ag.outils!.map((x) => `${x.outil} · ${x.detail}`).join(" ; ")}
    </p>
  );
}

/* ---------------------------------------------------------------- équipe d'agents -------------------------- */
const NOMS_ROLES: Record<string, [string, string]> = {
  contextualiser: ["Chef", "Contexte"], preparer: ["Rédacteur", "Préparation"],
  recherche: ["Analyste", "Recherche"], analyse_document: ["Analyste", "Analyse"], design: ["Designer", "UI/UX"],
  developpement: ["Développeur", "Code"], tests: ["Testeur", "Qualité"], redaction: ["Rédacteur", "Contenu"],
};

export const AgentsNode = memo(function AgentsNode({ data, selected }: P) {
  const o = data.objet;
  const agents = o.mission?.agents ?? [];
  const actifs = agents.filter((x) => !x.issue).length;
  return (
    <CardShell objet={o} selected={selected} classe="c-agents" entete={false}>
      <div className="entete">
        <Users size={19} /> ÉQUIPE D'AGENTS
        <span className="badge-actifs tab-num">{actifs} actif{actifs > 1 ? "s" : ""}</span>
      </div>
      {agents.length ? (
        <div className="grille-agents">
          {agents.slice(0, 4).map((ag) => {
            const [nom, role] = NOMS_ROLES[ag.role] ?? [ag.nom ?? ag.executant ?? "Agent", ag.role];
            return (
              <div key={ag.id} className="agent">
                <Avatar id={ag.id} role={ag.nom ?? nom} taille={80} statut={statutAgent(ag)} point={!ag.issue}
                  fournisseur={ag.fournisseur} titre={`${ag.nom ?? nom} — ${ag.fournisseur}${ag.executant ? ` sur ${ag.executant}` : ""}`} />
                <span className="nom">{ag.nom ?? nom}</span>
                <span className="role">{ag.nom ? ag.role : role}</span>
                {ag.outils?.[0] && <span className="outil-agent" title={ag.outils.map((x) => `${x.outil} ${x.detail}`).join(" · ")}>
                  <Wrench size={11} /> {ag.outils[ag.outils.length - 1]!.outil}</span>}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="vide-agents">Aucun agent n'a encore travaillé sur cette mission.<br />Ils apparaîtront ici dès qu'un exécutant prendra une tâche.</div>
      )}
    </CardShell>
  );
});
