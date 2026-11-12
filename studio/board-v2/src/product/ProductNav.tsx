import { memo, useEffect, useRef } from "react";
import { BarChart3, Bot, Library, Folder, Home, LayoutGrid, Moon, Search, Settings, Sun, Target } from "lucide-react";
import { resoudreTheme, ui, useUi } from "../etat/ui";
import { useStudioNavigation, type Vue } from "./routing";
import { Marque } from "../components/Marque";
import "./navigation.css";

const items = [
  ["accueil", "Accueil", Home],
  ["board", "Board", LayoutGrid],
  ["missions", "Missions", Target],
  ["agents", "Agents", Bot],
  ["references", "Références", Library],
  ["fichiers", "Fichiers", Folder],
  ["analytique", "Activité", BarChart3],
  ["configuration", "Configuration", Settings],
] as const;

type Props = {
  recherche?: string;
  setRecherche?: (value: string) => void;
  notifications?: number;
};

export const ProductNav = memo(function ProductNav({ recherche = "", setRecherche, notifications = 0 }: Props) {
  const { vue, aller } = useStudioNavigation();
  const input = useRef<HTMLInputElement>(null);
  const demo = new URLSearchParams(location.search).get("demo") === "1";
  // thème effectif (« auto » suit le système) : le bouton propose l'autre
  const theme = useUi((e) => e.theme);
  const jour = resoudreTheme(theme, typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: light)").matches) === "jour";

  // la section courante reste visible quand la navigation défile (petit écran) : elle revient au centre à chaque changement de vue
  const nav = useRef<HTMLElement>(null);
  useEffect(() => {
    nav.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView?.({ inline: "center", block: "nearest" });
  }, [vue]);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      // dans le Board, Ctrl/⌘+K ouvre la palette de commandes (registre) ; la recherche y répond à « / »
      if (vue === "board") return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && setRecherche) {
        event.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [setRecherche, vue]);

  return (
    <header className="topbar product-nav">
      <button className="marque product-brand" onClick={() => aller("accueil")} aria-label="Jarvis Studio, accueil">
        <Marque />Jarvis<span>Studio</span>
      </button>
      <nav ref={nav} className="nav" aria-label="Sections">
        {items.map(([key, label, Icon]) => (
          <button key={key} type="button" onClick={() => aller(key as Vue)}
            aria-current={vue === key || (key === "references" && vue === "connaissances") ? "page" : undefined} title={label}>
            <Icon strokeWidth={1.5} /><span>{label}</span>
          </button>
        ))}
      </nav>
      {/* la recherche garde sa place sur toutes les vues : la barre ne se recompose pas d'un onglet à l'autre. Là où il n'y a
          rien à filtrer (accueil, activité, configuration, références qui a son propre champ), la place est réservée, vide. */}
      {setRecherche ? (
        <label className="recherche">
          <Search size={16} strokeWidth={1.5} />
          <input ref={input} value={recherche} type="search" placeholder="Rechercher"
            aria-label={vue === "board" ? "Rechercher dans le Board" : "Rechercher dans cet espace"}
            onChange={event => setRecherche(event.target.value)} />
          <span className="touches-raccourci" aria-hidden>{vue === "board" ? <kbd>/</kbd> : <><kbd>Ctrl</kbd><kbd>K</kbd></>}</span>
        </label>
      ) : <span className="recherche recherche-reservee" aria-hidden />}
      {notifications > 0 && (
        <button className="p-button p-quiet p-notifications" onClick={() => aller("board")}
          aria-label={`${notifications} approbations en attente sur le Board`}>
          <span className="p-a-valider tab-num">{notifications}</span> à valider
        </button>
      )}
      {/* hors du Board (qui a son bouton dans sa barre et sa commande Maj+D) : le thème se change ici, pour tout le produit */}
      {/* sur le Board, ce bouton n'apparaît qu'en petit écran, où la sous-barre n'affiche plus le sien */}
      {(
        <button type="button" className={`p-icon-button p-theme${vue === "board" ? " p-theme-board" : ""}`} aria-label={jour ? "Passer au thème nuit" : "Passer au thème jour"}
          title={jour ? "Thème nuit" : "Thème jour"} aria-pressed={jour} onClick={() => ui.definir({ theme: jour ? "nuit" : "jour" })}>
          {jour ? <Moon size={16} strokeWidth={1.5} aria-hidden /> : <Sun size={16} strokeWidth={1.5} aria-hidden />}
        </button>
      )}
      {/* le Board affiche déjà son propre bandeau « DÉMO » : un seul badge par écran */}
      {!(demo && vue === "board") && (
        <span className={`p-mode ${demo ? "is-demo" : ""}`}
          title={demo ? "Données fictives. Aucune exécution réelle." : "Interface locale. La disponibilité des fournisseurs se vérifie dans Configuration."}>
          {demo ? "Démo" : "Local"}
        </span>
      )}
    </header>
  );
});
