import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import type { EspaceBoard } from "../types";
import { useStore } from "@xyflow/react";
import {
  ChevronDown, ClipboardPaste, Ellipsis, File, Grid3x3, ListFilter, Image as IconeImage,
  Check, Folder, FolderGit2, Link2, Maximize, Minus, Mic, Moon, Network, Plus, Presentation, Sun, Type, Upload, Video,
} from "lucide-react";
import { BoutonCommande, useCommandes } from "../commandes/react";
import { useUi } from "../etat/ui";

export { ProductNav as BarreHaut } from "../product/ProductNav";

/* ---------------------------------------------------------------- seconde rangée --------------------------- */
export type Filtre = "tous" | "notes" | "fichiers" | "liens" | "medias" | "missions" | "agents";
export const FILTRES: { cle: Filtre; nom: string; types: string[] }[] = [
  { cle: "tous", nom: "Tous", types: [] },
  { cle: "notes", nom: "Notes", types: ["note", "texte"] },
  { cle: "fichiers", nom: "Fichiers", types: ["pdf", "document", "dossier"] },
  { cle: "liens", nom: "Liens", types: ["lien"] },
  { cle: "medias", nom: "Médias", types: ["image", "audio", "video", "capture"] },
  { cle: "missions", nom: "Missions", types: ["mission", "plan", "tache"] },
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
        <Network size={16} aria-hidden /><span>{projet}</span><ChevronDown size={16} aria-hidden />
      </button>
      {ouvert && (
        <div role="menu" className="menu-deroulant liste-projets">
          {espaces.map((e) => (
            <button key={e.nom} role="menuitemradio" aria-checked={e.nom === projet || (e.nom === "accueil" && projet === "Accueil")}
              onClick={() => { setOuvert(false); changer(e.nom); }} title={e.description || undefined}>
              {e.projet ? <FolderGit2 size={16} /> : <Network size={16} />}
              <span className="nom-projet">{e.nom === "accueil" ? "Accueil" : e.nom}</span>
              <span className="compte">{e.objets}</span>
              {(e.nom === projet || (e.nom === "accueil" && projet === "Accueil")) && <Check size={16} />}
            </button>
          ))}
          {nouveau === null ? (
            <button role="menuitem" onClick={() => setNouveau("")}><Plus size={16} />Nouveau Board</button>
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

export const SousBarre = memo(function SousBarre({ projet, espaces = [], changerEspace, demo, compteurs, filtre, setFiltre, priorite, setPriorite, communaute }: {
  projet: string; espaces?: EspaceBoard[]; changerEspace?: (nom: string) => void; demo: boolean; compteurs: Record<Filtre, number>; filtre: Filtre; setFiltre: (f: Filtre) => void;
  priorite: string; setPriorite: (p: string) => void; communaute?: ReactNode;
}) {
  // chaque bouton de cette rangée est une commande du registre (même action que son raccourci et que la palette)
  const { executer } = useCommandes();
  const zoom = useStore((s) => s.transform[2]);
  const jour = useUi((e) => e.theme) === "jour";
  // fenêtre étroite : les filtres se replient derrière un bouton « Filtrer » qui ouvre la même liste (jamais de libellé rogné)
  const [filtresOuverts, setFiltresOuverts] = useState(false);
  const zoneFiltres = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!filtresOuverts) return;
    const dehors = (e: PointerEvent) => { if (!zoneFiltres.current?.contains(e.target as Node)) setFiltresOuverts(false); };
    const echap = (e: KeyboardEvent) => { if (e.key === "Escape") setFiltresOuverts(false); };
    window.addEventListener("pointerdown", dehors);
    window.addEventListener("keydown", echap);
    return () => { window.removeEventListener("pointerdown", dehors); window.removeEventListener("keydown", echap); };
  }, [filtresOuverts]);
  const filtreActif = FILTRES.find((f) => f.cle === filtre);
  return (
    <div className="subbar">
      <div className="projet">
        {changerEspace && !demo ? <MenuProjet projet={projet} espaces={espaces} changer={changerEspace} /> : (
          <><Network size={16} aria-hidden /><span>{projet}</span></>
        )}
        {demo && <span className="bandeau-demo" role="note" title="Données fictives, rien n'est enregistré">Démo</span>}
      </div>
      <div ref={zoneFiltres} className={`zone-filtres${filtresOuverts ? " ouverte" : ""}`}>
        <button type="button" className="filtres-replies" aria-expanded={filtresOuverts} aria-controls="liste-filtres"
          aria-label={`Filtrer : ${filtreActif?.nom ?? "Tous"}${priorite ? `, priorité ${priorite}` : ""}`} onClick={() => setFiltresOuverts((v) => !v)}>
          <ListFilter size={16} aria-hidden /><span>{filtre === "tous" ? "Filtrer" : filtreActif?.nom}</span>
          {priorite && <span className={`badge-p ${priorite} doux`}>{priorite}</span>}<ChevronDown size={16} aria-hidden />
        </button>
        <div id="liste-filtres" className="filtres" role="group" aria-label="Filtrer par type">
          {FILTRES.map((f) => (
            <button key={f.cle} type="button" aria-pressed={filtre === f.cle} onClick={() => { setFiltre(f.cle); setFiltresOuverts(false); }}>
              {f.nom}<span className="compte">{compteurs[f.cle]}</span>
            </button>
          ))}
          <button type="button" className="filtre-priorite" aria-label="Filtrer par priorité" title="Filtrer par priorité"
            onClick={() => setPriorite(priorite === "" ? "P1" : priorite === "P1" ? "P2" : priorite === "P2" ? "P3" : "")}>
            {priorite ? <span className={`badge-p ${priorite} doux`}>{priorite}</span> : <ListFilter size={16} />}<span className="nom-priorite">Priorité</span>
          </button>
        </div>
      </div>
      <div className="zoom" role="group" aria-label="Zoom">
        <BoutonCommande id="vue.zoomArriere"><Minus size={16} /></BoutonCommande>
        <output aria-live="polite">{Math.round(zoom * 100)}%</output>
        <BoutonCommande id="vue.zoomAvant"><Plus size={16} /></BoutonCommande>
      </div>
      <BoutonCommande id="vue.ajuster" classe="bouton-carre"><Maximize size={16} /></BoutonCommande>
      <BoutonCommande id="affichage.grille" classe="bouton-carre"><Grid3x3 size={16} /></BoutonCommande>
      <BoutonCommande id="affichage.theme.basculer" classe="bouton-carre">{jour ? <Moon size={16} /> : <Sun size={16} />}</BoutonCommande>
      <BoutonCommande id="presentation.demarrer" classe="bouton-carre"><Presentation size={16} /></BoutonCommande>
      <button type="button" className="bouton-principal" title="Lancer une mission (Ctrl+Maj+M)" onClick={() => executer("mission.lancer", "bouton")}>Lancer une mission</button>
      {communaute}
    </div>
  );
});

/* ---------------------------------------------------------------- barre d'ajout --------------------------- */
// Barre verticale « Ajouter au Board » : chaque entrée exécute une commande du registre.
const AJOUTS: [string, string, typeof Plus, boolean][] = [
  ["ajouter.pressePapiers", "Coller", ClipboardPaste, false], ["ajouter.importer", "Importer", Upload, false], ["ajouter.lien", "Lien", Link2, false],
  ["ajouter.note", "Texte", Type, false], ["ajouter.image", "Image", IconeImage, true], ["ajouter.video", "Vidéo", Video, true],
  ["ajouter.audio", "Audio", Mic, true], ["ajouter.document", "Document", File, true], ["ajouter.dossier", "Dossier", Folder, true],
];

export const BarreAjout = memo(function BarreAjout() {
  const { executer } = useCommandes();
  return (
    <div className="outils nodrag nopan" role="toolbar" aria-label="Ajouter au Board" aria-orientation="vertical">
      <button type="button" className="ajouter" onClick={() => executer("ajouter.note", "bouton", { selection: [] })} title="Ajouter une note (Maj+N)">
        <span><Plus size={16} /></span>Ajouter
      </button>
      {AJOUTS.map(([id, nom, Icone, secondaire]) => (
        <button key={id} type="button" className={secondaire ? "secondaire" : undefined} onClick={() => executer(id, "bouton", { selection: [] })}>
          <Icone />{nom}
        </button>
      ))}
      <button type="button" className="secondaire" aria-label="Toutes les commandes" title="Toutes les commandes (Ctrl+K)"
        onClick={() => executer("palette.ouvrir", "bouton")}><Ellipsis /></button>
    </div>
  );
});

/* ---------------------------------------------------------------- saisie d'URL ----------------------------- */
export function SaisieUrl({ valider, fermer }: { valider: (url: string) => void; fermer: () => void }) {
  const [v, setV] = useState("");
  return (
    <div className="popover saisie-url nodrag nopan" role="dialog" aria-label="Ajouter un lien">
      <label htmlFor="url-lien">Adresse du lien</label>
      <input id="url-lien" autoFocus placeholder="https://" value={v} onChange={(e) => setV(e.target.value)}
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
