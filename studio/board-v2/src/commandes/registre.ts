// Registre unique des commandes du Board. Tout ce qui déclenche une action (bouton, raccourci, menu contextuel,
// barre flottante, palette) appelle `executer(id, contexte, origine)` : la disponibilité est revérifiée, le niveau
// « sensible » demande confirmation, l'exécution est journalisée, et l'annulation est branchée sur l'historique.
import { Historique } from "./historique";
import { JournalUsage } from "./journal";
import { deEvenement, normaliser, type ToucheClavier } from "./raccourcis";
import { libelleDe, raccourcisDe, type Commande, type Emplacement, type Origine } from "./types";

export type Issue = "fait" | "indisponible" | "inconnue" | "refuse" | "erreur";

export interface OptionsRegistre<C> {
  journal?: JournalUsage;
  historique?: Historique;
  /** confirmation d'une commande sensible ; défaut : refus (jamais d'action sensible sans réponse explicite) */
  confirmer?(texte: string, commande: Commande<C>): boolean | Promise<boolean>;
  surErreur?(erreur: unknown, commande: Commande<C>): void;
}

export class Registre<C> {
  private commandes = new Map<string, Commande<C>>();
  private parRaccourci = new Map<string, string[]>();
  readonly journal: JournalUsage;
  readonly historique: Historique;

  constructor(private options: OptionsRegistre<C> = {}) {
    this.journal = options.journal ?? new JournalUsage(null);
    this.historique = options.historique ?? new Historique();
  }

  /** Déclare des commandes. Un identifiant ou un raccourci en double est une erreur de programmation : refusé net. */
  declarer(commandes: readonly Commande<C>[]): this {
    for (const c of commandes) {
      if (this.commandes.has(c.id)) throw new Error(`commande déclarée deux fois : ${c.id}`);
      this.commandes.set(c.id, c);
      for (const r of raccourcisDe(c)) {
        const cle = normaliser(r);
        this.parRaccourci.set(cle, [...(this.parRaccourci.get(cle) ?? []), c.id]);
      }
    }
    return this;
  }

  obtenir(id: string): Commande<C> | undefined {
    return this.commandes.get(id);
  }

  toutes(): Commande<C>[] {
    return [...this.commandes.values()];
  }

  disponible(id: string, contexte: C): boolean {
    const c = this.commandes.get(id);
    return Boolean(c) && (c!.disponible?.(contexte) ?? true);
  }

  /** Commandes disponibles dans ce contexte, dans l'ordre de déclaration ; `emplacement` restreint (menu, barre flottante). */
  disponibles(contexte: C, emplacement?: Emplacement): Commande<C>[] {
    return this.toutes().filter((c) => (!emplacement || emplacement === "palette" || c.emplacements?.includes(emplacement))
      && (c.disponible?.(contexte) ?? true));
  }

  /** Commande à exécuter pour cette frappe : la première DISPONIBLE parmi celles qui partagent le raccourci
   *  (« Échap » ferme la présentation si elle est ouverte, sinon désélectionne). */
  pourTouche(e: ToucheClavier, contexte: C): Commande<C> | undefined {
    const cle = deEvenement(e);
    if (!cle) return undefined;
    for (const id of this.parRaccourci.get(cle) ?? []) {
      if (this.disponible(id, contexte)) return this.commandes.get(id);
    }
    return undefined;
  }

  /** Raccourcis déclarés par plusieurs commandes (voulu seulement si leurs disponibilités s'excluent) : pour les tests. */
  raccourcisPartages(): [string, string[]][] {
    return [...this.parRaccourci.entries()].filter(([, ids]) => ids.length > 1);
  }

  async executer(id: string, contexte: C, origine: Origine = "programme"): Promise<Issue> {
    const c = this.commandes.get(id);
    if (!c) return "inconnue";
    if (!(c.disponible?.(contexte) ?? true)) return "indisponible";
    // une commande sensible demande toujours confirmation ; les autres seulement si elles le déclarent pour ce contexte
    const texte = c.confirmation?.(contexte) ?? (c.niveau === "sensible" ? `${libelleDe(c, contexte)} ?` : null);
    if (texte && !(await (this.options.confirmer?.(texte, c) ?? false))) return "refuse";
    this.journal.noter(id, origine);
    const avant = this.historique.marque;
    this.historique.marque = id;
    try {
      const r = c.executer(contexte);
      await r;
      if (c.annuler) {
        this.historique.ajouter({
          libelle: libelleDe(c, contexte), commande: id,
          annuler: async () => { await c.annuler!(contexte); },
          refaire: async () => { await c.executer(contexte); },
        });
      }
      return "fait";
    } catch (x) {
      this.options.surErreur?.(x, c);
      return "erreur";
    } finally {
      this.historique.marque = avant;
    }
  }

  /** Annule le dernier geste ; l'annulation est comptée dans le journal de la commande d'origine. */
  async annuler() {
    const r = await this.historique.annuler();
    if (r?.ok && r.commande) this.journal.noterAnnulation(r.commande);
    return r;
  }

  refaire() {
    return this.historique.refaire();
  }
}
