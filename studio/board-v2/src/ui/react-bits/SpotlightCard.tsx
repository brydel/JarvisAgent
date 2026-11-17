import type { ComponentPropsWithoutRef, PointerEvent } from "react";
import "./spotlight-card.css";

type Props = ({ as?: "div" } & ComponentPropsWithoutRef<"div">)
  | ({ as: "button" } & ComponentPropsWithoutRef<"button">);

const mouvement = typeof matchMedia === "function"
  ? matchMedia("(hover: hover) and (prefers-reduced-motion: no-preference)") : null;

function suivre(e: PointerEvent<HTMLElement>) {
  if (e.pointerType !== "mouse" || !mouvement?.matches) return;
  const carte = e.currentTarget;
  const { left, top } = carte.getBoundingClientRect();
  carte.style.setProperty("--spot-x", `${e.clientX - left}px`);
  carte.style.setProperty("--spot-y", `${e.clientY - top}px`);
}

// Spotlight Card de React Bits. Le conteneur de contenu conserve ses propres contrôles.
// https://reactbits.dev/components/spotlight-card
export function SpotlightCard(props: Props) {
  if (props.as === "button") {
    const { as: _as, className = "", ...attributs } = props;
    return <button {...attributs} className={`spotlight-card ${className}`} onPointerMove={suivre} />;
  }
  const { as: _as, className = "", ...attributs } = props;
  return <div {...attributs} className={`spotlight-card ${className}`} onPointerMove={suivre} />;
}
