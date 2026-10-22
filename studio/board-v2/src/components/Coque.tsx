import { memo, useEffect, useRef, useState } from "react";
import { useReactFlow, useStore } from "@xyflow/react";
import {
  BarChart3, BookOpen, Bot, ChevronDown, ClipboardPaste, Ellipsis, File, Folder, Grid3x3, Image as IconeImage, LayoutGrid,
  Link2, Maximize, Minus, Mic, Network, Plus, Search, Settings, Bell, Sparkles, Star, Type, Upload, Users, Video,
} from "lucide-react";

/* ---------------------------------------------------------------- barre supérieure ------------------------- */
export const BarreHaut = memo(function BarreHaut({ recherche, setRecherche, notifications }: {
  recherche: string; setRecherche: (v: string) => void; notifications: number;
}) {
  const champ = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        champ.current?.focus();
      }
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, []);
  const onglets: [string, typeof LayoutGrid][] = [["Board", LayoutGrid], ["Missions", Bot], ["Agents", Users], ["Connaissances", BookOpen],
    ["Fichiers", Folder], ["Analytique", BarChart3], ["Configuration", Settings]];
  return (
    <header className="topbar">
      <div className="marque"><img src="/v2/jarvis-mark.svg" alt="" /> Jarvis Studio</div>
      <nav className="nav" aria-label="Sections">
        {onglets.map(([nom, Icone]) => (
          <button key={nom} type="button" aria-current={nom === "Board" ? "page" : undefined} disabled={nom !== "Board"}
            title={nom === "Board" ? undefined : "Bientôt dans le Studio V2 (l'ancien Studio reste sur /)"}>
            <Icone /><span>{nom}</span>
          </button>
        ))}
      </nav>
      <label className="recherche">
        <Search size={17} />
        <input ref={champ} type="search" placeholder="Rechercher dans Jarvis…" value={recherche} onChange={(e) => setRecherche(e.target.value)}
          aria-label="Rechercher dans le Board" />
        <kbd>Ctrl K</kbd>
      </label>
      <button type="button" className="icone-bouton" aria-label={`${notifications} approbation(s) en attente`} style={{ marginLeft: 100 }}>
        <Bell size={21} />{notifications > 0 && <span className="pastille-notif" />}
      </button>
      <div className="profil">
        <span className="profil-avatar" aria-label="Ton profil">J</span>
        <ChevronDown size={18} className="chevron" color="var(--text-secondary)" />
      </div>
    </header>
  );
});

/* ---------------------------------------------------------------- seconde rangée --------------------------- */
export type Filtre = "tous" | "notes" | "fichiers" | "liens" | "medias" | "missions" | "agents";
export const FILTRES: { cle: Filtre; nom: string; types: string[] }[] = [
  { cle: "tous", nom: "Tous", types: [] },
  { cle: "notes", nom: "Notes", types: ["note", "texte"] },
  { cle: "fichiers", nom: "Fichiers", types: ["pdf", "document", "dossier"] },
  { cle: "liens", nom: "Liens", types: ["lien"] },
  { cle: "medias", nom: "Médias", types: ["image", "audio", "video", "capture"] },
  { cle: "missions", nom: "Missions", types: ["mission"] },
  { cle: "agents", nom: "Agents", types: ["agents"] },
];

export const SousBarre = memo(function SousBarre({ projet, demo, compteurs, filtre, setFiltre, priorite, setPriorite, magnetisme, setMagnetisme, lancer }: {
  projet: string; demo: boolean; compteurs: Record<Filtre, number>; filtre: Filtre; setFiltre: (f: Filtre) => void;
  priorite: string; setPriorite: (p: string) => void; magnetisme: boolean; setMagnetisme: (v: boolean) => void; lancer: () => void;
}) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const zoom = useStore((s) => s.transform[2]);
  return (
    <div className="subbar">
      <div className="projet">
        <Network size={20} color="var(--text-secondary)" />
        <span>{projet}</span><ChevronDown size={16} color="var(--text-secondary)" />
        {demo && <span className="bandeau-demo" role="note" title="Données fictives, rien n'est enregistré">DÉMO</span>}
        <span className="actions-projet"><Star size={18} /><Ellipsis size={18} style={{ marginLeft: 22 }} /></span>
      </div>
      <div className="filtres" role="group" aria-label="Filtrer par type">
        {FILTRES.map((f) => (
          <button key={f.cle} type="button" aria-pressed={filtre === f.cle} onClick={() => setFiltre(f.cle)}>
            {f.nom}<span className="compte tab-num">{compteurs[f.cle]}</span>
          </button>
        ))}
        <button type="button" aria-label="Filtrer par priorité" title="Filtrer par priorité"
          onClick={() => setPriorite(priorite === "" ? "P1" : priorite === "P1" ? "P2" : priorite === "P2" ? "P3" : "")}>
          {priorite ? <span className={`badge-p ${priorite}`} style={{ height: 20, minWidth: 26, fontSize: 11 }}>{priorite}</span> : <Plus size={15} />}
        </button>
      </div>
      <div className="zoom" role="group" aria-label="Zoom">
        <button type="button" aria-label="Zoom arrière" onClick={() => zoomOut({ duration: 160 })}><Minus size={17} /></button>
        <output className="tab-num" aria-live="polite">{Math.round(zoom * 100)}%</output>
        <button type="button" aria-label="Zoom avant" onClick={() => zoomIn({ duration: 160 })}><Plus size={17} /></button>
      </div>
      <button type="button" className="bouton-carre" aria-label="Ajuster à la vue" title="Ajuster à la vue (Maj+1)"
        onClick={() => fitView({ duration: 220, padding: 0.08 })}><Maximize size={18} /></button>
      <button type="button" className="bouton-carre" aria-pressed={magnetisme} aria-label="Magnétisme de la grille"
        title="Magnétisme de la grille" onClick={() => setMagnetisme(!magnetisme)}><Grid3x3 size={18} /></button>
      <button type="button" className="bouton-principal" onClick={lancer}><Sparkles size={18} /> Lancer une mission</button>
    </div>
  );
});

/* ---------------------------------------------------------------- barre d'outils --------------------------- */
export type Outil = "ajouter" | "coller" | "importer" | "lien" | "texte" | "image" | "video" | "audio" | "document" | "mindmap";

export const BarreOutils = memo(function BarreOutils({ agir }: { agir: (o: Outil) => void }) {
  const items: [Outil, string, typeof Plus, boolean][] = [
    ["coller", "Coller", ClipboardPaste, false], ["importer", "Importer", Upload, false], ["lien", "Lien", Link2, false],
    ["texte", "Texte", Type, false], ["image", "Image", IconeImage, true], ["video", "Vidéo", Video, true],
    ["audio", "Audio", Mic, true], ["document", "Document", File, true], ["mindmap", "Mind map", Network, true],
  ];
  return (
    <div className="outils nodrag nopan" role="toolbar" aria-label="Ajouter au Board" aria-orientation="vertical">
      <button type="button" className="ajouter" onClick={() => agir("ajouter")} title="Ajouter une note (N)">
        <span><Plus size={22} /></span>Ajouter
      </button>
      {items.map(([cle, nom, Icone, secondaire]) => (
        <button key={cle} type="button" className={secondaire ? "secondaire" : undefined} onClick={() => agir(cle)}>
          <Icone />{nom}
        </button>
      ))}
      <button type="button" className="secondaire" aria-label="Plus d'outils" style={{ height: 40 }}><Ellipsis size={20} /></button>
    </div>
  );
});

/* ---------------------------------------------------------------- saisie d'URL ----------------------------- */
export function SaisieUrl({ valider, fermer }: { valider: (url: string) => void; fermer: () => void }) {
  const [v, setV] = useState("");
  return (
    <div className="popover nodrag nopan" style={{ left: 96, top: 150 }} role="dialog" aria-label="Ajouter un lien">
      <label htmlFor="url-lien">Adresse du lien</label>
      <input id="url-lien" autoFocus placeholder="https://…" value={v} onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && v.trim()) valider(v.trim());
          if (e.key === "Escape") fermer();
        }} />
      <div className="ligne">
        <button type="button" className="bouton" onClick={fermer}>Annuler</button>
        <button type="button" className="bouton primaire" disabled={!v.trim()} onClick={() => valider(v.trim())}>Ajouter</button>
      </div>
    </div>
  );
}
