import { memo, useMemo, useState, type CSSProperties } from "react";
import { BaseEdge, EdgeLabelRenderer, Handle, MarkerType, MiniMap, Position, ReactFlow, useInternalNode, useReactFlow, useViewport, ViewportPortal,
  type Edge, type EdgeProps, type MiniMapNodeProps, type Node, type NodeChange, type NodeProps, type ReactFlowInstance } from "@xyflow/react";
import { AudioLines, BookOpen, FileText, Film, Focus, Folder, Image, Link2, Minus, NotebookPen, Plus, Target, Network, RotateCcw, Move } from "lucide-react";
import "@xyflow/react/dist/base.css";
import { centresMemoire, disposerMemoire } from "./DispositionMemoire";
import { ZoomGraphe, ZOOM_LIBELLES } from "./ZoomGraphe";
import { contourMemoire, grouperMemoire, relationsSessionsPartagees, teintesGroupes, voisinage, type GroupeMemoire, type Point } from "./GroupesMemoire";
import { useEntrainementMemoire } from "./useEntrainementMemoire";
import { idCentroide, positionsMemoire } from "./deplacementMemoire";
import "./graphe-memoire.css";
import { disposer, tronquer, type Disposition, type Entite, type Graphe, type Relation, type sousGraphe } from "./graphe";

const ICONES: Record<string, typeof FileText> = { image: Image, capture: Image, video: Film, audio: AudioLines, dossier: Folder,
  mission: Target, lien: Link2, reference: BookOpen, note: NotebookPen };
const TEINTES: Record<string, string> = {
  image: "--edge-inspire", capture: "--edge-inspire", video: "--edge-utilise", audio: "--edge-alimente",
  note: "--edge-alimente", texte: "--edge-alimente", pdf: "--accent-texte", document: "--accent-texte",
  mission: "--edge-depend", reference: "--edge-inspire", "memoire-blocage": "--edge-depend",
  "memoire-echec": "--accent-texte", "memoire-refus": "--edge-depend", "memoire-reprise": "--edge-utilise",
  "memoire-resolution": "--edge-alimente", "memoire-frustration": "--edge-inspire",
  "observation-structure": "--edge-utilise", "observation-style": "--edge-inspire",
  "observation-mesures": "--edge-alimente", "observation-preuves": "--accent-texte",
};
const teinteDe = (type: string) => TEINTES[type] ?? "--edge-default";
const variable = (nom: string) => "var(" + nom + ")";
const TEINTES_LIENS: Record<string, string> = {
  defaut: "var(--edge-default)", inspire: "var(--edge-inspire)", alimente: "var(--edge-alimente)", utilise: "var(--edge-utilise)",
  depend: "var(--edge-depend)", source: "var(--edge-inspire)", dossier: "var(--edge-default)", fichier: "var(--edge-utilise)",
  wikilien: "var(--edge-inspire)", memoire: "var(--edge-depend)", causalite: "var(--edge-utilise)",
};
type Donnees = { entite: Entite; actif: boolean; voisin: boolean; sourceContexte: boolean; survol: boolean; estompe: boolean; diametre: number; libelle: boolean; importance: number; teinte: string; groupe?: string; membres?: number; projet?: string; partages?: number };
type Noeud = Node<Donnees, "fichier" | "centroide">;
type Arc = Edge<{ relation: Relation; actif: boolean; estompe: boolean; contexte: boolean; sousTension: boolean; poids: number; couleur: string; libelle: boolean }, "relation">;

export function Miniature({ entite, taille = 20 }: { entite: Entite; taille?: number }) {
  const Icone = ICONES[entite.type] ?? FileText;
  const o = entite.objet;
  const src = (entite.type === "image" || entite.type === "capture") ? o?.asset?.vignette_url || o?.asset?.url || o?.meta.demo_src
    : entite.type === "video" ? o?.asset?.vignette_url : undefined;
  return src ? <img src={src} alt="" loading="lazy" draggable={false} /> : <Icone size={taille} aria-hidden />;
}

const Sommet = memo(function Sommet({ data }: NodeProps<Noeud>) {
  const { entite, actif, voisin, sourceContexte, survol, estompe, diametre, libelle, teinte, importance, groupe } = data;
  return <div className="mf-sommet" data-actif={actif} data-voisin={voisin} data-contexte={sourceContexte}
    data-survol={survol} data-estompe={estompe} data-libelle={libelle} data-type={entite.type} data-groupe={groupe}
    style={{ color: variable(teinte), "--mf-diametre": diametre + "px", "--mf-importance": importance,
      "--mf-lueur": 5 + importance * 16 + "px" } as CSSProperties}>
    <Handle type="target" position={Position.Left} isConnectable={false} />
    <div className="mf-orbe" aria-hidden="true" />
    <strong>{tronquer(entite.titre, 31)}</strong>
    <Handle type="source" position={Position.Right} isConnectable={false} />
  </div>;
});

const Centroide = memo(function Centroide({ data }: NodeProps<Noeud>) {
  const { zoom } = useViewport();
  return <div className="mf-sommet mf-centroide" data-type="centroide" data-groupe={data.groupe}
    data-actif={data.actif} data-libelle={data.libelle} title="Déplacer tout le groupe"
    style={{ color: variable(data.teinte), "--mf-diametre": "24px", "--mf-importance": 1,
      "--mf-centre-texte": 11 / zoom + "px", "--mf-centre-detail": 9 / zoom + "px",
      "--mf-centre-largeur": 190 / zoom + "px", "--mf-centre-offset": 18 / zoom + "px",
      "--mf-centre-detail-offset": 34 / zoom + "px" } as CSSProperties}>
    <Handle type="source" position={Position.Right} isConnectable={false} />
    <div className="mf-centroide-anneau" aria-hidden /><div className="mf-orbe" aria-hidden />
    <Move className="mf-centroide-icone" size={12} aria-hidden />
    <strong>{tronquer(data.entite.titre, 33)}</strong>
    <small>{data.projet && <>{data.projet} · </>}{data.membres} point{data.membres === 1 ? "" : "s"} affiché{data.membres === 1 ? "" : "s"}
      {!!data.partages && <> · {data.partages} partagé{data.partages === 1 ? "" : "s"}</>}</small>
  </div>;
});

function decharge(a: Point, b: Point, identifiant: string, ampleur: number) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const longueur = Math.max(1, Math.hypot(dx, dy));
  const segments = Math.max(3, Math.min(17, Math.round(longueur / 13)));
  let graine = 0;
  for (const lettre of identifiant) graine = (graine * 31 + lettre.charCodeAt(0)) | 0;
  let trace = "M " + a.x + " " + a.y;
  for (let i = 1; i < segments; i += 1) {
    const t = i / segments;
    const bruit = Math.sin(graine % 256 + i * 14.7) * Math.sin(Math.PI * t) * ampleur;
    trace += " L " + (a.x + dx * t - dy / longueur * bruit) + " " + (a.y + dy * t + dx / longueur * bruit);
  }
  return trace + " L " + b.x + " " + b.y;
}

const Trait = memo(function Trait({ id, source, target, markerEnd, data }: EdgeProps<Arc>) {
  const a = useInternalNode(source);
  const b = useInternalNode(target);
  if (!a || !b || !data) return null;
  const pa = a.internals.positionAbsolute, pb = b.internals.positionAbsolute;
  const dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.hypot(dx, dy) || 1;
  const tx = dx / d, ty = dy / d;
  const rayonSource = ((a.data as Donnees).diametre / 2) + 1;
  const rayonCible = ((b.data as Donnees).diametre / 2) + 2;
  const x = pa.x + 76 + tx * rayonSource, y = pa.y + 26 + ty * rayonSource;
  const v = pb.x + 76 - tx * rayonCible, w = pb.y + 26 - ty * rayonCible;
  const cx = (x + v) / 2, cy = (y + w) / 2;
  const path = decharge({ x, y }, { x: v, y: w }, id, data.sousTension ? 4.8 : 1.8 + data.poids * 2.5);
  const couleur = data.couleur;
  return <>
    <path className="mf-electricite-halo" d={path} aria-hidden
      style={{ stroke: couleur, opacity: data.sousTension ? .32 : data.estompe ? .04 : .08 + data.poids * .125 }} />
    <BaseEdge id={id} path={path} markerEnd={markerEnd}
      style={{ stroke: couleur, opacity: data.estompe ? .25 : data.actif || data.sousTension ? 1 : .47 + data.poids * .38,
        strokeWidth: data.sousTension ? 1.85 : .82 + data.poids * 1.25 }} />
    {(data.actif || data.sousTension) && <path d={path} className="mf-courant mf-electricite-impulsion"
      style={{ stroke: couleur }} aria-hidden />}
    {data.libelle && <EdgeLabelRenderer><span className="mf-lien-etiquette" style={{
      transform: `translate(-50%, -50%) translate(${cx}px,${cy}px)`,
    }}>{tronquer(data.relation.texte, 26)}{data.relation.occurrences ? ` ×${data.relation.occurrences}` : ""}</span></EdgeLabelRenderer>}
  </>;
});

const noeuds = { fichier: Sommet, centroide: Centroide };
const arcs = { relation: Trait };

function PointMiniCarte({ x, y, width, id, color, onClick, selected }: MiniMapNodeProps) {
  return <circle className="react-flow__minimap-node" cx={x + width / 2} cy={y + 26} r={selected ? 13 : 10}
    fill={color} onClick={onClick ? (e) => onClick(e, id) : undefined} />;
}
const dureeZoom = (ms: number) => matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : ms;

function Commandes({ groupes, basculer, reinitialiser }: { groupes: boolean; basculer: () => void; reinitialiser: () => void }) {
  const rf = useReactFlow();
  return <div className="mf-zoom" role="group" aria-label="Commandes du graphe">
    <button type="button" title="Zoom avant" aria-label="Zoom avant" onClick={() => void rf.zoomIn({ duration: dureeZoom(210) })}><Plus size={17} /></button>
    <button type="button" title="Zoom arrière" aria-label="Zoom arrière" onClick={() => void rf.zoomOut({ duration: dureeZoom(210) })}><Minus size={17} /></button>
    <button type="button" title="Afficher les groupes" aria-label="Afficher les groupes" aria-pressed={groupes} onClick={basculer}><Network size={16} /></button>
    <button type="button" title="Réinitialiser la disposition" aria-label="Réinitialiser la disposition" onClick={() => {
      reinitialiser();
      requestAnimationFrame(() => void rf.fitView({ padding: .19, maxZoom: 1.32, duration: dureeZoom(250) }));
    }}><RotateCcw size={16} /></button>
    <button type="button" title="Cadrer le graphe" aria-label="Cadrer le graphe" onClick={() => void rf.fitView({ padding: .19, maxZoom: 1.32, duration: dureeZoom(250) })}><Focus size={17} /></button>
  </div>;
}

function Enveloppes({ groupes, positions, modele, teintes }: {
  groupes: GroupeMemoire[]; positions: ReadonlyMap<string, Point>; modele: Graphe; teintes: ReadonlyMap<string, string>;
}) {
  const { zoom } = useViewport();
  const explicites = groupes.some((g) => g.explicite);
  return <ViewportPortal>
    <svg className="mf-groupes" width={1} height={1} aria-hidden="true">
      {groupes.filter((g) => explicites ? g.explicite : g.ids.length >= 2).map((g) => {
        const membres = g.explicite ? [...g.ids, idCentroide(g.ancre)] : g.ids;
        const points = membres.flatMap((id) => {
          const p = positions.get(id);
          return p ? [{ x: p.x + 76, y: p.y + 26 }] : [];
        });
        if (points.length === 0) return null;
        const forme = contourMemoire(points);
        const origine = modele.entites.get(g.ancre);
        const couleur = variable(teintes.get(g.ancre) ?? teinteDe(origine?.type ?? ""));
        const titre = Math.min(...forme.map((p) => p.x));
        const haut = Math.min(...forme.map((p) => p.y));
        return <g key={g.ancre} data-groupe={g.ancre} style={{ color: couleur }}>
          <polygon points={forme.map(({ x, y }) => x + "," + y).join(" ")} />
          {!g.explicite && zoom >= ZOOM_LIBELLES && <text x={titre} y={haut - 9 / zoom} style={{ fontSize: 11 / zoom,
            stroke: "var(--surface-inset)", strokeWidth: 3 / zoom, paintOrder: "stroke" }}>
            {tronquer(origine?.titre ?? "Groupe", 25)} · {points.length}
          </text>}
        </g>;
      })}
    </svg>
  </ViewportPortal>;
}

function LegendeGroupes({ groupes, modele, teintes, choisir, choisirGroupe, sauvegardeLocale }: {
  groupes: GroupeMemoire[]; modele: Graphe; teintes: ReadonlyMap<string, string>; choisir: (id: string) => void;
  choisirGroupe?: (id: string) => void; sauvegardeLocale: boolean;
}) {
  const explicites = groupes.filter((g) => g.explicite);
  const relies = explicites.length ? explicites : groupes.filter((g) => g.ids.length > 1);
  const isoles = explicites.length ? 0 : groupes.length - relies.length;
  const sessions = explicites.filter((g) => g.nature === "session").length;
  const sansSession = explicites.length - sessions;
  return <details className="mf-reperes" aria-label="Couleurs et brillance du graphe">
    <summary><Network size={14} aria-hidden /><span>{explicites.length ? `${sessions} session${sessions === 1 ? "" : "s"}${sansSession ? ` · ${sansSession} sans session` : ""}` : `${relies.length} groupe${relies.length === 1 ? "" : "s"}`}</span></summary>
    <p>{groupes.some((g) => g.explicite)
      ? "Déplace le centroïde pour déplacer tout son lot. Déplace un point pour dessiner librement sa place."
      : "Chaque couleur rassemble des éléments liés autour d’une mission, d’un dossier ou d’une source."}</p>
    {explicites.length > 0 && <p>Les ressources partagées relient les sessions. Les éléments sans rattachement sont identifiés à part.</p>}
    {relies.length > 0 && <ul>{relies.map((g) => <li key={g.ancre}>
      <button type="button" onClick={() => g.explicite ? choisirGroupe?.(g.ancre) : choisir(g.ancre)}
        aria-label={`Voir ${g.nature === "session" ? "la session" : "le groupe"} ${g.titre ?? modele.entites.get(g.ancre)?.titre ?? g.ancre}`}>
        <i aria-hidden style={{ background: variable(teintes.get(g.ancre) ?? "--edge-default") }} />
        <span>{g.titre ?? modele.entites.get(g.ancre)?.titre ?? g.ancre}</span><small>{g.ids.length}</small>
      </button>
    </li>)}</ul>}
    {isoles > 0 && <small>{isoles} élément{isoles === 1 ? "" : "s"} sans connexion visible</small>}
    <p className="mf-reperes-brillance">Taille et brillance suivent le nombre de connexions visibles. La sélection est mise en évidence.</p>
    {sauvegardeLocale && <p className="mf-reperes-local">Le dessin est enregistré sur cet appareil.</p>}
  </details>;
}

export function CarteGraphe({ modele, projection, disposition, centre, selection, liensContexte, choisir, onInit,
  groupesParDefaut = false, nomAccessible = "Graphe des fichiers", choisirGroupe, cleDisposition, effacerSelection }: {
  modele: Graphe; projection: ReturnType<typeof sousGraphe>; disposition: Disposition; centre: string | null;
  selection: string | null; liensContexte: ReadonlySet<string>; choisir: (id: string) => void; onInit: (rf: ReactFlowInstance<Noeud, Arc>) => void;
  groupesParDefaut?: boolean; nomAccessible?: string; choisirGroupe?: (id: string) => void; cleDisposition?: string; effacerSelection?: () => void;
}) {
  const [survol, setSurvol] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [groupesActifs, setGroupesActifs] = useState(groupesParDefaut);
  const miseEnAvant = survol ?? selection;
  const voisins = useMemo(() => voisinage(projection.ids, projection.relations), [projection]);
  const groupes = useMemo(() => {
    const explicites = modele.groupes;
    if (explicites) {
      const visibles = new Set(projection.ids);
      const centres: GroupeMemoire[] = explicites.map((g) => ({ ancre: g.id, titre: g.titre, projet: g.projet,
        ids: g.ids.filter((id) => visibles.has(id)), explicite: true, nature: g.nature }));
      const attribues = new Set(centres.flatMap((g) => g.ids));
      const libres = projection.ids.filter((id) => !attribues.has(id));
      const libresVoisins = voisinage(libres, projection.relations);
      return [...centres, ...grouperMemoire(libresVoisins, new Set())];
    }
    const rang: Record<string, number> = { mission: 3, dossier: 2, reference: 1 };
    const priorites = new Map(projection.ids.map((id) => [id, rang[modele.entites.get(id)?.type ?? ""] ?? 0]));
    return grouperMemoire(voisins, new Set(), priorites);
  }, [modele, projection.ids, voisins]);
  const palette = useMemo(() => teintesGroupes(groupes), [groupes]);
  const teintes = palette.variables;
  const groupeParId = useMemo(() => new Map(groupes.flatMap((g) => g.ids.map((id) => [id, g.ancre] as const))), [groupes]);
  const centres = useMemo(() => groupes.filter((g) => g.explicite), [groupes]);
  const lots = useMemo(() => new Map((modele.groupes ?? []).map((g) => [idCentroide(g.id), g.ids])), [modele.groupes]);
  const points = useMemo(() => {
    const resultat = disposition === "constellation"
      ? disposerMemoire(projection.ids, projection.relations, centre, groupesParDefaut ? groupes : [])
      : disposer(projection.ids, projection.relations, disposition, centre);
    const ancres = centresMemoire(groupes, centre);
    for (const groupe of centres) {
      const membres = groupe.ids.flatMap((id) => { const p = resultat.get(id); return p ? [p] : []; });
      if (!membres.length) { resultat.set(idCentroide(groupe.ancre), ancres.get(groupe.ancre) ?? { x: 0, y: 0 }); continue; }
      const moyenne = membres.reduce((p, m) => ({ x: p.x + m.x / membres.length, y: p.y + m.y / membres.length }), { x: 0, y: 0 });
      const ancre = ancres.get(groupe.ancre) ?? moyenne;
      resultat.set(idCentroide(groupe.ancre), ancre);
      groupe.ids.forEach((id, i) => {
        const avant = resultat.get(id)!;
        const dx = avant.x - moyenne.x, dy = avant.y - moyenne.y;
        const distance = Math.hypot(dx, dy);
        const rayonMax = Math.max(180, Math.sqrt(groupe.ids.length) * 32);
        const facteur = distance > rayonMax ? rayonMax / distance : 1;
        const p = { x: ancre.x + dx * facteur, y: ancre.y + dy * facteur };
        const angle = i * Math.PI * (3 - Math.sqrt(5));
        resultat.set(id, distance >= 70 ? p
          : { x: ancre.x + 82 * Math.cos(angle), y: ancre.y + 82 * Math.sin(angle) });
      });
    }
    return resultat;
  }, [projection, disposition, centre, groupes, groupesParDefaut, centres]);
  const appartenances = useMemo(() => relationsSessionsPartagees(modele.entites, projection.ids, groupes),
    [modele.entites, projection.ids, groupes]);
  const relationsAffichees = useMemo(() => [...projection.relations, ...appartenances], [projection.relations, appartenances]);
  const partages = useMemo(() => {
    const comptes = new Map<string, number>();
    for (const r of appartenances) comptes.set(r.source, (comptes.get(r.source) ?? 0) + 1);
    return comptes;
  }, [appartenances]);
  const groupeDeplace = useEntrainementMemoire(points, lots, cleDisposition);
  const { positions: personnelles, deplace } = groupeDeplace;
  const entraine = useMemo(() => new Set(deplace ? [deplace, ...(lots.get(deplace) ?? [])] : []), [deplace, lots]);
  const positions = useMemo(() => positionsMemoire(points, personnelles, lots), [points, personnelles, lots]);
  const libellesCentres = useMemo(() => {
    const visibles = new Set<string>();
    const places: Point[] = [];
    const priorite = (id: string) => id === selection ? 1 : 0;
    const ordre = [...centres].sort((a, b) => priorite(idCentroide(b.ancre)) - priorite(idCentroide(a.ancre)));
    for (const groupe of ordre) {
      const id = idCentroide(groupe.ancre), point = positions.get(id);
      if (!point) continue;
      const cible = { x: point.x * zoom, y: point.y * zoom };
      const important = priorite(id) > 0;
      if (!important && places.some((p) => Math.abs(p.x - cible.x) < 200 && Math.abs(p.y - cible.y) < 58)) continue;
      visibles.add(id); places.push(cible);
    }
    return visibles;
  }, [centres, positions, zoom, selection, survol]);
  const proches = useMemo(() => new Set(projection.relations.flatMap((r) => r.source === miseEnAvant ? [r.cible]
    : r.cible === miseEnAvant ? [r.source] : [])), [projection, miseEnAvant]);
  const entrants = useMemo(() => {
    const sources = new Map<string, Set<string>>();
    for (const r of projection.relations) {
      const notes = sources.get(r.cible) ?? new Set<string>();
      notes.add(r.source);
      sources.set(r.cible, notes);
    }
    return sources;
  }, [projection.relations]);
  const contexte = useMemo(() => {
    const relations = projection.relations.filter((r) => (r.idsRegroupes ?? [r.id]).some((id) => liensContexte.has(id)));
    return { arcs: new Set(relations.map((r) => r.id)), sources: new Set(relations.map((r) => r.source)) };
  }, [projection, liensContexte]);
  const libelles = useMemo(() => {
    const priorite = (id: string) => id === selection ? 4 : contexte.sources.has(id) ? 2 : proches.has(id) ? 1 : 0;
    const ordre = [...projection.ids].sort((a, b) => priorite(b) - priorite(a)
      || (entrants.get(b)?.size ?? 0) - (entrants.get(a)?.size ?? 0));
    const visibles = new Map<string, Point & { demiLargeur: number }>();
    for (const id of ordre) {
      const p = positions.get(id)!;
      const largeur = Math.min(148, 12 + tronquer(modele.entites.get(id)!.titre, 31).length * 7.5);
      if ([...visibles.values()].some((v) => Math.abs(v.y - p.y) < 20 && Math.abs(v.x - p.x) < v.demiLargeur + largeur / 2)) continue;
      visibles.set(id, { ...p, demiLargeur: largeur / 2 });
    }
    return visibles;
  }, [projection.ids, positions, modele, contexte, proches, entrants, selection]);
  const donnees = useMemo(() => {
    const resultat = new Map<string, Donnees>();
    for (const id of projection.ids) {
      const entite = modele.entites.get(id)!;
      const sourceContexte = contexte.sources.has(id);
      const importance = Math.min(1, Math.sqrt(voisins.get(id)?.size ?? 0) / 3 + (sourceContexte || id === selection ? .3 : 0));
      resultat.set(id, { entite, actif: selection === id, voisin: proches.has(id), sourceContexte,
        survol: survol === id, estompe: survol !== null && id !== survol && id !== selection && !proches.has(id) && !sourceContexte,
        diametre: 11 + 15 * importance, libelle: libelles.has(id), importance,
        groupe: groupeParId.get(id),
        teinte: groupesParDefaut ? teintes.get(groupeParId.get(id) ?? "") ?? teinteDe(entite.type) : teinteDe(entite.type) });
    }
    for (const groupe of centres) {
      const id = idCentroide(groupe.ancre);
      resultat.set(id, { entite: { id, titre: groupe.titre ?? groupe.ancre, type: "centroide" }, actif: selection === id,
        voisin: false, sourceContexte: false, survol: survol === id, estompe: false, diametre: 24, libelle: libellesCentres.has(id),
        importance: .85, groupe: groupe.ancre, teinte: teintes.get(groupe.ancre) ?? "--edge-default",
        membres: groupe.ids.length, projet: groupe.projet, partages: partages.get(id) ?? 0 });
    }
    return resultat;
  }, [projection.ids, voisins, contexte, modele, selection, proches, survol, libelles, groupeParId, groupesParDefaut, teintes, centres, partages, libellesCentres]);
  const nodes: Noeud[] = useMemo(() => [...donnees].map(([id, data]) => ({
    id, type: data.entite.type === "centroide" ? "centroide" : "fichier", width: 152, height: 86, position: positions.get(id)!,
    data, ariaLabel: data.entite.type === "centroide" ? "Centroïde de " + data.entite.titre : data.entite.titre, selected: data.actif,
  })), [donnees, positions]);
  const edges: Arc[] = useMemo(() => relationsAffichees.map((r) => {
    const actif = r.source === miseEnAvant || r.cible === miseEnAvant || contexte.arcs.has(r.id);
    const sousTension = !!entraine?.has(r.source) && !!entraine?.has(r.cible);
    const source = donnees.get(r.source), cible = donnees.get(r.cible);
    const poids = contexte.arcs.has(r.id) ? 1 : r.style === "causalite" ? .9 : .33 + ((source?.importance ?? 0) + (cible?.importance ?? 0)) * .28;
    const couleur = groupesParDefaut && source?.groupe && (source.entite.type === "centroide" || source.groupe === cible?.groupe)
      ? variable(source.teinte) : TEINTES_LIENS[r.style] ?? "var(--edge-default)";
    return {
      id: r.id, source: r.source, target: r.cible, type: "relation",
      data: { relation: r, actif, estompe: proches.size > 0 && !actif && !sousTension, contexte: contexte.arcs.has(r.id), sousTension, poids, couleur, libelle: zoom >= ZOOM_LIBELLES && actif },
      markerEnd: actif ? { type: MarkerType.ArrowClosed, width: 11, height: 11, color: couleur } : undefined,
    };
  }), [relationsAffichees, miseEnAvant, contexte, entraine, proches, donnees, groupesParDefaut, zoom]);
  const choisirNoeud = (id: string) => {
    const data = donnees.get(id);
    if (data?.entite.type === "centroide") choisirGroupe?.(data.groupe!);
    else choisir(id);
  };
  const repositionner = (changements: NodeChange<Noeud>[]) => {
    const positions = changements.flatMap((c) => c.type === "position" && c.position ? [[c.id, c.position] as const] : []);
    groupeDeplace.changer(positions);
  };
  return <div className="mf-canevas mf-graphe-memoire" aria-label={nomAccessible} style={palette.styles as CSSProperties}>
    <ReactFlow<Noeud, Arc> nodes={nodes} edges={edges} nodeTypes={noeuds} edgeTypes={arcs} onNodesChange={repositionner}
      onNodeDragStart={(_, n) => groupeDeplace.commencer(n.id, n.position)} onNodeDragStop={(_, n) => groupeDeplace.terminer(n.id, n.position)}
      onInit={onInit} onMove={(_, viewport) => setZoom(viewport.zoom)} onPaneClick={effacerSelection} onNodeClick={(_, n) => choisirNoeud(n.id)} onNodeDoubleClick={(_, n) => choisirNoeud(n.id)}
      onNodeMouseEnter={(_, n) => setSurvol(n.id)} onNodeMouseLeave={() => setSurvol(null)}
      onKeyDown={(e) => {
        if (e.key === "Escape" && effacerSelection) { e.preventDefault(); effacerSelection(); return; }
        if (e.key !== "Enter" || !(e.target instanceof HTMLElement)) return;
        const id = e.target.closest<HTMLElement>(".react-flow__node")?.dataset.id;
        if (id) choisirNoeud(id);
      }}
      nodesConnectable={false} edgesFocusable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={.12} maxZoom={3}
      fitView fitViewOptions={{ padding: .19, maxZoom: 1.32 }} zoomOnDoubleClick={false} onlyRenderVisibleElements>
      {groupesActifs && <Enveloppes groupes={groupes} positions={positions} modele={modele} teintes={groupesParDefaut ? teintes : new Map()} />}
      <ZoomGraphe />
      {nodes.length > 1 && <MiniMap pannable zoomable ariaLabel="Mini-carte des fichiers" nodeColor={(n) => variable((n.data as Donnees).teinte)}
        nodeComponent={PointMiniCarte} style={{ width: 133, height: 86 }} maskColor="var(--minimap-mask)" />}
      <Commandes groupes={groupesActifs} basculer={() => setGroupesActifs((actifs) => !actifs)} reinitialiser={groupeDeplace.reinitialiser} />
    </ReactFlow>
    {groupesParDefaut && <LegendeGroupes groupes={groupes} modele={modele} teintes={teintes} choisir={choisir}
      choisirGroupe={choisirGroupe} sauvegardeLocale={!!cleDisposition && !groupeDeplace.sauvegardeImpossible} />}
    {groupeDeplace.sauvegardeImpossible && <p className="mf-dessin-erreur" role="status">Le stockage local est indisponible. Le dessin est conservé pour cette ouverture.</p>}
    <div className="mf-canevas-compte tab-num">{projection.ids.length} éléments{centres.length > 0 && ` · ${centres.filter((g) => g.nature === "session").length} sessions${centres.some((g) => g.nature === "hors_session") ? ` · ${centres.filter((g) => g.nature === "hors_session").length} sans session` : ""}`} · {projection.relations.reduce((n, r) => n + (r.occurrences ?? 1), 0)} liens
      {appartenances.length > 0 && ` · ${appartenances.length} appartenances de session`}
      {groupesActifs && !centres.length && (" · " + groupes.filter((g) => g.ids.length >= 2).length + " groupes")}</div>
  </div>;
}
