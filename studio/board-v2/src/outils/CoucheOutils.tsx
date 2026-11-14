// Couche des outils de création : posée au-dessus du canevas dès qu'un outil autre que la sélection ou la main est
// actif. Elle capte le pointeur (souris, doigt, stylet), dessine un APERÇU sans passer par React (attributs SVG
// modifiés directement : aucune latence pendant le geste) et, au relâchement, crée l'objet par les services du
// Board (écriture versionnée, annulable).
//  - dessin : setPointerCapture, getCoalescedEvents (tous les points entre deux images), pression du stylet,
//    touch-action: none ; le trait fini reste affiché ici jusqu'à ce que le serveur ait confirmé l'objet ;
//  - molette et bouton du milieu : la vue reste zoomable et déplaçable pendant qu'un outil est actif.
import { useCallback, useEffect, useRef, useState, type PointerEvent as PointeurReact } from "react";
import { useReactFlow } from "@xyflow/react";
import { ZOOM_MAX, ZOOM_MIN } from "../board/detail";
import type { ServicesBoard } from "../commandes/contexte";
import { ui, type IdOutil } from "../etat/ui";
import { cheminDuGeste, figer, type PointTrait } from "./dessin";
import { dansLeLasso, indexDe, sousLaGomme, sousLePoint } from "./espace";
import { geometrieFleche } from "./fleche";
import { entreCoins, type Point } from "./geometrie";

interface Geste {
  outil: IdOutil;
  pointeur: number;
  depart: Point;
  departEcran: Point;
  zoom: number;
  points: PointTrait[];
  stylet: boolean;
  dernier: Point;
  effaces: Set<string>;
  couleur: string;
  epaisseur: number;
}
interface EnAttente {
  cle: number;
  d: string;
  classe: string;
}

const FORMES = new Set<IdOutil>(["rectangle", "ellipse", "losange", "cadre"]);
const DEFAUT: Partial<Record<IdOutil, [number, number]>> = { rectangle: [180, 130], ellipse: [180, 130], losange: [170, 150], cadre: [720, 460] };
let compteur = 0;

function marquer(ids: Iterable<string>, actif: boolean) {
  for (const id of ids) document.querySelector(`.react-flow__node[data-id="${CSS.escape(id)}"]`)?.classList.toggle("a-effacer", actif);
}

export function CoucheOutils({ outil, b }: { outil: IdOutil; b: ServicesBoard }) {
  const rf = useReactFlow();
  const racine = useRef<HTMLDivElement>(null);
  const groupe = useRef<SVGGElement>(null);
  const trace = useRef<SVGPathElement>(null);
  const forme = useRef<SVGPathElement>(null);
  const geste = useRef<Geste | null>(null);
  const image = useRef(0);
  const pan = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const [enAttente, setEnAttente] = useState<EnAttente[]>([]);

  const caler = useCallback(() => {
    const v = rf.getViewport();
    groupe.current?.setAttribute("transform", `translate(${v.x} ${v.y}) scale(${v.zoom})`);
  }, [rf]);
  const vers = useCallback((e: { clientX: number; clientY: number }): Point => rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }, { snapToGrid: false }), [rf]);

  const effacerApercu = () => {
    trace.current?.setAttribute("d", "");
    forme.current?.setAttribute("d", "");
  };
  const abandonner = useCallback(() => {
    if (geste.current) marquer(geste.current.effaces, false);
    geste.current = null;
    cancelAnimationFrame(image.current);
    effacerApercu();
  }, []);
  // changer d'outil (ou Échap) pendant un geste l'abandonne proprement
  useEffect(() => abandonner, [outil, abandonner]);

  // molette : zoom autour du pointeur (écouteur natif non passif : Ctrl+molette ne zoome pas la page)
  useEffect(() => {
    const el = racine.current;
    if (!el) return;
    const molette = (e: WheelEvent) => {
      e.preventDefault();
      if (geste.current) return;  // un tracé garde son repère jusqu’au relâchement
      const v = rf.getViewport(), r = el.getBoundingClientRect();
      const px = e.clientX - r.left, py = e.clientY - r.top;
      const k = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, v.zoom * 2 ** (-e.deltaY * (e.ctrlKey ? 0.01 : 0.002))));
      void rf.setViewport({ x: px - ((px - v.x) * k) / v.zoom, y: py - ((py - v.y) * k) / v.zoom, zoom: k });
      requestAnimationFrame(caler);
    };
    el.addEventListener("wheel", molette, { passive: false });
    return () => el.removeEventListener("wheel", molette);
  }, [rf, caler]);

  const dessinerApercu = () => {
    const g = geste.current;
    if (!g) return;
    const fin = g.dernier;
    if (g.outil === "crayon" || g.outil === "surligneur") {
      trace.current?.setAttribute("d", cheminDuGeste(g.points, { epaisseur: g.epaisseur, outil: g.outil, pressionReelle: g.stylet, enCours: true }));
    } else if (g.outil === "lasso") {
      trace.current?.setAttribute("d", `M${g.points.map((p) => `${p[0]},${p[1]}`).join("L")}Z`);
    } else if (g.outil === "fleche") {
      forme.current?.setAttribute("d", `M${g.depart.x},${g.depart.y}L${fin.x},${fin.y}`);
    } else if (FORMES.has(g.outil)) {
      const z = entreCoins(g.depart, fin);
      const [x, y, l, h] = [z.x, z.y, z.largeur, z.hauteur];
      forme.current?.setAttribute("d", g.outil === "ellipse"
        ? `M${x},${y + h / 2}a${l / 2},${h / 2} 0 1 0 ${l},0a${l / 2},${h / 2} 0 1 0 ${-l},0Z`
        : g.outil === "losange" ? `M${x + l / 2},${y}L${x + l},${y + h / 2}L${x + l / 2},${y + h}L${x},${y + h / 2}Z`
        : `M${x},${y}h${l}v${h}h${-l}Z`);
    }
  };

  const debut = (e: PointeurReact<HTMLDivElement>) => {
    if (geste.current) return;
    if (e.button === 1) {  // bouton du milieu : déplacer la vue sans quitter l'outil
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      const v = rf.getViewport();
      pan.current = { x: e.clientX, y: e.clientY, vx: v.x, vy: v.y };
      return;
    }
    if (e.button !== 0 || geste.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    caler();
    const p = vers(e);
    const { couleur, epaisseur } = ui.lire();
    const stylet = e.pointerType === "pen";
    geste.current = { outil, pointeur: e.pointerId, depart: p, departEcran: { x: e.clientX, y: e.clientY }, zoom: rf.getZoom(), dernier: p, stylet,
      points: [[p.x, p.y, stylet ? e.pressure || 0.5 : 0.5]], effaces: new Set(), couleur, epaisseur: outil === "surligneur" ? Math.max(18, epaisseur * 3) : epaisseur };
    if (trace.current) trace.current.setAttribute("class", `apercu-trace ${outil} teinte-${couleur}`);
    if (forme.current) forme.current.setAttribute("class", `apercu-forme ${outil} teinte-${couleur}`);
  };

  // Une alerte d'activité peut agrandir la bande au-dessus du Board pendant le tracé.
  // Le déplacement du pointeur reste mesuré dans le repère de départ, sans écraser le dessin.
  const pointDuGeste = (g: Geste, e: { clientX: number; clientY: number }): Point => ({
    x: g.depart.x + (e.clientX - g.departEcran.x) / g.zoom,
    y: g.depart.y + (e.clientY - g.departEcran.y) / g.zoom,
  });

  const mouvement = (e: PointeurReact<HTMLDivElement>) => {
    if (pan.current) {
      const v = rf.getViewport();
      void rf.setViewport({ x: pan.current.vx + e.clientX - pan.current.x, y: pan.current.vy + e.clientY - pan.current.y, zoom: v.zoom });
      requestAnimationFrame(caler);
      return;
    }
    const g = geste.current;
    if (!g || e.pointerId !== g.pointeur) return;
    // tous les échantillons du pointeur depuis la dernière image, pas seulement le dernier (trait fidèle au geste rapide)
    const natif = e.nativeEvent;
    const echantillons = typeof natif.getCoalescedEvents === "function" ? natif.getCoalescedEvents() : [];
    for (const ev of echantillons.length ? echantillons : [natif]) {
      const p = pointDuGeste(g, ev);
      if (g.outil === "gomme") {
        const touches = sousLaGomme(indexDe(b.objets()), g.dernier, p, 10 / rf.getZoom()).filter((o) => !g.effaces.has(o.id));
        for (const o of touches) g.effaces.add(o.id);
        marquer(touches.map((o) => o.id), true);
      } else if (g.outil === "crayon" || g.outil === "surligneur" || g.outil === "lasso") {
        g.points.push([p.x, p.y, g.stylet ? ev.pressure || 0.5 : 0.5]);
      }
      g.dernier = p;
    }
    cancelAnimationFrame(image.current);
    image.current = requestAnimationFrame(dessinerApercu);
  };

  const fin = (e: PointeurReact<HTMLDivElement>) => {
    if (pan.current) {
      pan.current = null;
      return;
    }
    const g = geste.current;
    if (!g || e.pointerId !== g.pointeur) return;
    geste.current = null;
    cancelAnimationFrame(image.current);
    const p = pointDuGeste(g, e);
    const zoom = g.zoom;
    const court = Math.hypot(e.clientX - g.departEcran.x, e.clientY - g.departEcran.y) < 6;
    const meta = { couleur: g.couleur };
    const revenir = () => ui.definir({ outil: "selection" });

    if (g.outil === "crayon" || g.outil === "surligneur") {
      const t = figer(g.points, g.epaisseur, zoom);
      const d = trace.current?.getAttribute("d") ?? "";
      effacerApercu();
      if (!t) return;
      // le trait reste visible ici jusqu'à la confirmation du serveur : pas de clignotement entre aperçu et objet
      const cle = ++compteur;
      setEnAttente((l) => [...l, { cle, d, classe: `apercu-trace ${g.outil} teinte-${g.couleur}` }]);
      b.creer({ type: "trait", ...t.boite, meta: { ...meta, points: t.points, boite: t.origine, outil: g.outil, epaisseur: g.epaisseur }, analyser: false }, "Trait")
        .catch((x: Error) => b.toast(x.message, { erreur: true }))
        .finally(() => setEnAttente((l) => l.filter((a) => a.cle !== cle)));
      return;
    }
    effacerApercu();
    if (g.outil === "gomme") {
      marquer(g.effaces, false);
      if (g.effaces.size) void b.supprimer([...g.effaces]);
      return;
    }
    if (g.outil === "lasso") {
      const touches = dansLeLasso(indexDe(b.objets()), g.points.map(([x, y]) => ({ x, y })));
      b.selectionner(touches.map((o) => o.id));
      revenir();
      return;
    }
    if (g.outil === "adhesif") {
      void b.creer({ type: "adhesif", x: Math.round(p.x - 110), y: Math.round(p.y - 110), largeur: 220, hauteur: 220, meta: { couleur: g.couleur === "neutre" || g.couleur === "indigo" ? "jaune" : g.couleur }, analyser: false }, "Note adhésive")
        .then((id) => { b.selectionner([id]); ui.definir({ outil: "selection", edition: id }); }).catch((x: Error) => b.toast(x.message, { erreur: true }));
      return;
    }
    if (g.outil === "texte") {
      void b.creer({ type: "texte_libre", x: Math.round(p.x), y: Math.round(p.y - 20), largeur: 280, hauteur: 56, meta: { couleur: "neutre", taille_police: 28 }, analyser: false }, "Texte")
        .then((id) => { b.selectionner([id]); ui.definir({ outil: "selection", edition: id }); }).catch((x: Error) => b.toast(x.message, { erreur: true }));
      return;
    }
    if (g.outil === "fleche") {
      if (court) return;
      const index = indexDe(b.objets());
      const de = sousLePoint(index, g.depart), a = sousLePoint(index, p, de?.id);
      revenir();
      // d'un objet à un autre : c'est une RELATION entre deux cartes (typée, nommable), pas un simple dessin
      if (de && a) {
        void b.lier(de.id, a.id);
        return;
      }
      const geo = geometrieFleche({ point: g.depart, cible: de }, { point: p, cible: a });
      void b.creer({ type: "fleche", ...geo.boite, meta: { ...meta, points: geo.points, ancres: geo.ancres, pointes: "fin", epaisseur: 3 }, analyser: false }, "Flèche")
        .then((id) => b.selectionner([id])).catch((x: Error) => b.toast(x.message, { erreur: true }));
      return;
    }
    if (FORMES.has(g.outil)) {
      const [dl, dh] = DEFAUT[g.outil]!;
      const z = court ? { x: p.x - dl / 2, y: p.y - dh / 2, largeur: dl, hauteur: dh } : entreCoins(g.depart, p);
      const boite = { x: Math.round(z.x), y: Math.round(z.y), largeur: Math.round(Math.max(40, z.largeur)), hauteur: Math.round(Math.max(40, z.hauteur)) };
      const cadre = g.outil === "cadre";
      revenir();
      void b.creer(cadre ? { type: "cadre", ...boite, meta: { titre: "Cadre" }, analyser: false }
        : { type: "forme", ...boite, meta: { ...meta, forme: g.outil as "rectangle" | "ellipse" | "losange", epaisseur: 3 }, analyser: false }, cadre ? "Cadre" : "Forme")
        .then((id) => b.selectionner([id])).catch((x: Error) => b.toast(x.message, { erreur: true }));
    }
  };

  return (
    <div ref={racine} className="couche-outils nodrag nopan" data-outil={outil} aria-hidden
      onPointerDown={debut} onPointerMove={mouvement} onPointerUp={fin} onPointerCancel={abandonner}
      onContextMenu={(e) => e.preventDefault()}>
      <svg className="apercu">
        <g ref={groupe}>
          {enAttente.map((a) => <path key={a.cle} d={a.d} className={a.classe} />)}
          <path ref={trace} className="apercu-trace" />
          <path ref={forme} className="apercu-forme" />
        </g>
      </svg>
    </div>
  );
}
