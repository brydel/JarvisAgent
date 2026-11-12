// Ce que la carte dit d'elle-même, hors de son cadre : états (bloquée, en attente de toi, périmée) au-dessus,
// effets de ses relations puis ligne de crédit (qui, avec quoi, quand, quelle version) dessous. Tout vient de
// etat.ts et du résumé des relations : rien n'est affiché quand la donnée n'existe pas.
//
// Ces lignes ne recouvrent jamais une carte voisine : la place libre est mesurée (board/degagement.ts). Ce qui
// ne tient pas dehors se replie dans le cadre de la carte elle-même (un onglet), et s'ouvre à la demande.
import { dateCourte, dateHeure } from "../lib/format";
import { memo, useEffect, useRef, useState } from "react";
import { ArrowRightToLine, BookMarked, ChevronDown, Hourglass, Lock, LockOpen } from "lucide-react";
import { DEBORD_HAUT, creditTient, lignesQuiTiennent, useDegagement } from "../board/degagement";
import { useCommandes } from "../commandes/react";
import { lignesRelations, type LigneRelation } from "../relations/effets";
import type { ObjetBoard } from "../types";
import { etatsCarte, provenance, type Provenance } from "./etat";

/** États de la carte : un point de couleur (le sens) et un mot. Dehors s'il y a la place, sinon en onglet dedans. */
export const EtatsCarte = memo(function EtatsCarte({ objet }: { objet: ObjetBoard }) {
  const { dessus } = useDegagement(objet.id);
  const etats = etatsCarte(objet);
  if (!etats.length) return null;
  return (
    <div className={`etats-carte${dessus < DEBORD_HAUT ? " dedans" : ""}`} role="status">
      {etats.map((e) => <span key={e.sorte + e.texte} className={`etat-carte ${e.sorte}`} title={e.raison}><i aria-hidden />{e.texte}</span>)}
    </div>
  );
});

/** Date absolue (stable, lisible hors contexte) plutôt que « il y a 3 min ». */
const jour = dateCourte;

/** La provenance en clair, pour l'info-bulle et les lecteurs d'écran. */
export function detailProvenance(p: Provenance): string {
  return [p.auteur && `Posée par ${p.auteur}`, p.modele && `modèle ou fournisseur : ${p.modele}`,
    p.date && `${p.modifiee ? "modifiée" : "créée"} le ${dateHeure(p.date)}`, `version ${p.version}`,
    p.sources ? `${p.sources} source${p.sources > 1 ? "s" : ""} liée${p.sources > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · ");
}

/** La ligne de crédit : qui, avec quoi, quand, quelle version. Détail-signature du produit (le filet vient du style). */
export function LigneCredit({ p, classe = "" }: { p: Provenance; classe?: string }) {
  const detail = detailProvenance(p);
  return (
    <p className={`credit points ${classe}`.trim()} title={detail} aria-label={`Provenance : ${detail}`}>
      {p.auteur && <b>{p.auteur}</b>}
      {p.modele && <span className="modele">{p.modele}</span>}
      {p.date && <span>{jour(p.date)}</span>}
      {p.modifiee && <span>v{p.version}</span>}
      {p.sources > 0 && <span>{p.sources} source{p.sources > 1 ? "s" : ""}</span>}
    </p>
  );
}

const ICONES_RELATION: Record<LigneRelation["sorte"], typeof Lock> = {
  bloquee: Lock, alimentee: ArrowRightToLine, citee: BookMarked, debloque: Hourglass, libere: LockOpen, attend: Hourglass,
};
const VISIBLES = 3;

/** Sous la carte : ce que ses relations lui font (chaque ligne mène à la carte concernée), puis sa ligne de
 *  crédit au survol ou à la sélection. Seules les lignes qui tiennent avant la carte voisine sont posées dehors ;
 *  les autres attendent derrière « N de plus », qui les déplie à la demande (Échap ou un clic ailleurs referme). */
export const SousCarte = memo(function SousCarte({ objet, sources }: { objet: ObjetBoard; sources: number }) {
  const { contexte } = useCommandes();
  const { dessous } = useDegagement(objet.id);
  const [tout, setTout] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!tout) return;
    const dehors = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setTout(false); };
    const echap = (e: KeyboardEvent) => { if (e.key === "Escape") setTout(false); };
    window.addEventListener("pointerdown", dehors, true);
    window.addEventListener("keydown", echap);
    return () => {
      window.removeEventListener("pointerdown", dehors, true);
      window.removeEventListener("keydown", echap);
    };
  }, [tout]);
  const lignes = lignesRelations(objet.relations);
  const p = provenance(objet, sources);
  if (!lignes.length && !p) return null;
  const place = Math.min(VISIBLES, lignesQuiTiennent(dessous));
  // tout tient : toutes les lignes ; sinon la dernière place va au bouton « N de plus »
  const directes = lignes.length <= place ? lignes.length : Math.max(0, place - 1);
  const montrees = tout ? lignes : lignes.slice(0, directes);
  const reste = lignes.length - directes;
  const replie = lignes.length > 0 && place === 0 && !tout;
  const occupees = tout ? lignes.length + 1 : reste ? directes + 1 : directes;
  return (
    <div ref={ref} className={`sous-carte${replie ? " repliee" : ""}${tout ? " depliee" : ""}`}>
      {lignes.length > 0 && (
        <ul className="relations-carte nodrag nopan" aria-label="Effets des relations de cette carte">
          {montrees.map((l) => {
            const Icone = ICONES_RELATION[l.sorte];
            const phrase = `${l.verbe} « ${l.carte.titre} »${l.precision ? ` (${l.precision})` : ""} — aller à cette carte`;
            return (
              <li key={`${l.sorte}-${l.carte.lien_id}`} className={l.sorte}>
                <button type="button" title={phrase} aria-label={phrase}
                  onClick={(e) => { e.stopPropagation(); contexte().b.allerA(l.carte.id); }}>
                  <Icone size={16} aria-hidden /><span className="verbe">{l.verbe}</span><span className="cible">{l.carte.titre}</span>
                  {l.precision && <span className="precision">{l.precision}</span>}
                </button>
              </li>
            );
          })}
          {reste > 0 && (
            <li><button type="button" className="plus" aria-expanded={tout} onClick={(e) => { e.stopPropagation(); setTout((v) => !v); }}>
              <ChevronDown size={16} aria-hidden className={tout ? "retourne" : undefined} />
              {tout ? "Réduire" : replie ? `${lignes.length} relation${lignes.length > 1 ? "s" : ""}` : `${reste} de plus`}</button></li>
          )}
        </ul>
      )}
      {p && !replie && !tout && creditTient(dessous, occupees) && <LigneCredit p={p} classe="provenance" />}
    </div>
  );
});
