import { useEffect, useRef, useState } from "react";
import type { Point } from "./GroupesMemoire";
import { positionsMemoire, translaterLot } from "./deplacementMemoire";

type Geste = { origine: string; departs: Map<string, Point>; membres: readonly string[] };
const nomStockage = (cle: string) => "jarvis.graphe.disposition.v1:" + cle;

function lire(cle?: string): Map<string, Point> {
  if (!cle) return new Map();
  try {
    const sauvegarde = JSON.parse(localStorage.getItem(nomStockage(cle)) ?? "{}") as { version?: number; points?: unknown };
    if (sauvegarde.version !== 1 || !Array.isArray(sauvegarde.points)) return new Map();
    const resultat = new Map<string, Point>();
    for (const entree of sauvegarde.points.slice(0, 5000)) {
      if (!Array.isArray(entree) || typeof entree[0] !== "string" || entree[0].length > 512) continue;
      const p = entree[1] as Partial<Point> | null;
      if (p && typeof p.x === "number" && typeof p.y === "number" && Number.isFinite(p.x) && Number.isFinite(p.y)
        && Math.abs(p.x) <= 1_000_000 && Math.abs(p.y) <= 1_000_000) resultat.set(entree[0], { x: p.x, y: p.y });
    }
    return resultat;
  } catch {
    return new Map();
  }
}

export function useEntrainementMemoire(points: ReadonlyMap<string, Point>, lots: ReadonlyMap<string, readonly string[]>,
  cleDisposition?: string) {
  const [positions, setPositions] = useState(() => lire(cleDisposition));
  const [deplace, setDeplace] = useState<string | null>(null);
  const [sauvegardeImpossible, setSauvegardeImpossible] = useState(false);
  const positionsRef = useRef(positions);
  const geste = useRef<Geste | null>(null);

  const publier = (suite: Map<string, Point>) => {
    positionsRef.current = suite;
    setPositions(suite);
  };
  const enregistrer = (suite: ReadonlyMap<string, Point>) => {
    if (!cleDisposition) return;
    try {
      localStorage.setItem(nomStockage(cleDisposition), JSON.stringify({ version: 1, points: [...suite].slice(-5000) }));
      setSauvegardeImpossible(false);
    } catch {
      setSauvegardeImpossible(true);
    }
  };

  useEffect(() => {
    publier(lire(cleDisposition));
    geste.current = null;
    setDeplace(null);
  }, [cleDisposition]);
  useEffect(() => {
    if (!cleDisposition) return;
    const attente = window.setTimeout(() => enregistrer(positionsRef.current), 240);
    const quitter = () => enregistrer(positionsRef.current);
    window.addEventListener("beforeunload", quitter);
    return () => { window.clearTimeout(attente); window.removeEventListener("beforeunload", quitter); };
  }, [positions, cleDisposition]);

  const commencer = (id: string, position: Point) => {
    const departs = positionsMemoire(points, positionsRef.current, lots);
    departs.set(id, position);
    geste.current = { origine: id, departs, membres: lots.get(id) ?? [] };
    publier(departs);
    setDeplace(id);
  };
  const changer = (modifications: readonly (readonly [string, Point])[]) => {
    if (!modifications.length) return;
    const courant = geste.current;
    if (courant) {
      const destination = modifications.find(([id]) => id === courant.origine)?.[1];
      if (destination) publier(translaterLot(courant.departs, courant.origine, destination, courant.membres));
      return;
    }
    let suite = positionsMemoire(points, positionsRef.current, lots);
    for (const [id, destination] of modifications) suite = translaterLot(suite, id, destination, lots.get(id) ?? []);
    publier(suite);
  };
  const terminer = (id: string, position: Point) => {
    if (geste.current?.origine !== id) return;
    changer([[id, position]]);
    geste.current = null;
    setDeplace(null);
    enregistrer(positionsRef.current);
  };
  const reinitialiser = () => {
    geste.current = null;
    setDeplace(null);
    publier(new Map());
    enregistrer(new Map());
  };
  return { positions, deplace, commencer, changer, terminer, reinitialiser, sauvegardeImpossible };
}
