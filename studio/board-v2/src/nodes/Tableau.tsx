// Objets de tableau blanc : note adhésive, texte libre, forme (rectangle, ellipse, losange), trait à main levée,
// cadre. Nœuds LÉGERS (pas de coque de carte) : un <div> ou un <svg>, couleurs par jetons (`teinte-…`).
// Le texte s'édite dans une surcouche non transformée (outils/EditeurTexte.tsx) : pendant l'édition, le nœud
// masque son texte pour ne pas le montrer deux fois.
import { memo, useState } from "react";
import { Handle, NodeResizer, Position, type Node, type NodeProps } from "@xyflow/react";
import { useNiveauDetail, vientDEtrePose } from "../board/detail";
import { ui, useUi } from "../etat/ui";
import { aPressionReelle, cheminDuTrait } from "../outils/dessin";
import type { DonneesNoeud, ObjetBoard } from "../types";

type P = NodeProps<Node<DonneesNoeud>>;
const COTES = [Position.Top, Position.Right, Position.Bottom, Position.Left];
const editer = (id: string) => ui.definir({ edition: id, outil: "selection" });
export const teinte = (o: ObjetBoard, defaut = "neutre") => (typeof o.meta.couleur === "string" && o.meta.couleur) || defaut;

/** Poignées de relation : quatre au niveau de détail complet, une seule ensuite, aucune sous 12 % de zoom. */
function Poignees({ niveau }: { niveau: number }) {
  if (niveau === 2) return null;
  return niveau === 0 ? <>{COTES.map((p) => <Handle key={p} id={p} type="source" position={p} />)}</> : <Handle id="top" type="source" position={Position.Top} />;
}

/** Taille du texte d'un adhésif : la plus grande qui laisse tenir le texte, bornée (même calcul dans l'éditeur). */
export function policeAdhesif(o: Pick<ObjetBoard, "contenu" | "largeur" | "hauteur">, texte = o.contenu): number {
  const surface = Math.max(1, (o.largeur - 32) * (o.hauteur - 32));
  return Math.round(Math.max(13, Math.min(30, Math.sqrt(surface / (Math.max(8, texte.length) * 1.5)))));
}

/* ---------------------------------------------------------------- note adhésive ---------------------------- */
export const AdhesifNode = memo(function AdhesifNode({ data, selected }: P) {
  const o = data.objet;
  const niveau = useNiveauDetail();
  const [neuf] = useState(() => vientDEtrePose(o.cree));  // posée à l'instant : elle se dépose, une fois
  const enEdition = useUi((e) => e.edition === o.id);
  return (
    <>
      <NodeResizer isVisible={selected && !o.verrouille} minWidth={96} minHeight={72} maxWidth={2400} maxHeight={2400} />
      <Poignees niveau={niveau} />
      <div className={`adhesif teinte-${teinte(o, "jaune")}${neuf ? " vient-d-etre-pose" : ""}`} onDoubleClick={() => !o.verrouille && editer(o.id)}>
        {niveau < 2 && !enEdition && (
          <div className="adhesif-texte" style={{ fontSize: policeAdhesif(o) }}>
            {o.contenu || (niveau === 0 ? <span className="indice">Double-clic pour écrire</span> : null)}
          </div>
        )}
      </div>
    </>
  );
});

/* ---------------------------------------------------------------- texte libre ------------------------------ */
export const TexteLibreNode = memo(function TexteLibreNode({ data, selected }: P) {
  const o = data.objet;
  const niveau = useNiveauDetail();
  const enEdition = useUi((e) => e.edition === o.id);
  return (
    <>
      <NodeResizer isVisible={selected && !o.verrouille} minWidth={40} minHeight={40} maxWidth={4000} maxHeight={4000} />
      <div className={`texte-libre teinte-${teinte(o)}`} style={{ fontSize: o.meta.taille_police ?? 28 }} onDoubleClick={() => !o.verrouille && editer(o.id)}>
        {niveau < 2 && !enEdition && (o.contenu || <span className="indice">Texte</span>)}
        {niveau === 2 && <span className="trait-texte" aria-hidden />}
      </div>
    </>
  );
});

/* ---------------------------------------------------------------- forme ------------------------------------ */
export const FormeNode = memo(function FormeNode({ data, selected, width, height }: P) {
  const o = data.objet;
  const niveau = useNiveauDetail();
  const enEdition = useUi((e) => e.edition === o.id);
  const l = width ?? o.largeur, h = height ?? o.hauteur;
  const e = Math.max(0, Math.min(Number(o.meta.epaisseur ?? 3), Math.min(l, h) / 2));
  const m = e / 2;
  const sansFond = o.meta.fond === "";
  const dessin = o.meta.forme === "ellipse" ? <ellipse cx={l / 2} cy={h / 2} rx={Math.max(0, l / 2 - m)} ry={Math.max(0, h / 2 - m)} />
    : o.meta.forme === "losange" ? <polygon points={`${l / 2},${m} ${l - m},${h / 2} ${l / 2},${h - m} ${m},${h / 2}`} />
    : <rect x={m} y={m} width={Math.max(0, l - e)} height={Math.max(0, h - e)} rx={Math.min(10, l / 6, h / 6)} />;
  return (
    <>
      <NodeResizer isVisible={selected && !o.verrouille} minWidth={40} minHeight={40} maxWidth={4000} maxHeight={4000} />
      <Poignees niveau={niveau} />
      <div className={`forme teinte-${teinte(o, "neutre")}${sansFond ? " sans-fond" : ""}`} onDoubleClick={() => !o.verrouille && editer(o.id)}>
        <svg width={l} height={h} aria-hidden style={{ strokeWidth: e }}>{dessin}</svg>
        {niveau < 2 && !enEdition && o.contenu && <div className={`forme-texte ${o.meta.forme ?? "rectangle"}`}>{o.contenu}</div>}
      </div>
    </>
  );
});

/* ---------------------------------------------------------------- trait à main levée ----------------------- */
export const TraitNode = memo(function TraitNode({ data, selected, width, height }: P) {
  const o = data.objet;
  const points = Array.isArray(o.meta.points) ? o.meta.points : [];
  const [l0, h0] = o.meta.boite ?? [o.largeur, o.hauteur];
  const outil = o.meta.outil === "surligneur" ? "surligneur" : "crayon";
  // chemin calculé une fois par trait (cache par tableau de points) : le rendu ne refait aucun calcul de contour
  const d = points.length >= 6 ? cheminDuTrait(points, Number(o.meta.epaisseur ?? 6), outil, aPressionReelle(points)) : "";
  return (
    <>
      <NodeResizer isVisible={selected && !o.verrouille} minWidth={40} minHeight={40} maxWidth={4000} maxHeight={4000} />
      <svg className={`trait ${outil} teinte-${teinte(o, "neutre")}`} width={width ?? o.largeur} height={height ?? o.hauteur}
        viewBox={`0 0 ${l0} ${h0}`} preserveAspectRatio="none" aria-hidden>
        <path d={d} />
      </svg>
    </>
  );
});

/* ---------------------------------------------------------------- cadre ------------------------------------ */
export const CadreNode = memo(function CadreNode({ data, selected }: P) {
  const o = data.objet;
  const niveau = useNiveauDetail();
  const enEdition = useUi((e) => e.edition === o.id);
  const focus = useUi((e) => e.focus === o.id);
  return (
    <>
      <NodeResizer isVisible={selected && !o.verrouille} minWidth={120} minHeight={80} maxWidth={4000} maxHeight={4000} />
      <section className={`cadre teinte-${teinte(o)}${focus ? " en-focus" : ""}`} aria-label={`Cadre ${o.meta.titre ?? ""}`}>
        {niveau < 2 && (
          <header className="cadre-titre" onDoubleClick={() => !o.verrouille && editer(o.id)}>
            {!enEdition && (o.meta.titre || "Cadre")}
          </header>
        )}
        <div className="cadre-bord" />
      </section>
    </>
  );
});
