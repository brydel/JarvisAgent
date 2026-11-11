// Flèche libre : un segment entre deux extrémités libres ou ancrées (outils/fleche.ts). Sélectionnée, ses deux
// extrémités se déplacent à la main ; relâchée sur un objet, une extrémité s'y ancre.
import { memo, useCallback, useRef, useState, type PointerEvent as PointeurReact } from "react";
import { useReactFlow, useStore, type Node, type NodeProps, type ReactFlowState } from "@xyflow/react";
import { useUi } from "../etat/ui";
import { contourDe, extremitesBrutes, extremitesReelles, geometrieFleche, pointe, type Cible } from "../outils/fleche";
import type { Point } from "../outils/geometrie";
import type { DonneesNoeud, ObjetBoard } from "../types";
import { useActions } from "./contexte";
import { teinte } from "./Tableau";

type P = NodeProps<Node<DonneesNoeud>>;

/** Boîtes et contours des objets visés, sous forme de texte : la flèche ne se re-rend que si l'un d'eux bouge. */
function cleDesCibles(ids: (string | undefined)[]) {
  return (s: ReactFlowState): string => ids.map((id) => {
    const n = id ? s.nodeLookup.get(id) : undefined;
    if (!n) return "";
    const o = (n.data as Partial<DonneesNoeud>).objet;
    const p = n.internals.positionAbsolute;
    return [p.x, p.y, n.measured.width ?? n.width ?? 0, n.measured.height ?? n.height ?? 0, o ? contourDe(o) : "rectangle"].join(",");
  }).join("|");
}

function lireCible(cle: string): Cible | undefined {
  if (!cle) return undefined;
  const [x, y, l, h, contour] = cle.split(",");
  return { boite: { x: Number(x), y: Number(y), largeur: Number(l), hauteur: Number(h) }, contour: contour as Cible["contour"] };
}

export const FlecheNode = memo(function FlecheNode({ data, selected, positionAbsoluteX, positionAbsoluteY }: P) {
  const o = data.objet;
  const a = useActions();
  const rf = useReactFlow();
  const enEdition = useUi((e) => e.edition === o.id);
  const ancres = o.meta.ancres ?? {};
  const cle = useStore(useCallback(cleDesCibles([ancres.de?.id, ancres.vers?.id]), [ancres.de?.id, ancres.vers?.id]));
  const [brouillon, setBrouillon] = useState<{ bout: 0 | 1; point: Point } | null>(null);
  const geste = useRef<{ bout: 0 | 1 } | null>(null);
  const origine = { x: positionAbsoluteX, y: positionAbsoluteY };
  const [cleDe, cleVers] = cle.split("|");
  const cibles: Record<string, Cible | undefined> = { [ancres.de?.id ?? ""]: lireCible(cleDe ?? ""), [ancres.vers?.id ?? " "]: lireCible(cleVers ?? "") };
  let [p1, p2] = extremitesReelles(o, (id) => cibles[id], origine);
  if (brouillon) [p1, p2] = brouillon.bout === 0 ? [brouillon.point, p2] : [p1, brouillon.point];
  // coordonnées locales au nœud (le <svg> déborde : la flèche suit ses ancres hors de sa boîte)
  const l1 = { x: p1.x - origine.x, y: p1.y - origine.y }, l2 = { x: p2.x - origine.x, y: p2.y - origine.y };
  const epaisseur = Math.max(1, Number(o.meta.epaisseur ?? 3));
  const tete = 8 + epaisseur * 2.2;
  const pointes = o.meta.pointes ?? "fin";

  const saisir = (bout: 0 | 1) => (e: PointeurReact<SVGCircleElement>) => {
    if (o.verrouille || e.button !== 0) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    geste.current = { bout };
    setBrouillon({ bout, point: bout === 0 ? p1 : p2 });
  };
  const bouger = (e: PointeurReact<SVGCircleElement>) => {
    if (!geste.current) return;
    setBrouillon({ bout: geste.current.bout, point: rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }, { snapToGrid: false }) });
  };
  const lacher = (e: PointeurReact<SVGCircleElement>) => {
    const g = geste.current;
    geste.current = null;
    setBrouillon(null);
    if (!g) return;
    const point = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }, { snapToGrid: false });
    // l'extrémité déplacée s'ancre à l'objet sous le pointeur ; l'autre garde son ancre et sa visée
    const [b1, b2] = extremitesBrutes(o, origine);
    const objetDe = (id?: string): ObjetBoard | undefined => (id ? a.objet(id) : undefined);
    const fixe = g.bout === 0
      ? { point: ancres.vers && objetDe(ancres.vers.id) ? viser(objetDe(ancres.vers.id)!, ancres.vers) : b2, cible: objetDe(ancres.vers?.id) }
      : { point: ancres.de && objetDe(ancres.de.id) ? viser(objetDe(ancres.de.id)!, ancres.de) : b1, cible: objetDe(ancres.de?.id) };
    const mobile = { point, cible: a.sousLePoint(point, o.id) };
    const geo = g.bout === 0 ? geometrieFleche(mobile, fixe) : geometrieFleche(fixe, mobile);
    a.modifier(o.id, { ...geo.boite, meta: { ...o.meta, points: geo.points, ancres: geo.ancres } });
  };

  return (
    <svg className={`fleche teinte-${teinte(o)}${selected ? " selectionnee" : ""}`} width={o.largeur} height={o.hauteur} aria-hidden={false}
      role="img" aria-label={`Flèche${o.contenu ? ` : ${o.contenu}` : ""}`} style={{ strokeWidth: epaisseur }}>
      <line className="fleche-prise" x1={l1.x} y1={l1.y} x2={l2.x} y2={l2.y} onDoubleClick={() => !o.verrouille && a.editer(o.id)} />
      <line className="fleche-trait" x1={l1.x} y1={l1.y} x2={l2.x} y2={l2.y} />
      {pointes !== "aucune" && <polygon className="fleche-pointe" points={pointe(l1, l2, tete)} />}
      {pointes === "deux" && <polygon className="fleche-pointe" points={pointe(l2, l1, tete)} />}
      {o.contenu && !enEdition && (
        <text className="fleche-libelle" x={(l1.x + l2.x) / 2} y={(l1.y + l2.y) / 2} textAnchor="middle" dominantBaseline="central">{o.contenu}</text>
      )}
      {selected && !o.verrouille && ([l1, l2] as const).map((p, i) => (
        <circle key={i} className={`fleche-bout nodrag nopan${(i === 0 ? ancres.de : ancres.vers) ? " ancre" : ""}`} cx={p.x} cy={p.y} r={7}
          onPointerDown={saisir(i as 0 | 1)} onPointerMove={bouger} onPointerUp={lacher} onPointerCancel={() => { geste.current = null; setBrouillon(null); }}>
          <title>{(i === 0 ? ancres.de : ancres.vers) ? "Extrémité ancrée : glisse-la pour la détacher" : "Extrémité libre : glisse-la sur un objet pour l'ancrer"}</title>
        </circle>
      ))}
    </svg>
  );
});

function viser(o: ObjetBoard, ancre: { nx: number; ny: number }): Point {
  return { x: o.x + ancre.nx * o.largeur, y: o.y + ancre.ny * o.hauteur };
}
