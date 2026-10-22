// Accès aux données. Deux sources, même interface :
// - SourceReelle : l'API authentifiée du Studio (lib/jarvis/studio_api.py), seule source de vérité ;
// - SourceDemo   : jeu de démonstration EN MÉMOIRE (src/demo/fixture.ts), signalé « DÉMO », jamais persisté,
//                  jamais présenté comme des missions ou des agents réels.
import type { Approbation, Asset, EtatBoard, LienBoard, ObjetBoard, StyleLien } from "./types";
import { fixtureDemo, inspectionDemo } from "./demo/fixture";
import type { DemandeMission } from "./components/DialogueMission";

const ENTETE = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" } as const;

export class ErreurApi extends Error {
  constructor(message: string, public statut: number) {
    super(message);
  }
}

async function json<T>(chemin: string, init?: RequestInit): Promise<T> {
  const r = await fetch(chemin, { credentials: "same-origin", ...init });
  const data = (await r.json().catch(() => ({}))) as { erreur?: string };
  if (!r.ok) throw new ErreurApi(data.erreur || `erreur ${r.status}`, r.status);
  return data as T;
}
const poster = <T,>(chemin: string, corps: unknown) =>
  json<T>(chemin, { method: "POST", headers: ENTETE, body: JSON.stringify(corps) });

export interface NouvelObjet {
  type: ObjetBoard["type"];
  contenu?: string;
  x: number;
  y: number;
  largeur: number;
  hauteur: number;
  priorite?: ObjetBoard["priorite"];
  meta?: ObjetBoard["meta"];
  asset_id?: string | null;
  mission_id?: string | null;
  analyser?: boolean;
}
export interface Modification {
  id: string;
  champs: Partial<Pick<ObjetBoard, "x" | "y" | "largeur" | "hauteur" | "z" | "priorite" | "meta" | "contenu" | "parent_id">> & {
    verrouille?: boolean;
  };
  version?: number;
}
export interface Apercu {
  url: string;
  hote: string;
  titre: string;
  description: string;
  site: string;
  image: Asset | null;
  favicon: Asset | null;
}

export interface Source {
  demo: boolean;
  charger(): Promise<EtatBoard>;
  creer(o: NouvelObjet): Promise<string>;
  modifier(mods: Modification[]): Promise<{ id: string; ok: boolean; erreur?: string; version?: number }[]>;
  supprimer(ids: string[], restaurer?: boolean): Promise<void>;
  lier(source: string, cible: string, libelle: string, style: StyleLien): Promise<string>;
  modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }): Promise<void>;
  televerser(fichier: File): Promise<Asset>;
  apercu(url: string): Promise<Apercu>;
  inspection(missionId: string): Promise<Inspection>;
  approbations(): Promise<Approbation[]>;
  decider(id: string, accord: boolean): Promise<void>;
  commentaires(objetId: string): Promise<{ id: string; auteur: string; texte: string; cree: number }[]>;
  commenter(objetId: string, texte: string): Promise<void>;
  lancerMission(demande: DemandeMission, x: number, y: number): Promise<string>;
  contextualiser(objetId: string): Promise<void>;
  deciderProposition(objetId: string, index: number, decision: "lancer" | "ecarter"): Promise<{ carte_id?: string }>;
}

export interface Inspection {
  id: string;
  objectif: string;
  statut: string;
  source: string;
  demandeur: string;
  cree: number;
  taches: {
    id: string; type: string; niveau: string; statut: string; essais: number; essais_max: number;
    fournisseur_choisi: string | null; raison: string; libelle?: string;
    tentatives: { id: string; executant_nom: string | null; fournisseur: string; issue: string | null; debut: number; fin: number | null }[];
    approbations: { id: string; statut: string; demandeur: string; decide_par: string | null; cree: number }[];
  }[];
  artefacts: { id: string; fournisseur: string; factice: number; revue: string; contenu: string }[];
  chronologie: { seq: number; type: string; ts: number; tache_id: string | null; donnees: Record<string, unknown> }[];
  description?: string;
  tags?: string[];
}

export class SourceReelle implements Source {
  demo = false;
  constructor(private espace = "accueil") {}
  charger() {
    return json<EtatBoard>(`/api/v2/board?espace=${encodeURIComponent(this.espace)}`);
  }
  async creer(o: NouvelObjet) {
    const r = await poster<{ objet_id: string }>("/api/v2/objets", { ...o, espace: this.espace });
    return r.objet_id;
  }
  async modifier(mods: Modification[]) {
    const r = await poster<{ resultats: { id: string; ok: boolean; erreur?: string; version?: number }[] }>(
      "/api/v2/objets/lot", { modifications: mods });
    return r.resultats;
  }
  async supprimer(ids: string[], restaurer = false) {
    await poster("/api/v2/objets/supprimer", { ids, restaurer });
  }
  async lier(source: string, cible: string, libelle: string, style: StyleLien) {
    const r = await poster<{ id: string }>("/api/v2/liens", { source_id: source, cible_id: cible, libelle, style, espace: this.espace });
    return r.id;
  }
  async modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }) {
    await poster(`/api/v2/liens/${id}`, champs);
  }
  async televerser(fichier: File) {
    const r = await fetch("/api/v2/fichiers", {
      method: "POST", credentials: "same-origin", body: fichier,
      headers: { "X-Jarvis-Studio": "1", "X-Nom-Fichier": encodeURIComponent(fichier.name), "Content-Type": "application/octet-stream" },
    });
    const data = (await r.json().catch(() => ({}))) as Asset & { erreur?: string };
    if (!r.ok) throw new ErreurApi(data.erreur || `erreur ${r.status}`, r.status);
    return data;
  }
  apercu(url: string) {
    return poster<Apercu>("/api/v2/apercu", { url });
  }
  inspection(missionId: string) {
    return json<Inspection>(`/api/missions/${missionId}/inspection`);
  }
  async approbations() {
    return (await json<{ approbations: Approbation[] }>("/api/approbations")).approbations;
  }
  async decider(id: string, accord: boolean) {
    await poster(`/api/approbations/${id}`, { accord });
  }
  async commentaires(objetId: string) {
    return (await json<{ commentaires: { id: string; auteur: string; texte: string; cree: number }[] }>(
      `/api/v2/objets/${objetId}/commentaires`)).commentaires;
  }
  async commenter(objetId: string, texte: string) {
    await poster(`/api/v2/objets/${objetId}/commentaires`, { texte });
  }
  async lancerMission(demande: DemandeMission, x: number, y: number) {
    const r = await poster<{ objet_id: string }>("/api/v2/missions", { ...demande, x, y, espace: this.espace });
    return r.objet_id;
  }
  async contextualiser(objetId: string) {
    await poster(`/api/v2/objets/${objetId}/contextualiser`, {});
  }
  deciderProposition(objetId: string, index: number, decision: "lancer" | "ecarter") {
    return poster<{ carte_id?: string }>(`/api/v2/objets/${objetId}/propositions`, { index, decision });
  }
}

/** Démo en mémoire : chaque modification vit le temps de l'onglet. */
export class SourceDemo implements Source {
  demo = true;
  private etat: EtatBoard = fixtureDemo();
  private compteur = 0;
  private commentairesDemo = new Map<string, { id: string; auteur: string; texte: string; cree: number }[]>();
  private id(p: string) {
    this.compteur += 1;
    return `${p}-demo${String(this.compteur).padStart(7, "0")}`;
  }
  async charger() {
    return structuredClone(this.etat);
  }
  async creer(o: NouvelObjet) {
    const id = this.id("BO");
    const z = Math.max(0, ...this.etat.objets.map((x) => x.z)) + 1;
    this.etat.objets.push({
      id, type: o.type, espace: "accueil", contenu: o.contenu ?? "", x: o.x, y: o.y, largeur: o.largeur, hauteur: o.hauteur,
      z, priorite: o.priorite ?? "", meta: o.meta ?? {}, asset_id: o.asset_id ?? null, asset: o.asset_id ? this.assets.get(o.asset_id) ?? null : null,
      mission_id: null, parent_id: null, verrouille: 0, version: 1, cree: Date.now() / 1000, maj: Date.now() / 1000,
    });
    return id;
  }
  async modifier(mods: Modification[]) {
    return mods.map((m) => {
      const o = this.etat.objets.find((x) => x.id === m.id);
      if (!o) return { id: m.id, ok: false, erreur: "objet inconnu" };
      const { verrouille, ...reste } = m.champs;
      Object.assign(o, reste);
      if (verrouille !== undefined) o.verrouille = verrouille ? 1 : 0;
      o.version += 1;
      return { id: m.id, ok: true, version: o.version };
    });
  }
  private supprimes = new Map<string, ObjetBoard>();
  private liensSupprimes = new Map<string, LienBoard>();
  async supprimer(ids: string[], restaurer = false) {
    if (restaurer) {
      for (const id of ids) {
        const o = this.supprimes.get(id);
        if (o) this.etat.objets.push(o);
        this.supprimes.delete(id);
      }
      for (const [id, l] of this.liensSupprimes) {
        if (ids.includes(l.source_id) || ids.includes(l.cible_id)) {
          this.etat.liens.push(l);
          this.liensSupprimes.delete(id);
        }
      }
      return;
    }
    for (const id of ids) {
      const o = this.etat.objets.find((x) => x.id === id);
      if (o) this.supprimes.set(id, o);
    }
    this.etat.objets = this.etat.objets.filter((o) => !ids.includes(o.id));
    for (const l of this.etat.liens.filter((l) => ids.includes(l.source_id) || ids.includes(l.cible_id))) {
      this.liensSupprimes.set(l.id, l);
    }
    this.etat.liens = this.etat.liens.filter((l) => !this.liensSupprimes.has(l.id));
  }
  async lier(source: string, cible: string, libelle: string, style: StyleLien) {
    const id = this.id("BL");
    this.etat.liens.push({ id, source_id: source, cible_id: cible, libelle, style });
    return id;
  }
  async modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }) {
    const l = this.etat.liens.find((x) => x.id === id) ?? this.liensSupprimes.get(id);
    if (!l) return;
    if (champs.libelle !== undefined) l.libelle = champs.libelle;
    if (champs.style !== undefined) l.style = champs.style;
    if (champs.supprime === true) {
      this.etat.liens = this.etat.liens.filter((x) => x.id !== id);
      this.liensSupprimes.set(id, l);
    } else if (champs.supprime === false && this.liensSupprimes.has(id)) {
      this.liensSupprimes.delete(id);
      this.etat.liens.push(l);
    }
  }
  private assets = new Map<string, Asset>();
  async televerser(fichier: File) {
    // en démo, le fichier reste dans le navigateur (URL blob), rien n'est envoyé ni stocké
    const famille = fichier.type.startsWith("image/") ? "image" : fichier.type.startsWith("audio/") ? "audio"
      : fichier.type.startsWith("video/") ? "video" : fichier.type === "application/pdf" ? "pdf" : null;
    if (!famille) throw new ErreurApi("type de fichier non pris en charge", 415);
    const url = URL.createObjectURL(fichier);
    const a: Asset = { id: this.id("AS"), mime: fichier.type, taille: fichier.size, nom: fichier.name, famille, meta: {}, url, vignette_url: null };
    this.assets.set(a.id, a);
    return a;
  }
  async apercu(url: string): Promise<Apercu> {
    const hote = (() => { try { return new URL(url).hostname; } catch { return url; } })();
    return { url, hote, titre: hote, description: "Aperçu indisponible en mode démo (aucune requête réseau).", site: "", image: null, favicon: null };
  }
  async inspection(missionId: string) {
    return inspectionDemo(missionId);
  }
  async approbations() {
    return [];
  }
  async decider() {}
  async commentaires(objetId: string) {
    return this.commentairesDemo.get(objetId) ?? [];
  }
  async commenter(objetId: string, texte: string) {
    const l = this.commentairesDemo.get(objetId) ?? [];
    l.push({ id: this.id("CM"), auteur: "vous (démo)", texte, cree: Date.now() / 1000 });
    this.commentairesDemo.set(objetId, l);
  }
  async contextualiser(objetId: string) {
    // démo : aucun modèle n'est appelé ; la carte le dit
    const o = this.etat.objets.find((x) => x.id === objetId);
    if (o) o.meta = { ...o.meta, jarvis_resume: "Mode démo : aucune IA n'a lu cet élément.", propositions: [] };
  }
  async deciderProposition(objetId: string, index: number, decision: "lancer" | "ecarter") {
    const p = this.etat.objets.find((x) => x.id === objetId)?.meta.propositions?.[index];
    if (p) p.statut = decision === "lancer" ? "lancee" : "ecartee";
    return {};
  }
  async lancerMission(demande: DemandeMission, x: number, y: number) {
    return this.creer({ type: "note", contenu: `**Mission (démo, non lancée)** : ${demande.objectif}\n\n${demande.contexte}`.trim(),
      x, y, largeur: 408, hauteur: 300, priorite: demande.priorite, meta: { titre: "Mission (démo)" } });
  }
}

export async function sessionValide(): Promise<boolean> {
  const jeton = location.hash.slice(1);
  if (jeton) {
    history.replaceState(null, "", location.pathname.replace(/connexion$/, "") + location.search);
    try {
      await poster("/api/session", { jeton });
    } catch {
      return false;
    }
  }
  try {
    const r = await json<{ authentifie: boolean }>("/api/session");
    return r.authentifie;
  } catch {
    return false;
  }
}
