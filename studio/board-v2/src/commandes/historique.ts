// Annuler / rétablir : une pile de commandes INVERSES. Chaque geste qui écrit dans le Board dépose une entrée
// { annuler, refaire } dont les deux faces passent par la file d'écritures optimistes (src/donnees/ecritures.ts) :
// l'annulation est donc durable, versionnée, et refusée proprement si la carte a changé ailleurs (conflit 409).
//
// Garanties :
// - une opération à la fois : dix Ctrl+Z rapides s'exécutent dans l'ordre, jamais entrelacés ;
// - un geste composé (dupliquer cinq cartes, grouper dans un dossier) = UNE entrée (`grouper`) ;
// - une annulation refusée par le serveur (`false`) est retirée de la pile : elle n'écrase rien et ne bloque pas
//   les suivantes ; l'appelant le sait (`ok: false`) et le dit à l'utilisateur ;
// - une entrée dont l'écriture d'origine a été refusée se retire (`retirer`) : rien à annuler.
// Aucune dépendance à React ni au réseau : testé seul (historique.test.ts).

export interface Entree {
  libelle: string;
  /** identifiant de la commande du registre à l'origine du geste (journal d'usage : compteur d'annulations) */
  commande?: string;
  /** rend `false` si l'opération a été refusée (conflit) : l'entrée est alors abandonnée */
  annuler(): Promise<boolean | void>;
  refaire(): Promise<boolean | void>;
}

export interface Resultat {
  libelle: string;
  ok: boolean;
  commande?: string;
}

export class Historique {
  private passe: Entree[] = [];
  private futur: Entree[] = [];
  private chaine: Promise<unknown> = Promise.resolve();
  private groupes: Entree[][] = [];
  private abonnes = new Set<() => void>();
  /** posée par le registre pendant l'exécution d'une commande : les entrées déposées portent son identifiant */
  marque: string | undefined;

  constructor(private limite = 200) {}

  abonner = (f: () => void): (() => void) => {
    this.abonnes.add(f);
    return () => this.abonnes.delete(f);
  };

  private publier() {
    for (const f of this.abonnes) f();
  }

  ajouter(e: Entree): void {
    const entree = e.commande || !this.marque ? e : Object.assign(e, { commande: this.marque });
    const groupe = this.groupes[this.groupes.length - 1];
    if (groupe) {
      groupe.push(entree);
      return;
    }
    this.passe.push(entree);
    if (this.passe.length > this.limite) this.passe.shift();
    this.futur = [];
    this.publier();
  }

  /** Retire une entrée dont l'écriture a finalement été refusée par le serveur : rien à annuler. */
  retirer(e: Entree): void {
    for (const g of this.groupes) {
      const i = g.indexOf(e);
      if (i >= 0) g.splice(i, 1);
    }
    this.passe = this.passe.filter((x) => x !== e);
    this.futur = this.futur.filter((x) => x !== e);
    this.publier();
  }

  /** Tout ce que `f` dépose devient une seule entrée : annulée en ordre inverse, rétablie dans l'ordre. */
  async grouper<T>(libelle: string, f: () => Promise<T>): Promise<T> {
    const groupe: Entree[] = [];
    this.groupes.push(groupe);
    try {
      return await f();
    } finally {
      this.groupes.splice(this.groupes.indexOf(groupe), 1);
      if (groupe.length === 1) this.ajouter({ ...groupe[0]!, libelle });
      else if (groupe.length > 1) {
        this.ajouter({
          libelle, commande: groupe[0]!.commande,
          annuler: async () => {
            let ok = true;
            for (const e of [...groupe].reverse()) ok = (await e.annuler()) !== false && ok;
            return ok;
          },
          refaire: async () => {
            let ok = true;
            for (const e of groupe) ok = (await e.refaire()) !== false && ok;
            return ok;
          },
        });
      }
    }
  }

  private enchainer<T>(f: () => Promise<T>): Promise<T> {
    const p = this.chaine.then(f, f);
    this.chaine = p.catch(() => undefined);
    return p;
  }

  private jouer(sens: "annuler" | "refaire"): Promise<Resultat | null> {
    return this.enchainer(async () => {
      const [de, vers] = sens === "annuler" ? [this.passe, this.futur] : [this.futur, this.passe];
      const e = de.pop();
      if (!e) return null;
      let ok = false;
      try {
        ok = (await e[sens]()) !== false;
      } catch {
        ok = false;
      }
      if (ok) vers.push(e);
      this.publier();
      return { libelle: e.libelle, ok, commande: e.commande };
    });
  }

  annuler(): Promise<Resultat | null> {
    return this.jouer("annuler");
  }

  refaire(): Promise<Resultat | null> {
    return this.jouer("refaire");
  }

  /** Libellés du prochain « annuler » et du prochain « rétablir » (null : rien). */
  etat(): { annuler: string | null; refaire: string | null } {
    return { annuler: this.passe[this.passe.length - 1]?.libelle ?? null, refaire: this.futur[this.futur.length - 1]?.libelle ?? null };
  }

  vider(): void {
    this.passe = [];
    this.futur = [];
    this.publier();
  }
}
