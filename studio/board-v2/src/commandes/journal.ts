// Journal d'usage des commandes, tenu sur ce poste : combien de fois chaque commande est exécutée, par quel chemin
// (bouton, raccourci, palette…), combien de fois elle est annulée juste après. La palette s'en sert pour ses
// « récents » ; `exporter()` rend une structure stable, prête à être envoyée plus tard au serveur pour apprendre les
// préférences. Rien n'est envoyé aujourd'hui, et aucun contenu de carte n'y figure (identifiants de commandes seuls).
import type { Origine } from "./types";

export interface UsageCommande {
  id: string;
  /** nombre d'exécutions */
  n: number;
  /** exécutions annulées ensuite (Ctrl+Z) : signal d'une commande déclenchée par erreur ou décevante */
  annulations: number;
  /** horodatage (ms) de la dernière exécution */
  dernier: number;
  origines: Partial<Record<Origine, number>>;
}

export interface ExportJournal {
  version: 1;
  /** horodatage (ms) de la première entrée connue */
  depuis: number;
  genere: number;
  commandes: UsageCommande[];
}

export interface Stockage {
  getItem(cle: string): string | null;
  setItem(cle: string, valeur: string): void;
}

const CLE = "jarvis.board.commandes.v1";
const MAX_COMMANDES = 400;

export class JournalUsage {
  private usages = new Map<string, UsageCommande>();
  private depuis = 0;
  private abonnes = new Set<() => void>();

  constructor(private stockage: Stockage | null = stockageLocal(), private cle = CLE, private horloge: () => number = Date.now) {
    this.charger();
  }

  private charger() {
    try {
      const brut = this.stockage?.getItem(this.cle);
      if (!brut) return;
      const d = JSON.parse(brut) as Partial<ExportJournal>;
      if (d.version !== 1 || !Array.isArray(d.commandes)) return;
      this.depuis = Number(d.depuis) || 0;
      for (const u of d.commandes.slice(0, MAX_COMMANDES)) {
        if (typeof u?.id !== "string" || !Number.isFinite(u.n)) continue;
        this.usages.set(u.id, { id: u.id, n: u.n, annulations: Number(u.annulations) || 0, dernier: Number(u.dernier) || 0, origines: { ...u.origines } });
      }
    } catch {
      // stockage illisible ou refusé (navigation privée) : le journal repart de zéro, le Board fonctionne
    }
  }

  private enregistrer() {
    try {
      this.stockage?.setItem(this.cle, JSON.stringify(this.exporter()));
    } catch {
      // quota ou stockage refusé : le journal reste en mémoire
    }
    for (const f of this.abonnes) f();
  }

  abonner = (f: () => void): (() => void) => {
    this.abonnes.add(f);
    return () => this.abonnes.delete(f);
  };

  noter(id: string, origine: Origine): void {
    const t = this.horloge();
    if (!this.depuis) this.depuis = t;
    const u = this.usages.get(id) ?? { id, n: 0, annulations: 0, dernier: 0, origines: {} };
    u.n += 1;
    u.dernier = t;
    u.origines[origine] = (u.origines[origine] ?? 0) + 1;
    this.usages.set(id, u);
    this.enregistrer();
  }

  noterAnnulation(id: string): void {
    const u = this.usages.get(id);
    if (!u) return;
    u.annulations += 1;
    this.enregistrer();
  }

  usage(id: string): UsageCommande | undefined {
    return this.usages.get(id);
  }

  /** Identifiants des dernières commandes exécutées, la plus récente d'abord. */
  recents(n = 6): string[] {
    return [...this.usages.values()].filter((u) => u.dernier > 0).sort((a, b) => b.dernier - a.dernier).slice(0, n).map((u) => u.id);
  }

  exporter(): ExportJournal {
    return {
      version: 1, depuis: this.depuis, genere: this.horloge(),
      commandes: [...this.usages.values()].sort((a, b) => b.n - a.n).slice(0, MAX_COMMANDES).map((u) => ({ ...u, origines: { ...u.origines } })),
    };
  }

  vider(): void {
    this.usages.clear();
    this.depuis = 0;
    this.enregistrer();
  }
}

function stockageLocal(): Stockage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
