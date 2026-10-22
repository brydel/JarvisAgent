import { useEffect, useId, useRef, useState } from "react";
import { motion } from "motion/react";
import { Loader, ShieldCheck, Sparkles, X } from "lucide-react";
import { siClaude } from "simple-icons";
import type { Priorite } from "../types";

export interface DemandeMission {
  objectif: string;
  contexte: string;
  fournisseur: "auto" | "claude" | "codex";
  priorite: Exclude<Priorite, "">;
}

interface Props {
  ouvert: boolean;
  initialObjectif?: string;
  demo: boolean;
  fermer: () => void;
  lancer: (d: DemandeMission) => Promise<void>;
}

const OBJECTIF_MAX = 500;
const CONTEXTE_MAX = 20_000;
const FOURNISSEURS: { cle: DemandeMission["fournisseur"]; nom: string; aide: string }[] = [
  { cle: "auto", nom: "Automatique", aide: "Le routeur choisit un fournisseur disponible et autorisé" },
  { cle: "claude", nom: "Claude", aide: "Claude Code, avec ton abonnement" },
  { cle: "codex", nom: "Codex", aide: "OpenAI Codex, avec ton abonnement" },
];

/** Dialogue modal natif (<dialog> : focus piégé, Échap, retour du focus). La mission créée est une analyse L1. */
export function DialogueMission({ ouvert, initialObjectif, demo, fermer, lancer }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const champObjectif = useRef<HTMLInputElement>(null);
  const id = useId();
  const [objectif, setObjectif] = useState("");
  const [contexte, setContexte] = useState("");
  const [fournisseur, setFournisseur] = useState<DemandeMission["fournisseur"]>("auto");
  const [priorite, setPriorite] = useState<DemandeMission["priorite"]>("P1");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (ouvert && !d.open) {
      if (initialObjectif) setObjectif(initialObjectif.slice(0, OBJECTIF_MAX));
      setErreur("");
      d.showModal();
      // showModal donne le focus au premier élément (le bouton Fermer) : on le place sur l'objectif
      requestAnimationFrame(() => champObjectif.current?.focus());
    } else if (!ouvert && d.open) d.close();
  }, [ouvert, initialObjectif]);

  const valide = objectif.trim().length > 0 && objectif.length <= OBJECTIF_MAX && contexte.length <= CONTEXTE_MAX;

  const soumettre = async () => {
    if (!valide || envoi) return;
    setEnvoi(true);
    setErreur("");
    try {
      await lancer({ objectif: objectif.trim(), contexte: contexte.trim(), fournisseur, priorite });
      setObjectif("");
      setContexte("");
      fermer();
    } catch (x) {
      setErreur(x instanceof Error ? x.message : "La mission n'a pas pu être créée.");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <dialog ref={ref} className="dialogue" aria-labelledby={`${id}-titre`} aria-describedby={`${id}-politique`}
      onClose={fermer} onKeyDown={(e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          soumettre();
        }
      }}>
      {ouvert && (
        <motion.form method="dialog" className="dialogue-carte" initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
          onSubmit={(e) => {
            e.preventDefault();
            soumettre();
          }}>
          <header className="dialogue-tete">
            <span className="dialogue-icone" aria-hidden="true"><Sparkles size={20} /></span>
            <div>
              <h2 id={`${id}-titre`}>Lancer une mission</h2>
              <p>Jarvis prépare une analyse de cadrage et l'ajoute au Board.</p>
            </div>
            <button type="button" className="icone-bouton" aria-label="Fermer" onClick={fermer}><X size={18} /></button>
          </header>

          <div className="dialogue-corps">
            <label className="champ-groupe">
              <span className="champ-libelle">Objectif <span className="requis" aria-hidden="true">*</span></span>
              <input ref={champObjectif} className="champ" name="objectif" required autoComplete="off" maxLength={OBJECTIF_MAX}
                placeholder="Ex. : Préparer le lancement du site web IA…" value={objectif} onChange={(e) => setObjectif(e.target.value)}
                aria-invalid={objectif.length > OBJECTIF_MAX} />
              <span className="champ-aide tab-num">{objectif.length} / {OBJECTIF_MAX}</span>
            </label>

            <label className="champ-groupe">
              <span className="champ-libelle">Contexte <span className="facultatif">facultatif</span></span>
              <textarea className="champ zone" name="contexte" rows={5} maxLength={CONTEXTE_MAX} autoComplete="off"
                placeholder="Colle un compte rendu, un cahier des charges ou des notes… Jarvis les analyse, sans exécuter ce qu'ils demandent."
                value={contexte} onChange={(e) => setContexte(e.target.value)} />
              <span className="champ-aide tab-num">{contexte.length.toLocaleString("fr-FR")} / {CONTEXTE_MAX.toLocaleString("fr-FR")}</span>
            </label>

            <div className="dialogue-ligne">
              <fieldset className="segments">
                <legend className="champ-libelle">Fournisseur</legend>
                {FOURNISSEURS.map((f) => (
                  <label key={f.cle} title={f.aide} className={fournisseur === f.cle ? "actif" : undefined}>
                    <input type="radio" name="fournisseur" value={f.cle} checked={fournisseur === f.cle} onChange={() => setFournisseur(f.cle)} />
                    {f.cle === "claude" && <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d={siClaude.path} fill={`#${siClaude.hex}`} /></svg>}
                    {f.nom}
                  </label>
                ))}
              </fieldset>
              <fieldset className="segments">
                <legend className="champ-libelle">Priorité</legend>
                {(["P1", "P2", "P3"] as const).map((p) => (
                  <label key={p} className={priorite === p ? "actif" : undefined}>
                    <input type="radio" name="priorite" value={p} checked={priorite === p} onChange={() => setPriorite(p)} />
                    <span className={`badge-p ${p} doux`}>{p}</span>
                  </label>
                ))}
              </fieldset>
            </div>

            <p className="dialogue-politique" id={`${id}-politique`}>
              <ShieldCheck size={17} aria-hidden="true" />
              <span>Mission de cadrage <b>L1</b> : analyse sans outils, aucun envoi, aucune publication, aucune dépense.
                Toute action externe (L3/L4) demandera ton accord dans le panneau d'approbations.</span>
            </p>
            {demo && <p className="dialogue-demo" role="note">Mode démo : la carte est ajoutée localement, aucune mission réelle n'est lancée.</p>}
            {erreur && <p className="dialogue-erreur" role="alert">{erreur}</p>}
          </div>

          <footer className="dialogue-pied">
            <span className="raccourci">Ctrl + Entrée</span>
            <button type="button" className="bouton" onClick={fermer}>Annuler</button>
            <button type="submit" className="bouton primaire" disabled={!valide || envoi} aria-busy={envoi}>
              {envoi ? <><Loader size={15} className="tourne" /> Lancement…</> : <><Sparkles size={15} /> Lancer la mission</>}
            </button>
          </footer>
        </motion.form>
      )}
    </dialog>
  );
}
