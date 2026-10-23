import { memo } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import { ClipboardList, GitBranch, Loader, Wrench } from "lucide-react";
import type { DonneesNoeud } from "../types";
import { Avatar } from "../components/Avatar";
import { CardShell } from "./CardShell";

type P = NodeProps<Node<DonneesNoeud>>;
type Element = { issue: string; role: string; agent: string; modele: string; desc: string; lance: boolean };

const STATUT_PLAN: Record<string, string> = { en_attente: "À valider", approuve: "Approuvé", refuse: "Refusé" };

/** Plan du chef (Telegram ou terminal), tel qu'il a été proposé ou validé : ses tâches et leur affectation. */
export const PlanNode = memo(function PlanNode({ data, selected }: P) {
  const o = data.objet;
  const m = o.meta as Record<string, unknown>;
  const elements = (m.elements as Element[] | undefined) ?? [];
  const statut = String(m.statut ?? "");
  return (
    <CardShell objet={o} selected={selected} classe="c-plan" entete={false}>
      <div className="contenu">
        <div className="ligne1">
          <span className="icone-plan"><ClipboardList size={22} /></span>
          <span className="etiquette-type">PLAN {String(m.plan_id ?? "")}</span>
          <span className={`statut-pill ${statut === "approuve" ? "reussie" : statut === "refuse" ? "echec" : "attente"}`}>
            {STATUT_PLAN[statut] ?? statut}</span>
        </div>
        <h3>{String(m.titre ?? "Plan")}</h3>
        {Boolean(m.resume) && <p className="meta-carte">{String(m.resume)}</p>}
        <ul className="elements-plan">
          {elements.slice(0, 6).map((e) => (
            <li key={e.issue} className={e.lance ? "lance" : ""}>
              <b>{e.issue}</b> <span>{e.role || "généraliste"}</span>
              <span className="modele">{e.modele || e.agent}</span>
              {e.desc && <small>{e.desc}</small>}
            </li>
          ))}
        </ul>
        <p className="meta-carte">Mode {String(m.mode ?? "vague")} · proposé par {String(m.origine ?? "le chef")}</p>
      </div>
    </CardShell>
  );
});

function depuis(ts: unknown): string {
  const s = typeof ts === "number" ? Date.now() / 1000 - ts : 0;
  return s <= 0 ? "" : s < 3600 ? `${Math.max(1, Math.floor(s / 60))} min` : `${Math.floor(s / 3600)} h`;
}

/** Une tâche confiée à un agent de code : qui (rôle, modèle), sur quoi (issue, worktree), où il en est. */
export const TacheNode = memo(function TacheNode({ data, selected }: P) {
  const o = data.objet;
  const m = o.meta as Record<string, unknown>;
  const actif = Boolean(m.actif);
  const statut = String(m.statut ?? "");
  return (
    <CardShell objet={o} selected={selected} classe={`c-tache${actif ? " active" : ""}`} entete={false}>
      <div className="contenu">
        <div className="ligne1">
          <span className="etiquette-type"><Wrench size={13} /> TÂCHE {String(m.issue ?? "")}</span>
          <span className={`statut-pill ${actif ? "en-cours" : statut === "terminé" ? "reussie" : "attente"}`}>
            {actif && <Loader size={15} className="tourne" />}{statut}{actif && m.debut ? ` · ${depuis(m.debut)}` : ""}</span>
        </div>
        <div className="agent-tache">
          <Avatar id={String(m.role ?? "agent")} role={String(m.role_titre ?? m.role ?? "agent")} taille={52}
            statut={actif ? "actif" : statut === "terminé" ? "termine" : "attente"} fournisseur={String(m.agent ?? "")}
            titre={`${String(m.role_titre ?? "")} — ${String(m.modele || m.agent || "")}`} />
          <div>
            <b>{String(m.role_titre ?? m.role ?? "Agent")}</b>
            <span className="modele">{String(m.modele || m.agent || "modèle ?")}{m.effort ? ` · ${String(m.effort)}` : ""}</span>
            <span className="meta-carte"><GitBranch size={12} /> {String(m.worktree ?? "")}</span>
          </div>
        </div>
        {Boolean(m.verdict) && <p className="meta-carte">Verdict : {String(m.verdict)}</p>}
        {Number(m.essai) > 1 && <p className="meta-carte">Essai n° {String(m.essai)}</p>}
      </div>
    </CardShell>
  );
});
