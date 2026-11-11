// Guides magnétiques : les lignes d'alignement montrées pendant un glisser (calcul dans espace.ts::accrocher).
// La vue ne bouge pas pendant un glisser : la transformation est lue une fois par rendu, sans abonnement.
import { memo } from "react";
import { useReactFlow } from "@xyflow/react";
import type { Guide } from "./espace";

export const Guides = memo(function Guides({ guides }: { guides: Guide[] }) {
  const rf = useReactFlow();
  if (!guides.length) return null;
  const v = rf.getViewport();
  return (
    <svg className="guides" aria-hidden>
      {guides.map((g, i) => (g.axe === "x"
        ? <line key={i} x1={g.position * v.zoom + v.x} x2={g.position * v.zoom + v.x} y1={g.debut * v.zoom + v.y} y2={g.fin * v.zoom + v.y} />
        : <line key={i} y1={g.position * v.zoom + v.y} y2={g.position * v.zoom + v.y} x1={g.debut * v.zoom + v.x} x2={g.fin * v.zoom + v.x} />))}
    </svg>
  );
});
