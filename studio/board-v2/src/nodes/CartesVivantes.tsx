import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import { Bold, Check, FileText, Italic, List, Loader, Pencil, Target, Underline, Users, Wrench, X } from "lucide-react";
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
    <CardShell objet={o} selected={selected} sources={data.sources} classe="c-note">
      <div className="entete">
        <FileText size={20} aria-hidden />
        <div className="titre-carte">{o.meta.titre || "Note"}</div>
      </div>
      <div className="barre-format nodrag" role="toolbar" aria-label="Mise en forme">
        <button type="button" aria-label="Gras" onClick={() => entourer("**")}><Bold size={20} /></button>
        <button type="button" aria-label="Italique" onClick={() => entourer("*")}><Italic size={20} /></button>
        <button type="button" aria-label="Souligné" onClick={() => entourer("__")}><Underline size={20} /></button>
        <button type="button" aria-label="Liste" onClick={() => entourer("\n- ", "")}><List size={20} /></button>
        <button type="button" aria-label="Modifier le texte" onClick={() => (edition ? terminer() : setEdition(true))}>
          {edition ? <Check size={20} /> : <Pencil size={20} />}
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
      <CardShell objet={o} selected={selected} sources={data.sources} classe="c-mission" entete={false}>
        <div className="contenu"><h3>Mission introuvable</h3><p className="meta-carte">La mission liée n'existe plus</p></div>
      </CardShell>
    );
  }
  const s = statutMission(m);
  const agents = m.agents;
  return (
    <CardShell objet={o} selected={selected} sources={data.sources} classe="c-mission" entete={false}>
      <div className="contenu" onDoubleClick={() => a.inspecter(o.id)}>
        <div className="ligne1">
          <span className="etiquette-type"><Target size={20} aria-hidden />Mission</span>
          <span className={`statut-pill ${s.classe}`}>
            {s.classe === "en-cours" ? <Loader size={20} className="tourne" /> : <i className="point-statut" aria-hidden />}
            {s.libelle}{s.classe === "en-cours" && <DepuisTravail agents={agents} />}
          </span>
        </div>
        <h3>{o.meta.titre || m.objectif}</h3>
        <div className="progression" aria-label={`Progression : ${m.faites} sur ${m.total} tâche${m.total > 1 ? "s" : ""}`}>
          <div className="barre"><span style={{ transform: `scaleX(${m.progression / 100})` }} /></div>
          <output className="tab-num">{m.faites} / {m.total}</output>
        </div>
        <ul className="etapes">
          {m.taches.slice(0, 4).map((t) => {
            const etat = t.statut === "SUCCEEDED" ? "faite" : ["LEASED", "RUNNING", "REVIEW"].includes(t.statut) ? "encours"
              : ["FAILED", "CANCELLED", "EXPIRED"].includes(t.statut) ? "echec" : "attente";
            return (
              <li key={t.id} className={etat === "encours" ? "encours" : ""}>
                <span className={`coche ${etat}`}>{etat === "faite" ? <Check size={16} className="trait-fort" /> : etat === "echec" ? <X size={16} className="trait-fort" /> : null}</span>
                <span className="libelle-etape">{libelleTache(t)}</span>
                {t.niveau && <span className="niveau" title={t.niveau === "L1" ? "Sans effet externe" : "Attend ton accord avant toute action externe"}>{t.niveau}</span>}
              </li>
            );
          })}
          {m.taches.length > 4 && <li className="meta-carte">+ {m.taches.length - 4} autres tâches</li>}
        </ul>
        <OutilsAgents agents={agents} />
        <div className="bas">
          {o.meta.echeance ? <span>Échéance <span className="date">{String(o.meta.echeance)}</span></span> : null}
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

/** Depuis quand l'agent en cours travaille (tentative réelle, sans fin) ; actualisé toutes les 30 s. */
function DepuisTravail({ agents }: { agents: AgentResume[] }) {
  const [, rafraichir] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => rafraichir((n) => n + 1), 30_000);
    return () => window.clearInterval(t);
  }, []);
  const ag = agents.find((x) => !x.fin);
  if (!ag) return null;
  return <span className="depuis" title="Durée de travail de l'agent en cours"> · {dureeDepuis(ag.debut)}</span>;
}

const ISSUES: Record<string, string> = { reussi: "terminé", echec: "échec", annule: "annulé", expire: "expiré" };

/** Durée bornée (min, puis h, puis j) depuis un horodatage en secondes. */
function dureeDepuis(debut: number): string {
  const s = Math.max(0, Date.now() / 1000 - debut);
  return s < 60 ? "< 1 min" : s < 3600 ? `${Math.floor(s / 60)} min` : s < 86400 ? `${Math.floor(s / 3600)} h` : `${Math.floor(s / 86400)} j`;
}

/** Depuis quand cet agent travaille (tentative réelle, sans fin) ; actualisé toutes les 30 s. */
function DepuisAgent({ debut }: { debut: number }) {
  const [, rafraichir] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => rafraichir((n) => n + 1), 30_000);
    return () => window.clearInterval(t);
  }, []);
  return <>{dureeDepuis(debut)}</>;
}

/** Dernière action réelle de l'équipe (outils déclarés par l'exécutant) : ce qui a été lu ou utilisé. */
function OutilsAgents({ agents }: { agents: AgentResume[] }) {
  const ag = agents.find((x) => x.outils?.length);
  if (!ag) return null;
  const [nom] = NOMS_ROLES[ag.role] ?? [ag.role];
  return (
    <p className="outils-mission" title={ag.outils!.map((x) => `${x.outil} ${x.detail}`).join(" · ")}>
      <Wrench size={16} aria-hidden /><b>{nom}</b> {ag.outils!.map((x) => `${x.outil} · ${x.detail}`).join(" ; ")}
    </p>
  );
}

/* ---------------------------------------------------------------- équipe d'agents -------------------------- */
const NOMS_ROLES: Record<string, [string, string]> = {
  contextualiser: ["Chef", "Contexte"], preparer: ["Rédacteur", "Préparation"],
  recherche: ["Analyste", "Recherche"], analyse_document: ["Analyste", "Analyse"], design: ["Designer", "UI/UX"],
  developpement: ["Développeur", "Code"], tests: ["Testeur", "Qualité"], redaction: ["Rédacteur", "Contenu"],
};

type Membre = { id: string; role: string; titre: string; modele: string; agent: string; statut: string; actif: boolean; issue: string; depuis: string };

/** Équipe d'un projet (agents de code du chef) : chaque agent, son rôle, son modèle et ce qu'il fait maintenant. */
function EquipeProjet({ o, selected }: { o: P["data"]["objet"]; selected: boolean }) {
  const membres = (o.meta.membres as Membre[]) ?? [];
  const actifs = membres.filter((x) => x.actif).length;
  return (
    <CardShell objet={o} selected={selected} classe="c-agents" entete={false}>
      <div className="entete">
        <Users size={20} aria-hidden />{String(o.meta.titre ?? "Équipe")}
        <span className="badge-actifs tab-num">{actifs ? `${actifs} au travail` : "au repos"}</span>
      </div>
      <ul className="liste-agents">
        {[...membres].sort((a, b) => Number(b.actif) - Number(a.actif)).slice(0, 4).map((ag) => (
          <li key={ag.id} className={ag.actif ? "actif" : undefined}>
            <Avatar id={ag.id} role={ag.titre} taille={44} point={ag.actif}
              fournisseur={ag.agent} titre={`${ag.titre} — ${ag.modele || ag.agent} — ${ag.statut}`} />
            <span className="qui"><span className="nom">{ag.titre}</span><span className="role">{ag.modele || ag.agent}</span></span>
            <span className="outil-agent">{ag.issue ? `${ag.issue} · ` : ""}{ag.statut}{ag.depuis ? ` · ${ag.depuis}` : ""}</span>
          </li>
        ))}
      </ul>
      {membres.length > 4 && <p className="meta-carte">+ {membres.length - 4} {membres.length - 4 > 1 ? "autres agents" : "autre agent"}</p>}
    </CardShell>
  );
}

export const AgentsNode = memo(function AgentsNode({ data, selected }: P) {
  const o = data.objet;
  if (!o.mission && Array.isArray(o.meta.membres)) return <EquipeProjet o={o} selected={selected} />;
  const agents = [...(o.mission?.agents ?? [])].sort((a, b) => Number(Boolean(a.fin || a.issue)) - Number(Boolean(b.fin || b.issue)) || b.debut - a.debut);
  const actifs = agents.filter((x) => !x.fin && !x.issue).length;
  return (
    <CardShell objet={o} selected={selected} sources={data.sources} classe="c-agents" entete={false}>
      <div className="entete">
        <Users size={20} aria-hidden />Équipe d'agents
        <span className="badge-actifs tab-num">{actifs} actif{actifs > 1 ? "s" : ""}</span>
      </div>
      {agents.length ? (
        <ul className="liste-agents">
          {agents.slice(0, 4).map((ag) => {
            const [nom, role] = NOMS_ROLES[ag.role] ?? [ag.nom ?? ag.executant ?? "Agent", ag.role];
            const actif = !ag.fin && !ag.issue;
            const dernier = ag.outils?.length ? ag.outils[ag.outils.length - 1]! : null;
            return (
              <li key={ag.id} className={actif ? "actif" : undefined}>
                <Avatar id={ag.id} role={ag.nom ?? nom} taille={44} point={actif}
                  fournisseur={ag.fournisseur} titre={`${ag.nom ?? nom} — ${ag.fournisseur}${ag.executant ? ` sur ${ag.executant}` : ""}`} />
                <span className="qui"><span className="nom">{ag.nom ?? nom}</span><span className="role">{ag.nom ? ag.role : role}</span></span>
                <span className="outil-agent" title={ag.outils?.length ? ag.outils.map((x) => `${x.outil} ${x.detail}`).join(" · ") : undefined}>
                  {dernier ? dernier.outil : actif ? <DepuisAgent debut={ag.debut} /> : ISSUES[ag.issue ?? ""] ?? ag.issue}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="vide-agents">Aucun agent n'a encore travaillé sur cette mission.<br />Ils apparaîtront ici dès qu'un exécutant prendra une tâche.</div>
      )}
      {agents.length > 4 && <p className="meta-carte">+ {agents.length - 4} {agents.length - 4 > 1 ? "tentatives" : "tentative"} dans l'historique de la mission</p>}
    </CardShell>
  );
});
