// Annuler / rétablir : chaque action persistée enregistre sa réciproque (exécutée par l'API, donc durable).
export interface Commande {
  libelle: string;
  annuler: () => Promise<void>;
  refaire: () => Promise<void>;
}

export class Historique {
  private passe: Commande[] = [];
  private futur: Commande[] = [];
  constructor(private limite = 100) {}
  ajouter(c: Commande) {
    this.passe.push(c);
    if (this.passe.length > this.limite) this.passe.shift();
    this.futur = [];
  }
  async annuler(): Promise<string | null> {
    const c = this.passe.pop();
    if (!c) return null;
    await c.annuler();
    this.futur.push(c);
    return c.libelle;
  }
  async refaire(): Promise<string | null> {
    const c = this.futur.pop();
    if (!c) return null;
    await c.refaire();
    this.passe.push(c);
    return c.libelle;
  }
}
