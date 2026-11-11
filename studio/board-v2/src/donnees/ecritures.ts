// File d'écritures optimistes du Board.
//
// Chaque écriture est appliquée tout de suite à l'écran (surcouche du store), puis envoyée au serveur AVEC la
// version connue de l'objet. Les envois sont faits un par un, dans l'ordre : la version d'une écriture est lue au
// moment de son envoi, donc deux gestes rapides sur la même carte s'enchaînent sans se marcher dessus.
//
// Conflit (409 : la carte a changé ailleurs) : on relit la carte. Si les champs que l'on voulait changer n'ont pas
// bougé côté serveur (quelqu'un a modifié AUTRE CHOSE), l'écriture est rejouée une fois sur la nouvelle version.
// Sinon elle est annulée : la carte reprend l'état du serveur et l'utilisateur est prévenu. Jamais d'écrasement.
import type { DeltaBoard } from "../types";
import { CLES_CHEF, egal, type ChampsLien, type ChampsObjet, type StoreBoard } from "./store";

export interface ModificationVersionnee {
  id: string;
  champs: ChampsObjet;
  version?: number;
}
export interface ResultatModification {
  id: string;
  ok: boolean;
  erreur?: string;
  /** « conflit » : version périmée */
  code?: string;
  version?: number;
}
/** Ce dont la file a besoin de la source de données (SourceReelle, SourceDemo, ou un double de test). */
export interface SourceEcritures {
  modifier(mods: ModificationVersionnee[]): Promise<ResultatModification[]>;
  supprimer(ids: string[], restaurer?: boolean, versions?: Record<string, number>): Promise<{ versions?: Record<string, number> }>;
  modifierLien(id: string, champs: ChampsLien, version?: number): Promise<{ version?: number }>;
  lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard>;
}
export interface Rappels {
  /** écriture annulée parce que l'élément a changé ailleurs */
  conflit?(ids: string[]): void;
  /** écriture refusée pour une autre raison (verrou, validation, réseau) */
  erreur?(message: string): void;
}

export function estConflit(x: unknown): boolean {
  return typeof x === "object" && x !== null && (x as { statut?: number }).statut === 409;
}
const message = (x: unknown) => (x instanceof Error ? x.message : "écriture impossible");

/** Compare une valeur du serveur à celle que l'utilisateur avait sous les yeux (meta : hors clés du chef). */
function inchange(cle: string, serveur: unknown, base: unknown): boolean {
  if (cle === "verrouille") return Boolean(serveur) === Boolean(base);
  if (cle === "meta" && serveur && base && typeof serveur === "object" && typeof base === "object") {
    const sans = (m: object) => Object.fromEntries(Object.entries(m).filter(([k]) => !(CLES_CHEF as readonly string[]).includes(k)).sort(([a], [b]) => (a < b ? -1 : 1)));
    return egal(sans(serveur), sans(base));
  }
  return egal(serveur ?? null, base ?? null);
}

interface Attente {
  cle: number;
  id: string;
  champs: ChampsObjet;
  /** valeurs affichées au moment du geste, pour chaque champ modifié */
  base: Record<string, unknown>;
}

export class FileEcritures {
  private chaine: Promise<unknown> = Promise.resolve();

  constructor(private source: SourceEcritures, private store: StoreBoard, private rappels: Rappels = {}) {}

  private enchainer<T>(f: () => Promise<T>): Promise<T> {
    const suite = this.chaine.then(f, f);
    this.chaine = suite.catch(() => undefined);
    return suite;
  }

  /** Résolue quand toutes les écritures déjà demandées ont reçu leur réponse. */
  repos(): Promise<void> {
    return this.chaine.then(() => undefined);
  }

  /* ------------------------------------------------------------ objets ----------------------------------- */
  /** Modifie des objets : visible tout de suite, envoyé avec les versions, annulé si le serveur refuse. */
  modifier(mods: { id: string; champs: ChampsObjet }[]): Promise<ResultatModification[]> {
    const attentes: Attente[] = [];
    const inconnus: ResultatModification[] = [];
    for (const m of mods) {
      const vu = this.store.objet(m.id) as unknown as Record<string, unknown> | undefined;
      if (!vu) {
        inconnus.push({ id: m.id, ok: false, erreur: "objet inconnu" });
        continue;
      }
      const base: Record<string, unknown> = {};
      for (const k of Object.keys(m.champs)) base[k] = vu[k];
      attentes.push({ cle: this.store.ajouterSurcouche({ sorte: "objet", id: m.id, champs: m.champs }), id: m.id, champs: m.champs, base });
    }
    if (!attentes.length) return Promise.resolve(inconnus);
    return this.enchainer(async () => [...inconnus, ...(await this.envoyer(attentes, true))]);
  }

  private async envoyer(attentes: Attente[], rejouable: boolean): Promise<ResultatModification[]> {
    let resultats: ResultatModification[];
    try {
      resultats = await this.source.modifier(attentes.map((a) => ({ id: a.id, champs: a.champs, version: this.store.objetServeur(a.id)?.version })));
    } catch (x) {
      for (const a of attentes) this.store.retirerSurcouche(a.cle);
      this.rappels.erreur?.(message(x));
      return attentes.map((a) => ({ id: a.id, ok: false, erreur: message(x) }));
    }
    const sortie: ResultatModification[] = [];
    const conflits: Attente[] = [];
    let premiereErreur = "";
    attentes.forEach((a, i) => {
      const r = resultats[i] ?? { id: a.id, ok: false, erreur: "réponse incomplète" };
      if (r.ok) {
        this.store.confirmerObjet(a.id, a.champs, r.version ?? (this.store.objetServeur(a.id)?.version ?? 0) + 1);
        this.store.retirerSurcouche(a.cle);
        sortie.push(r);
      } else if (r.code === "conflit") {
        conflits.push(a);
      } else {
        this.store.retirerSurcouche(a.cle);
        premiereErreur ||= r.erreur ?? "erreur";
        sortie.push(r);
      }
    });
    if (premiereErreur) this.rappels.erreur?.(premiereErreur);
    if (conflits.length) sortie.push(...(await this.resoudre(conflits, rejouable)));
    return sortie;
  }

  /** Conflit de version : relire, rejouer ce qui ne heurte rien, annuler le reste. */
  private async resoudre(conflits: Attente[], rejouable: boolean): Promise<ResultatModification[]> {
    const ids = conflits.map((a) => a.id);
    try {
      const jalon = this.store.jalon();
      this.store.appliquerDelta(await this.source.lire({ objets: ids }), { objets: ids }, jalon);
    } catch {
      // relecture impossible : on annule quand même, le flux ou le prochain chargement remettra l'état exact
    }
    const rejouer: Attente[] = [];
    const perdus: Attente[] = [];
    for (const a of conflits) {
      const serveur = this.store.objetServeur(a.id) as unknown as Record<string, unknown> | undefined;
      if (rejouable && serveur && Object.keys(a.champs).every((k) => inchange(k, serveur[k], a.base[k]))) rejouer.push(a);
      else perdus.push(a);
    }
    for (const a of perdus) this.store.retirerSurcouche(a.cle);
    if (perdus.length) this.rappels.conflit?.(perdus.map((a) => a.id));
    const sortie: ResultatModification[] = perdus.map((a) => ({ id: a.id, ok: false, code: "conflit", erreur: "modifié ailleurs" }));
    if (rejouer.length) sortie.push(...(await this.envoyer(rejouer, false)));
    return sortie;
  }

  /** Suppression douce : les cartes disparaissent tout de suite ; refus (carte modifiée ailleurs) = elles reviennent. */
  supprimer(ids: string[]): Promise<boolean> {
    const visibles = ids.filter((id) => this.store.objet(id));
    const cle = visibles.length ? this.store.ajouterSurcouche({ sorte: "suppression", ids: visibles }) : 0;
    return this.enchainer(async () => {
      // présence relue à l'envoi : une restauration encore en file (annuler puis rétablir) a pu ramener ces cartes
      const presents = ids.filter((id) => this.store.objetServeur(id));
      if (!presents.length) {
        this.store.retirerSurcouche(cle);
        return false;
      }
      const versions: Record<string, number> = {};
      for (const id of presents) {
        const o = this.store.objetServeur(id);
        if (o) versions[id] = o.version;
      }
      try {
        await this.source.supprimer(presents, false, versions);
        this.store.retirerObjets(presents);
        this.store.retirerSurcouche(cle);
        return true;
      } catch (x) {
        if (estConflit(x)) {
          await this.relire({ objets: presents });
          this.rappels.conflit?.(presents);
        } else {
          this.rappels.erreur?.(message(x));
        }
        this.store.retirerSurcouche(cle);
        return false;
      }
    });
  }

  /** Restauration (annuler une suppression) : le serveur fait foi, les cartes et leurs relations sont relues. */
  restaurer(ids: string[]): Promise<boolean> {
    return this.enchainer(async () => {
      try {
        await this.source.supprimer(ids, true);
        await this.relire({ objets: ids });
        return true;
      } catch (x) {
        this.rappels.erreur?.(message(x));
        return false;
      }
    });
  }

  /* ------------------------------------------------------------ relations -------------------------------- */
  modifierLien(id: string, champs: ChampsLien): Promise<boolean> {
    const cle = this.store.lienServeur(id) ? this.store.ajouterSurcouche({ sorte: "lien", id, champs }) : 0;
    return this.enchainer(async () => {
      try {
        // état relu à l'envoi : une suppression encore en file a pu retirer la relation entre-temps
        const r = await this.source.modifierLien(id, champs, this.store.lienServeur(id)?.version);
        if (champs.supprime !== false && this.store.lienServeur(id)) this.store.confirmerLien(id, champs, r.version);
        else if (champs.supprime !== true) await this.relire({ liens: [id] });  // relation restaurée : absente du store
        return true;
      } catch (x) {
        if (estConflit(x)) {
          await this.relire({ liens: [id] });
          this.rappels.conflit?.([id]);
        } else {
          this.rappels.erreur?.(message(x));
        }
        return false;
      } finally {
        if (cle) this.store.retirerSurcouche(cle);
      }
    });
  }

  private async relire(demande: { objets?: string[]; liens?: string[] }): Promise<void> {
    try {
      const jalon = this.store.jalon();
      this.store.appliquerDelta(await this.source.lire(demande), demande, jalon);
    } catch {
      // le flux ou le prochain chargement rétablira l'état
    }
  }
}
