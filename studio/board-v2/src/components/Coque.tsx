import { memo, useEffect, useRef, useState } from "react";
import type { EspaceBoard } from "../types";
import { useReactFlow, useStore } from "@xyflow/react";
import {
  ChevronDown, ClipboardPaste, Ellipsis, File, Grid3x3, Image as IconeImage, 
  Check, FolderGit2, Link2, Maximize, Minus, Mic, Network, Plus, Sparkles, Star, Type, Upload, Video,
} from "lucide-react";

export { ProductNav as BarreHaut } from "../product/ProductNav";

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

/** Un Board par projet : les projets Jarvis connus + les Boards déjà créés ; « Nouveau Board » en crée un. */
function MenuProjet({ projet, espaces, changer }: { projet: string; espaces: EspaceBoard[]; changer: (nom: string) => void }) {
  const [ouvert, setOuvert] = useState(false);
  const [nouveau, setNouveau] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ouvert) return;
    const fermer = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOuvert(false); };
    const echap = (e: KeyboardEvent) => { if (e.key === "Escape") setOuvert(false); };
    window.addEventListener("pointerdown", fermer);
    window.addEventListener("keydown", echap);
    return () => {
      window.removeEventListener("pointerdown", fermer);
      window.removeEventListener("keydown", echap);
    };
  }, [ouvert]);
  return (
    <div ref={ref} className="menu-projet">
      <button type="button" className="bouton-projet" aria-haspopup="menu" aria-expanded={ouvert} aria-label={`Board : ${projet}. Changer de projet`}
        onClick={() => { setOuvert((v) => !v); setNouveau(null); }}>
        <Network size={20} color="var(--text-secondary)" /><span>{projet}</span><ChevronDown size={16} color="var(--text-secondary)" />
      </button>
      {ouvert && (
        <div role="menu" className="menu-deroulant liste-projets">
          {espaces.map((e) => (
            <button key={e.nom} role="menuitemradio" aria-checked={e.nom === projet || (e.nom === "accueil" && projet === "Accueil")}
              onClick={() => { setOuvert(false); changer(e.nom); }} title={e.description || undefined}>
              {e.projet ? <FolderGit2 size={15} /> : <Network size={15} />}
              <span className="nom-projet">{e.nom === "accueil" ? "Accueil" : e.nom}</span>
              <span className="compte tab-num">{e.objets}</span>
              {(e.nom === projet || (e.nom === "accueil" && projet === "Accueil")) && <Check size={14} />}
            </button>
          ))}
          {nouveau === null ? (
            <button role="menuitem" onClick={() => setNouveau("")}><Plus size={15} /> Nouveau Board</button>
          ) : (
            <form className="nouveau-projet" onSubmit={(e) => { e.preventDefault(); if (nouveau.trim()) { setOuvert(false); changer(nouveau.trim()); } }}>
              <input className="champ" autoFocus maxLength={80} placeholder="Nom du projet" aria-label="Nom du nouveau Board"
                value={nouveau} onChange={(e) => setNouveau(e.target.value)} />
              <button type="submit" className="bouton primaire" disabled={!nouveau.trim()}>Créer</button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

export const SousBarre = memo(function SousBarre({ projet, espaces = [], changerEspace, demo, compteurs, filtre, setFiltre, priorite, setPriorite, magnetisme, setMagnetisme, lancer }: {
  projet: string; espaces?: EspaceBoard[]; changerEspace?: (nom: string) => void; demo: boolean; compteurs: Record<Filtre, number>; filtre: Filtre; setFiltre: (f: Filtre) => void;
  priorite: string; setPriorite: (p: string) => void; magnetisme: boolean; setMagnetisme: (v: boolean) => void; lancer: () => void;
}) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const zoom = useStore((s) => s.transform[2]);
  return (
    <div className="subbar">
      <div className="projet">
        {changerEspace && !demo ? <MenuProjet projet={projet} espaces={espaces} changer={changerEspace} /> : (
          <><Network size={20} color="var(--text-secondary)" /><span>{projet}</span><ChevronDown size={16} color="var(--text-secondary)" /></>
        )}
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
