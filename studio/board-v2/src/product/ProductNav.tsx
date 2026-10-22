import { memo, useEffect, useRef } from "react";
import { ArrowUpRight, BarChart3, BookOpen, Bot, Folder, Home, LayoutGrid, Search, Settings, Target } from "lucide-react";
import { useStudioNavigation, type Vue } from "./routing";
import "./navigation.css";
const items = [["accueil", "Accueil", Home], ["board", "Board", LayoutGrid], ["missions", "Missions", Target],
  ["agents", "Agents", Bot], ["connaissances", "Connaissances", BookOpen], ["fichiers", "Fichiers", Folder],
  ["analytique", "Activité", BarChart3], ["configuration", "Configuration", Settings]] as const;
export const ProductNav = memo(function ProductNav({ recherche = "", setRecherche, notifications = 0 }: {
  recherche?: string; setRecherche?: (value: string) => void; notifications?: number;
}) {
  const { vue, aller } = useStudioNavigation();
  const input = useRef<HTMLInputElement>(null);
  const demo = new URLSearchParams(location.search).get("demo") === "1";
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && setRecherche) { e.preventDefault(); input.current?.focus(); } };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [setRecherche]);
  return <header className="topbar product-nav">
    <button className="marque product-brand" onClick={() => aller("accueil")} aria-label="Jarvis Studio, accueil"><img src="/v2/jarvis-mark.svg" alt="" />Jarvis<span>Studio</span></button>
    <nav className="nav" aria-label="Sections">{items.map(([key, label, Icon]) => <button key={key} type="button"
      onClick={() => aller(key as Vue)} aria-current={vue === key ? "page" : undefined} title={label}><Icon /><span>{label}</span></button>)}</nav>
    {setRecherche && <label className="recherche"><Search size={16} /><input ref={input} value={recherche} type="search"
      aria-label={vue === "board" ? "Rechercher dans le Board" : "Rechercher dans cet espace"} placeholder="Rechercher..." onChange={e => setRecherche(e.target.value)} /><kbd>Ctrl K</kbd></label>}
    {notifications > 0 && <button className="p-button p-quiet p-notifications" onClick={() => aller("missions")} aria-label={`${notifications} approbations en attente`}>{notifications} à valider<ArrowUpRight size={14}/></button>}
    <span className={`p-mode ${demo ? "is-demo" : ""}`} title={demo ? "Données fictives. Aucune exécution réelle." : "Interface locale ; ce badge ne prouve pas la disponibilité des fournisseurs."}>{demo ? "DÉMO" : "LOCAL"}</span>
  </header>;
