// Déplacer et redimensionner dans le canevas : guides magnétiques, cadres qui emportent leur contenu, rangement
// dans un dossier, puis UNE écriture annulable au relâchement.
//
// React Flow calcule la position d'un nœud glissé à partir du pointeur et nous la propose (onNodesChange). On la
// corrige avant de l'appliquer : accroche sur les voisins (index spatial, seuil de 6 px écran), et même décalage
// pour le contenu des cadres glissés. La dernière position corrigée de chaque nœud est gardée : c'est elle qui est
// enregistrée, pas la position brute que React Flow renvoie au relâchement.
import { useCallback, useRef, useState } from "react";
import { applyNodeChanges, type Edge, type Node, type NodeChange, type ReactFlowInstance } from "@xyflow/react";
import type { Modification } from "../api";
import type { ServicesBoard } from "../commandes/contexte";
import type { DonneesLien } from "../edges/RelationEdge";
import { ui } from "../etat/ui";
import { accrocher, boiteDe, contenuDuCadre, indexDe, type Guide } from "../outils/espace";
import { englobante, type Boite, type Point } from "../outils/geometrie";
import type { DonneesNoeud } from "../types";

type Noeud = Node<DonneesNoeud>;
type Rf = ReactFlowInstance<Noeud, Edge<DonneesLien>>;
const SEUIL_ECRAN = 6;
const VOISINES_MAX = 300;

export function useGlisser(rf: Rf, b: ServicesBoard, setNoeuds: (f: (ns: Noeud[]) => Noeud[]) => void) {
  const [guides, setGuides] = useState<Guide[]>([]);
  const [enCours, setEnCours] = useState(false);
  const depart = useRef(new Map<string, Point>());
  /** contenu des cadres glissés : identifiant → cadre qui l'emporte */
  const emportes = useRef(new Map<string, string>());
  const dernieres = useRef(new Map<string, Point>());
  const voisines = useRef<Boite[]>([]);
  const departTaille = useRef(new Map<string, { largeur: number; hauteur: number }>());
  const minuteries = useRef(new Map<string, number>());

  const onNodeDragStart = useCallback((_: unknown, __: Noeud, ns: Noeud[]) => {
    const index = indexDe(b.objets());
    const glisses = new Set(ns.map((n) => n.id));
    depart.current = new Map(ns.map((n) => [n.id, { x: n.position.x, y: n.position.y }]));
    emportes.current = new Map();
    dernieres.current = new Map();
    for (const n of ns) {
      if (n.type !== "cadre") continue;
      for (const o of contenuDuCadre(index, n.data.objet)) {
        if (glisses.has(o.id) || o.verrouille || emportes.current.has(o.id)) continue;
        emportes.current.set(o.id, n.id);
        depart.current.set(o.id, { x: o.x, y: o.y });
      }
    }
    // voisines possibles pour l'accroche : ce qui est à l'écran, hors objets en mouvement
    const r = document.querySelector(".canevas")?.getBoundingClientRect();
    if (r && ui.lire().guides && !ui.lire().grille) {
      const hg = rf.screenToFlowPosition({ x: r.left, y: r.top }), bd = rf.screenToFlowPosition({ x: r.right, y: r.bottom });
      voisines.current = index.dans({ x: hg.x, y: hg.y, largeur: bd.x - hg.x, hauteur: bd.y - hg.y })
        .filter((o) => !glisses.has(o.id) && !emportes.current.has(o.id) && o.type !== "trait" && o.type !== "fleche").slice(0, VOISINES_MAX).map(boiteDe);
    } else voisines.current = [];
    setEnCours(true);
  }, [b, rf]);

  const onNodesChange = useCallback((changes: NodeChange<Noeud>[]) => {
    const glisse = changes.filter((c): c is Extract<NodeChange<Noeud>, { type: "position" }> => c.type === "position" && Boolean(c.position) && c.dragging === true);
    let tous: NodeChange<Noeud>[] = changes;
    if (glisse.length) {
      // 1. accroche magnétique de l'ensemble glissé sur ses voisines
      if (voisines.current.length) {
        const boites = glisse.map((c) => {
          const n = rf.getNode(c.id);
          return { x: c.position!.x, y: c.position!.y, largeur: n?.width ?? n?.measured?.width ?? 0, hauteur: n?.height ?? n?.measured?.height ?? 0 };
        });
        const a = accrocher(englobante(boites)!, voisines.current, SEUIL_ECRAN / rf.getZoom());
        if (a.dx || a.dy) for (const c of glisse) c.position = { x: c.position!.x + a.dx, y: c.position!.y + a.dy };
        setGuides((avant) => (avant.length === a.guides.length && avant.every((g, i) => g.axe === a.guides[i]!.axe && g.position === a.guides[i]!.position
          && g.debut === a.guides[i]!.debut && g.fin === a.guides[i]!.fin) ? avant : a.guides));
      }
      // 2. le contenu des cadres glissés suit du même décalage
      const suite: NodeChange<Noeud>[] = [];
      for (const c of glisse) dernieres.current.set(c.id, c.position!);
      for (const [id, cadre] of emportes.current) {
        const pc = dernieres.current.get(cadre), dc = depart.current.get(cadre), d = depart.current.get(id);
        if (!pc || !dc || !d) continue;
        const position = { x: d.x + pc.x - dc.x, y: d.y + pc.y - dc.y };
        dernieres.current.set(id, position);
        suite.push({ id, type: "position", position, dragging: true });
      }
      if (suite.length) tous = [...changes, ...suite];
    }
    for (const c of tous) {
      // relâchement : React Flow renvoie la position brute ; on garde la dernière position corrigée
      if (c.type === "position" && c.dragging === false && dernieres.current.has(c.id)) c.position = dernieres.current.get(c.id);
      if (c.type === "dimensions" && c.dimensions) {
        const o = b.objet(c.id);
        if (c.resizing && o && !departTaille.current.has(c.id)) departTaille.current.set(c.id, { largeur: o.largeur, hauteur: o.hauteur });
        if (c.resizing === false && departTaille.current.has(c.id)) {
          departTaille.current.delete(c.id);
          const n = rf.getNode(c.id);
          void b.modifier([{ id: c.id, champs: { largeur: Math.round(c.dimensions.width), hauteur: Math.round(c.dimensions.height),
            ...(n ? { x: Math.round(n.position.x), y: Math.round(n.position.y) } : {}) } }], "Redimensionnement");
        }
      }
      // déplacement au clavier (flèches) : enregistré après une courte pause
      if (c.type === "position" && c.position && c.dragging === undefined) {
        const id = c.id, pos = c.position;
        window.clearTimeout(minuteries.current.get(id));
        minuteries.current.set(id, window.setTimeout(() => {
          void b.modifier([{ id, champs: { x: Math.round(pos.x), y: Math.round(pos.y) } }], "Déplacement");
        }, 400));
      }
    }
    setNoeuds((ns) => applyNodeChanges(tous, ns));
  }, [b, rf, setNoeuds]);

  const onNodeDragStop = useCallback(async (_: unknown, noeud: Noeud, ns: Noeud[]) => {
    const d = depart.current, fin = dernieres.current, suivis = [...emportes.current.keys()];
    const position = (id: string, defaut: Point) => fin.get(id) ?? defaut;
    setGuides([]);
    setEnCours(false);
    // le contenu emporté quitte l'état « en cours de glisser »
    if (suivis.length) setNoeuds((liste) => applyNodeChanges(suivis.map((id) => ({ id, type: "position" as const, position: fin.get(id), dragging: false })), liste));
    const mods: Modification[] = [...ns.map((n) => ({ id: n.id, p: position(n.id, n.position) })), ...suivis.map((id) => ({ id, p: fin.get(id) }))]
      .filter((m): m is { id: string; p: Point } => {
        const o = d.get(m.id);
        return Boolean(m.p && o && (Math.abs(o.x - m.p.x) > 0.5 || Math.abs(o.y - m.p.y) > 0.5));
      }).map((m) => ({ id: m.id, champs: { x: Math.round(m.p.x), y: Math.round(m.p.y) } }));
    dernieres.current = new Map();
    emportes.current = new Map();
    // dépôt d'une carte seule sur un dossier : elle y est rangée
    if (ns.length === 1 && noeud.type !== "dossier" && noeud.type !== "cadre") {
      const dossier = rf.getIntersectingNodes(noeud).find((n) => n.type === "dossier" && n.id !== noeud.id);
      if (dossier) {
        await b.modifier([{ id: noeud.id, champs: { parent_id: dossier.id } }], "Rangement dans le dossier");
        b.toast("Carte rangée dans le dossier", { action: { nom: "Annuler", faire: () => void b.annuler() } });
        return;
      }
    }
    if (mods.length) await b.modifier(mods, "Déplacement");
  }, [b, rf, setNoeuds]);

  return { guides, enCours, onNodesChange, onNodeDragStart, onNodeDragStop };
}
