import { useEffect, useId, useRef } from "react";
import { FileCheck2 } from "lucide-react";
import type { Inspection } from "../api";
import { dateHeure } from "../lib/format";
const etatMission = (etat: string) => ({ WAITING_PROVIDER: "Fournisseur indisponible", RUNNING: "En cours", REVIEW: "En vérification", SUCCEEDED: "Terminée", FAILED: "À examiner" }[etat] || etat);
const etatValidation = (etat: string) => ({ approuvee: "Approuvée", refusee: "Refusée", en_attente: "En attente" }[etat] || etat);
const titreEtape = (etape: Inspection["taches"][number]) => etape.libelle || etape.type;

export type CiblePreuve = { sequence: number; etape?: string; tentative?: string };

const TYPES: Readonly<Record<string, string>> = {
  tache_etat: "Changement d’état",
  frustration_declaree: "Frustration déclarée",
  tache_retenue: "Étape retenue par une dépendance",
  approbation: "Décision de validation",
};

const lireTexte = (donnees: Record<string, unknown> | undefined, cles: string[]) => {
  for (const cle of cles) {
    const v = donnees?.[cle];
    if (typeof v === "string" && v.trim()) return v.trim().slice(0, 1_000);
  }
  return "";
};

export function PreuveMission({ detail, cible }: { detail: Inspection; cible: CiblePreuve }) {
  const titre = useId();
  const panneau = useRef<HTMLElement>(null);
  const evenement = detail.chronologie.find((e) => e.seq === cible.sequence);
  const etape = evenement?.tache_id ? detail.taches.find((t) => t.id === evenement.tache_id) : undefined;
  const tentative = lireTexte(evenement?.donnees, ["tentative_id"]) || cible.tentative;
  const essai = etape?.tentatives.find((t) => t.id === tentative);
  const raison = lireTexte(evenement?.donnees, ["raison", "avis", "frustration", "detail", "texte", "message"]);
  const avant = lireTexte(evenement?.donnees, ["de"]);
  const apres = lireTexte(evenement?.donnees, ["vers"]);
  const auteur = lireTexte(evenement?.donnees, ["auteur", "par"]);
  const decision = lireTexte(evenement?.donnees, ["decision"]);
  const approbation = lireTexte(evenement?.donnees, ["approbation_id"]);

  useEffect(() => {
    const zone = panneau.current;
    zone?.focus({ preventScroll: true });
    zone?.scrollIntoView({ block: "start", behavior: "instant" });
  }, [cible.sequence]);

  return <section className="jm-preuve-mission" ref={panneau} tabIndex={-1} aria-labelledby={titre}>
    <header><FileCheck2 size={19} aria-hidden /><h3 id={titre}>Preuve du journal</h3></header>
    {evenement ? <>
      <p><strong>{TYPES[evenement.type] || evenement.type.replaceAll("_", " ")}</strong>
        {Boolean(evenement.donnees?.factice) && <span> · Exécution simulée</span>}</p>
      {raison && <p className="jm-preuve-detail">{raison}</p>}
      <dl className="jm-preuve-donnees">
        <div><dt>Événement</dt><dd>#{evenement.seq} · {dateHeure(evenement.ts)}</dd></div>
        {avant && apres && <div><dt>Transition</dt><dd>{etatMission(avant)} → {etatMission(apres)}</dd></div>}
        {etape && <div><dt>Étape</dt><dd>{titreEtape(etape)} · {etape.id}</dd></div>}
        {essai && <div><dt>Tentative</dt><dd>{[essai.id, essai.executant_nom, essai.issue].filter(Boolean).join(" · ")}</dd></div>}
        {approbation && decision && <div><dt>Validation</dt><dd>{etatValidation(decision)} · {approbation}</dd></div>}
        {auteur && <div><dt>Auteur</dt><dd>{auteur}</dd></div>}
      </dl>
    </> : <p className="credit">L’événement demandé est introuvable dans cette mission.</p>}
  </section>;
}
