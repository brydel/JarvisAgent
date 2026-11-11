// Les SERVICES du Board : ce que les commandes, les outils et les cartes peuvent faire. Toutes les écritures passent
// par la file optimiste versionnée (src/donnees/ecritures.ts) et déposent leur inverse dans l'historique : chaque
// geste est annulable, et une annulation en conflit (409) est refusée proprement au lieu d'écraser.
import { useEffect, useMemo, useRef } from "react";
import type { Edge, Node, ReactFlowInstance } from "@xyflow/react";
import type { Modification, NouvelObjet, Source } from "../api";
import type { ServicesBoard, OptionsToast } from "../commandes/contexte";
import type { Historique } from "../commandes/historique";
import type { FileEcritures } from "../donnees/ecritures";
import type { ChampsObjet, StoreBoard } from "../donnees/store";
import type { Synchroniseur } from "../donnees/synchro";
import type { DonneesLien } from "../edges/RelationEdge";
import { ui } from "../etat/ui";
import { boiteDe } from "../outils/espace";
import { englobante, type Point } from "../outils/geometrie";
import type { DonneesNoeud, ObjetBoard, StyleLien } from "../types";
import { MARGE_VUE, forcerDetail } from "./detail";
import { capturer, nomDeFichier, telechargerBlob } from "./exportPng";

export const MARQUEUR_PRESSE_PAPIERS = "jarvis-board/objets:";
type Rf = ReactFlowInstance<Node<DonneesNoeud>, Edge<DonneesLien>>;

export interface Entrees {
  source: Source;
  store: StoreBoard;
  file: FileEcritures;
  sync: Synchroniseur;
  creerObjet(o: NouvelObjet): Promise<string>;
  rf: Rf;
  historique: Historique;
  toast(texte: string, options?: OptionsToast): void;
  ouvrirMission(): void;
  saisirLien(): void;
  choisirFichiers(accept: string): void;
  collerPressePapiers(): Promise<void>;
  /** carte à sélectionner dès qu'elle existe dans le canevas */
  viserSelection(ids: string[]): void;
}

const calme = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const duree = (ms: number) => (calme() ? 0 : ms);
const deuxImages = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));

/** Valeurs actuelles des champs qu'une modification va changer : c'est son inverse. */
export function inverseDe(o: ObjetBoard | undefined, champs: ChampsObjet): ChampsObjet {
  const inverse: Record<string, unknown> = {};
  if (o) for (const k of Object.keys(champs)) inverse[k] = k === "verrouille" ? Boolean(o.verrouille) : (o as unknown as Record<string, unknown>)[k];
  return inverse as ChampsObjet;
}

export function useServices(e: Entrees): ServicesBoard {
  const entrees = useRef(e);
  entrees.current = e;
  const pressePapiers = useRef<{ objets: ObjetBoard[]; collages: number }>({ objets: [], collages: 0 });

  const services = useMemo<ServicesBoard>(() => {
    const E = () => entrees.current;
    const objet = (id: string) => E().store.objet(id);

    const modifier = async (mods: Modification[], libelle: string) => {
      if (!mods.length) return;
      const { file, historique } = E();
      const inverse = mods.map((m) => ({ id: m.id, champs: inverseDe(objet(m.id), m.champs) }));
      const jouer = async (liste: Modification[]) => (await file.modifier(liste)).some((r) => r.ok);
      // entrée posée AU MOMENT DU GESTE (Ctrl+Z fonctionne avant la réponse du serveur : son écriture attend son tour
      // dans la file) et retirée si le serveur refuse tout
      const entree = { libelle, annuler: () => jouer(inverse), refaire: () => jouer(mods) };
      historique.ajouter(entree);
      if (!(await jouer(mods))) historique.retirer(entree);
    };

    const creer = async (o: NouvelObjet, libelle = "Ajout") => {
      const { creerObjet, file, historique } = E();
      const id = await creerObjet(o);
      historique.ajouter({ libelle, annuler: () => file.supprimer([id]), refaire: () => file.restaurer([id]) });
      return id;
    };

    const supprimer = async (ids: string[]) => {
      if (!ids.length) return;
      const { file, historique, toast } = E();
      const entree = { libelle: "Suppression", annuler: () => file.restaurer(ids), refaire: () => file.supprimer(ids) };
      historique.ajouter(entree);
      if (!(await file.supprimer(ids))) {
        historique.retirer(entree);
        return;
      }
      toast(`${ids.length} objet${ids.length > 1 ? "s" : ""} supprimé${ids.length > 1 ? "s" : ""}`, { action: { nom: "Annuler", faire: () => void services.annuler() } });
    };

    /** Recrée des objets (copie fidèle : contenu, apparence, fichier) décalés de (dx, dy) ; un seul pas d'annulation. */
    const copies = (objets: ObjetBoard[], dx: number, dy: number, libelle: string) => E().historique.grouper(libelle, async () => {
      const crees: string[] = [];
      for (const o of objets) {
        if (o.type === "mission" || o.type === "agents") continue;  // un travail réel ne se recopie pas
        crees.push(await creer({ type: o.type, contenu: o.contenu, x: Math.round(o.x + dx), y: Math.round(o.y + dy), largeur: o.largeur, hauteur: o.hauteur,
          priorite: o.priorite, meta: o.meta, asset_id: o.asset_id, analyser: false }, libelle));
      }
      return crees;
    });

    const jouerHistorique = async (sens: "annuler" | "refaire") => {
      const r = await E().historique[sens]();
      if (!r) return;
      const verbe = sens === "annuler" ? "Annulé" : "Rétabli";
      E().toast(r.ok ? `${verbe} : ${r.libelle}` : `${sens === "annuler" ? "Annulation" : "Rétablissement"} impossible (« ${r.libelle} ») : l'élément a changé ailleurs`, { erreur: !r.ok });
    };

    const services: ServicesBoard = {
      get demo() { return E().source.demo; },
      ui,
      objet,
      objets: () => E().store.lire().objets,
      liens: () => E().store.lire().liens,
      visibles: () => E().rf.getNodes().filter((n) => !n.hidden).map((n) => n.id),
      modifier, creer, supprimer,
      dupliquer: (ids, decalage = { x: 40, y: 40 }) => copies(ids.map(objet).filter((o): o is ObjetBoard => Boolean(o)), decalage.x, decalage.y, "Duplication"),
      lier: async (source: string, cible: string, style: StyleLien = "defaut") => {
        if (source === cible) return null;
        const { source: src, sync, file, historique, toast } = E();
        let id: string;
        try {
          id = await src.lier(source, cible, "", style);
        } catch (x) {
          toast(x instanceof Error ? x.message : "relation refusée", { erreur: true });
          return null;
        }
        // les deux cartes sont relues avec la relation : leur résumé calculé (bloquée par, alimentée par…) en dépend
        await sync.lireMaintenant(style === "defaut" || style === "utilise" ? [] : [source, cible], [id]);
        historique.ajouter({ libelle: "Relation", annuler: () => file.modifierLien(id, { supprime: true }), refaire: () => file.modifierLien(id, { supprime: false }) });
        return id;
      },
      modifierLien: async (id, champs) => {
        const { file, historique, store } = E();
        const l = store.lire().liens.find((x) => x.id === id);
        if (!l) return;
        const avant = { ...(champs.libelle !== undefined ? { libelle: l.libelle } : {}), ...(champs.style !== undefined ? { style: l.style } : {}) };
        const entree = { libelle: "Relation", annuler: () => file.modifierLien(id, avant), refaire: () => file.modifierLien(id, champs) };
        historique.ajouter(entree);
        if (!(await file.modifierLien(id, champs))) historique.retirer(entree);
      },
      supprimerLien: async (id) => {
        const { file, historique } = E();
        const entree = { libelle: "Suppression de relation", annuler: () => file.modifierLien(id, { supprime: false }), refaire: () => file.modifierLien(id, { supprime: true }) };
        historique.ajouter(entree);
        if (!(await file.modifierLien(id, { supprime: true }))) historique.retirer(entree);
      },
      commenter: async (id, texte) => {
        const { source, sync, toast } = E();
        try {
          await source.commenter(id, texte);
          sync.demander([id]);
        } catch (x) {
          toast(x instanceof Error ? x.message : "commentaire refusé", { erreur: true });
        }
      },
      grouper: (libelle, f) => E().historique.grouper(libelle, f),
      annuler: () => jouerHistorique("annuler"),
      retablir: () => jouerHistorique("refaire"),
      historique: () => E().historique.etat(),
      relire: async (id, action, options) => {
        const { source, sync, toast } = E();
        try {
          const r = await source.relecture(id, action, options);
          await sync.lireMaintenant([id]);
          return r;
        } catch (x) {
          toast(x instanceof Error ? x.message : "relecture refusée", { erreur: true });
          return null;
        }
      },

      copier: (ids) => {
        pressePapiers.current = { objets: ids.map(objet).filter((o): o is ObjetBoard => Boolean(o)), collages: 0 };
        navigator.clipboard?.writeText(MARQUEUR_PRESSE_PAPIERS + ids.join(",")).catch(() => undefined);
      },
      peutColler: () => pressePapiers.current.objets.length > 0,
      coller: async (ou) => {
        const pp = pressePapiers.current;
        if (!pp.objets.length) return;
        pp.collages += 1;
        const zone = englobante(pp.objets.map(boiteDe))!;
        // à l'endroit visé (menu contextuel) ; sinon en cascade à côté de l'original
        const [dx, dy] = ou ? [ou.x - zone.x, ou.y - zone.y] : [40 * pp.collages, 40 * pp.collages];
        services.selectionner(await copies(pp.objets, dx, dy, "Collage"));
      },

      selectionner: (ids) => {
        const choisis = new Set(ids);
        const { rf, viserSelection } = E();
        viserSelection(ids.filter((id) => !rf.getNode(id)));  // pas encore dans le canevas : sélectionnés à leur arrivée
        rf.setNodes((ns) => ns.map((n) => (n.selected === choisis.has(n.id) ? n : { ...n, selected: choisis.has(n.id) })));
        rf.setEdges((es) => es.map((x) => (x.selected ? { ...x, selected: false } : x)));
      },
      inspecter: (id) => services.selectionner([id]),
      allerA: (id) => {
        const o = objet(id);
        if (!o) {
          E().toast("Cette carte n'est plus sur ce Board", { erreur: true });
          return;
        }
        services.selectionner([id]);
        services.montrer(boiteDe(o));
      },
      ajuster: () => void E().rf.fitView({ duration: duree(220), padding: MARGE_VUE }),
      zoomer: (facteur) => void E().rf.zoomTo(E().rf.getZoom() * facteur, { duration: duree(160) }),
      zoomA: (niveau) => void E().rf.zoomTo(niveau, { duration: duree(160) }),
      cadrer: (zone, marge = 0.1) => void E().rf.fitBounds({ x: zone.x, y: zone.y, width: Math.max(1, zone.largeur), height: Math.max(1, zone.hauteur) }, { padding: marge, duration: duree(280) }),
      montrer: (zone) => {
        const { rf } = E();
        const r = document.querySelector(".canevas")?.getBoundingClientRect();
        if (!r) return;
        const hg = rf.screenToFlowPosition({ x: r.left, y: r.top }), bd = rf.screenToFlowPosition({ x: r.right, y: r.bottom });
        const visible = zone.x >= hg.x && zone.y >= hg.y && zone.x + zone.largeur <= bd.x && zone.y + zone.hauteur <= bd.y;
        if (!visible) void rf.setCenter(zone.x + zone.largeur / 2, zone.y + zone.hauteur / 2, { zoom: rf.getZoom(), duration: duree(220) });
      },
      centreVue: (): Point => {
        const r = document.querySelector(".canevas")?.getBoundingClientRect();
        const p = E().rf.screenToFlowPosition({ x: (r?.left ?? 0) + (r?.width ?? 800) / 2 - 200, y: (r?.top ?? 0) + (r?.height ?? 600) / 2 - 150 });
        // décalé tant qu'une carte occupe déjà l'emplacement : les ajouts successifs ne s'empilent pas
        const objets = E().store.lire().objets;
        for (let i = 0; i < 60 && objets.some((o) => !o.parent_id && Math.abs(o.x - p.x) < 36 && Math.abs(o.y - p.y) < 36); i++) {
          p.x += 48;
          p.y += 48;
        }
        return { x: Math.round(p.x), y: Math.round(p.y) };
      },

      toast: (texte, options) => E().toast(texte, options),
      ouvrirMission: () => E().ouvrirMission(),
      saisirLien: () => E().saisirLien(),
      choisirFichiers: (accept) => E().choisirFichiers(accept),
      collerPressePapiers: () => E().collerPressePapiers(),
      contextualiser: (id) => {
        const { source, sync, toast } = E();
        source.contextualiser(id).then(() => {
          toast(source.demo ? "Mode démo : aucune IA n'est appelée" : "Jarvis analyse l'élément…");
          sync.demander([id]);
        }).catch((x: Error) => toast(x.message, { erreur: true }));
      },
      exporterPng: async (ids, nom) => {
        const { rf, toast } = E();
        const objets = ids.map(objet).filter((o): o is ObjetBoard => Boolean(o));
        const calque = document.querySelector<HTMLElement>(".canevas .react-flow__viewport");
        const zone = englobante(objets.map(boiteDe));
        if (!calque || !zone) return;
        const cadre = objets.length === 1 && objets[0]!.type === "cadre";
        const marge = cadre ? 0 : 24;
        const avec = { x: zone.x - marge, y: zone.y - marge - (cadre ? 34 : 0), largeur: zone.largeur + 2 * marge, hauteur: zone.hauteur + 2 * marge + (cadre ? 34 : 0) };
        const vue = rf.getViewport();
        try {
          // la zone entière doit être rendue (les objets hors écran sont virtualisés) et en détail complet
          forcerDetail(true);
          await rf.fitBounds({ x: avec.x, y: avec.y, width: avec.largeur, height: avec.hauteur }, { padding: 0.02, duration: 0 });
          await deuxImages();
          const fond = getComputedStyle(document.documentElement).getPropertyValue("--bg-canvas").trim() || "transparent";
          telechargerBlob(await capturer({ calque, zone: avec, garder: cadre ? null : new Set(ids), fond }), nomDeFichier(nom));
          toast(`Image exportée : ${nomDeFichier(nom)}`);
        } catch (x) {
          toast(`Export impossible : ${x instanceof Error ? x.message : "erreur inconnue"}`, { erreur: true });
        } finally {
          forcerDetail(false);
          await rf.setViewport(vue);
        }
      },
      pleinEcran: async (actif) => {
        try {
          if (actif && !document.fullscreenElement) await document.documentElement.requestFullscreen();
          else if (!actif && document.fullscreenElement) await document.exitFullscreen();
        } catch {
          E().toast("Plein écran refusé par le navigateur", { erreur: true });
        }
      },
    };
    return services;
  }, []);

  // l'état « plein écran » suit le navigateur (touche Échap du navigateur, F11…)
  useEffect(() => {
    const suivre = () => ui.definir({ pleinEcran: Boolean(document.fullscreenElement) });
    document.addEventListener("fullscreenchange", suivre);
    return () => document.removeEventListener("fullscreenchange", suivre);
  }, []);

  return services;
}
