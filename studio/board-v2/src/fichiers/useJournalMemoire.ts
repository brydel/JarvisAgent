import { useEffect, useState } from "react";
import type { Source } from "../api";
import { requete } from "../product/api";
import { journalDemo } from "./journal-demo";
import type { NatureMemoire, PageMemoire } from "./journal-donnees";

const VIDE: PageMemoire["entrees"] = [];

export function useJournalMemoire(source: Source, actif: boolean) {
  const [nature, setNature] = useState<NatureMemoire | "">("");
  const [curseurs, setCurseurs] = useState<(string | null)[]>([null]);
  const [relance, setRelance] = useState(0);
  const [etat, setEtat] = useState<{ cle: string; page?: PageMemoire; erreur?: string } | null>(null);
  const curseur = curseurs.at(-1);
  const cle = JSON.stringify([source.espace, source.demo, nature, curseur, relance]);

  useEffect(() => {
    if (!actif) return;
    if (source.demo) {
      setEtat({ cle, page: { entrees: journalDemo.filter((e) => !nature || e.nature === nature), avant: null } });
      return;
    }
    const controle = new AbortController();
    const params = new URLSearchParams({ espace: source.espace, limite: "20" });
    if (nature) params.set("nature", nature);
    if (curseur) params.set("avant", curseur);
    requete<PageMemoire>("/api/v2/journal-memoire?" + params.toString(), undefined, controle.signal)
      .then((page) => { if (!controle.signal.aborted) setEtat({ cle, page }); })
      .catch((e: unknown) => {
        if (!controle.signal.aborted) setEtat({ cle, erreur: e instanceof Error ? e.message : "Le journal est indisponible." });
      });
    return () => controle.abort();
  }, [cle, actif, source.espace, source.demo, nature, curseur]);

  const courant = etat?.cle === cle ? etat : null;
  const avant = courant?.page?.avant;
  return {
    nature,
    filtrer: (valeur: NatureMemoire | "") => { setNature(valeur); setCurseurs([null]); },
    entrees: courant?.page?.entrees ?? VIDE,
    charge: courant === null,
    erreur: courant?.erreur,
    page: curseurs.length,
    actualiser: () => { setCurseurs([null]); setRelance((n) => n + 1); },
    reessayer: () => setRelance((n) => n + 1),
    precedent: curseurs.length > 1 ? () => setCurseurs((v) => v.slice(0, -1)) : undefined,
    suivant: avant ? () => setCurseurs((v) => v.at(-1) === avant ? v : [...v, avant]) : undefined,
  };
}
