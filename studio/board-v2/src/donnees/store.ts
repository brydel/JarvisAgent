// Store normalisé du Board : objets et relations rangés par identifiant.
//
// Deux couches, jamais mélangées :
// - l'état SERVEUR (dernière vérité reçue : chargement complet, lecture ciblée, réponse d'une écriture) ;
// - les SURCOUCHES : écritures optimistes encore en attente de réponse, appliquées par-dessus dans l'ordre.
// La vue (ce que le canevas affiche) = serveur ⊕ surcouches. Annuler une écriture refusée revient à retirer sa
// surcouche ; une mise à jour distante reçue pendant un glisser ne détruit pas le geste en cours.
//
// Aucune dépendance à React ni au réseau : testé seul (store.test.ts).
import type { DeltaBoard, EtatBoard, LienBoard, ObjetBoard } from "../types";

/** Champs d'un objet modifiables par le client (miroir de CHAMPS_MAJ dans lib/jarvis/board.py). */
export type ChampsObjet = Partial<Pick<ObjetBoard, "x" | "y" | "largeur" | "hauteur" | "z" | "priorite" | "meta" | "contenu" | "parent_id">> & {
  verrouille?: boolean;
};
export type ChampsLien = { libelle?: string; style?: LienBoard["style"]; supprime?: boolean };

export type Surcouche =
  | { sorte: "objet"; id: string; champs: ChampsObjet }
  | { sorte: "suppression"; ids: string[] }
  | { sorte: "lien"; id: string; champs: ChampsLien };

export interface Instantane {
  objets: ObjetBoard[];
  liens: LienBoard[];
}

/** Clés de meta écrites par le moteur seul : le serveur les conserve quoi qu'envoie un client (CLES_CHEF). */
export const CLES_CHEF = ["jarvis_resume", "propositions", "jarvis_mission"] as const;

export function egal(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/** Applique des champs modifiés à un objet, comme le ferait le serveur (verrouille en 0/1, clés du chef gardées). */
export function appliquerChamps(o: ObjetBoard, champs: ChampsObjet): ObjetBoard {
  const { verrouille, meta, ...reste } = champs;
  const suivant: ObjetBoard = { ...o, ...reste };
  if (verrouille !== undefined) suivant.verrouille = verrouille ? 1 : 0;
  if (meta !== undefined) {
    const garde: Record<string, unknown> = {};
    for (const k of CLES_CHEF) if (k in o.meta) garde[k] = o.meta[k];
    suivant.meta = { ...meta, ...garde };
  }
  return suivant;
}

const ordreObjets = (a: ObjetBoard, b: ObjetBoard) => a.z - b.z || a.cree - b.cree || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

export class StoreBoard {
  private objetsServeur = new Map<string, ObjetBoard>();
  private liensServeur = new Map<string, LienBoard>();
  private surcouches = new Map<number, Surcouche>();
  private prochaineCle = 1;
  /** vues composées, recalculées seulement pour les identifiants touchés (identité stable sinon) */
  private vues = new Map<string, ObjetBoard>();
  private instantane: Instantane | null = null;
  private abonnes = new Set<() => void>();
  /** horloge locale : ordonne les retraits par rapport aux lectures lancées avant eux (voir `jalon`) */
  private horloge = 0;
  private tombes = new Map<string, number>();

  /* ------------------------------------------------------------ abonnement (useSyncExternalStore) ------- */
  abonner = (f: () => void): (() => void) => {
    this.abonnes.add(f);
    return () => this.abonnes.delete(f);
  };

  lire = (): Instantane => {
    if (!this.instantane) {
      const caches = this.idsMasques();
      const objets = [...this.objetsServeur.keys()].filter((id) => !caches.has(id)).map((id) => this.vue(id)!).sort(ordreObjets);
      const liens: LienBoard[] = [];
      for (const l of this.liensServeur.values()) {
        const v = this.vueLien(l);
        // une relation n'est montrée que si ses deux cartes sont là (jamais de trait vers une carte retirée)
        if (v && !caches.has(v.source_id) && !caches.has(v.cible_id) && this.objetsServeur.has(v.source_id) && this.objetsServeur.has(v.cible_id)) liens.push(v);
      }
      this.instantane = { objets, liens };
    }
    return this.instantane;
  };

  private publier(ids?: Iterable<string>) {
    if (ids) for (const id of ids) this.vues.delete(id);
    else this.vues.clear();
    this.instantane = null;
    for (const f of this.abonnes) f();
  }

  /* ------------------------------------------------------------ lecture ---------------------------------- */
  /** Objet tel qu'affiché (écritures en attente comprises) ; undefined s'il est absent ou en cours de suppression. */
  objet(id: string): ObjetBoard | undefined {
    return this.idsMasques().has(id) ? undefined : this.vue(id);
  }

  /** Dernière version connue du serveur, sans les écritures en attente. */
  objetServeur(id: string): ObjetBoard | undefined {
    return this.objetsServeur.get(id);
  }

  lienServeur(id: string): LienBoard | undefined {
    return this.liensServeur.get(id);
  }

  objetsDeMission(missionId: string): string[] {
    const ids: string[] = [];
    for (const o of this.objetsServeur.values()) if (o.mission_id === missionId) ids.push(o.id);
    return ids;
  }

  get taille(): number {
    return this.objetsServeur.size;
  }

  enAttente(): number {
    return this.surcouches.size;
  }

  private vue(id: string): ObjetBoard | undefined {
    const base = this.objetsServeur.get(id);
    if (!base) return undefined;
    let v = this.vues.get(id);
    if (!v) {
      v = base;
      for (const s of this.surcouches.values()) if (s.sorte === "objet" && s.id === id) v = appliquerChamps(v, s.champs);
      this.vues.set(id, v);
    }
    return v;
  }

  private vueLien(l: LienBoard): LienBoard | undefined {
    let v: LienBoard | undefined = l;
    for (const s of this.surcouches.values()) {
      if (s.sorte !== "lien" || s.id !== l.id || !v) continue;
      if (s.champs.supprime) return undefined;
      const { supprime: _s, ...reste } = s.champs;
      if (Object.keys(reste).length) v = { ...v, ...reste };
    }
    return v;
  }

  private idsMasques(): Set<string> {
    const ids = new Set<string>();
    for (const s of this.surcouches.values()) if (s.sorte === "suppression") for (const id of s.ids) ids.add(id);
    return ids;
  }

  /* ------------------------------------------------------------ état serveur ----------------------------- */
  /** À prendre AVANT de lancer une lecture : elle n'effacera pas ce qui a été retiré ou confirmé depuis. */
  jalon(): number {
    return this.horloge;
  }

  private accepter(o: ObjetBoard, jalon: number): boolean {
    if ((this.tombes.get(o.id) ?? -1) > jalon) return false;  // retiré après le départ de cette lecture
    const local = this.objetsServeur.get(o.id);
    if (local && local.version > o.version) return false;      // réponse plus ancienne que ce qu'on sait déjà
    if (local && egal(local, o)) return false;                 // rien de neuf : la référence (et le nœud) restent
    this.objetsServeur.set(o.id, o);
    this.tombes.delete(o.id);
    return true;
  }

  private accepterLien(l: LienBoard, jalon: number): boolean {
    if (Math.max(this.tombes.get(l.id) ?? -1, this.tombes.get(l.source_id) ?? -1, this.tombes.get(l.cible_id) ?? -1) > jalon) return false;
    const local = this.liensServeur.get(l.id);
    if (local && (local.version ?? 0) > (l.version ?? 0)) return false;
    if (local && egal(local, l)) return false;
    this.liensServeur.set(l.id, l);
    this.tombes.delete(l.id);
    return true;
  }

  /** Chargement complet : remplace l'état serveur. Les écritures en attente restent appliquées par-dessus. */
  remplacer(etat: EtatBoard, jalon = this.horloge): void {
    const vus = new Set<string>();
    for (const o of etat.objets) {
      vus.add(o.id);
      this.accepter(o, jalon);
    }
    for (const id of [...this.objetsServeur.keys()]) if (!vus.has(id)) this.objetsServeur.delete(id);
    const liensVus = new Set<string>();
    for (const l of etat.liens) {
      liensVus.add(l.id);
      this.accepterLien(l, jalon);
    }
    for (const id of [...this.liensServeur.keys()]) if (!liensVus.has(id)) this.liensServeur.delete(id);
    this.publier();
  }

  /** Lecture ciblée. Pour chaque objet demandé, la réponse fait foi : objet absent = retiré ; les relations qui le
   *  touchent sont exactement celles renvoyées. Renvoie vrai si quelque chose a changé. */
  appliquerDelta(delta: DeltaBoard, demande: { objets?: string[]; liens?: string[] }, jalon = this.horloge): boolean {
    let change = false;
    const touches = new Set<string>();
    const recus = new Set(delta.objets.map((o) => o.id));
    for (const o of delta.objets) {
      if (this.accepter(o, jalon)) {
        change = true;
        touches.add(o.id);
      }
    }
    for (const id of delta.absents.objets) {
      if (this.objetsServeur.delete(id)) {
        change = true;
        touches.add(id);
      }
    }
    const liensRecus = new Set(delta.liens.map((l) => l.id));
    for (const l of delta.liens) if (this.accepterLien(l, jalon)) change = true;
    const demandes = new Set(demande.objets ?? []);
    const absents = new Set(delta.absents.objets);
    for (const l of [...this.liensServeur.values()]) {
      if (liensRecus.has(l.id) || (this.tombes.get(l.id) ?? -1) > jalon) continue;
      const touche = (id: string) => demandes.has(id) && (recus.has(id) || absents.has(id));
      if (touche(l.source_id) || touche(l.cible_id)) {
        this.liensServeur.delete(l.id);
        change = true;
      }
    }
    for (const id of delta.absents.liens) if (this.liensServeur.delete(id)) change = true;
    if (change) this.publier(touches);
    return change;
  }

  /** Retrait confirmé (réponse d'une suppression, événement distant) : objets et relations qui les touchent. */
  retirerObjets(ids: string[]): void {
    const cible = new Set(ids);
    let change = false;
    for (const id of ids) {
      this.tombes.set(id, ++this.horloge);
      if (this.objetsServeur.delete(id)) change = true;
    }
    for (const l of [...this.liensServeur.values()]) {
      if (cible.has(l.source_id) || cible.has(l.cible_id)) {
        this.liensServeur.delete(l.id);
        change = true;
      }
    }
    if (change) this.publier(ids);
  }

  retirerLiens(ids: string[]): void {
    let change = false;
    for (const id of ids) {
      this.tombes.set(id, ++this.horloge);
      if (this.liensServeur.delete(id)) change = true;
    }
    if (change) this.publier([]);
  }

  /** Écriture acceptée par le serveur : les champs envoyés et la nouvelle version entrent dans l'état serveur. */
  confirmerObjet(id: string, champs: ChampsObjet, version: number): void {
    const o = this.objetsServeur.get(id);
    if (!o || o.version >= version) return;
    this.objetsServeur.set(id, { ...appliquerChamps(o, champs), version });
    ++this.horloge;
    this.publier([id]);
  }

  confirmerLien(id: string, champs: ChampsLien, version?: number): void {
    const l = this.liensServeur.get(id);
    if (!l) return;
    if (champs.supprime) {
      this.retirerLiens([id]);
      return;
    }
    const { supprime: _s, ...reste } = champs;
    this.liensServeur.set(id, { ...l, ...reste, version: version ?? l.version });
    ++this.horloge;
    this.publier([]);
  }

  poserLien(l: LienBoard): void {
    if (this.accepterLien(l, this.horloge)) this.publier([]);
  }

  /* ------------------------------------------------------------ surcouches optimistes -------------------- */
  ajouterSurcouche(s: Surcouche): number {
    const cle = this.prochaineCle++;
    this.surcouches.set(cle, s);
    this.publier(s.sorte === "objet" ? [s.id] : s.sorte === "suppression" ? s.ids : []);
    return cle;
  }

  retirerSurcouche(cle: number): void {
    const s = this.surcouches.get(cle);
    if (!s) return;
    this.surcouches.delete(cle);
    this.publier(s.sorte === "objet" ? [s.id] : s.sorte === "suppression" ? s.ids : []);
  }
}
