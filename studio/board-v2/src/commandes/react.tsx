// Branchement du registre sur React : un contexte (registre + fabrique de contexte de commande + exécution), et le
// bouton générique qui affiche libellé, icône, raccourci et état d'une commande sans les redéclarer.
import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import { ui } from "../etat/ui";
import type { ContexteBoard } from "./contexte";
import type { RegistreBoard } from "./index";
import { afficher } from "./raccourcis";
import { etatDe, libelleDe, raccourcisDe, type Commande, type Origine } from "./types";

export interface AccesCommandes {
  registre: RegistreBoard;
  /** contexte courant (sélection, interface) ; `extra` : cible d'un menu contextuel */
  contexte(extra?: Partial<Pick<ContexteBoard, "selection" | "lien" | "point">>): ContexteBoard;
  executer(id: string, origine: Origine, extra?: Partial<Pick<ContexteBoard, "selection" | "lien" | "point">>): void;
}

export const ContexteCommandes = createContext<AccesCommandes | null>(null);

export function useCommandes(): AccesCommandes {
  const a = useContext(ContexteCommandes);
  if (!a) throw new Error("ContexteCommandes manquant");
  return a;
}

/** « Aligner à gauche (Alt+A) » : libellé et premier raccourci, pour une info-bulle. Commande indisponible : la
 *  raison déclarée par le registre suit (« Annuler (Ctrl+Z) — indisponible : rien à annuler »). */
export function titreCommande(cmd: Commande<ContexteBoard>, c: ContexteBoard): string {
  const r = raccourcisDe(cmd)[0];
  const base = r ? `${libelleDe(cmd, c)} (${afficher(r)})` : libelleDe(cmd, c);
  const etat = etatDe(cmd, c);
  return etat.disponible ? base : `${base} — indisponible : ${etat.raison ?? "hors de ce contexte"}`;
}

/** Abonnement à l'historique (annuler / rétablir) : les boutons qui en dépendent se mettent à jour. */
function useHistorique(registre: RegistreBoard): void {
  useSyncExternalStore(registre.historique.abonner, () => {
    const e = registre.historique.etat();
    return `${e.annuler ?? ""}\u0000${e.refaire ?? ""}`;
  });
}

interface PropsBouton {
  id: string;
  origine?: Origine;
  /** montre le libellé à côté de l'icône */
  texte?: boolean;
  classe?: string;
  taille?: number;
  children?: ReactNode;
}

/** Bouton d'une commande. Se re-rend quand l'état d'interface change (état « actif », libellé de bascule). */
export function BoutonCommande({ id, origine = "bouton", texte = false, classe, taille = 16, children }: PropsBouton) {
  const { registre, contexte, executer } = useCommandes();
  useSyncExternalStore(ui.abonner, ui.lire);
  useHistorique(registre);
  const cmd = registre.obtenir(id);
  if (!cmd) return null;
  const c = contexte();
  const Icone = cmd.icone;
  const libelle = libelleDe(cmd, c);
  const etat = etatDe(cmd, c);
  // grisé mais focalisable et cliquable (aria-disabled) : l'info-bulle et le clic disent POURQUOI, un `disabled` natif
  // ne dirait rien au clavier ni au lecteur d'écran
  return (
    <button type="button" className={classe} title={titreCommande(cmd, c)} aria-label={etat.disponible ? libelle : `${libelle} — indisponible : ${etat.raison ?? "hors de ce contexte"}`}
      aria-pressed={cmd.actif ? cmd.actif(c) : undefined} aria-disabled={!etat.disponible || undefined} onClick={() => executer(id, origine)}>
      {children ?? (Icone ? <Icone size={taille} aria-hidden /> : null)}
      {texte && <span>{libelle}</span>}
    </button>
  );
}
