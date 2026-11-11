// Clavier : chaque frappe hors d'un champ de saisie est proposée au registre ; la première commande DISPONIBLE qui
// déclare ce raccourci s'exécute (origine « raccourci » dans le journal). Aucun raccourci n'est câblé ailleurs.
import { useEffect } from "react";
import { ui } from "../etat/ui";
import { dansChamp } from "../commandes/raccourcis";
import type { AccesCommandes } from "../commandes/react";

/** Entrée et Espace sur un bouton, un lien ou une entrée de menu l'activent : le Board ne les intercepte pas. */
function activeUnControle(e: KeyboardEvent): boolean {
  return (e.key === "Enter" || e.key === " ") && e.target instanceof Element
    && Boolean(e.target.closest("button, a[href], summary, [role='menuitem'], [role='menuitemcheckbox'], [role='option'], [role='tab']"));
}

export function useClavier({ registre, contexte, executer }: AccesCommandes): void {
  useEffect(() => {
    const trouver = (e: KeyboardEvent) => {
      if (e.defaultPrevented || dansChamp(e.target) || activeUnControle(e)) return undefined;
      // du texte est sélectionné dans la page (panneau, note) : Ctrl+C / Ctrl+X restent ceux du navigateur
      if ((e.ctrlKey || e.metaKey) && (e.key === "c" || e.key === "x") && String(window.getSelection() ?? "").trim()) return undefined;
      // un dialogue modal ou la palette ont leur propre clavier (Échap les ferme) ; seul Ctrl+K reste actif partout
      const modal = Boolean(document.querySelector("dialog[open], [aria-modal='true'], .visionneuse")) || ui.lire().palette;
      const cmd = registre.pourTouche(e, contexte());
      return cmd && (!modal || cmd.id === "palette.ouvrir") ? cmd : undefined;
    };
    const touche = (e: KeyboardEvent) => {
      const cmd = trouver(e);
      if (cmd) {
        e.preventDefault();
        executer(cmd.id, "raccourci");
        return;
      }
      // raccourci connu mais indisponible ici : le registre dit pourquoi (message), au lieu d'un silence
      if (e.defaultPrevented || e.repeat || dansChamp(e.target) || activeUnControle(e) || ui.lire().presentation !== null || ui.lire().palette) return;
      if (document.querySelector("dialog[open], [aria-modal='true'], .visionneuse")) return;
      const refus = registre.refusPourTouche(e, contexte());
      if (!refus) return;
      e.preventDefault();
      executer(refus.commande.id, "raccourci");  // indisponible : `surRefus` affiche la raison, rien ne s'exécute
    };
    // Alt+flèche (aller à l'objet voisin) est pris AVANT React Flow, qui sinon déplacerait l'objet qui a le focus
    const avant = (e: KeyboardEvent) => {
      if (!e.altKey || !e.key.startsWith("Arrow")) return;
      const cmd = trouver(e);
      if (!cmd) return;
      e.preventDefault();
      e.stopPropagation();
      executer(cmd.id, "raccourci");
    };
    window.addEventListener("keydown", touche);
    window.addEventListener("keydown", avant, true);
    return () => {
      window.removeEventListener("keydown", touche);
      window.removeEventListener("keydown", avant, true);
    };
  }, [registre, contexte, executer]);
}
