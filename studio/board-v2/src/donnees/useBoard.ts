// Branche la couche de données du Board (store, file d'écritures, synchronisation, flux) sur React.
// La vue (Board.tsx) lit `etat` et appelle `file` / `creer` ; elle ne parle plus au réseau pour ses cartes.
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { NouvelObjet, Source } from "../api";
import type { Approbation, EspaceBoard, EtatBoard, Evenement, ReglagesBoard } from "../types";
import { FileEcritures } from "./ecritures";
import { ClientFlux } from "./flux";
import { StoreBoard, type Instantane } from "./store";
import { Synchroniseur } from "./synchro";

export interface Notifications {
  /** écriture annulée : l'élément a changé ailleurs, l'écran montre maintenant la version du serveur */
  conflit(ids: string[]): void;
  erreur(message: string): void;
  /** événement reçu du flux (toasts) */
  evenement?(e: Evenement): void;
}

export interface DonneesBoard {
  /** null tant que le premier chargement n'a pas abouti */
  etat: Instantane | null;
  erreur: string;
  reglages?: ReglagesBoard;
  definirReglages(r: ReglagesBoard): void;
  approbations: Approbation[];
  rafraichirApprobations(): void;
  evenements: Evenement[];
  espaces: EspaceBoard[];
  /** augmente à chaque changement appliqué : les panneaux qui lisent des détails (commentaires, inspection) se rafraîchissent */
  tick: number;
  store: StoreBoard;
  file: FileEcritures;
  sync: Synchroniseur;
  recharger(): Promise<void>;
  /** crée un objet puis lit sa forme complète (fichier, mission) : une petite requête, pas de rechargement */
  creer(o: NouvelObjet): Promise<string>;
}

export function useBoard(source: Source, notifications: Notifications, preparer?: (e: EtatBoard) => EtatBoard): DonneesBoard {
  const notif = useRef(notifications);
  notif.current = notifications;
  const prep = useRef(preparer);
  prep.current = preparer;
  const [charge, setCharge] = useState(false);
  const [erreur, setErreur] = useState("");
  const [reglages, setReglages] = useState<ReglagesBoard | undefined>();
  const [approbations, setApprobations] = useState<Approbation[]>([]);
  const [evenements, setEvenements] = useState<Evenement[]>([]);
  const [espaces, setEspaces] = useState<EspaceBoard[]>([]);
  const [tick, setTick] = useState(0);
  const actif = useRef(true);

  const rafraichirApprobations = useCallback(() => {
    if (source.demo) return;
    source.approbations().then((a) => actif.current && setApprobations(a)).catch(() => undefined);
  }, [source]);
  const rafraichirEspaces = useCallback(() => {
    source.espaces().then((e) => actif.current && setEspaces(e)).catch(() => undefined);
  }, [source]);

  const moteur = useMemo(() => {
    const store = new StoreBoard();
    const file = new FileEcritures(source, store, {
      conflit: (ids) => notif.current.conflit(ids),
      erreur: (m) => notif.current.erreur(m),
    });
    let fluxLance = false;
    let minuteurApprobations = 0;
    const sync = new Synchroniseur(source, store, {
      espace: source.espace,
      preparer: (e) => (prep.current ? prep.current(e) : e),
      surApplique: () => setTick((t) => t + 1),
      surReglages: () => { source.lire({}).then((d) => d.reglages && actif.current && setReglages(d.reglages)).catch(() => undefined); },
      surErreur: (m) => setErreur(m),
      surCharge: (etat) => {
        setCharge(true);
        setErreur("");
        setReglages(etat.reglages);
        rafraichirApprobations();
        rafraichirEspaces();
        if (!source.demo && !fluxLance) {
          fluxLance = true;
          flux.demarrer(etat.curseur ?? 0);
          // l'activité récente du Board, lue une fois : le flux ne rejoue plus l'historique
          source.historique(200).then((l) => setEvenements((deja) => fusionner(l, deja))).catch(() => undefined);
        }
      },
    });
    const flux = new ClientFlux({
      url: (apres) => `/api/flux?apres=${apres}&espace=${encodeURIComponent(source.espace)}`,
      // filet : trou dans le flux, reconnexion, ou flux coupé (alors une relecture toutes les 10 s, onglet visible)
      filetMs: 10_000,
      surTrou: (raison) => {
        if (raison === "filet" && document.visibilityState !== "visible") return;
        void sync.recharger();
      },
      surEvenement: (e) => {
        setEvenements((l) => (l.length > 300 ? [...l.slice(-200), e] : [...l, e]));
        sync.surEvenement(e);
        if (e.tache_id || e.type.includes("approbation")) {
          window.clearTimeout(minuteurApprobations);
          minuteurApprobations = window.setTimeout(rafraichirApprobations, 300);
        }
        notif.current.evenement?.(e);
      },
    });
    return { store, file, sync, flux, reinitialiser: () => { fluxLance = false; window.clearTimeout(minuteurApprobations); } };
  }, [source, rafraichirApprobations, rafraichirEspaces]);

  useEffect(() => {
    actif.current = true;
    moteur.sync.demarrer();
    void moteur.sync.recharger();
    return () => {
      actif.current = false;
      moteur.sync.arreter();
      moteur.flux.arreter();
      moteur.reinitialiser();
    };
  }, [moteur]);

  const instantane = useSyncExternalStore(moteur.store.abonner, moteur.store.lire);

  const creer = useCallback(async (o: NouvelObjet) => {
    const id = await source.creer(o);
    await moteur.sync.lireMaintenant([id]);
    rafraichirEspaces();
    return id;
  }, [source, moteur, rafraichirEspaces]);

  return {
    etat: charge ? instantane : null, erreur, reglages, definirReglages: setReglages, approbations, rafraichirApprobations,
    evenements, espaces, tick, store: moteur.store, file: moteur.file, sync: moteur.sync,
    recharger: useCallback(() => moteur.sync.recharger(), [moteur]), creer,
  };
}

function fusionner(anciens: Evenement[], recents: Evenement[]): Evenement[] {
  const vus = new Set(recents.map((e) => e.seq));
  return [...anciens.filter((e) => !vus.has(e.seq)), ...recents].sort((a, b) => a.seq - b.seq).slice(-300);
}
