import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import { Handle, NodeResizer, Position } from "@xyflow/react";
import { ArrowUpToLine, Copy, Lock, LockOpen, MoreHorizontal, PanelRight, Trash2 } from "lucide-react";
import type { ObjetBoard, Priorite } from "../types";
import { TAILLES, useActions } from "./contexte";

interface Props {
  objet: ObjetBoard;
  selected: boolean;
  classe: string;
  children: ReactNode;
  /** badge de priorité et menu en surimpression (cartes à visuel) ou laissés à la carte */
  entete?: boolean;
  ratio?: boolean;
}

const COTES = [Position.Top, Position.Right, Position.Bottom, Position.Left];

export const CardShell = memo(function CardShell({ objet, selected, classe, children, entete = true, ratio }: Props) {
  const t = TAILLES[objet.type] ?? TAILLES.note!;
  const verrou = Boolean(objet.verrouille);
  return (
    <>
      <NodeResizer isVisible={selected && !verrou} minWidth={t.min[0]} minHeight={t.min[1]} maxWidth={2400} maxHeight={2400}
        keepAspectRatio={ratio} />
      {COTES.map((p) => <Handle key={p} id={p} type="source" position={p} />)}
      <article className={`carte ${classe}${verrou ? " verrouillee" : ""}`} aria-label={objet.meta.titre || objet.type}>
        {entete && (
          <div className="entete-flottante">
            {objet.priorite ? <span className={`badge-p ${objet.priorite}`}>{objet.priorite}</span> : <span />}
            <MenuCarte objet={objet} />
          </div>
        )}
        {children}
      </article>
    </>
  );
});

export function BadgePriorite({ p }: { p: Priorite }) {
  return p ? <span className={`badge-p ${p}`}>{p}</span> : null;
}

export function MenuCarte({ objet }: { objet: ObjetBoard }) {
  const a = useActions();
  const [ouvert, setOuvert] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ouvert) return;
    const fermer = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOuvert(false);
    };
    const echap = (e: KeyboardEvent) => e.key === "Escape" && setOuvert(false);
    window.addEventListener("pointerdown", fermer);
    window.addEventListener("keydown", echap);
    return () => {
      window.removeEventListener("pointerdown", fermer);
      window.removeEventListener("keydown", echap);
    };
  }, [ouvert]);
  const faire = (f: () => void) => () => {
    f();
    setOuvert(false);
  };
  return (
    <div ref={ref} className="nodrag nopan" style={{ position: "relative" }}>
      <button type="button" className="menu-carte" aria-label="Actions de la carte" aria-haspopup="menu" aria-expanded={ouvert}
        onClick={() => setOuvert((v) => !v)}>
        <MoreHorizontal size={20} />
      </button>
      {ouvert && (
        <div role="menu" className="menu-deroulant">
          <div className="menu-priorites" role="group" aria-label="Priorité">
            {(["P1", "P2", "P3", ""] as Priorite[]).map((p) => (
              <button key={p || "aucune"} role="menuitemradio" aria-checked={objet.priorite === p} className={p ? `badge-p ${p}` : "badge-p aucune"}
                onClick={faire(() => a.priorite(objet.id, p))}>{p || "—"}</button>
            ))}
          </div>
          <button role="menuitem" onClick={faire(() => a.inspecter(objet.id))}><PanelRight size={16} /> Détails</button>
          <button role="menuitem" onClick={faire(() => a.dupliquer([objet.id]))}><Copy size={16} /> Dupliquer</button>
          <button role="menuitem" onClick={faire(() => a.devant([objet.id]))}><ArrowUpToLine size={16} /> Amener devant</button>
          <button role="menuitem" onClick={faire(() => a.modifier(objet.id, { verrouille: !objet.verrouille }))}>
            {objet.verrouille ? <><LockOpen size={16} /> Déverrouiller</> : <><Lock size={16} /> Verrouiller</>}
          </button>
          {objet.parent_id && <button role="menuitem" onClick={faire(() => a.sortirDuDossier(objet.id))}>Sortir du dossier</button>}
          <button role="menuitem" className="danger" onClick={faire(() => a.supprimer([objet.id]))}><Trash2 size={16} /> Supprimer</button>
        </div>
      )}
    </div>
  );
}

export function Tags({ tags, max = 3 }: { tags?: string[]; max?: number }) {
  if (!tags?.length) return null;
  return (
    <div className="tags">
      {tags.slice(0, max).map((t, i) => <span key={t} className={`tag c${i % 3}`}>#{t}</span>)}
      {tags.length > max && <span className="tag plus">+{tags.length - max}</span>}
    </div>
  );
}
