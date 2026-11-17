import { useCallback, useLayoutEffect, useRef } from "react";
import { flushSync } from "react-dom";

const preference = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
const transitionEnCours = new WeakMap<HTMLElement, Animation>();

function disponible(zone: HTMLElement): boolean {
  return typeof zone.animate === "function" && !preference?.matches && document.visibilityState === "visible";
}

function opacite(zone: HTMLElement, debut: number, fin: number, duree: number, fill: FillMode = "none"): Animation {
  const effet = zone.animate([{ opacity: debut }, { opacity: fin }], {
    duration: duree, easing: "cubic-bezier(.2, .65, .3, 1)", fill,
  });
  transitionEnCours.set(zone, effet);
  return effet;
}

export function fondreEntree(zone: HTMLElement, depart = .55): Animation | undefined {
  if (!disponible(zone)) return;
  transitionEnCours.get(zone)?.cancel();
  return opacite(zone, depart, 1, 160);
}

/** Remplace le contenu au creux du fondu, sans redimensionner ni cloner ses éléments. */
export function useZoneFondu<T extends HTMLElement>() {
  const zone = useRef<T>(null);
  const passage = useRef<Animation | undefined>(undefined);
  useLayoutEffect(() => () => passage.current?.cancel(), []);

  const changer = useCallback((appliquer: () => void) => {
    const element = zone.current;
    const precedent = passage.current;
    if (!element || !disponible(element)) {
      precedent?.cancel();
      appliquer();
      return;
    }
    const depart = Number(getComputedStyle(element).opacity);
    precedent?.cancel();
    transitionEnCours.get(element)?.cancel();
    const sortie = opacite(element, depart, .12, 75, "forwards");
    passage.current = sortie;
    sortie.onfinish = () => {
      if (passage.current !== sortie || !element.isConnected) return;
      // Les classes de disposition et le contrôle actif changent ensemble, avant le prochain rendu du navigateur.
      flushSync(appliquer);
      sortie.cancel();
      passage.current = fondreEntree(element, .12);
    };
  }, []);

  return [zone, changer] as const;
}

/** Les bascules successives convergent vers le dernier choix, même avant le rendu de la disposition. */
export function useDispositionAnimee<T>(valeur: T, appliquer: (valeur: T) => void, changer: (appliquer: () => void) => void) {
  const destination = useRef(valeur);
  useLayoutEffect(() => { destination.current = valeur; }, [valeur]);
  return (suivante: T) => {
    if (destination.current === suivante) return;
    destination.current = suivante;
    changer(() => appliquer(suivante));
  };
}
