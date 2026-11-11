// Doubles de test de la couche de données : un faux serveur en mémoire (versions, conflits, journal) et un faux
// flux SSE. Utilisés seulement par les fichiers *.test.ts.
import type { DeltaBoard, EtatBoard, LienBoard, ObjetBoard } from "../types";
import type { ModificationVersionnee, ResultatModification, SourceEcritures } from "./ecritures";
import type { FluxNatif } from "./flux";
import { appliquerChamps, type ChampsLien } from "./store";
import type { SourceLecture } from "./synchro";

export function carte(id: string, champs: Partial<ObjetBoard> = {}): ObjetBoard {
  return {
    id, type: "note", espace: "accueil", contenu: `note ${id}`, x: 0, y: 0, largeur: 400, hauteur: 300, z: 1, priorite: "",
    meta: {}, asset_id: null, mission_id: null, parent_id: null, verrouille: 0, version: 1, cree: 1, maj: 1, ...champs,
  };
}
export function lien(id: string, source: string, cible: string, champs: Partial<LienBoard> = {}): LienBoard {
  return { id, source_id: source, cible_id: cible, libelle: "", style: "defaut", version: 1, ...champs };
}

class Erreur409 extends Error {
  statut = 409;
}

/** Faux serveur : même contrat que l'API (version exigée, 409 si périmée), compte ses appels. */
export class FauxServeur implements SourceEcritures, SourceLecture {
  objets = new Map<string, ObjetBoard>();
  liens = new Map<string, LienBoard>();
  supprimes = new Map<string, ObjetBoard>();
  liensSupprimes = new Map<string, LienBoard>();
  appels = { charger: 0, lire: 0, modifier: 0, supprimer: 0, modifierLien: 0 };
  demandes: { objets?: string[]; liens?: string[] }[] = [];
  envois: ModificationVersionnee[][] = [];
  curseur = 10;
  /** si défini, le prochain appel réseau échoue avec cette erreur */
  panne: Error | null = null;
  /** exécuté juste avant de traiter le prochain `modifier` (simule une écriture concurrente) */
  avantModifier: (() => void) | null = null;

  constructor(objets: ObjetBoard[] = [], liens: LienBoard[] = []) {
    for (const o of objets) this.objets.set(o.id, o);
    for (const l of liens) this.liens.set(l.id, l);
  }

  private tomber() {
    if (this.panne) {
      const x = this.panne;
      this.panne = null;
      throw x;
    }
  }

  /** Écriture faite « ailleurs » (autre onglet, chef) : version incrémentée. */
  ailleurs(id: string, champs: Partial<ObjetBoard>) {
    const o = this.objets.get(id)!;
    this.objets.set(id, { ...o, ...champs, version: o.version + 1 });
    this.curseur += 1;
  }

  async charger(): Promise<EtatBoard> {
    this.appels.charger += 1;
    this.tomber();
    return structuredClone({ espace: "accueil", objets: [...this.objets.values()], liens: [...this.liens.values()], curseur: this.curseur });
  }

  async lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard> {
    this.appels.lire += 1;
    this.demandes.push(demande);
    this.tomber();
    const ids = demande.objets ?? [], idsLiens = demande.liens ?? [];
    const objets = ids.map((id) => this.objets.get(id)).filter((o): o is ObjetBoard => Boolean(o));
    const liens = [...this.liens.values()].filter((l) => idsLiens.includes(l.id) || ids.includes(l.source_id) || ids.includes(l.cible_id));
    return structuredClone({
      espace: "accueil", objets, liens, curseur: this.curseur,
      absents: { objets: ids.filter((id) => !this.objets.has(id)), liens: idsLiens.filter((id) => !this.liens.has(id)) },
    });
  }

  async modifier(mods: ModificationVersionnee[]): Promise<ResultatModification[]> {
    this.appels.modifier += 1;
    this.envois.push(structuredClone(mods));
    this.tomber();
    this.avantModifier?.();
    this.avantModifier = null;
    return mods.map((m) => {
      const o = this.objets.get(m.id);
      if (!o) return { id: m.id, ok: false, erreur: "objet inconnu", code: "inconnue" };
      if (m.version !== undefined && m.version !== o.version) return { id: m.id, ok: false, erreur: "modifié ailleurs", code: "conflit" };
      if (o.verrouille && ("x" in m.champs || "y" in m.champs) && !("verrouille" in m.champs)) return { id: m.id, ok: false, erreur: "objet verrouillé", code: "verrouille" };
      const suivant = { ...appliquerChamps(o, m.champs), version: o.version + 1 };
      this.objets.set(m.id, suivant);
      this.curseur += 1;
      return { id: m.id, ok: true, version: suivant.version };
    });
  }

  async supprimer(ids: string[], restaurer = false, versions?: Record<string, number>) {
    this.appels.supprimer += 1;
    this.tomber();
    const sortie: Record<string, number> = {};
    if (restaurer) {
      for (const id of ids) {
        const o = this.supprimes.get(id);
        if (!o) continue;
        this.supprimes.delete(id);
        this.objets.set(id, { ...o, version: o.version + 1 });
        sortie[id] = o.version + 1;
      }
      return { versions: sortie };
    }
    for (const id of ids) {
      const o = this.objets.get(id);
      if (o && versions && versions[id] !== undefined && versions[id] !== o.version) throw new Erreur409("modifié ailleurs");
    }
    for (const id of ids) {
      const o = this.objets.get(id);
      if (!o) continue;
      this.objets.delete(id);
      this.supprimes.set(id, { ...o, version: o.version + 1 });
      sortie[id] = o.version + 1;
    }
    this.curseur += 1;
    return { versions: sortie };
  }

  async modifierLien(id: string, champs: ChampsLien, version?: number) {
    this.appels.modifierLien += 1;
    this.tomber();
    const l = this.liens.get(id) ?? this.liensSupprimes.get(id);  // suppression douce : le serveur garde la relation
    if (!l) throw new Error("relation inconnue");
    if (version !== undefined && version !== l.version) throw new Erreur409("relation modifiée ailleurs");
    const suivant = { ...l, ...(champs.libelle !== undefined ? { libelle: champs.libelle } : {}), ...(champs.style ? { style: champs.style } : {}), version: (l.version ?? 1) + 1 };
    const supprime = champs.supprime ?? !this.liens.has(id);
    this.liens.delete(id);
    this.liensSupprimes.delete(id);
    (supprime ? this.liensSupprimes : this.liens).set(id, suivant);
    return { version: suivant.version };
  }
}

/** Faux EventSource : les tests poussent eux-mêmes messages, erreurs et ouvertures. */
export class FauxFlux implements FluxNatif {
  readyState = 0;
  onopen: ((e: unknown) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  ferme = false;
  private ecouteurs = new Map<string, ((e: { data: string }) => void)[]>();
  constructor(public url: string) {}
  addEventListener(type: string, f: (e: { data: string }) => void) {
    this.ecouteurs.set(type, [...(this.ecouteurs.get(type) ?? []), f]);
  }
  close() {
    this.ferme = true;
    this.readyState = 2;
  }
  ouvrir() {
    this.readyState = 1;
    this.onopen?.({});
  }
  pousser(type: string, donnees: unknown) {
    for (const f of this.ecouteurs.get(type) ?? []) f({ data: JSON.stringify(donnees) });
  }
  /** `definitif` : connexion fermée pour de bon (le navigateur ne réessaiera pas) */
  echouer(definitif: boolean) {
    this.readyState = definitif ? 2 : 0;
    this.onerror?.({});
  }
}

/** Minuterie manuelle : les tests décident quand le temps passe. */
export class Horloge {
  private taches: { f: () => void; a: number; h: number }[] = [];
  private maintenant = 0;
  private n = 0;
  poser = (f: () => void, ms: number) => {
    const h = ++this.n;
    this.taches.push({ f, a: this.maintenant + ms, h });
    return h;
  };
  lever = (h: unknown) => {
    this.taches = this.taches.filter((t) => t.h !== h);
  };
  avancer(ms: number) {
    this.maintenant += ms;
    const dues = this.taches.filter((t) => t.a <= this.maintenant).sort((a, b) => a.a - b.a);
    this.taches = this.taches.filter((t) => t.a > this.maintenant);
    for (const t of dues) t.f();
  }
  get enAttente() {
    return this.taches.map((t) => t.a - this.maintenant);
  }
}

/** Laisse passer les promesses en attente. */
export const souffler = async (tours = 6) => {
  for (let i = 0; i < tours; i++) await Promise.resolve();
};
