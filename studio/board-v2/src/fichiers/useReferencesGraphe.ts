import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Source } from "../api";
import { chargerGraphe, voir, type Fiche, type PageGrapheReferences, type ReferenceGraphe } from "../references/api";

type Lot = PageGrapheReferences & { cle: string; erreur?: string };
type Details = { cle: string; fiches: Map<string, Fiche>; courante?: Fiche; charge: boolean; erreur: string };
const message = (e: unknown) => e instanceof Error ? e.message : "Les références sont indisponibles.";

export function useReferencesGraphe(source: Source) {
  const [relance, setRelance] = useState(0);
  const cle = JSON.stringify([source.espace, source.demo, relance]);
  const [position, setPosition] = useState({ cle, page: 1 });
  const page = position.cle === cle ? position.page : 1;
  const [lot, setLot] = useState<Lot | null>(null);
  const [details, setDetails] = useState<Details | null>(null);
  const demande = useRef<AbortController | null>(null);
  const cache = useRef<{ cle: string; fiches: Map<string, Fiche> }>({ cle: "", fiches: new Map() });

  useEffect(() => {
    const controle = new AbortController();
    void chargerGraphe(source.demo, page, controle.signal).then((nouveau) => {
      if (controle.signal.aborted) return;
      if (nouveau.page !== page) setPosition({ cle, page: nouveau.page });
      setLot((ancien) => {
        const cumulees = new Map<string, ReferenceGraphe>();
        if (page > 1 && ancien?.cle === cle) {
          for (const r of ancien.references) cumulees.set(r.id, r);
        }
        for (const r of nouveau.references) cumulees.set(r.id, r);
        return { ...nouveau, cle, references: [...cumulees.values()] };
      });
    }, (e: unknown) => {
      if (controle.signal.aborted) return;
      setLot((ancien) => ({ cle, references: ancien?.cle === cle ? ancien.references : [],
        total: ancien?.cle === cle ? ancien.total : 0, page, limite: 8, erreur: message(e) }));
    });
    return () => controle.abort();
  }, [source.demo, cle, page]);

  useEffect(() => {
    return () => demande.current?.abort();
  }, [cle]);

  const chargerReference = useCallback(async (id: string) => {
    demande.current?.abort();
    const controle = new AbortController();
    demande.current = controle;
    const fiches = cache.current.cle === cle ? cache.current.fiches : new Map<string, Fiche>();
    cache.current = { cle, fiches };
    const connue = fiches.get(id);
    setDetails({ cle, fiches: new Map(fiches), courante: connue, charge: !connue, erreur: "" });
    if (connue) return;
    try {
      const fiche = await voir(source.demo, id, controle.signal);
      if (controle.signal.aborted) return;
      fiches.set(fiche.id, fiche);
      setDetails({ cle, fiches: new Map(fiches), courante: fiche, charge: false, erreur: "" });
    } catch (e) {
      if (!controle.signal.aborted) {
        setDetails({ cle, fiches: new Map(fiches), charge: false, erreur: message(e) });
      }
    }
  }, [source.demo, cle]);

  const courant = lot?.cle === cle ? lot : null;
  const detail = details?.cle === cle ? details : null;
  const references = useMemo(() => {
    const toutes = new Map<string, ReferenceGraphe>();
    for (const r of courant?.references ?? []) toutes.set(r.id, r);
    for (const r of detail?.fiches.values() ?? []) toutes.set(r.id, r);
    return [...toutes.values()];
  }, [courant, detail]);

  return {
    references,
    referenceChargee: detail?.courante,
    chargerReference,
    charge: courant === null || courant.page !== page,
    chargeReference: detail?.charge ?? false,
    erreur: courant?.erreur || detail?.erreur || "",
    suivant: courant && !courant.erreur && courant.page === page && page * courant.limite < courant.total
      ? () => setPosition({ cle, page: page + 1 }) : undefined,
    actualiser: () => setRelance((n) => n + 1),
    total: courant?.total ?? 0,
  };
}
