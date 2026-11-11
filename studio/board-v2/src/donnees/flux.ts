// Client du flux d'événements (SSE) avec reprise.
//
// - Le flux est ouvert AU CURSEUR rendu par le chargement du Board : l'historique n'est jamais rejoué.
// - Chaque message porte `prec`, le numéro du message précédent de ce flux : si la chaîne est rompue (message
//   perdu, reprise au mauvais endroit), `surTrou` est appelé et l'appelant relit le Board en entier — c'est le
//   seul cas, avec la reconnexion après coupure franche, où une relecture complète a lieu.
// - Le serveur filtre par espace ; ses messages « curseur » font avancer le point de reprise même quand tous les
//   événements récents concernaient d'autres Boards.
// - Reconnexion : le navigateur reprend seul avec Last-Event-ID ; si la connexion est fermée pour de bon (serveur
//   arrêté, session expirée), on la rouvre nous-mêmes à `?apres=<dernier numéro>`, avec une attente croissante.
// - Flux coupé (réseau ou proxy qui bloque le SSE) : tant que la connexion n'est PAS établie, `surTrou("filet")`
//   est appelé toutes les `filetMs` — le Board reste à jour par relecture, comme avant, mais seulement dans ce
//   mode dégradé. Dès que le flux est ouvert, plus aucune relecture périodique.
import type { Evenement } from "../types";

/** Le strict nécessaire d'un EventSource (remplacé par un double dans les tests). */
export interface FluxNatif {
  readyState: number;
  onopen: ((e: unknown) => void) | null;
  onerror: ((e: unknown) => void) | null;
  addEventListener(type: string, f: (e: { data: string }) => void): void;
  close(): void;
}
const FERME = 2;

export interface OptionsFlux {
  url(apres: number): string;
  ouvrir?(url: string): FluxNatif;
  surEvenement(e: Evenement): void;
  /** continuité rompue ou resynchronisation demandée par le serveur : relire le Board en entier */
  surTrou(raison: "trou" | "resync" | "reconnexion" | "filet"): void;
  /** mode dégradé : période de relecture tant que le flux n'est pas connecté (absent = pas de filet périodique) */
  filetMs?: number;
  /** échecs consécutifs avant de prévenir une première fois (le Board affiche alors l'erreur du serveur) */
  echecsAvantAlerte?: number;
  delaiMin?: number;
  delaiMax?: number;
  minuterie?: { poser(f: () => void, ms: number): unknown; lever(h: unknown): void };
}

export class ClientFlux {
  private natif: FluxNatif | null = null;
  private dernier = 0;
  private echecs = 0;
  private attente: unknown = null;
  private filet: unknown = null;
  private arrete = true;
  private readonly minuterie: NonNullable<OptionsFlux["minuterie"]>;

  constructor(private o: OptionsFlux) {
    this.minuterie = o.minuterie ?? { poser: (f, ms) => setTimeout(f, ms), lever: (h) => clearTimeout(h as ReturnType<typeof setTimeout>) };
  }

  /** Numéro du dernier message reçu : point de reprise. */
  get curseur(): number {
    return this.dernier;
  }

  demarrer(curseur: number): void {
    this.arreter();
    this.arrete = false;
    this.dernier = curseur;
    this.echecs = 0;
    this.ouvrir();
  }

  arreter(): void {
    this.arrete = true;
    if (this.attente !== null) this.minuterie.lever(this.attente);
    this.attente = null;
    this.desarmerFilet();
    this.natif?.close();
    this.natif = null;
  }

  /** Tant que le flux n'est pas connecté : une relecture toutes les `filetMs`. */
  private armerFilet(): void {
    if (this.filet !== null || !this.o.filetMs || this.arrete) return;
    this.filet = this.minuterie.poser(() => {
      this.filet = null;
      if (this.arrete) return;
      this.o.surTrou("filet");
      this.armerFilet();
    }, this.o.filetMs);
  }

  private desarmerFilet(): void {
    if (this.filet !== null) this.minuterie.lever(this.filet);
    this.filet = null;
  }

  private ouvrir(): void {
    const ouvrir = this.o.ouvrir ?? ((url: string) => new EventSource(url) as unknown as FluxNatif);
    const natif = ouvrir(this.o.url(this.dernier));
    this.natif = natif;
    this.armerFilet();  // pas encore connecté
    natif.onopen = () => {
      if (this.natif !== natif) return;
      this.desarmerFilet();
      const coupure = this.echecs > 0;
      this.echecs = 0;
      if (coupure) this.o.surTrou("reconnexion");  // rouvert par nous après une coupure franche : filet complet
    };
    natif.onerror = () => {
      if (this.natif !== natif || this.arrete) return;
      this.armerFilet();
      if (natif.readyState !== FERME) return;  // le navigateur réessaie seul, avec Last-Event-ID
      natif.close();
      this.natif = null;
      this.echecs += 1;
      if (this.echecs === (this.o.echecsAvantAlerte ?? 3)) this.o.surTrou("reconnexion");
      const delai = Math.min(this.o.delaiMax ?? 30_000, (this.o.delaiMin ?? 1000) * 2 ** Math.min(this.echecs - 1, 10));
      this.attente = this.minuterie.poser(() => {
        this.attente = null;
        if (!this.arrete) this.ouvrir();
      }, delai);
    };
    natif.addEventListener("message", (m) => {
      if (this.natif !== natif) return;
      const e = lireJson<Evenement>(m.data);
      if (!e || typeof e.seq !== "number") return;
      if (e.seq <= this.dernier) return;  // déjà vu (reprise large) : sans effet
      const rompu = typeof e.prec === "number" && e.prec !== this.dernier;
      this.dernier = e.seq;
      if (rompu) this.o.surTrou("trou");
      this.o.surEvenement(e);
    });
    natif.addEventListener("curseur", (m) => {
      if (this.natif !== natif) return;
      const c = lireJson<{ seq: number; prec?: number }>(m.data);
      if (!c || typeof c.seq !== "number" || c.seq <= this.dernier) return;
      const rompu = typeof c.prec === "number" && c.prec !== this.dernier;
      this.dernier = c.seq;
      if (rompu) this.o.surTrou("trou");
    });
    natif.addEventListener("resync", (m) => {
      if (this.natif !== natif) return;
      const c = lireJson<{ seq: number }>(m.data);
      if (c && typeof c.seq === "number") this.dernier = c.seq;
      this.o.surTrou("resync");
    });
  }
}

function lireJson<T>(texte: string): T | null {
  try {
    return JSON.parse(texte) as T;
  } catch {
    return null;
  }
}
