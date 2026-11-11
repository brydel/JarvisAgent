// Synchronisation incrémentale : d'un événement du flux au plus petit changement du store.
//
// `planifier` (fonction pure) décide quoi faire d'un événement : rien (autre espace, version déjà connue), retirer
// des cartes, ou relire UN objet / UN lien. `Synchroniseur` regroupe les relectures proches en une seule requête
// (GET /api/v2/objets?ids=…) et fait passer toutes les lectures — ciblées ou complètes — par une seule file : une
// réponse ancienne n'écrase donc jamais une plus récente.
import type { DeltaBoard, EtatBoard, Evenement } from "../types";
import type { StoreBoard } from "./store";

export interface Plan {
  /** objets et liens à relire */
  objets: string[];
  liens: string[];
  retirerObjets: string[];
  retirerLiens: string[];
  /** réglages du Board modifiés ailleurs */
  reglages: boolean;
  /** événement du Board impossible à cibler : relecture complète (ne devrait pas arriver) */
  complet: boolean;
}

const chaines = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

export function planifier(e: Evenement, store: StoreBoard, espace: string): Plan {
  const plan: Plan = { objets: [], liens: [], retirerObjets: [], retirerLiens: [], reglages: false, complet: false };
  const d = e.donnees ?? {};
  if (typeof d.espace === "string" && d.espace !== espace) return plan;  // un autre Board : rien à faire ici
  const version = typeof d.version === "number" ? d.version : null;
  if (e.type === "reglages_board") {
    plan.reglages = true;
  } else if (e.type === "board_supprime") {
    plan.retirerObjets = chaines(d.objets);
    // les cartes reliées à celles qui partent par une relation à effet : leur résumé calculé change
    plan.objets = store.voisinsParEffet(plan.retirerObjets).filter((id) => !plan.retirerObjets.includes(id));
  } else if (e.type === "board_restaure") {
    plan.objets = chaines(d.objets);
  } else if (e.type === "board_lien" || e.type === "board_lien_maj") {
    const id = typeof d.lien_id === "string" ? d.lien_id : "";
    const local = id ? store.lienServeur(id) : undefined;
    // notre propre écriture (version déjà connue, ou relation déjà retirée ici) : la file a relu ce qu'il fallait
    const echo = d.supprime === true ? !local : Boolean(local && version !== null && (local.version ?? 0) >= version);
    if (!id) plan.complet = true;
    else if (d.supprime === true) plan.retirerLiens = [id];
    else if (!echo) plan.liens = [id];
    // le type d'une relation a un effet : le résumé calculé de ses deux cartes change avec elle
    if (id && !echo && d.style !== "defaut" && d.style !== "utilise") {
      for (const bout of [d.source_id, d.cible_id, local?.source_id, local?.cible_id]) {
        if (typeof bout === "string" && store.objetServeur(bout) && !plan.objets.includes(bout)) plan.objets.push(bout);
      }
    }
  } else if (e.type.startsWith("board_") && e.type !== "board_fichier") {
    const ids = typeof d.objet_id === "string" ? [d.objet_id] : chaines(d.objets);
    if (!ids.length) plan.complet = true;
    for (const id of ids) {
      const local = store.objetServeur(id);
      if (!(local && version !== null && local.version >= version)) plan.objets.push(id);  // notre propre écriture : déjà à jour
    }
  }
  // l'avancement d'une mission change le résumé affiché sur ses cartes (sans changer leur version)
  if (e.mission_id) for (const id of store.objetsDeMission(e.mission_id)) if (!plan.objets.includes(id)) plan.objets.push(id);
  return plan;
}

export interface SourceLecture {
  charger(): Promise<EtatBoard>;
  lire(demande: { objets?: string[]; liens?: string[] }): Promise<DeltaBoard>;
}

export interface OptionsSynchro {
  espace: string;
  /** regroupement des relectures (ms) */
  delai?: number;
  /** identifiants par requête */
  lot?: number;
  minuterie?: { poser(f: () => void, ms: number): unknown; lever(h: unknown): void };
  /** après chaque changement appliqué au store */
  surApplique?(): void;
  surReglages?(): void;
  /** après un chargement complet réussi (curseur du journal, état brut) */
  surCharge?(etat: EtatBoard): void;
  /** lecture impossible : le message est affiché, l'état local est gardé */
  surErreur?(message: string): void;
  /** transforme l'état chargé avant de le ranger (mode démo : cartes de charge) */
  preparer?(etat: EtatBoard): EtatBoard;
}

export class Synchroniseur {
  private objets = new Set<string>();
  private liens = new Set<string>();
  private minuteur: unknown = null;
  private chaine: Promise<unknown> = Promise.resolve();
  private rechargement: Promise<void> | null = null;
  private arrete = false;
  private readonly minuterie: NonNullable<OptionsSynchro["minuterie"]>;
  /** compteurs lus par les tests et le diagnostic : combien de lectures complètes et ciblées ont eu lieu */
  readonly compteurs = { complets: 0, cibles: 0 };

  constructor(private source: SourceLecture, private store: StoreBoard, private o: OptionsSynchro) {
    this.minuterie = o.minuterie ?? { poser: (f, ms) => setTimeout(f, ms), lever: (h) => clearTimeout(h as ReturnType<typeof setTimeout>) };
  }

  demarrer(): void {
    this.arrete = false;
  }

  arreter(): void {
    this.arrete = true;
    if (this.minuteur !== null) this.minuterie.lever(this.minuteur);
    this.minuteur = null;
  }

  private enchainer<T>(f: () => Promise<T>): Promise<T> {
    const suite = this.chaine.then(f, f);
    this.chaine = suite.catch(() => undefined);
    return suite;
  }

  /** Événement reçu du flux. */
  surEvenement(e: Evenement): void {
    const plan = planifier(e, this.store, this.o.espace);
    if (plan.retirerObjets.length) {
      this.store.retirerObjets(plan.retirerObjets);
      this.o.surApplique?.();
    }
    if (plan.retirerLiens.length) this.store.retirerLiens(plan.retirerLiens);
    if (plan.reglages) this.o.surReglages?.();
    if (plan.complet) void this.recharger();
    else if (plan.objets.length || plan.liens.length) this.demander(plan.objets, plan.liens);
  }

  /** Relecture ciblée, regroupée avec celles demandées dans les `delai` ms. */
  demander(objets: string[], liens: string[] = []): void {
    for (const id of objets) this.objets.add(id);
    for (const id of liens) this.liens.add(id);
    if (this.minuteur !== null || this.arrete) return;
    this.minuteur = this.minuterie.poser(() => {
      this.minuteur = null;
      void this.vider();
    }, this.o.delai ?? 60);
  }

  /** Relecture ciblée immédiate (après une création, une décision…) ; résolue quand le store est à jour. */
  lireMaintenant(objets: string[], liens: string[] = []): Promise<void> {
    for (const id of objets) this.objets.add(id);
    for (const id of liens) this.liens.add(id);
    return this.vider();
  }

  private vider(): Promise<void> {
    return this.enchainer(async () => {
      const objets = [...this.objets], liens = [...this.liens];
      this.objets.clear();
      this.liens.clear();
      const lot = this.o.lot ?? 100;
      let change = false;
      for (let i = 0; i < Math.max(objets.length, liens.length); i += lot) {
        const demande = { objets: objets.slice(i, i + lot), liens: liens.slice(i, i + lot) };
        if (!demande.objets.length && !demande.liens.length || this.arrete) break;
        const jalon = this.store.jalon();
        try {
          this.compteurs.cibles += 1;
          change = this.store.appliquerDelta(await this.source.lire(demande), demande, jalon) || change;
        } catch {
          void this.recharger();  // lecture ciblée impossible : le chargement complet dira ce qui ne va pas
          return;
        }
      }
      if (change) this.o.surApplique?.();
    });
  }

  /** Chargement complet : au démarrage, puis seulement comme filet (trou dans le flux, reconnexion). */
  recharger(): Promise<void> {
    if (this.rechargement) return this.rechargement;  // déjà demandé, pas encore commencé : une seule lecture
    const p = this.enchainer(async () => {
      this.rechargement = null;
      if (this.arrete) return;
      const jalon = this.store.jalon();
      try {
        this.compteurs.complets += 1;
        let etat = await this.source.charger();
        if (this.arrete) return;
        if (this.o.preparer) etat = this.o.preparer(etat);
        this.store.remplacer(etat, jalon);
        this.o.surCharge?.(etat);
        this.o.surApplique?.();
      } catch (x) {
        this.o.surErreur?.(x instanceof Error ? x.message : "chargement impossible");
      }
    });
    this.rechargement = p;
    return p;
  }
}
