// Le canevas : React Flow (MIT) et tout ce qui s'y passe — nœuds dérivés du store, glisser, relations, outils de
// tableau blanc, édition de texte en surcouche, guides, barre flottante, menu contextuel, modes d'affichage.
// Le composant ne lit jamais « tous les nœuds » du store de React Flow : il possède son tableau (mode contrôlé) et
// les surcouches s'abonnent au strict nécessaire (transformation, un booléen, un entier).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Background, BackgroundVariant, ConnectionMode, MarkerType, MiniMap, ReactFlow, useReactFlow,
  type Connection, type Edge, type EdgeChange, type Node, type Viewport,
} from "@xyflow/react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import type { Source } from "../api";
import { BarreFlottante } from "../commandes/BarreFlottante";
import { MARGE_DIAPOSITIVE, diapositives } from "../commandes/catalogue/affichage";
import type { ServicesBoard } from "../commandes/contexte";
import { MenuContextuel } from "../commandes/MenuContextuel";
import { BoutonCommande } from "../commandes/react";
import type { Filtre } from "../components/Coque";
import type { Instantane } from "../donnees/store";
import { RelationEdge, couleurRelation, type DonneesLien } from "../edges/RelationEdge";
import { EFFETS, lireFleche } from "../relations/effets";
import { ui, useUi } from "../etat/ui";
import { PlanNode, TacheNode } from "../nodes/CartesTravail";
import { AudioNode, VideoNode } from "../nodes/CartesMedia";
import { DossierNode, ImageNode, LienNode, PdfNode } from "../nodes/CartesVisuelles";
import { AgentsNode, MissionNode, NoteNode } from "../nodes/CartesVivantes";
import { FlecheNode } from "../nodes/Fleche";
import { AdhesifNode, CadreNode, FormeNode, TexteLibreNode, TraitNode } from "../nodes/Tableau";
import { BarreModes } from "../outils/BarreModes";
import { CoucheOutils } from "../outils/CoucheOutils";
import { EditeurTexte } from "../outils/EditeurTexte";
import { contenuDuCadre, indexDe } from "../outils/espace";
import { Guides } from "../outils/Guides";
import type { DonneesNoeud, ObjetBoard } from "../types";
import { ContexteDetail, MARGE_VUE, ZONE_LIBRE, ZOOM_MAX, ZOOM_MIN, useNiveauCalcule } from "./detail";
import { estVisible, versNoeud } from "./noeuds";
import { useGlisser } from "./useGlisser";

const TYPES_NOEUDS = {
  image: ImageNode, capture: ImageNode, lien: LienNode, pdf: PdfNode, document: PdfNode, note: NoteNode, texte: NoteNode,
  mission: MissionNode, agents: AgentsNode, audio: AudioNode, video: VideoNode, dossier: DossierNode, plan: PlanNode, tache: TacheNode,
  adhesif: AdhesifNode, texte_libre: TexteLibreNode, forme: FormeNode, trait: TraitNode, cadre: CadreNode, fleche: FlecheNode,
};
const TYPES_LIENS = { relation: RelationEdge };
const COULEUR_MINICARTE: Record<string, string> = {
  plan: "var(--accent-plan-strong)", tache: "var(--edge-utilise)", mission: "var(--brand-indigo)", agents: "var(--success)", note: "var(--note-border)",
  image: "var(--cadre-bord)", video: "var(--cadre-bord)", adhesif: "var(--adhesif-jaune)", forme: "var(--teinte-indigo)", cadre: "transparent",
  trait: "var(--teinte-neutre)", fleche: "transparent", texte_libre: "var(--teinte-neutre)",
};
const OUTILS_DIRECTS = new Set(["selection", "main"]);
/** sous 12 % de zoom, les relations ne sont plus tracées (illisibles, et les blocs n'ont plus de poignée) */
const SANS_RELATION: Edge<DonneesLien>[] = [];
type Noeud = Node<DonneesNoeud>;

interface Props {
  source: Source;
  etat: Instantane | null;
  b: ServicesBoard;
  filtre: Filtre;
  priorite: string;
  recherche: string;
  selection: ObjetBoard[];
  setSelection(f: (avant: string[]) => string[]): void;
  /** carte à sélectionner dès qu'elle existe (créée côté serveur, pas encore dans les nœuds) */
  aSelectionner: { current: Set<string> };
  deposer(transfert: DataTransfer, ou: { x: number; y: number }): void;
  children?: ReactNode;
}

export function Canevas({ source, etat, b, filtre, priorite, recherche, selection, setSelection, aSelectionner, deposer, children }: Props) {
  const rf = useReactFlow<Noeud, Edge<DonneesLien>>();
  const [noeuds, setNoeuds] = useState<Noeud[]>([]);
  const [depot, setDepot] = useState(false);
  const outil = useUi((e) => e.outil);
  const edition = useUi((e) => e.edition);
  const menu = useUi((e) => e.menu);
  const focus = useUi((e) => e.focus);
  const presentation = useUi((e) => e.presentation);
  const minicarte = useUi((e) => e.minicarte);
  const grille = useUi((e) => e.grille);
  const liaison = useUi((e) => e.liaison);
  const niveau = useNiveauCalcule();
  const { guides, enCours, onNodesChange, onNodeDragStart, onNodeDragStop } = useGlisser(rf, b, setNoeuds);

  /* ---------------------------------------------------------------- nœuds et relations dérivés du store ---- */
  const sources = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of etat?.liens ?? []) m.set(l.cible_id, (m.get(l.cible_id) ?? 0) + 1);
    return m;
  }, [etat?.liens]);
  // mode concentration (et présentation) : seul le cadre visé et son contenu restent nets
  const nets = useMemo(() => {
    const cadre = focus && etat ? etat.objets.find((o) => o.id === focus) : undefined;
    return cadre && etat ? new Set([cadre.id, ...contenuDuCadre(indexDe(etat.objets), cadre).map((o) => o.id)]) : null;
  }, [focus, etat]);

  useEffect(() => {
    if (!etat) return;
    setNoeuds((prec) => {
      const parId = new Map(prec.map((n) => [n.id, n]));
      return etat.objets.map((o) => {
        let n = versNoeud(o, source.demo, sources.get(o.id) ?? 0, Boolean(nets && !nets.has(o.id)), parId.get(o.id));
        if (aSelectionner.current.delete(o.id)) {
          if (!n.selected) n = { ...n, selected: true };
        }
        const cache = !estVisible(o, filtre, priorite, recherche);
        return Boolean(n.hidden) === cache ? n : { ...n, hidden: cache };
      });
    });
  }, [etat, source.demo, sources, nets, filtre, priorite, recherche, aSelectionner]);

  const renommer = useCallback((id: string, libelle: string) => void b.modifierLien(id, { libelle }), [b]);
  const aretes = useMemo<Edge<DonneesLien>[]>(() => {
    const parId = new Map((etat?.objets ?? []).map((o) => [o.id, o]));
    return (etat?.liens ?? []).map((l) => {
      // ce que la flèche fait en ce moment, lu dans le résumé que le serveur a calculé pour ses deux cartes
      const lecture = lireFleche(l, parId.get(l.source_id), parId.get(l.cible_id));
      return {
        id: l.id, source: l.source_id, target: l.cible_id, type: "relation",
        data: { libelle: l.libelle, style: l.style, renommer, cotes: l.cotes, auteur: l.auteur, lecture,
          estompe: Boolean(nets && !(nets.has(l.source_id) && nets.has(l.cible_id))) },
        className: nets && !(nets.has(l.source_id) && nets.has(l.cible_id)) ? "estompe" : undefined,
        ariaLabel: `Relation « ${EFFETS[l.style]?.nom ?? l.style} » : ${lecture.detail}`,
        markerEnd: { type: MarkerType.ArrowClosed, color: couleurRelation(l.style, lecture.etat), width: 16, height: 16 },
      };
    });
  }, [etat?.liens, etat?.objets, renommer, nets]);

  /* ---------------------------------------------------------------- sélection, relations ------------------- */
  // mémoïsé (exigé par React Flow) et sans nouvelle valeur si la sélection n'a pas changé : sinon boucle de rendu
  const surSelection = useCallback(({ nodes }: { nodes: Node[] }) => {
    setSelection((avant) => {
      const ids = nodes.map((n) => n.id);
      return ids.length === avant.length && ids.every((id, i) => id === avant[i]) ? avant : ids;
    });
  }, [setSelection]);

  const onEdgesChange = useCallback((changes: EdgeChange<Edge<DonneesLien>>[]) => {
    for (const c of changes) if (c.type === "remove") void b.supprimerLien(c.id);
  }, [b]);

  const derniereConnexion = useRef({ cle: "", t: 0 });
  const onConnect = useCallback(async (c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    // React Flow peut signaler deux fois le même relâchement sur une poignée (mode de connexion libre) : un seul ajout
    const cle = `${c.source}>${c.target}`;
    if (derniereConnexion.current.cle === cle && performance.now() - derniereConnexion.current.t < 800) return;
    derniereConnexion.current = { cle, t: performance.now() };
    if (await b.lier(c.source, c.target)) b.toast("Relation créée, sans effet pour l'instant — clic droit sur la flèche : « Dépend de » bloque, « Alimente » joint le livrable");
  }, [b]);

  const onNodeClick = useCallback((_: unknown, n: Node) => {
    const depuis = ui.lire().liaison;
    if (!depuis || depuis === n.id) return;
    ui.definir({ liaison: null });
    void b.lier(depuis, n.id).then((id) => id && b.toast("Relation créée, sans effet pour l'instant — clic droit sur la flèche : « Dépend de » bloque, « Alimente » joint le livrable"));
  }, [b]);

  const ouvrirMenu = useCallback((e: { clientX: number; clientY: number; preventDefault(): void }, cible?: string, lien?: string) => {
    e.preventDefault();
    if (ui.lire().presentation !== null) return;
    if (cible && !rf.getNode(cible)?.selected) b.selectionner([cible]);
    ui.definir({ menu: { x: e.clientX, y: e.clientY, cible, lien, point: rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }) } });
  }, [rf, b]);
  const fermerMenu = useCallback(() => ui.definir({ menu: null }), []);
  // la cible du menu : une relation, la carte visée, la sélection en cours, ou le canevas (sélection vide)
  const extraMenu = useMemo(() => {
    if (!menu) return {};
    if (menu.lien) return { selection: [], lien: etat?.liens.find((l) => l.id === menu.lien), point: menu.point };
    if (!menu.cible) return { selection: [], point: menu.point };
    const visee = etat?.objets.find((o) => o.id === menu.cible);
    return { selection: selection.some((o) => o.id === menu.cible) ? selection : visee ? [visee] : [], point: menu.point };
  }, [menu, etat, selection]);

  /* ---------------------------------------------------------------- rendu ---------------------------------- */
  // la démo ouvre sur une vue fixe (contrat visuel), décalée sous la barre d'outils ; un vrai Board est cadré dans
  // la zone libre du canevas (fitView + MARGE_VUE) : dans les deux cas aucune carte n'est sous une barre à l'ouverture
  const vueInitiale: Viewport = source.demo ? { x: 0, y: ZONE_LIBRE.top - 12, zoom: 0.8 } : { x: ZONE_LIBRE.left, y: ZONE_LIBRE.top, zoom: 0.8 };
  const direct = OUTILS_DIRECTS.has(outil);
  const enPresentation = presentation !== null;
  const manipulable = outil === "selection" && !enPresentation;
  const enEdition = edition ? etat?.objets.find((o) => o.id === edition) : undefined;
  const cadres = useMemo(() => (enPresentation && etat ? diapositives(etat.objets) : []), [enPresentation, etat]);
  // présentation : la diapositive est recadrée quand le canevas change de taille (barres masquées, plein écran,
  // fenêtre redimensionnée) — sinon elle resterait cadrée pour l'ancienne mise en page
  const diapo = presentation !== null ? cadres[presentation] : undefined;
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!diapo || !section.current) return;
    const zone = { x: diapo.x, y: diapo.y, largeur: diapo.largeur, hauteur: diapo.hauteur };
    let image = 0;
    const observateur = new ResizeObserver(() => {
      cancelAnimationFrame(image);
      image = requestAnimationFrame(() => b.cadrer(zone, MARGE_DIAPOSITIVE));
    });
    observateur.observe(section.current);
    return () => {
      observateur.disconnect();
      cancelAnimationFrame(image);
    };
  }, [diapo, b]);

  return (
    <section ref={section} className={`canevas outil-${outil}${liaison ? " en-liaison" : ""}${enPresentation ? " en-presentation" : ""}${focus ? " en-concentration" : ""}`}
      aria-label="Canevas du Board"
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files") || e.dataTransfer.types.includes("text/uri-list")) { e.preventDefault(); setDepot(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDepot(false); }}
      onDrop={(e) => {
        e.preventDefault();
        setDepot(false);
        deposer(e.dataTransfer, rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
      }}>
      <ContexteDetail.Provider value={niveau}>
      <ReactFlow
        nodes={noeuds} edges={niveau === 2 ? SANS_RELATION : aretes} nodeTypes={TYPES_NOEUDS} edgeTypes={TYPES_LIENS}
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
        onNodeDragStart={onNodeDragStart} onNodeDragStop={onNodeDragStop} onNodeClick={onNodeClick}
        onSelectionChange={surSelection}
        onNodeContextMenu={(e, n) => ouvrirMenu(e, n.id)} onPaneContextMenu={(e) => ouvrirMenu(e)}
        onEdgeContextMenu={(e, l) => ouvrirMenu(e, undefined, l.id)} onSelectionContextMenu={(e) => ouvrirMenu(e, selection[0]?.id)}
        defaultViewport={vueInitiale} minZoom={ZOOM_MIN} maxZoom={ZOOM_MAX} connectionMode={ConnectionMode.Loose}
        snapToGrid={grille} snapGrid={[20, 20]} deleteKeyCode={null} multiSelectionKeyCode={["Shift", "Meta", "Control"]}
        selectionKeyCode="Shift" panOnScroll={false} zoomOnDoubleClick={false} onlyRenderVisibleElements={noeuds.length > 80}
        nodesDraggable={manipulable} nodesConnectable={manipulable} elementsSelectable={manipulable}
        elevateNodesOnSelect={false} proOptions={{ hideAttribution: false }} fitView={!source.demo && Boolean(etat?.objets.length)}
        fitViewOptions={{ padding: MARGE_VUE, maxZoom: 0.9 }}>
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.6} color="var(--grid-dot)" />
        {minicarte && !enPresentation && (
          <MiniMap pannable zoomable ariaLabel="Mini-carte du Board" nodeBorderRadius={8} maskColor="var(--minimap-mask)"
            nodeColor={(n) => COULEUR_MINICARTE[n.type ?? ""] ?? "var(--minimap-node)"} style={{ width: 124, height: 92 }} />
        )}
      </ReactFlow>
      </ContexteDetail.Provider>
      {!direct && !enPresentation && <CoucheOutils outil={outil} b={b} />}
      <Guides guides={guides} />
      {enEdition && <EditeurTexte key={enEdition.id} objet={enEdition} b={b} fermer={() => ui.definir({ edition: null })} />}
      {!enPresentation && <BarreModes />}
      {selection.length > 0 && manipulable && !enCours && !edition && <BarreFlottante selection={selection} />}
      {menu && <MenuContextuel menu={menu} extra={extraMenu} fermer={fermerMenu} />}
      {focus && !enPresentation && (
        <div className="bandeau-mode" role="status">
          Concentration sur « {etat?.objets.find((o) => o.id === focus)?.meta.titre || "Cadre"} »
          <BoutonCommande id="affichage.concentration.quitter" texte><X size={14} aria-hidden /></BoutonCommande>
        </div>
      )}
      {enPresentation && (
        <div className="barre-presentation" role="toolbar" aria-label="Présentation">
          <BoutonCommande id="presentation.precedente"><ChevronLeft size={18} aria-hidden /></BoutonCommande>
          <output className="tab-num" aria-live="polite">{presentation + 1} / {cadres.length}</output>
          <span className="titre-diapo">{cadres[presentation]?.meta.titre || "Cadre"}</span>
          <BoutonCommande id="presentation.suivante"><ChevronRight size={18} aria-hidden /></BoutonCommande>
          <BoutonCommande id="presentation.quitter" texte><X size={14} aria-hidden /></BoutonCommande>
        </div>
      )}
      {depot && <div className="depot">Dépose pour ajouter au Board</div>}
      {children}
    </section>
  );
}
