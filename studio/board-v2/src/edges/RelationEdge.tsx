import { memo, useState } from "react";
import {
  BaseEdge, EdgeLabelRenderer, Position, getBezierPath, useInternalNode, useReactFlow, type Edge, type EdgeProps, type InternalNode,
} from "@xyflow/react";
import { Sparkles, X } from "lucide-react";
import { contourDe } from "../outils/fleche";
import { pointSurContour } from "../outils/geometrie";
import type { CoteLien, DonneesNoeud, StyleLien } from "../types";

export interface DonneesLien extends Record<string, unknown> {
  libelle: string;
  style: StyleLien;
  renommer: (id: string, libelle: string) => void;
  auteur?: string;
  /** hors du cadre mis en avant (concentration, présentation) : trait atténué, étiquette masquée */
  estompe?: boolean;
  cotes?: { s: CoteLien; sf: number; t: CoteLien; tf: number; c?: number; lt?: number };
}

/** Un rendu distinct par type de relation : couleur ET tracé (le type se lit aussi sans la couleur). Le type n'a
 *  aujourd'hui aucun effet métier (blocage, relais de livrable) : il qualifie le lien, rien de plus. */
export const RENDU_RELATION: Record<StyleLien, { couleur: string; tirets?: string; epaisseur: number; nom: string }> = {
  defaut: { couleur: "var(--edge-default)", epaisseur: 2.6, nom: "Relation" },
  inspire: { couleur: "var(--edge-inspire)", tirets: "2 7", epaisseur: 3, nom: "Inspire" },
  alimente: { couleur: "var(--edge-alimente)", epaisseur: 3.4, nom: "Alimente" },
  utilise: { couleur: "var(--edge-utilise)", tirets: "7 7", epaisseur: 2.6, nom: "Utilisé par" },
  depend: { couleur: "var(--edge-depend)", tirets: "14 5 3 5", epaisseur: 2.8, nom: "Dépend de" },
};

const POS: Record<CoteLien, Position> = { top: Position.Top, right: Position.Right, bottom: Position.Bottom, left: Position.Left };

/** Point à la fraction f du côté donné (ancrage explicite). */
function ancre(n: InternalNode, cote: CoteLien, f: number): { x: number; y: number; cote: Position } {
  const { x, y } = n.internals.positionAbsolute;
  const w = n.measured.width ?? 0, h = n.measured.height ?? 0;
  const p = cote === "top" ? { x: x + w * f, y } : cote === "bottom" ? { x: x + w * f, y: y + h }
    : cote === "left" ? { x, y: y + h * f } : { x: x + w, y: y + h * f };
  return { ...p, cote: POS[cote] };
}

let mesureur: SVGPathElement | null = null;
/** Position de l'étiquette à la fraction lt du chemin (0,5 par défaut = milieu donné par React Flow). */
function pointSur(d: string, lt: number | undefined, cx: number, cy: number): [number, number] {
  if (lt === undefined || lt === 0.5 || typeof document === "undefined") return [cx, cy];
  mesureur ??= document.createElementNS("http://www.w3.org/2000/svg", "path");
  mesureur.setAttribute("d", d);
  const p = mesureur.getPointAtLength(mesureur.getTotalLength() * lt);
  return [p.x, p.y];
}

function centre(n: InternalNode) {
  const w = n.measured.width ?? 0;
  const h = n.measured.height ?? 0;
  return { x: n.internals.positionAbsolute.x + w / 2, y: n.internals.positionAbsolute.y + h / 2, w, h };
}

/** Point du bord de `a` sur la droite qui joint les centres de a et b, et le côté correspondant. Pour une forme
 *  (ellipse, losange), le point est sur son PÉRIMÈTRE RÉEL, pas sur sa boîte englobante. */
function bord(a: InternalNode, b: InternalNode): { x: number; y: number; cote: Position } {
  const ca = centre(a), cb = centre(b);
  const dx = cb.x - ca.x, dy = cb.y - ca.y;
  if (!dx && !dy) return { x: ca.x, y: ca.y, cote: Position.Right };
  const sx = ca.w / 2 / Math.abs(dx || 1e-9), sy = ca.h / 2 / Math.abs(dy || 1e-9);
  const s = Math.min(sx, sy);
  const cote = sx < sy ? (dx > 0 ? Position.Right : Position.Left) : (dy > 0 ? Position.Bottom : Position.Top);
  const objet = (a.data as Partial<DonneesNoeud>).objet;
  const contour = objet ? contourDe(objet) : "rectangle";
  if (contour !== "rectangle") {
    const p = pointSurContour(contour, { x: ca.x - ca.w / 2, y: ca.y - ca.h / 2, largeur: ca.w, hauteur: ca.h }, cb);
    return { ...p, cote };
  }
  return { x: ca.x + dx * s, y: ca.y + dy * s, cote };
}

export const RelationEdge = memo(function RelationEdge({ id, source, target, data, selected, markerEnd }: EdgeProps<Edge<DonneesLien>>) {
  const s = useInternalNode(source);
  const t = useInternalNode(target);
  const [edition, setEdition] = useState(false);
  const [valeur, setValeur] = useState(data?.libelle ?? "");
  const { deleteElements } = useReactFlow();
  if (!s || !t || !data) return null;
  const c = data.cotes;
  const a = c ? ancre(s, c.s, c.sf) : bord(s, t), b = c ? ancre(t, c.t, c.tf) : bord(t, s);
  const [chemin, cx, cy] = getBezierPath({ sourceX: a.x, sourceY: a.y, sourcePosition: a.cote, targetX: b.x, targetY: b.y, targetPosition: b.cote, curvature: c?.c ?? 0.35 });
  const [lx, ly] = pointSur(chemin, c?.lt, cx, cy);
  const rendu = RENDU_RELATION[data.style] ?? RENDU_RELATION.defaut;
  const couleur = rendu.couleur;
  return (
    <>
      <BaseEdge id={id} path={chemin} markerEnd={markerEnd} interactionWidth={18}
        style={{ stroke: couleur, strokeWidth: rendu.epaisseur + (selected ? 0.9 : 0), strokeDasharray: rendu.tirets, strokeLinecap: rendu.tirets ? "round" : undefined, color: couleur }} />
      {!data.estompe && (data.libelle || edition || selected) && (
        <EdgeLabelRenderer>
          <div className={`etiquette-lien nodrag nopan${data.auteur === "jarvis" ? " par-jarvis" : ""}`}
            title={data.auteur === "jarvis" ? "Relation tracée par Jarvis. Faux ? Sélectionne-la et retire-la." : undefined}
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)`, color: couleur, borderColor: couleur }}
            onDoubleClick={() => {
              setValeur(data.libelle);
              setEdition(true);
            }}>
            {edition ? (
              <input autoFocus value={valeur} maxLength={60} aria-label="Libellé de la relation"
                onChange={(e) => setValeur(e.target.value)}
                onBlur={() => {
                  setEdition(false);
                  data.renommer(id, valeur.trim());
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  if (e.key === "Escape") setEdition(false);
                }} />
            ) : <>
              {data.auteur === "jarvis" && <Sparkles size={11} aria-label="Tracé par Jarvis" />}
              {data.libelle || <span style={{ opacity: 0.7 }}>{data.style === "defaut" ? "Nommer…" : rendu.nom}</span>}
            </>}
            {selected && !edition && (
              <button type="button" className="retirer-lien" aria-label="Retirer cette relation"
                onClick={(e) => { e.stopPropagation(); deleteElements({ edges: [{ id }] }); }}><X size={12} /></button>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
