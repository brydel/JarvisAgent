import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, BackgroundVariant, ConnectionMode, MarkerType, MiniMap, ReactFlow, useReactFlow,
  type Edge, type Node, type NodeChange, type EdgeChange, type Connection, type Viewport, applyNodeChanges,
} from "@xyflow/react";
import { AlignHorizontalJustifyCenter, AlignLeft, AlignStartVertical, ArrowUpToLine, Copy, FolderInput, Lock, Trash2, AlignVerticalJustifyCenter } from "lucide-react";
import type { Source, NouvelObjet, Modification } from "./api";
import type { Approbation, DonneesNoeud, EtatBoard, Evenement, ObjetBoard, Priorite, StyleLien } from "./types";
import { ImageNode, LienNode, PdfNode, DossierNode } from "./nodes/CartesVisuelles";
import { NoteNode, MissionNode, AgentsNode } from "./nodes/CartesVivantes";
import { AudioNode, VideoNode } from "./nodes/CartesMedia";
import { RelationEdge, type DonneesLien } from "./edges/RelationEdge";
import { ContexteActions, TAILLES, type ActionsBoard } from "./nodes/contexte";
import { BarreHaut, BarreOutils, FILTRES, SaisieUrl, SousBarre, type Filtre, type Outil } from "./components/Coque";
import { Panneau } from "./components/Panneau";
import { DialogueMission, type DemandeMission } from "./components/DialogueMission";
import { Historique } from "./lib/historique";
import { cascade, depuisTexte, depuisTransfert, familleFichier, type Element } from "./lib/ingestion";

const TYPES_NOEUDS = {
  image: ImageNode, capture: ImageNode, lien: LienNode, pdf: PdfNode, document: PdfNode, note: NoteNode, texte: NoteNode,
  mission: MissionNode, agents: AgentsNode, audio: AudioNode, video: VideoNode, dossier: DossierNode,
};
const TYPES_LIENS = { relation: RelationEdge };
const MARQUEUR_PRESSE_PAPIERS = "jarvis-board/objets:";
const COULEUR_MINIMAP: Record<string, string> = { mission: "#5B6CFF", agents: "#3FB984", note: "#2E2A55", image: "#3A4260", video: "#3A4260" };
const COULEUR_FLECHE: Record<StyleLien, string> = { inspire: "#B26BF5", alimente: "#3FCF9A", utilise: "#38BDF8", depend: "#5B6CFF", defaut: "#5B6CFF" };

/** Vrai si la cible est un champ de saisie (le collage et les raccourcis du Board ne s'y appliquent pas). */
function dansChamp(t: EventTarget | null): boolean {
  return t instanceof Element && Boolean(t.closest("input, textarea, select, [contenteditable='true']"));
}

type Toast = { id: number; texte: string; erreur?: boolean; action?: { nom: string; faire: () => void } };

function versNoeud(o: ObjetBoard, demo: boolean, precedent?: Node<DonneesNoeud>): Node<DonneesNoeud> {
  const t = TAILLES[o.type]?.defaut ?? [400, 300];
  const largeur = o.largeur || t[0];
  const hauteur = o.hauteur || t[1];
  if (precedent && precedent.data.objet === o) return precedent;
  return {
    id: o.id, type: o.type, position: { x: o.x, y: o.y }, data: { objet: o, demo }, width: largeur, height: hauteur,
    zIndex: o.z, draggable: !o.verrouille, selected: precedent?.selected ?? false,
    ariaLabel: `${o.type} : ${o.meta.titre || o.contenu.slice(0, 40) || o.asset?.nom || ""}`,
  };
}

interface Props {
  source: Source;
  charge?: number;
}

export function Board({ source, charge }: Props) {
  const rf = useReactFlow<Node<DonneesNoeud>, Edge<DonneesLien>>();
  const [etat, setEtat] = useState<EtatBoard | null>(null);
  const [noeuds, setNoeuds] = useState<Node<DonneesNoeud>[]>([]);
  const [erreur, setErreur] = useState("");
  const initial = useMemo(() => lireUrl(), []);
  const [filtre, setFiltre] = useState<Filtre>(initial.filtre);
  const [prio, setPrio] = useState(initial.priorite);
  const [recherche, setRecherche] = useState(initial.q);
  const [dialogueMission, setDialogueMission] = useState(false);
  const [magnetisme, setMagnetisme] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  /** carte à sélectionner dès qu'elle existe (créée côté serveur, pas encore dans les nœuds) */
  const aSelectionner = useRef<string | null>(null);
  const [saisieUrl, setSaisieUrl] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [depot, setDepot] = useState(false);
  const [evenements, setEvenements] = useState<Evenement[]>([]);
  const [approbations, setApprobations] = useState<Approbation[]>([]);
  const [tick, setTick] = useState(0);
  const [visionneuse, setVisionneuse] = useState<{ src: string; titre: string } | null>(null);
  const historique = useRef(new Historique());
  const etatRef = useRef<EtatBoard | null>(null);
  const pressePapiers = useRef<ObjetBoard[]>([]);
  const departGlisser = useRef(new Map<string, { x: number; y: number }>());
  const departTaille = useRef(new Map<string, { largeur: number; hauteur: number }>());
  const fichierInput = useRef<HTMLInputElement>(null);
  const acceptFichier = useRef("");
  const rechargement = useRef<number>(0);
  etatRef.current = etat;

  const toast = useCallback((texte: string, opts: Omit<Toast, "id" | "texte"> = {}) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, texte, ...opts }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), opts.action ? 7000 : 4000);
  }, []);

  /* ------------------------------------------------------------ chargement et synchronisation ---------- */
  const charger = useCallback(async () => {
    try {
      const e = await source.charger();
      if (charge && source.demo) e.objets.push(...genererCharge(charge));
      setEtat(e);
      setErreur("");
      if (!source.demo) source.approbations().then(setApprobations).catch(() => undefined);
      setTick((t) => t + 1);
    } catch (x) {
      setErreur(x instanceof Error ? x.message : "chargement impossible");
    }
  }, [source, charge]);
  const rechargerBientot = useCallback(() => {
    window.clearTimeout(rechargement.current);
    rechargement.current = window.setTimeout(charger, 250);
  }, [charger]);
  useEffect(() => {
    charger();
  }, [charger]);

  // Flux d'événements réel (SSE). Le navigateur se reconnecte seul avec Last-Event-ID ; on recharge l'état à la reprise.
  useEffect(() => {
    if (source.demo) return;
    const es = new EventSource("/api/flux?apres=0");
    const ouvertA = Date.now() / 1000 - 2;  // le flux rejoue l'historique : seuls les événements récents font un toast
    let premier = true;
    es.onopen = () => {
      if (!premier) rechargerBientot();
      premier = false;
    };
    es.onmessage = (m) => {
      const e = JSON.parse(m.data) as Evenement;
      setEvenements((l) => (l.length > 300 ? [...l.slice(-200), e] : [...l, e]));
      if (e.type !== "board_maj" || !e.donnees.par || e.donnees.par !== "studio") rechargerBientot();
      if (e.type === "board_propositions" && e.ts >= ouvertA) {
        const n = Number(e.donnees.n ?? 0);
        toast(`Jarvis a contextualisé un élément : ${n} action${n > 1 ? "s" : ""} proposée${n > 1 ? "s" : ""}`);
      }
    };
    return () => {
      es.close();
      window.clearTimeout(rechargement.current);
    };
  }, [source, rechargerBientot, toast]);

  /* ------------------------------------------------------------ nœuds et liens dérivés ----------------- */
  const visibleSelon = useCallback((o: ObjetBoard) => {
    if (o.parent_id) return false;
    const f = FILTRES.find((x) => x.cle === filtre);
    if (f && f.types.length && !f.types.includes(o.type)) return false;
    if (prio && o.priorite !== prio) return false;
    if (recherche.trim()) {
      const q = recherche.trim().toLowerCase();
      const texte = [o.meta.titre, o.meta.description, o.contenu, o.asset?.nom, o.mission?.objectif, ...(o.meta.tags ?? [])].join(" ").toLowerCase();
      if (!texte.includes(q)) return false;
    }
    return true;
  }, [filtre, prio, recherche]);

  useEffect(() => {
    if (!etat) return;
    setNoeuds((prec) => {
      const parId = new Map(prec.map((n) => [n.id, n]));
      return etat.objets.map((o) => {
        let n = versNoeud(o, source.demo, parId.get(o.id));
        if (aSelectionner.current === o.id) {
          aSelectionner.current = null;
          if (!n.selected) n = { ...n, selected: true };
        }
        const cache = !visibleSelon(o);
        return n.hidden === cache ? n : { ...n, hidden: cache };
      });
    });
  }, [etat, source.demo, visibleSelon]);

  const renommerLien = useCallback(async (id: string, libelle: string) => {
    await source.modifierLien(id, { libelle });
    charger();
  }, [source, charger]);

  const aretes = useMemo<Edge<DonneesLien>[]>(() => (etat?.liens ?? []).map((l) => ({
    id: l.id, source: l.source_id, target: l.cible_id, type: "relation",
    data: { libelle: l.libelle, style: l.style, renommer: renommerLien, cotes: l.cotes },
    markerEnd: { type: MarkerType.ArrowClosed, color: COULEUR_FLECHE[l.style] ?? COULEUR_FLECHE.defaut, width: 16, height: 16 },
  })), [etat?.liens, renommerLien]);

  const compteurs = useMemo(() => {
    const c = Object.fromEntries(FILTRES.map((f) => [f.cle, 0])) as Record<Filtre, number>;
    for (const o of etat?.objets ?? []) {
      if (o.parent_id) continue;
      c.tous += 1;
      for (const f of FILTRES) if (f.types.includes(o.type)) c[f.cle] += 1;
    }
    return c;
  }, [etat?.objets]);

  /* ------------------------------------------------------------ persistance ----------------------------- */
  const modifier = useCallback(async (mods: Modification[], libelle?: string, inverse?: Modification[]) => {
    const r = await source.modifier(mods);
    const echecs = r.filter((x) => !x.ok);
    if (echecs.length) toast(`Non enregistré : ${echecs[0]?.erreur ?? "erreur"}`, { erreur: true });
    if (libelle && inverse) {
      historique.current.ajouter({
        libelle,
        annuler: async () => { await source.modifier(inverse); await charger(); },
        refaire: async () => { await source.modifier(mods); await charger(); },
      });
    }
    await charger();
  }, [source, toast, charger]);

  const objet = useCallback((id: string) => etatRef.current?.objets.find((o) => o.id === id), []);

  const creer = useCallback(async (o: NouvelObjet, libelle = "Ajout") => {
    const id = await source.creer(o);
    historique.current.ajouter({
      libelle, annuler: async () => { await source.supprimer([id]); await charger(); },
      refaire: async () => { await source.supprimer([id], true); await charger(); },
    });
    return id;
  }, [source, charger]);

  const supprimer = useCallback(async (ids: string[]) => {
    if (!ids.length) return;
    if (ids.length >= 10 && !window.confirm(`Supprimer ${ids.length} cartes ? (Ctrl+Z pour annuler)`)) return;
    await source.supprimer(ids);
    historique.current.ajouter({
      libelle: "Suppression", annuler: async () => { await source.supprimer(ids, true); await charger(); },
      refaire: async () => { await source.supprimer(ids); await charger(); },
    });
    await charger();
    toast(`${ids.length} carte${ids.length > 1 ? "s" : ""} supprimée${ids.length > 1 ? "s" : ""}`, {
      action: { nom: "Annuler", faire: async () => { await historique.current.annuler(); } },
    });
  }, [source, charger, toast]);

  const dupliquer = useCallback(async (ids: string[]) => {
    const objs = ids.map(objet).filter((o): o is ObjetBoard => Boolean(o) && o!.type !== "mission" && o!.type !== "agents");
    for (const o of objs) {
      await creer({ type: o.type, contenu: o.contenu, x: o.x + 40, y: o.y + 40, largeur: o.largeur, hauteur: o.hauteur,
        priorite: o.priorite, meta: o.meta, asset_id: o.asset_id, analyser: false }, "Duplication");
    }
    await charger();
  }, [objet, creer, charger]);

  const devant = useCallback(async (ids: string[]) => {
    const max = Math.max(0, ...(etatRef.current?.objets ?? []).map((o) => o.z));
    await modifier(ids.map((id, i) => ({ id, champs: { z: max + 1 + i } })), "Amener devant",
      ids.map((id) => ({ id, champs: { z: objet(id)?.z ?? 0 } })));
  }, [modifier, objet]);

  const actions = useMemo<ActionsBoard>(() => ({
    modifier: (id, champs) => {
      const o = objet(id);
      const inverse: Modification["champs"] = {};
      if (o) for (const k of Object.keys(champs) as (keyof typeof champs)[]) {
        (inverse as Record<string, unknown>)[k] = k === "verrouille" ? Boolean(o.verrouille) : (o as unknown as Record<string, unknown>)[k];
      }
      modifier([{ id, champs }], "Modification", [{ id, champs: inverse }]);
    },
    priorite: (id, p: Priorite) => modifier([{ id, champs: { priorite: p } }], "Priorité", [{ id, champs: { priorite: objet(id)?.priorite ?? "" } }]),
    supprimer, dupliquer, devant,
    inspecter: (id) => {
      aSelectionner.current = id;
      rf.setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === id })));
      setSelection([id]);
    },
    agrandir: (src, titre) => setVisionneuse({ src, titre }),
    sortirDuDossier: (id) => {
      const o = objet(id);
      const parent = o?.parent_id ? objet(o.parent_id) : undefined;
      modifier([{ id, champs: { parent_id: null, x: (parent?.x ?? 0) + 40, y: (parent?.y ?? 0) + (parent?.hauteur ?? 150) + 40 } }],
        "Sortie du dossier", [{ id, champs: { parent_id: o?.parent_id ?? null } }]);
    },
    enfants: (dossierId) => (etatRef.current?.objets ?? []).filter((o) => o.parent_id === dossierId),
    contextualiser: (id) => {
      source.contextualiser(id).then(() => {
        toast(source.demo ? "Mode démo : aucune IA n'est appelée" : "Jarvis analyse l'élément…");
        charger();
      }).catch((x: Error) => toast(x.message, { erreur: true }));
    },
  }), [objet, modifier, supprimer, dupliquer, devant, rf, source, toast, charger]);

  /* ------------------------------------------------------------ interactions du canevas ---------------- */
  // mémoïsé (exigé par React Flow) et sans nouvelle valeur si la sélection n'a pas changé : sinon boucle de rendu
  const surSelection = useCallback(({ nodes }: { nodes: Node[] }) => {
    setSelection((avant) => {
      const ids = nodes.map((n) => n.id);
      return ids.length === avant.length && ids.every((id, i) => id === avant[i]) ? avant : ids;
    });
  }, []);
  const minuteriesPosition = useRef(new Map<string, number>());
  const onNodesChange = useCallback((changes: NodeChange<Node<DonneesNoeud>>[]) => {
    setNoeuds((ns) => applyNodeChanges(changes, ns));
    for (const c of changes) {
      if (c.type === "dimensions" && c.dimensions) {
        const o = objet(c.id);
        if (c.resizing && o && !departTaille.current.has(c.id)) departTaille.current.set(c.id, { largeur: o.largeur, hauteur: o.hauteur });
        if (c.resizing === false && departTaille.current.has(c.id)) {
          const avant = departTaille.current.get(c.id)!;
          departTaille.current.delete(c.id);
          const n = rf.getNode(c.id);
          const champs = { largeur: Math.round(c.dimensions.width), hauteur: Math.round(c.dimensions.height),
            ...(n ? { x: Math.round(n.position.x), y: Math.round(n.position.y) } : {}) };
          modifier([{ id: c.id, champs }], "Redimensionnement", [{ id: c.id, champs: { ...avant, x: o?.x, y: o?.y } as Modification["champs"] }]);
        }
      }
      // déplacements au clavier (flèches) : enregistrés après une courte pause
      if (c.type === "position" && c.position && c.dragging === undefined) {
        const id = c.id, pos = c.position;
        window.clearTimeout(minuteriesPosition.current.get(id));
        minuteriesPosition.current.set(id, window.setTimeout(() => {
          modifier([{ id, champs: { x: Math.round(pos.x), y: Math.round(pos.y) } }]);
        }, 400));
      }
    }
  }, [objet, modifier, rf]);

  const onNodeDragStart = useCallback((_: unknown, __: Node, ns: Node[]) => {
    departGlisser.current = new Map(ns.map((n) => [n.id, { x: n.position.x, y: n.position.y }]));
  }, []);

  const onNodeDragStop = useCallback(async (_: unknown, noeud: Node, ns: Node[]) => {
    const depart = departGlisser.current;
    const bouges = ns.filter((n) => {
      const d = depart.get(n.id);
      return d && (Math.abs(d.x - n.position.x) > 0.5 || Math.abs(d.y - n.position.y) > 0.5);
    });
    // dépôt d'une carte seule sur un dossier : elle y est rangée
    if (ns.length === 1 && noeud.type !== "dossier") {
      const dossier = rf.getIntersectingNodes(noeud).find((n) => n.type === "dossier" && n.id !== noeud.id);
      if (dossier) {
        const d = depart.get(noeud.id)!;
        await modifier([{ id: noeud.id, champs: { parent_id: dossier.id } }], "Rangement dans le dossier",
          [{ id: noeud.id, champs: { parent_id: null, x: d.x, y: d.y } }]);
        toast("Carte rangée dans le dossier", { action: { nom: "Annuler", faire: () => historique.current.annuler() } });
        return;
      }
    }
    if (!bouges.length) return;
    await modifier(bouges.map((n) => ({ id: n.id, champs: { x: Math.round(n.position.x), y: Math.round(n.position.y) } })), "Déplacement",
      bouges.map((n) => ({ id: n.id, champs: { x: depart.get(n.id)!.x, y: depart.get(n.id)!.y } })));
  }, [modifier, rf, toast]);

  const onEdgesChange = useCallback(async (changes: EdgeChange<Edge<DonneesLien>>[]) => {
    const suppr = changes.filter((c) => c.type === "remove").map((c) => c.id);
    for (const id of suppr) {
      await source.modifierLien(id, { supprime: true });
      historique.current.ajouter({
        libelle: "Suppression de relation", annuler: async () => { await source.modifierLien(id, { supprime: false }); await charger(); },
        refaire: async () => { await source.modifierLien(id, { supprime: true }); await charger(); },
      });
    }
    if (suppr.length) charger();
  }, [source, charger]);

  const derniereConnexion = useRef({ cle: "", t: 0 });
  const onConnect = useCallback(async (c: Connection) => {
    if (!c.source || !c.target || c.source === c.target) return;
    // React Flow peut signaler deux fois le même relâchement sur une poignée (mode de connexion libre) : un seul ajout
    const cle = `${c.source}>${c.target}`;
    if (derniereConnexion.current.cle === cle && performance.now() - derniereConnexion.current.t < 800) return;
    derniereConnexion.current = { cle, t: performance.now() };
    const id = await source.lier(c.source, c.target, "", "defaut");
    historique.current.ajouter({
      libelle: "Relation", annuler: async () => { await source.modifierLien(id, { supprime: true }); await charger(); },
      refaire: async () => { await source.modifierLien(id, { supprime: false }); await charger(); },
    });
    await charger();
    toast("Relation créée — double-clique l'étiquette pour la nommer");
  }, [source, charger, toast]);

  /* ------------------------------------------------------------ ingestion -------------------------------- */
  // centre de la vue, décalé tant qu'une carte occupe déjà l'emplacement (les ajouts successifs ne s'empilent pas)
  const centreVue = useCallback(() => {
    const el = document.querySelector(".canevas");
    const r = el?.getBoundingClientRect();
    const p = rf.screenToFlowPosition({ x: (r?.left ?? 0) + (r?.width ?? 800) / 2 - 200, y: (r?.top ?? 0) + (r?.height ?? 600) / 2 - 150 });
    const objets = etatRef.current?.objets ?? [];
    for (let i = 0; i < 60 && objets.some((o) => !o.parent_id && Math.abs(o.x - p.x) < 36 && Math.abs(o.y - p.y) < 36); i++) {
      p.x += 48;
      p.y += 48;
    }
    return { x: Math.round(p.x), y: Math.round(p.y) };
  }, [rf]);

  const ingerer = useCallback(async (elements: Element[], ou?: { x: number; y: number }) => {
    if (!elements.length) return;
    const base = ou ?? centreVue();
    let i = 0;
    const fichiers = elements.filter((e) => e.sorte === "fichier").length;
    if (fichiers) toast(`Téléversement de ${fichiers} fichier${fichiers > 1 ? "s" : ""}…`);
    for (const e of elements) {
      const p = cascade(base.x, base.y, i++);
      try {
        if (e.sorte === "texte") {
          await creer({ type: "note", contenu: e.texte, ...p, largeur: 408, hauteur: 320, meta: { titre: e.texte.split("\n")[0]?.slice(0, 60) || "Note" } });
        } else if (e.sorte === "url") {
          let hote = e.url;
          try { hote = new URL(e.url).hostname; } catch { /* adresse brute */ }
          const id = await creer({ type: "lien", contenu: e.url, ...p, largeur: 434, hauteur: 356, meta: { url: e.url, hote, titre: hote } });
          await charger();
          source.apercu(e.url).then(async (a) => {
            await source.modifier([{ id, champs: { meta: { url: a.url, hote: a.hote, titre: a.titre || a.hote, description: a.description, site: a.site,
              apercu_image: a.image, favicon: a.favicon } } }]);
            charger();
          }).catch(async (x: Error) => {
            await source.modifier([{ id, champs: { meta: { url: e.url, hote, titre: hote, apercu_erreur: x.message } } }]);
            charger();
          });
        } else {
          const famille = familleFichier(e.fichier);
          if (!famille) {
            toast(`« ${e.fichier.name} » : type non pris en charge (image, audio, vidéo, PDF)`, { erreur: true });
            continue;
          }
          const a = await source.televerser(e.fichier);
          const [l, h] = TAILLES[famille]?.defaut ?? [400, 300];
          const ratio = a.meta.largeur && a.meta.hauteur ? a.meta.hauteur / a.meta.largeur : 0;
          await creer({ type: famille, ...p, largeur: l, hauteur: famille === "image" && ratio ? Math.round(l * ratio) + 72 : h,
            asset_id: a.id, meta: { titre: e.fichier.name.replace(/\.[^.]+$/, "") } });
        }
      } catch (x) {
        toast(x instanceof Error ? x.message : "ajout impossible", { erreur: true });
      }
    }
    await charger();
  }, [centreVue, creer, charger, source, toast]);

  // Coller : fichiers et images du presse-papiers, URL, texte — ou les cartes copiées dans le Board
  useEffect(() => {
    const surColler = (e: ClipboardEvent) => {
      if (dansChamp(e.target)) return;
      const texte = e.clipboardData?.getData("text/plain") ?? "";
      if (texte.startsWith(MARQUEUR_PRESSE_PAPIERS) && pressePapiers.current.length) {
        e.preventDefault();
        dupliquer(pressePapiers.current.map((o) => o.id));
        return;
      }
      const elements = depuisTransfert(e.clipboardData);
      if (elements.length) {
        e.preventDefault();
        ingerer(elements);
      }
    };
    window.addEventListener("paste", surColler);
    return () => window.removeEventListener("paste", surColler);
  }, [ingerer, dupliquer]);

  // Raccourcis : annuler / rétablir, copier, supprimer, dupliquer, ajuster
  useEffect(() => {
    const touche = async (e: KeyboardEvent) => {
      if (dansChamp(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      const k = e.key.toLowerCase();
      if (mod && k === "z") {
        e.preventDefault();
        const l = e.shiftKey ? await historique.current.refaire() : await historique.current.annuler();
        if (l) toast(`${e.shiftKey ? "Rétabli" : "Annulé"} : ${l}`);
      } else if (mod && k === "y") {
        e.preventDefault();
        const l = await historique.current.refaire();
        if (l) toast(`Rétabli : ${l}`);
      } else if (mod && k === "c" && selection.length) {
        pressePapiers.current = selection.map(objet).filter((o): o is ObjetBoard => Boolean(o));
        navigator.clipboard?.writeText(MARQUEUR_PRESSE_PAPIERS + selection.join(",")).catch(() => undefined);
      } else if (mod && k === "d" && selection.length) {
        e.preventDefault();
        dupliquer(selection);
      } else if ((e.key === "Delete" || e.key === "Backspace") && selection.length) {
        e.preventDefault();
        supprimer(selection);
      } else if (e.shiftKey && e.key === "!") {
        rf.fitView({ duration: 220, padding: 0.08 });
      } else if (!mod && k === "n") {
        const p = centreVue();
        await creer({ type: "note", contenu: "Nouvelle note", ...p, largeur: 408, hauteur: 320, meta: { titre: "Note" }, analyser: false });
        charger();
      } else if (e.key === "Escape") {
        rf.setNodes((ns) => ns.map((n) => (n.selected ? { ...n, selected: false } : n)));
      }
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [selection, objet, dupliquer, supprimer, rf, toast, centreVue, creer, charger]);

  /* ------------------------------------------------------------ barre d'outils -------------------------- */
  const agir = useCallback(async (o: Outil) => {
    const p = centreVue();
    if (o === "ajouter" || o === "texte") {
      await creer({ type: "note", contenu: "Nouvelle note", ...p, largeur: 408, hauteur: 320, meta: { titre: "Note" }, analyser: false });
      charger();
    } else if (o === "lien") setSaisieUrl(true);
    else if (o === "mindmap") {
      await creer({ type: "dossier", ...p, largeur: 378, hauteur: 152, meta: { titre: "Nouveau dossier" } });
      charger();
      toast("Dossier créé : glisse des cartes dessus pour les y ranger");
    } else if (o === "coller") {
      try {
        const items = await navigator.clipboard.read();
        const elements: Element[] = [];
        for (const it of items) {
          const typeImage = it.types.find((t) => t.startsWith("image/"));
          if (typeImage) {
            const blob = await it.getType(typeImage);
            elements.push({ sorte: "fichier", fichier: new File([blob], `presse-papiers.${typeImage.split("/")[1]}`, { type: typeImage }) });
          } else if (it.types.includes("text/plain")) {
            elements.push(...depuisTexte(await (await it.getType("text/plain")).text()));
          }
        }
        if (elements.length) ingerer(elements, p);
        else toast("Presse-papiers vide");
      } catch {
        toast("Accès au presse-papiers refusé : utilise Ctrl+V sur le Board", { erreur: true });
      }
    } else {
      acceptFichier.current = o === "image" ? "image/png,image/jpeg,image/webp,image/gif" : o === "video" ? "video/*"
        : o === "audio" ? "audio/*" : o === "document" ? "application/pdf" : "image/*,audio/*,video/*,application/pdf";
      if (fichierInput.current) {
        fichierInput.current.accept = acceptFichier.current;
        fichierInput.current.click();
      }
    }
  }, [centreVue, creer, charger, ingerer, toast]);

  const ouvrirDialogueMission = useCallback(() => setDialogueMission(true), []);
  const lancerMission = useCallback(async (d: DemandeMission) => {
    const p = centreVue();
    const id = await source.lancerMission(d, p.x, p.y);  // une erreur reste affichée dans le dialogue
    toast(source.demo ? "Mode démo : aucune mission réelle n'est lancée" : "Mission créée : un exécutant va la prendre en charge");
    await charger();
    rf.setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === id })));
    setSelection([id]);
  }, [source, centreVue, charger, toast, rf]);

  /* ------------------------------------------------------------ sélection multiple ---------------------- */
  const aligner = useCallback(async (mode: "gauche" | "haut" | "centreH" | "centreV" | "distribuerH") => {
    const objs = selection.map(objet).filter((o): o is ObjetBoard => Boolean(o));
    if (objs.length < 2) return;
    let mods: Modification[] = [];
    if (mode === "gauche") { const x = Math.min(...objs.map((o) => o.x)); mods = objs.map((o) => ({ id: o.id, champs: { x } })); }
    if (mode === "haut") { const y = Math.min(...objs.map((o) => o.y)); mods = objs.map((o) => ({ id: o.id, champs: { y } })); }
    if (mode === "centreV") { const c = objs.reduce((s, o) => s + o.x + o.largeur / 2, 0) / objs.length; mods = objs.map((o) => ({ id: o.id, champs: { x: Math.round(c - o.largeur / 2) } })); }
    if (mode === "centreH") { const c = objs.reduce((s, o) => s + o.y + o.hauteur / 2, 0) / objs.length; mods = objs.map((o) => ({ id: o.id, champs: { y: Math.round(c - o.hauteur / 2) } })); }
    if (mode === "distribuerH") {
      const tri = [...objs].sort((a, b) => a.x - b.x);
      const total = tri.reduce((s, o) => s + o.largeur, 0);
      const espace = (tri[tri.length - 1]!.x + tri[tri.length - 1]!.largeur - tri[0]!.x - total) / (tri.length - 1);
      let x = tri[0]!.x;
      mods = tri.map((o) => { const m = { id: o.id, champs: { x: Math.round(x) } }; x += o.largeur + espace; return m; });
    }
    await modifier(mods, "Alignement", objs.map((o) => ({ id: o.id, champs: { x: o.x, y: o.y } })));
  }, [selection, objet, modifier]);

  /* ------------------------------------------------------------ état dans l'URL -------------------------- */
  // filtre, priorité, recherche et carte sélectionnée : partageables et conservés au rechargement (replaceState :
  // l'historique du navigateur n'est pas rempli à chaque frappe)
  useEffect(() => {
    const u = new URL(location.href);
    const poser = (cle: string, v: string) => (v ? u.searchParams.set(cle, v) : u.searchParams.delete(cle));
    poser("filtre", filtre === "tous" ? "" : filtre);
    poser("priorite", prio);
    poser("q", recherche.trim());
    poser("carte", selection.length === 1 ? selection[0]! : "");
    if (u.href !== location.href) history.replaceState(history.state, "", u);
  }, [filtre, prio, recherche, selection]);

  const carteRestauree = useRef(false);
  useEffect(() => {
    if (carteRestauree.current || !etat || !initial.carte) return;
    carteRestauree.current = true;
    const o = etat.objets.find((x) => x.id === initial.carte);
    if (!o) return;
    rf.setNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === o.id })));
    setSelection([o.id]);
    window.setTimeout(() => rf.setCenter(o.x + (o.largeur || 400) / 2, o.y + (o.hauteur || 300) / 2, { zoom: Math.max(0.7, rf.getZoom()), duration: 250 }), 120);
  }, [etat, initial.carte, rf]);

  /* ------------------------------------------------------------ rendu ------------------------------------ */
  const selectionne = selection.length === 1 ? objet(selection[0]!) ?? null : null;
  const vueInitiale: Viewport = source.demo ? { x: 0, y: 0, zoom: 0.8 } : { x: 40, y: 20, zoom: 0.8 };
  const vide = etat && !etat.objets.length;

  return (
    <ContexteActions.Provider value={actions}>
      <div className="app">
        <BarreHaut recherche={recherche} setRecherche={setRecherche} notifications={approbations.length} />
        <SousBarre projet={source.demo ? "Projet Site Web IA" : "Espace accueil"} demo={source.demo} compteurs={compteurs} filtre={filtre} setFiltre={setFiltre}
          priorite={prio} setPriorite={setPrio} magnetisme={magnetisme} setMagnetisme={setMagnetisme} lancer={ouvrirDialogueMission} />
        <div className="travail">
          <section className="canevas" aria-label="Canevas du Board"
            onDragOver={(e) => { if (e.dataTransfer.types.includes("Files") || e.dataTransfer.types.includes("text/uri-list")) { e.preventDefault(); setDepot(true); } }}
            onDragLeave={(e) => { if (e.currentTarget === e.target) setDepot(false); }}
            onDrop={(e) => {
              e.preventDefault();
              setDepot(false);
              ingerer(depuisTransfert(e.dataTransfer), rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
            }}>
            <ReactFlow
              nodes={noeuds} edges={aretes} nodeTypes={TYPES_NOEUDS} edgeTypes={TYPES_LIENS}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
              onNodeDragStart={onNodeDragStart} onNodeDragStop={onNodeDragStop}
              onSelectionChange={surSelection}
              defaultViewport={vueInitiale} minZoom={0.15} maxZoom={2.5} connectionMode={ConnectionMode.Loose}
              snapToGrid={magnetisme} snapGrid={[20, 20]} deleteKeyCode={null} multiSelectionKeyCode={["Shift", "Meta", "Control"]}
              selectionKeyCode="Shift" panOnScroll={false} zoomOnDoubleClick={false} onlyRenderVisibleElements={noeuds.length > 80}
              elevateNodesOnSelect={false} proOptions={{ hideAttribution: false }} fitView={!source.demo && Boolean(etat?.objets.length)}
              fitViewOptions={{ padding: 0.08, maxZoom: 0.9 }}>
              <Background variant={BackgroundVariant.Dots} gap={20} size={1.6} color="var(--grid-dot)" />
              <MiniMap pannable zoomable ariaLabel="Mini-carte du Board" nodeBorderRadius={8} maskColor="rgba(11,14,21,0.6)"
                nodeColor={(n) => COULEUR_MINIMAP[n.type ?? ""] ?? "#2A3147"} style={{ width: 124, height: 92 }} />
            </ReactFlow>
            <BarreOutils agir={agir} />
            {saisieUrl && <SaisieUrl fermer={() => setSaisieUrl(false)} valider={(u) => { setSaisieUrl(false); ingerer(depuisTexte(u).length ? depuisTexte(u) : [{ sorte: "url", url: u }]); }} />}
            {selection.length > 1 && (
              <div className="selection nodrag" role="toolbar" aria-label="Sélection">
                <span className="compte-sel tab-num">{selection.length} cartes</span>
                <button type="button" onClick={() => aligner("gauche")} title="Aligner à gauche"><AlignLeft size={16} /></button>
                <button type="button" onClick={() => aligner("haut")} title="Aligner en haut"><AlignStartVertical size={16} /></button>
                <button type="button" onClick={() => aligner("centreV")} title="Centrer verticalement"><AlignVerticalJustifyCenter size={16} /></button>
                <button type="button" onClick={() => aligner("centreH")} title="Centrer horizontalement"><AlignHorizontalJustifyCenter size={16} /></button>
                <button type="button" onClick={() => aligner("distribuerH")} title="Répartir horizontalement" disabled={selection.length < 3}>Répartir</button>
                <span className="sep" />
                {(["P1", "P2", "P3"] as Priorite[]).map((p) => (
                  <button key={p} type="button" onClick={() => modifier(selection.map((id) => ({ id, champs: { priorite: p } })), "Priorité",
                    selection.map((id) => ({ id, champs: { priorite: objet(id)?.priorite ?? "" } })))}><span className={`badge-p ${p}`} style={{ height: 20, minWidth: 26, fontSize: 11 }}>{p}</span></button>
                ))}
                <span className="sep" />
                <button type="button" onClick={() => devant(selection)} title="Amener devant"><ArrowUpToLine size={16} /></button>
                <button type="button" onClick={() => dupliquer(selection)} title="Dupliquer (Ctrl+D)"><Copy size={16} /></button>
                <button type="button" onClick={() => modifier(selection.map((id) => ({ id, champs: { verrouille: true } })), "Verrouillage",
                  selection.map((id) => ({ id, champs: { verrouille: false } })))} title="Verrouiller"><Lock size={16} /></button>
                <button type="button" onClick={async () => {
                  const d = await creer({ type: "dossier", x: Math.min(...selection.map((id) => objet(id)?.x ?? 0)), y: Math.min(...selection.map((id) => objet(id)?.y ?? 0)) - 200,
                    largeur: 378, hauteur: 152, meta: { titre: "Groupe" } }, "Groupe");
                  await modifier(selection.map((id) => ({ id, champs: { parent_id: d } })), "Groupe", selection.map((id) => ({ id, champs: { parent_id: null } })));
                }} title="Grouper dans un dossier"><FolderInput size={16} /></button>
                <button type="button" onClick={() => supprimer(selection)} title="Supprimer (Suppr)"><Trash2 size={16} /></button>
              </div>
            )}
            {vide && (
              <div className="etat-vide">
                <div>
                  <h2>Ton Board est prêt</h2>
                  Colle une image, un lien ou un texte (Ctrl+V), dépose des fichiers, ou utilise la barre d'outils à gauche.
                  <div><button type="button" className="bouton primaire" onClick={() => agir("texte")}>Écrire une première note</button></div>
                </div>
              </div>
            )}
            {erreur && <div className="etat-vide"><div role="alert"><h2>Board indisponible</h2>{erreur}<div><button type="button" className="bouton" onClick={charger}>Réessayer</button></div></div></div>}
            {depot && <div className="depot">Dépose pour ajouter au Board</div>}
            <div className="toasts" aria-live="polite">
              {toasts.map((t) => (
                <div key={t.id} className={`toast${t.erreur ? " erreur" : ""}`}>{t.texte}
                  {t.action && <button type="button" onClick={t.action.faire}>{t.action.nom}</button>}</div>
              ))}
            </div>
            <input ref={fichierInput} type="file" multiple hidden onChange={(e) => {
              ingerer(Array.from(e.target.files ?? []).map((fichier) => ({ sorte: "fichier" as const, fichier })));
              e.target.value = "";
            }} />
          </section>
          <Panneau source={source} objet={selectionne} objets={etat?.objets ?? []} evenements={evenements} approbations={approbations} tick={tick}
            priorite={actions.priorite} modifierMeta={(o, meta) => modifier([{ id: o.id, champs: { meta } }], "Étiquettes", [{ id: o.id, champs: { meta: o.meta } }])}
            decider={async (id, accord) => { await source.decider(id, accord); charger(); }}
            contextualiser={actions.contextualiser}
            deciderProposition={async (o, i, d) => {
              try {
                const r = await source.deciderProposition(o.id, i, d);
                toast(d === "ecarter" ? "Proposition écartée" : source.demo ? "Mode démo : aucune mission réelle n'est lancée"
                  : "Mission de préparation créée, reliée à l'élément");
                await charger();
                if (r.carte_id) actions.inspecter(r.carte_id);
              } catch (x) {
                toast(x instanceof Error ? x.message : "décision refusée", { erreur: true });
              }
            }} />
        </div>
      </div>
      <DialogueMission ouvert={dialogueMission} demo={source.demo} fermer={() => setDialogueMission(false)} lancer={lancerMission} />
      {visionneuse && (
        <div className="visionneuse" role="dialog" aria-label={visionneuse.titre || "Image"} onClick={() => setVisionneuse(null)}
          onKeyDown={(e) => e.key === "Escape" && setVisionneuse(null)}>
          <img src={visionneuse.src} alt={visionneuse.titre} />
          <button type="button" className="bouton" autoFocus onClick={() => setVisionneuse(null)}>Fermer</button>
        </div>
      )}
    </ContexteActions.Provider>
  );
}

const FILTRES_VALIDES = new Set<string>(FILTRES.map((f) => f.cle));

/** État initial lu dans l'URL ; toute valeur inconnue est ignorée. */
function lireUrl(): { filtre: Filtre; priorite: string; q: string; carte: string } {
  const p = new URLSearchParams(location.search);
  const f = p.get("filtre") ?? "";
  const pr = p.get("priorite") ?? "";
  const carte = p.get("carte") ?? "";
  return {
    filtre: (FILTRES_VALIDES.has(f) ? f : "tous") as Filtre,
    priorite: ["P1", "P2", "P3"].includes(pr) ? pr : "",
    q: (p.get("q") ?? "").slice(0, 200),
    carte: /^BO-[A-Za-z0-9-]{1,40}$/.test(carte) ? carte : "",
  };
}

/** Mode charge (démo, ?charge=N) : N cartes de types mixtes pour mesurer les performances. Jamais en mode réel. */
function genererCharge(n: number): ObjetBoard[] {
  const types: ObjetBoard["type"][] = ["note", "image", "lien", "pdf", "audio", "video"];
  const cotes = Math.max(4, Math.ceil(Math.sqrt(n)));
  return Array.from({ length: n }, (_, i) => {
    const type = types[i % types.length]!;
    const [l, h] = TAILLES[type]?.defaut ?? [400, 300];
    return {
      id: `BO-charge${i}`, type, espace: "accueil", contenu: type === "note" ? `Note de charge ${i}\n- élément\n- autre` : "",
      x: 2000 + (i % cotes) * 520, y: (Math.floor(i / cotes)) * 420, largeur: l, hauteur: h, z: 1, priorite: (["P1", "P2", "P3", ""] as const)[i % 4]!,
      meta: { titre: `Carte ${i}`, url: type === "lien" ? "https://exemple.test" : undefined }, asset_id: null, asset: null, mission_id: null,
      parent_id: null, verrouille: 0, version: 1, cree: 0, maj: 0,
    };
  });
}
