import { useCallback, useEffect, useRef, useState } from "react";
import type { Source } from "../api";
import { requete } from "../product/api";
import { grapheGlobalDemo } from "./global-demo";
import type { CouvertureGlobale, PageGrapheGlobal } from "./global-donnees";

type Etat = { cle: Source; page: number; revision: number; donnees: PageGrapheGlobal; erreur: string };
const COUVERTURE_VIDE: CouvertureGlobale = {
  objets: { charges: 0, total: 0 }, liens: { charges: 0, total: 0 },
  sessions: { charges: 0, total: 0 }, entrees: { charges: 0, total: 0 },
};
const message = (e: unknown) => e instanceof Error ? e.message : "La mémoire globale est indisponible.";
const union = (a: readonly string[], b: readonly string[]) => [...new Set([...a, ...b])];

function fusionner<T extends { id: string }>(anciennes: readonly T[], nouvelles: readonly T[]): T[] {
  const parId = new Map(anciennes.map((v) => [v.id, v]));
  for (const valeur of nouvelles) parId.set(valeur.id, valeur);
  return [...parId.values()];
}

export function fusionnerGlobal(ancienne: PageGrapheGlobal | undefined, nouvelle: PageGrapheGlobal,
  garderPagination = false): PageGrapheGlobal {
  if (!ancienne) return nouvelle;
  const sessions = new Map(ancienne.sessions.map((s) => [s.id, s]));
  for (const s of nouvelle.sessions) {
    const connue = sessions.get(s.id);
    sessions.set(s.id, connue ? {
      ...connue, ...s, projets: union(connue.projets, s.projets),
      objet_ids: union(connue.objet_ids, s.objet_ids), mission_ids: union(connue.mission_ids, s.mission_ids),
      evenement_ids: union(connue.evenement_ids, s.evenement_ids),
    } : s);
  }
  const objets = fusionner(ancienne.objets, nouvelle.objets);
  const liens = fusionner(ancienne.liens, nouvelle.liens);
  const entrees = fusionner(ancienne.entrees, nouvelle.entrees);
  const projets = new Map(ancienne.projets.map((p) => [p.nom, p]));
  for (const p of nouvelle.projets) projets.set(p.nom, p);
  return {
    ...nouvelle, objets, liens, entrees, sessions: [...sessions.values()], projets: [...projets.values()],
    ...(garderPagination ? { page: ancienne.page, suivant: ancienne.suivant } : {}),
    couverture: {
      objets: { total: nouvelle.couverture.objets.total, charges: objets.length },
      liens: { total: nouvelle.couverture.liens.total, charges: liens.length },
      entrees: { total: nouvelle.couverture.entrees.total, charges: entrees.length },
      sessions: { total: nouvelle.couverture.sessions.total, charges: sessions.size },
    },
    avertissements: union(ancienne.avertissements, nouvelle.avertissements),
  };
}

export async function rafraichirLotsGlobaux(lirePage: (page: number) => Promise<PageGrapheGlobal>,
  dernierePage: number, signal: AbortSignal): Promise<PageGrapheGlobal> {
  const nombre = Math.max(1, Math.floor(dernierePage));
  const resultats: PageGrapheGlobal[] = [];
  let prochaine = 1;
  async function lireSuite() {
    while (prochaine <= nombre) {
      signal.throwIfAborted();
      const page = prochaine++;
      const donnees = await lirePage(page);
      signal.throwIfAborted();
      resultats[page - 1] = donnees;
    }
  }
  await Promise.all(Array.from({ length: Math.min(2, nombre) }, () => lireSuite()));
  return resultats.reduce((avant: PageGrapheGlobal | undefined, donnees) => fusionnerGlobal(avant, donnees), undefined)!;
}

function parametresCible(cible?: string | null): { cle: "objet" | "session" | "entree"; id: string } | undefined {
  if (!cible) return undefined;
  if (cible.startsWith("BO-")) return { cle: "objet", id: cible };
  if (/^journal:memoire:[1-9][0-9]*$/.test(cible)) return { cle: "entree", id: cible.slice("journal:".length) };
  const session = cible.replace(/^centroide:/, "");
  return /^(AT-|AR-|T-|workmux:)/.test(session) ? { cle: "session", id: session } : undefined;
}

function ciblePresente(donnees: PageGrapheGlobal, cible?: string | null) {
  const p = parametresCible(cible);
  if (!p) return true;
  if (p.cle === "objet") return donnees.objets.some((o) => o.id === p.id);
  if (p.cle === "entree") return donnees.entrees.some((e) => e.id === p.id);
  return donnees.sessions.some((s) => s.id === p.id);
}

async function charger(source: Source, page: number, cible: string | null | undefined, signal: AbortSignal) {
  if (source.demo) return grapheGlobalDemo(source);
  const p = new URLSearchParams({ page: String(page) });
  const demande = parametresCible(cible);
  if (demande) p.set(demande.cle, demande.id);
  return requete<PageGrapheGlobal>("/api/v2/graphe-global?" + p, undefined, signal);
}

export function useGrapheGlobal(source: Source, cible?: string | null) {
  const [relance, setRelance] = useState(0);
  const cle = source;
  const [position, setPosition] = useState({ cle, page: 1 });
  const page = position.cle === cle ? position.page : 1;
  const [etat, setEtat] = useState<Etat | null>(null);
  const [cibleEtat, setCibleEtat] = useState<{ cle: Source | null; id: string; page: number; revision: number; charge: boolean; erreur: string }>({
    cle: null, id: "", page: 0, revision: 0, charge: false, erreur: "",
  });
  const essayees = useRef<{ cle: Source | null; revision: number; ids: Set<string> }>({ cle: null, revision: 0, ids: new Set() });
  const courant = etat?.cle === cle ? etat : null;

  useEffect(() => {
    const controle = new AbortController();
    const reconstruire = courant && courant.revision !== relance;
    const lecture = reconstruire
      ? rafraichirLotsGlobaux((numero) => charger(source, numero, numero === 1 ? cible : undefined, controle.signal), page, controle.signal)
      : charger(source, page, cible, controle.signal);
    void lecture.then((donnees) => {
      if (controle.signal.aborted) return;
      if (donnees.page !== page) setPosition({ cle, page: donnees.page });
      setEtat((avant) => ({ cle, page: donnees.page, revision: relance, erreur: "",
        donnees: reconstruire ? donnees : fusionnerGlobal(avant?.cle === cle ? avant.donnees : undefined, donnees) }));
    }, (e: unknown) => {
      if (controle.signal.aborted) return;
      controle.abort();
      setEtat((avant) => {
        const donnees = avant?.cle === cle ? avant.donnees : {
          page, limite: 100, objets: [], liens: [], entrees: [], sessions: [], projets: [],
          couverture: COUVERTURE_VIDE, suivant: null, avertissements: [], cle_disposition: "",
        };
        return { cle, page, revision: relance, donnees, erreur: message(e) };
      });
    });
    return () => controle.abort();
    // La cible est ajoutée au lot courant. Ses changements sont traités par la lecture ciblée ci-dessous.
  }, [source, cle, page, relance]);

  useEffect(() => {
    if (!cible || !courant || courant.erreur || courant.page !== page || courant.revision !== relance || ciblePresente(courant.donnees, cible)) return;
    if (essayees.current.cle !== cle || essayees.current.revision !== relance) essayees.current = { cle, revision: relance, ids: new Set() };
    if (essayees.current.ids.has(cible)) return;
    essayees.current.ids.add(cible);
    const controle = new AbortController();
    let termine = false;
    setCibleEtat({ cle, id: cible, page, revision: relance, charge: true, erreur: "" });
    void charger(source, page, cible, controle.signal).then((donnees) => {
      if (controle.signal.aborted) return;
      termine = true;
      setEtat((avant) => avant?.cle === cle ? { ...avant, donnees: fusionnerGlobal(avant.donnees, donnees, true) } : avant);
      setCibleEtat({ cle, id: cible, page, revision: relance, charge: false,
        erreur: ciblePresente(donnees, cible) ? "" : "Cet élément est absent de la mémoire globale disponible." });
    }, (e: unknown) => {
      if (controle.signal.aborted) return;
      termine = true;
      setCibleEtat({ cle, id: cible, page, revision: relance, charge: false, erreur: message(e) });
    });
    return () => {
      controle.abort();
      if (!termine) essayees.current.ids.delete(cible);
    };
  }, [source, cle, page, relance, cible, courant]);

  const actualiser = useCallback(() => setRelance((v) => v + 1), []);
  const donnees = courant?.donnees;
  const lectureCible = cibleEtat.cle === cle && cibleEtat.id === cible && cibleEtat.page === page
    && cibleEtat.revision === relance ? cibleEtat : null;
  const charge = !courant || courant.page !== page || courant.revision !== relance;
  return {
    donnees,
    objets: donnees?.objets ?? [],
    liens: donnees?.liens ?? [],
    entrees: donnees?.entrees ?? [],
    sessions: donnees?.sessions ?? [],
    projets: donnees?.projets ?? [],
    couverture: donnees?.couverture ?? COUVERTURE_VIDE,
    avertissements: donnees?.avertissements ?? [],
    cle_disposition: donnees?.cle_disposition ?? "",
    charge,
    chargeCible: lectureCible?.charge ?? false,
    erreur: courant?.erreur || lectureCible?.erreur || "",
    page,
    suivant: !charge && !courant?.erreur && donnees?.suivant
      ? () => setPosition({ cle, page: donnees.suivant! }) : undefined,
    actualiser,
  };
}
