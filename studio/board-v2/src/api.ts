// Accès aux données. Deux sources, même interface :
// - SourceReelle : l'API authentifiée du Studio (lib/jarvis/studio_api.py), seule source de vérité ;
// - SourceDemo   : jeu de démonstration EN MÉMOIRE (src/demo/fixture.ts), signalé « DÉMO », jamais persisté,
//                  jamais présenté comme des missions ou des agents réels.
import { calculerRelations, creeraitBoucle, phraseBlocage } from "./relations/effets";
import type { Approbation, Asset, DeltaBoard, EspaceBoard, EtatBoard, Evenement, LienBoard, ObjetBoard, ReglagesBoard, Relecture, StyleLien } from "./types";
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
  /** Board courant : un par projet */
  espace: string;
  espaces(): Promise<EspaceBoard[]>;
  regler(valeurs: Partial<ReglagesBoard>): Promise<ReglagesBoard>;
  /** Board entier + curseur du journal. Réservé au démarrage et au filet de sécurité (trou, reconnexion). */
  charger(): Promise<EtatBoard>;
  /** Lecture ciblée : quelques objets (et les relations qui les touchent), quelques relations. */
  lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard>;
  /** Derniers événements du Board (activité récente), du plus ancien au plus récent. */
  historique(dernier: number): Promise<Evenement[]>;
  creer(o: NouvelObjet): Promise<string>;
  /** Chaque modification porte la version connue ; `code: "conflit"` si elle est périmée. */
  modifier(mods: Modification[]): Promise<{ id: string; ok: boolean; erreur?: string; code?: string; version?: number }[]>;
  /** `versions` : version connue de chaque objet ; rejet 409 (ErreurApi) si l'un d'eux a changé ailleurs. */
  supprimer(ids: string[], restaurer?: boolean, versions?: Record<string, number>): Promise<{ versions?: Record<string, number> }>;
  lier(source: string, cible: string, libelle: string, style: StyleLien): Promise<string>;
  modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }, version?: number): Promise<{ version?: number }>;
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
  /** « Faire relire » : demande suivie côté serveur (file lisible par le chef). Aucun agent n'est lancé. */
  relecture(objetId: string, action: "demander" | "annuler" | "rendre", options?: { verdict?: "pret" | "corrections"; avis?: string }): Promise<Relecture>;
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
  constructor(public readonly espace = "accueil") {}
  async espaces() {
    return (await json<{ espaces: EspaceBoard[] }>("/api/v2/espaces")).espaces;
  }
  regler(valeurs: Partial<ReglagesBoard>) {
    return poster<ReglagesBoard>("/api/v2/reglages", valeurs);
  }
  charger() {
    return json<EtatBoard>(`/api/v2/board?espace=${encodeURIComponent(this.espace)}`);
  }
  async creer(o: NouvelObjet) {
    const r = await poster<{ objet_id: string }>("/api/v2/objets", { ...o, espace: this.espace });
    return r.objet_id;
  }
  lire(demande: { objets?: string[]; liens?: string[] }) {
    const p = new URLSearchParams({ espace: this.espace });
    if (demande.objets?.length) p.set("ids", demande.objets.join(","));
    if (demande.liens?.length) p.set("liens", demande.liens.join(","));
    return json<DeltaBoard>(`/api/v2/objets?${p}`);
  }
  async historique(dernier: number) {
    return (await json<{ evenements: Evenement[] }>(`/api/evenements?dernier=${dernier}&espace=${encodeURIComponent(this.espace)}`)).evenements;
  }
  async modifier(mods: Modification[]) {
    const r = await poster<{ resultats: { id: string; ok: boolean; erreur?: string; code?: string; version?: number }[] }>(
      "/api/v2/objets/lot", { modifications: mods });
    return r.resultats;
  }
  supprimer(ids: string[], restaurer = false, versions?: Record<string, number>) {
    return poster<{ versions?: Record<string, number> }>("/api/v2/objets/supprimer", { ids, restaurer, ...(versions ? { versions } : {}) });
  }
  async lier(source: string, cible: string, libelle: string, style: StyleLien) {
    const r = await poster<{ id: string }>("/api/v2/liens", { source_id: source, cible_id: cible, libelle, style, espace: this.espace });
    return r.id;
  }
  modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }, version?: number) {
    return poster<{ version?: number }>(`/api/v2/liens/${id}`, version === undefined ? champs : { ...champs, version });
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
  relecture(objetId: string, action: "demander" | "annuler" | "rendre", options: { verdict?: "pret" | "corrections"; avis?: string } = {}) {
    return poster<Relecture>(`/api/v2/objets/${objetId}/relecture`, { action, ...options });
  }
  deciderProposition(objetId: string, index: number, decision: "lancer" | "ecarter") {
    return poster<{ carte_id?: string }>(`/api/v2/objets/${objetId}/propositions`, { index, decision });
  }
}

/** Démo en mémoire : chaque modification vit le temps de l'onglet. */
export class SourceDemo implements Source {
  demo = true;
  espace = "Refonte de l'accueil";
  private reglagesDemo: ReglagesBoard = { auto_analyse: true, actions_auto: true };
  async espaces() {
    return [{ nom: this.espace, objets: this.etat.objets.length, projet: true, description: "Démonstration" }];
  }
  async regler(valeurs: Partial<ReglagesBoard>) {
    this.reglagesDemo = { ...this.reglagesDemo, ...valeurs };
    return this.reglagesDemo;
  }
  private etat: EtatBoard = fixtureDemo();
  private compteur = 0;
  private commentairesDemo = new Map<string, { id: string; auteur: string; texte: string; cree: number }[]>();
  private id(p: string) {
    this.compteur += 1;
    return `${p}-demo${String(this.compteur).padStart(7, "0")}`;
  }
  /** Le résumé des relations est calculé ici comme le fait le serveur (relations/effets.ts) : la démo n'a pas de serveur. */
  private avecRelations(objets: ObjetBoard[]): ObjetBoard[] {
    const resumes = calculerRelations(this.etat.objets, this.etat.liens);
    return objets.map((o) => {
      const { relations: _r, relecture: _l, ...reste } = o;
      const relations = resumes.get(o.id), relecture = this.relecturesDemo.get(o.id);
      return { ...reste, ...(relations ? { relations } : {}), ...(relecture ? { relecture } : {}) };
    });
  }
  private relecturesDemo = new Map<string, Relecture>();
  async charger() {
    return structuredClone({ ...this.etat, objets: this.avecRelations(this.etat.objets) });
  }
  async lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard> {
    const ids = new Set(demande.objets ?? []), idsLiens = new Set(demande.liens ?? []);
    const objets = this.avecRelations(this.etat.objets.filter((o) => ids.has(o.id)));
    const liens = this.etat.liens.filter((l) => idsLiens.has(l.id) || ids.has(l.source_id) || ids.has(l.cible_id));
    return structuredClone({
      espace: this.espace, objets, liens, reglages: this.reglagesDemo,
      absents: { objets: [...ids].filter((id) => !objets.some((o) => o.id === id)), liens: [...idsLiens].filter((id) => !liens.some((l) => l.id === id)) },
    });
  }
  async historique() {
    return [];
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
      return {};
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
    return {};
  }
  private refuserBoucle(source: string, cible: string, sauf?: string) {
    const boucle = creeraitBoucle(this.etat.liens, source, cible, sauf);
    if (!boucle) return;
    const nom = (id: string) => `« ${(this.etat.objets.find((o) => o.id === id)?.meta.titre ?? id)} »`;
    throw new ErreurApi(`dépendance refusée : elle fermerait une boucle (${boucle.map(nom).join(" → ")})`, 409);
  }
  async lier(source: string, cible: string, libelle: string, style: StyleLien) {
    if (style === "depend") this.refuserBoucle(source, cible);
    const id = this.id("BL");
    this.etat.liens.push({ id, source_id: source, cible_id: cible, libelle, style, version: 1 });
    return id;
  }
  async modifierLien(id: string, champs: { libelle?: string; style?: StyleLien; supprime?: boolean }) {
    const l = this.etat.liens.find((x) => x.id === id) ?? this.liensSupprimes.get(id);
    if (!l) return {};
    if ((champs.style ?? l.style) === "depend" && champs.supprime !== true && (l.style !== "depend" || this.liensSupprimes.has(id))) {
      this.refuserBoucle(l.source_id, l.cible_id, id);
    }
    if (champs.libelle !== undefined) l.libelle = champs.libelle;
    if (champs.style !== undefined) l.style = champs.style;
    if (champs.supprime === true) {
      this.etat.liens = this.etat.liens.filter((x) => x.id !== id);
      this.liensSupprimes.set(id, l);
    } else if (champs.supprime === false && this.liensSupprimes.has(id)) {
      this.liensSupprimes.delete(id);
      this.etat.liens.push(l);
    }
    return {};
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
  async relecture(objetId: string, action: "demander" | "annuler" | "rendre", options: { verdict?: "pret" | "corrections"; avis?: string } = {}) {
    const maintenant = Date.now() / 1000;
    const ouverte = this.relecturesDemo.get(objetId);
    if (action === "demander") {
      if (ouverte?.statut === "demandee") return ouverte;
      const r: Relecture = { id: this.id("RL"), objet_id: objetId, espace: this.espace, statut: "demandee", demande_par: "vous (démo)", note: "",
        verdict: "", avis: "", rendu_par: "", cree: maintenant, maj: maintenant };
      this.relecturesDemo.set(objetId, r);
      return r;
    }
    if (ouverte?.statut !== "demandee") throw new ErreurApi("aucune demande de relecture ouverte", 404);
    const r: Relecture = { ...ouverte, statut: action === "annuler" ? "annulee" : "rendue", verdict: action === "rendre" ? options.verdict ?? "pret" : "",
      avis: options.avis ?? "", rendu_par: "vous (démo)", maj: maintenant };
    this.relecturesDemo.set(objetId, r);
    return r;
  }
  async contextualiser(objetId: string) {
    // même refus que le serveur : une carte bloquée par une dépendance ne se lance pas
    const blocage = phraseBlocage(calculerRelations(this.etat.objets, this.etat.liens).get(objetId));
    if (blocage) throw new ErreurApi(`carte ${blocage.charAt(0).toLowerCase()}${blocage.slice(1)} : termine d'abord ce dont elle dépend`, 409);
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
