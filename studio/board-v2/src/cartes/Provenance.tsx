// Ce que la carte dit d'elle-même : pastilles d'état (bloquée, en attente de toi, périmée) et pied « provenance »
// discret (auteur humain ou agent, modèle si connu, date, version, sources liées). Tout vient de etat.ts : rien
// n'est affiché quand la donnée n'existe pas.
import { memo, useState } from "react";
import { ArrowRightToLine, BookMarked, Bot, ChevronDown, CircleAlert, CircleCheck, Clock3, Hourglass, Link2, Lock, LockOpen, User } from "lucide-react";
import { useCommandes } from "../commandes/react";
import { lignesRelations, type LigneRelation } from "../relations/effets";
import type { ObjetBoard } from "../types";
import { etatsCarte, provenance, type SorteEtat } from "./etat";

const ICONES: Record<SorteEtat, typeof Clock3> = { bloquee: CircleAlert, attente: Hourglass, perimee: Clock3, pret: CircleCheck };

export const EtatsCarte = memo(function EtatsCarte({ objet }: { objet: ObjetBoard }) {
  const etats = etatsCarte(objet);
  if (!etats.length) return null;
  return (
    <div className="etats-carte" role="status">
      {etats.map((e) => {
        const Icone = ICONES[e.sorte];
        return <span key={e.sorte + e.texte} className={`etat-carte ${e.sorte}`} title={e.raison}><Icone size={13} aria-hidden />{e.texte}</span>;
      })}
    </div>
  );
});

export const PiedProvenance = memo(function PiedProvenance({ objet, sources }: { objet: ObjetBoard; sources: number }) {
  const p = provenance(objet, sources);
  if (!p) return null;
  const Auteur = p.agent ? Bot : User;
  // date absolue (stable, lisible hors contexte) plutôt que « il y a 3 min »
  const quand = p.date ? new Date(p.date * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "";
  const detail = [p.auteur && `Posée par ${p.auteur}`, p.modele && `modèle ou fournisseur : ${p.modele}`,
    p.date && `${p.modifiee ? "modifiée" : "créée"} le ${new Date(p.date * 1000).toLocaleString("fr-FR")}`, `version ${p.version}`,
    sources ? `${sources} source${sources > 1 ? "s" : ""} liée${sources > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · ");
  return (
    <footer className="provenance" title={detail} aria-label={`Provenance : ${detail}`}>
      {p.auteur && <span className={p.agent ? "agent" : undefined}><Auteur size={12} aria-hidden />{p.auteur}</span>}
      {p.modele && <span className="modele">{p.modele}</span>}
      {quand && <span className="tab-num">{quand}</span>}
      {p.modifiee && <span className="tab-num">v{p.version}</span>}
      {sources > 0 && <span className="tab-num"><Link2 size={12} aria-hidden />{sources}</span>}
    </footer>
  );
});

const ICONES_RELATION: Record<LigneRelation["sorte"], typeof Lock> = {
  bloquee: Lock, alimentee: ArrowRightToLine, citee: BookMarked, debloque: Hourglass, libere: LockOpen, attend: Hourglass,
};
const VISIBLES = 3;

/** Sous la carte : ce que ses relations lui font, d'après le résumé calculé par le serveur. Chaque ligne est un
 *  bouton qui mène à la carte concernée. Une carte sans relation à effet n'affiche rien. */
export const RelationsCarte = memo(function RelationsCarte({ objet }: { objet: ObjetBoard }) {
  const { contexte } = useCommandes();
  const [tout, setTout] = useState(false);
  const lignes = lignesRelations(objet.relations);
  if (!lignes.length) return null;
  const montrees = tout ? lignes : lignes.slice(0, VISIBLES);
  return (
    <ul className="relations-carte nodrag nopan" aria-label="Effets des relations de cette carte">
      {montrees.map((l) => {
        const Icone = ICONES_RELATION[l.sorte];
        const phrase = `${l.verbe} « ${l.carte.titre} »${l.precision ? ` (${l.precision})` : ""} — aller à cette carte`;
        return (
          <li key={`${l.sorte}-${l.carte.lien_id}`} className={l.sorte}>
            <button type="button" title={phrase} aria-label={phrase}
              onClick={(e) => { e.stopPropagation(); contexte().b.allerA(l.carte.id); }}>
              <Icone size={13} aria-hidden /><span className="verbe">{l.verbe}</span><span className="cible">{l.carte.titre}</span>
              {l.precision && <span className="precision">{l.precision}</span>}
            </button>
          </li>
        );
      })}
      {lignes.length > VISIBLES && (
        <li><button type="button" className="plus" aria-expanded={tout} onClick={(e) => { e.stopPropagation(); setTout((v) => !v); }}>
          <ChevronDown size={13} aria-hidden style={tout ? { transform: "rotate(180deg)" } : undefined} />{tout ? "Réduire" : `${lignes.length - VISIBLES} de plus`}</button></li>
      )}
    </ul>
  );
});
