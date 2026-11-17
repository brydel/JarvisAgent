import { useId, useLayoutEffect, useRef, useState, type FocusEventHandler, type KeyboardEvent, type RefObject } from "react";
import { FileText } from "lucide-react";
import { encoderWiki } from "../lib/wikiliens";
import "./editeur-note.css";

type Cible = { id: string; titre: string };
type Saisie = { debut: number; fin: number; requete: string };
type Props = {
  valeur: string;
  surChangement: (valeur: string) => void;
  cibles: (requete: string) => readonly Cible[];
  zone?: RefObject<HTMLTextAreaElement | null>;
  surQuitter?: FocusEventHandler<HTMLElement>;
  surEchapper?: () => void;
};

function lienSousCurseur(texte: string, position: number): Saisie | null {
  const avant = texte.slice(0, position);
  const finFermee = avant.endsWith("]]");
  const sansFin = finFermee ? avant.slice(0, -2) : avant;
  const correspondance = /\[\[([^\[\]\n\r|]{0,240})$/.exec(sansFin);
  if (!correspondance) return null;
  const autreFin = /^[^\[\]\n\r|]{0,240}\]\]/.exec(texte.slice(position));
  return {
    debut: correspondance.index,
    fin: position + (!finFermee && autreFin ? autreFin[0].length : 0),
    requete: correspondance[1]!.trim(),
  };
}

export function EditeurNote({ valeur, surChangement, cibles, zone, surQuitter, surEchapper }: Props) {
  const zoneInterne = useRef<HTMLTextAreaElement>(null);
  const champ = zone ?? zoneInterne;
  const liste = useRef<HTMLUListElement>(null);
  const prochainCurseur = useRef<number | null>(null);
  const listeId = useId();
  const [position, setPosition] = useState<number | null>(null);
  const [actif, setActif] = useState(0);
  const [ferme, setFerme] = useState(false);
  const [composition, setComposition] = useState(false);
  const saisie = position !== null && !ferme && !composition ? lienSousCurseur(valeur, position) : null;
  const suggestions = saisie ? cibles(saisie.requete) : [];
  const indexActif = Math.min(actif, suggestions.length - 1);

  const lireCurseur = (z: HTMLTextAreaElement) => {
    setPosition(z.selectionStart === z.selectionEnd ? z.selectionEnd : null);
  };
  const changerSaisie = (z: HTMLTextAreaElement) => {
    lireCurseur(z);
    setFerme(false);
    setActif(0);
  };

  useLayoutEffect(() => {
    const z = champ.current;
    const p = prochainCurseur.current;
    if (!z || p === null) return;
    prochainCurseur.current = null;
    z.focus();
    z.setSelectionRange(p, p);
  }, [champ, valeur]);

  const choisir = (cible: Cible) => {
    if (!saisie) return;
    const lien = encoderWiki(cible);
    const v = valeur.slice(0, saisie.debut) + lien + valeur.slice(saisie.fin);
    if (v.length > 50_000) return;
    prochainCurseur.current = saisie.debut + lien.length;
    setPosition(prochainCurseur.current);
    setFerme(true);
    setActif(0);
    surChangement(v);
  };

  const clavier = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (composition || e.nativeEvent.isComposing) return;
    if (e.key === "Escape") {
      if (!saisie && !surEchapper) return;
      e.preventDefault();
      e.stopPropagation();
      if (saisie) setFerme(true);
      else surEchapper?.();
      return;
    }
    if (!suggestions.length || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      const prochain = (indexActif + (e.key === "ArrowDown" ? 1 : suggestions.length - 1)) % suggestions.length;
      setActif(prochain);
      liste.current?.children[prochain]?.scrollIntoView({ block: "nearest" });
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      choisir(suggestions[indexActif]!);
    }
  };

  return <div className="editeur-note nodrag nopan" onBlur={(e) => {
    if (e.relatedTarget instanceof Node && e.currentTarget.contains(e.relatedTarget)) return;
    setPosition(null);
    surQuitter?.(e);
  }}>
    <textarea ref={champ} className="nodrag nowheel nopan" value={valeur} autoFocus aria-label="Texte de la note" maxLength={50000}
      aria-autocomplete="list" aria-controls={suggestions.length ? listeId : undefined}
      aria-activedescendant={indexActif >= 0 ? listeId + "-" + indexActif : undefined}
      onChange={(e) => { changerSaisie(e.currentTarget); surChangement(e.currentTarget.value); }}
      onSelect={(e) => lireCurseur(e.currentTarget)}
      onClick={(e) => changerSaisie(e.currentTarget)}
      onCompositionStart={() => setComposition(true)}
      onCompositionEnd={(e) => { setComposition(false); changerSaisie(e.currentTarget); }}
      onKeyDown={clavier} />
    {saisie && <div className="editeur-note-suggestions nowheel">
      {suggestions.length ? <ul id={listeId} ref={liste} role="listbox" aria-label="Notes à lier">
        {suggestions.map((cible, i) => <li key={cible.id} id={listeId + "-" + i} role="option" aria-selected={i === indexActif}
          onMouseDown={(e) => e.preventDefault()} onClick={() => choisir(cible)}>
          <FileText size={15} aria-hidden />
          <span>{cible.titre}</span>
          {suggestions.some((autre) => autre.titre === cible.titre && autre.id !== cible.id) && <small>{cible.id}</small>}
        </li>)}
      </ul> : <p role="status">Aucune note correspondante</p>}
    </div>}
  </div>;
}
