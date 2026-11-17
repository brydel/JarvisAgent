import { Component, lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useStoreApi } from "@xyflow/react";

export const ZOOM_LIBELLES = 2;

const CrystalizedBall = lazy(() => import("../ui/react-bits/crystalized-ball/CrystalizedBall"));

class LimitePlasma extends Component<{ children: ReactNode }, { indisponible: boolean }> {
  state = { indisponible: false };
  static getDerivedStateFromError() { return { indisponible: true }; }
  render() { return this.state.indisponible ? null : this.props.children; }
}

type Tuile = { toile: HTMLCanvasElement; contexte: CanvasRenderingContext2D; teinte: string; image: number };

// Chaque catégorie reçoit sa copie teintée d'une même image du shader. Les points n'allouent pas de contexte GPU.
export function ZoomGraphe() {
  const store = useStoreApi();
  const support = useRef<HTMLDivElement>(null);
  const copie = useRef<HTMLCanvasElement>(null);
  const sourcePlasma = useRef<HTMLDivElement>(null);
  const premiereImage = useRef(false);
  const atlas = useRef(new Map<string, Tuile>());
  const compteur = useRef(0);
  const [actif, setActif] = useState(false);
  const [anime, setAnime] = useState(false);

  const dessiner = useCallback((source: HTMLCanvasElement) => {
    const toile = copie.current;
    const contexte = toile?.getContext("2d");
    const surface = support.current;
    const { width, height, transform: [tx, ty, zoom], nodeLookup } = store.getState();
    if (!toile || !contexte || !surface || width <= 0 || height <= 0 || !source.width || !source.height) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(1_300_000 / (width * height)));
    const largeur = Math.max(1, Math.round(width * dpr));
    const hauteur = Math.max(1, Math.round(height * dpr));
    if (toile.width !== largeur) toile.width = largeur;
    if (toile.height !== hauteur) toile.height = hauteur;
    contexte.setTransform(dpr, 0, 0, dpr, 0, 0);
    contexte.clearRect(0, 0, width, height);
    const image = ++compteur.current;
    let styles: CSSStyleDeclaration | undefined;

    const tuilePour = (variable: string) => {
      let tuile = atlas.current.get(variable);
      if (!tuile) {
        const imageTeintee = document.createElement("canvas");
        const ctx = imageTeintee.getContext("2d");
        if (!ctx) return source;
        const teinte = (styles ??= getComputedStyle(surface)).getPropertyValue(variable).trim();
        tuile = { toile: imageTeintee, contexte: ctx, teinte, image: -1 };
        atlas.current.set(variable, tuile);
      }
      if (!tuile.teinte) return source;
      if (tuile.image === image) return tuile.toile;
      if (tuile.toile.width !== source.width) tuile.toile.width = source.width;
      if (tuile.toile.height !== source.height) tuile.toile.height = source.height;
      const { contexte: ctx } = tuile;
      ctx.clearRect(0, 0, source.width, source.height);
      ctx.drawImage(source, 0, 0);
      ctx.globalCompositeOperation = "source-atop";
      ctx.fillStyle = tuile.teinte;
      ctx.globalAlpha = .87;
      ctx.fillRect(0, 0, source.width, source.height);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      tuile.image = image;
      return tuile.toile;
    };

    for (const noeud of nodeLookup.values()) {
      const centre = noeud.internals.positionAbsolute;
      const x = (centre.x + 76) * zoom + tx;
      const y = (centre.y + 26) * zoom + ty;
      const { diametre, teinte, importance, estompe } = noeud.data;
      const taille = typeof diametre === "number" ? diametre : 11;
      const rayon = Math.max(5, Math.min(55, taille * zoom * 1.24));
      if (noeud.hidden || x + rayon < 0 || x - rayon > width || y + rayon < 0 || y - rayon > height) continue;
      contexte.globalAlpha = estompe ? .28 : .59 + .41 * (typeof importance === "number" ? importance : .55);
      const tuile = typeof teinte === "string" ? tuilePour(teinte) : source;
      contexte.drawImage(tuile, x - rayon, y - rayon, rayon * 2, rayon * 2);
    }
    contexte.globalAlpha = 1;
    if (!premiereImage.current) {
      premiereImage.current = true;
      surface.dataset.pret = "true";
    }
  }, [store]);

  useEffect(() => {
    const zone = support.current;
    const surface = zone?.closest<HTMLElement>(".mf-canevas");
    if (!surface || !zone) return;
    const mouvementReduit = matchMedia("(prefers-reduced-motion: reduce)");
    let visible = false;
    let horloge = 0;
    let transformation = store.getState().transform;
    let noeuds = store.getState().nodes;
    let { width, height } = store.getState();

    const autorise = () => visible && !document.hidden && !mouvementReduit.matches;
    const reveiller = () => {
      if (!autorise()) return;
      window.clearTimeout(horloge);
      setAnime(true);
      horloge = window.setTimeout(() => setAnime(false), 850);
    };
    const permission = () => {
      const permis = autorise();
      if (!permis) {
        window.clearTimeout(horloge);
        setAnime(false);
        delete zone.dataset.pret;
        premiereImage.current = false;
      }
      setActif(permis);
      if (permis) reveiller();
    };
    const actualiserLibelles = (zoom: number) => { surface.dataset.libelles = zoom >= ZOOM_LIBELLES ? "visibles" : "masques"; };
    actualiserLibelles(transformation[2]);
    const vue = new IntersectionObserver(([entree]) => {
      visible = !!entree?.isIntersecting;
      permission();
    });
    vue.observe(surface);
    const theme = new MutationObserver(() => { atlas.current.clear(); reveiller(); });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    const suivreSurvol = (evenement: PointerEvent) => {
      const id = evenement.target instanceof Element ? evenement.target.closest<HTMLElement>(".react-flow__node")?.dataset.id : undefined;
      if (!id || !sourcePlasma.current) return;
      const { nodeLookup, transform: [x, y, zoom] } = store.getState();
      const centre = nodeLookup.get(id)?.internals.positionAbsolute;
      if (!centre) return;
      reveiller();
      sourcePlasma.current.style.left = (centre.x + 76) * zoom + x + "px";
      sourcePlasma.current.style.top = (centre.y + 26) * zoom + y + "px";
    };
    surface.addEventListener("pointermove", suivreSurvol, { passive: true });
    document.addEventListener("visibilitychange", permission);
    mouvementReduit.addEventListener("change", permission);
    const suivre = store.subscribe(({ transform, nodes, width: largeur, height: hauteur }) => {
      if (noeuds === nodes && transformation === transform && width === largeur && height === hauteur) return;
      width = largeur;
      height = hauteur;
      if (transform[2] !== transformation[2]) actualiserLibelles(transform[2]);
      noeuds = nodes;
      transformation = transform;
      reveiller();
    });
    return () => {
      suivre();
      window.clearTimeout(horloge);
      vue.disconnect();
      theme.disconnect();
      premiereImage.current = false;
      delete zone.dataset.pret;
      delete surface.dataset.libelles;
      surface.removeEventListener("pointermove", suivreSurvol);
      document.removeEventListener("visibilitychange", permission);
      mouvementReduit.removeEventListener("change", permission);
    };
  }, [store]);

  return <div ref={support} className="mf-plasma" aria-hidden="true">
    {actif && <>
      <canvas ref={copie} className="mf-plasma-copie" />
      <div ref={sourcePlasma} className="mf-plasma-source">
        <LimitePlasma><Suspense fallback={null}>
          <CrystalizedBall preset="plasma" size={0.7} crackle={0.85} fill={0.5} interactive hoverStrength={0.7}
            intro={false} paused={!anime} onFrame={dessiner} />
        </Suspense></LimitePlasma>
      </div>
    </>}
  </div>;
}
