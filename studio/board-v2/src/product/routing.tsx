import { createContext, useCallback, useContext, useEffect, useState, useRef, type ReactNode } from "react";

export const VUES = ["accueil", "board", "agents", "missions", "connaissances", "fichiers", "analytique", "configuration"] as const;
export type Vue = typeof VUES[number];
function lireVue(): Vue {
  const v = new URLSearchParams(location.search).get("vue");
  return VUES.includes(v as Vue) ? v as Vue : "board";
}
type Brouillon = { texte: string; pourquoi: string; base: string };
const Navigation = createContext<{ vue: Vue; aller: (vue: Vue, extras?: Record<string, string>) => void; lireBrouillon: (id: string) => Brouillon | undefined; garderBrouillon: (id: string, d: Brouillon) => void; retirerBrouillon: (id: string) => void }>({
  vue: "board", aller: () => undefined, lireBrouillon: () => undefined, garderBrouillon: () => undefined, retirerBrouillon: () => undefined,
});
export function StudioNavigation({ children }: { children: ReactNode }) {
  const brouillons = useRef(new Map<string, Brouillon>());
  const lireBrouillon = useCallback((id: string) => brouillons.current.get(id), []);
  const garderBrouillon = useCallback((id: string, d: Brouillon) => { brouillons.current.set(id, d); }, []);
  const retirerBrouillon = useCallback((id: string) => { brouillons.current.delete(id); }, []);
  useEffect(() => {
    const protect = (e: BeforeUnloadEvent) => { if (brouillons.current.size) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, []);
  const [vue, setVue] = useState(lireVue);
  useEffect(() => {
    const update = () => setVue(lireVue());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const aller = useCallback((next: Vue, extras: Record<string, string> = {}) => {
    const u = new URL(location.href);
    u.searchParams.set("vue", next);
    for (const key of ["carte", "filtre", "q", "priorite", "agent"]) u.searchParams.delete(key);
    for (const [key, value] of Object.entries(extras)) u.searchParams.set(key, value);
    history.pushState(null, "", u);
    setVue(next);
  }, []);
  return <Navigation.Provider value={{ vue, aller, lireBrouillon, garderBrouillon, retirerBrouillon }}>{children}</Navigation.Provider>;
}
export const useStudioNavigation = () => useContext(Navigation);
