// Barre flottante au-dessus de la sélection : les actions contextuelles déclarées par le registre pour ce qui est
// sélectionné (une tâche, un lien, un livrable, une forme, plusieurs cartes…). Elle suit la vue ; elle n'existe
// que s'il y a une sélection (aucun abonnement au zoom le reste du temps).
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@xyflow/react";
import { ZONE_LIBRE } from "../board/detail";
import { COULEURS } from "../etat/ui";
import { TYPES_TABLEAU, boiteDe } from "../outils/espace";
import { englobante } from "../outils/geometrie";
import type { ObjetBoard } from "../types";
import { titreCommande, useCommandes } from "./react";
import { libelleDe } from "./types";

const transformation = (s: { transform: [number, number, number] }) => s.transform;
const egales = (a: [number, number, number], b: [number, number, number]) => a[0] === b[0] && a[1] === b[1] && a[2] === b[2];

export function BarreFlottante({ selection }: { selection: ObjetBoard[] }) {
  const { registre, contexte, executer } = useCommandes();
  const [tx, ty, zoom] = useStore(transformation, egales);
  const ref = useRef<HTMLDivElement>(null);
  const [largeur, setLargeur] = useState(0);
  const c = useMemo(() => contexte({ selection }), [contexte, selection]);
  const proposees = useMemo(() => registre.proposees(c, "flottante"), [registre, c]);
  const commandes = useMemo(() => proposees.map((p) => p.cmd), [proposees]);
  const dessins = selection.every((o) => TYPES_TABLEAU.has(o.type));
  const cartes = selection.every((o) => !TYPES_TABLEAU.has(o.type));
  useLayoutEffect(() => setLargeur(ref.current?.offsetWidth ?? 0), [commandes.length, dessins, cartes, selection.length]);

  const zone = englobante(selection.map(boiteDe));
  if (!zone || !commandes.length) return null;
  const parent = ref.current?.parentElement;
  const lMax = parent?.clientWidth ?? 1200, hMax = parent?.clientHeight ?? 800;
  const cx = (zone.x + zone.largeur / 2) * zoom + tx;
  const haut = zone.y * zoom + ty - 52;
  // au-dessus de la sélection ; dessous si elle touche le haut du canevas ; toujours dans le cadre (le bas est borné
  // en CSS : la hauteur du canevas change quand le panneau s'ouvre, sans nouveau rendu de cette barre)
  // sur un grand canevas, la barre ne passe ni sous la barre d'outils (en haut) ni sur la barre d'ajout (à gauche)
  const large = lMax > 900;
  const hautLibre = large ? ZONE_LIBRE.top : 8, gaucheLibre = large ? ZONE_LIBRE.left - 8 : 8;
  const y = haut >= hautLibre ? haut : Math.min(hMax - 52, (zone.y + zone.hauteur) * zoom + ty + 12);
  const x = Math.max(gaucheLibre + largeur / 2, Math.min(lMax - 8 - largeur / 2, cx));
  const actif = (id: string) => registre.obtenir(id)?.actif?.(c);

  return (
    <div ref={ref} className="selection barre-flottante nodrag nopan" role="toolbar" aria-label="Sélection"
      style={{ left: x, top: `min(calc(100% - 52px), ${Math.max(hautLibre, y)}px)`, visibility: largeur ? "visible" : "hidden" }}>
      {selection.length > 1 && <span className="compte-sel tab-num">{selection.length} objets</span>}
      {proposees.map(({ cmd, etat }, i) => {
        const Icone = cmd.icone;
        const libelle = libelleDe(cmd, c);
        return (
          <span key={cmd.id} className="groupe-flottant">
            {i > 0 && commandes[i - 1]!.categorie !== cmd.categorie && <span className="sep" aria-hidden />}
            <button type="button" title={titreCommande(cmd, c)} aria-label={etat.disponible ? libelle : `${libelle} — indisponible : ${etat.raison}`}
              aria-pressed={cmd.actif ? Boolean(cmd.actif(c)) : undefined} aria-disabled={!etat.disponible || undefined}
              className={cmd.id === "edition.supprimer" ? "danger" : undefined} onClick={() => executer(cmd.id, "flottante", { selection })}>
              {Icone ? <Icone size={16} aria-hidden /> : libelle}
            </button>
          </span>
        );
      })}
      {cartes && (
        <span className="groupe-flottant" role="group" aria-label="Priorité">
          <span className="sep" aria-hidden />
          {(["P1", "P2", "P3"] as const).map((p) => (
            <button key={p} type="button" title={`Priorité ${p}`} aria-label={`Priorité ${p}`} aria-pressed={Boolean(actif(`carte.priorite.${p}`))}
              onClick={() => executer(actif(`carte.priorite.${p}`) ? "carte.priorite.aucune" : `carte.priorite.${p}`, "flottante", { selection })}>
              <span className={`badge-p ${p} mini`}>{p}</span>
            </button>
          ))}
        </span>
      )}
      {dessins && (
        <span className="groupe-flottant" role="group" aria-label="Couleur">
          <span className="sep" aria-hidden />
          {COULEURS.map((couleur) => (
            <button key={couleur} type="button" className={`pastille teinte-${couleur}`} title={`Couleur ${couleur}`} aria-label={`Couleur ${couleur}`}
              aria-pressed={Boolean(actif(`style.couleur.${couleur}`))} onClick={() => executer(`style.couleur.${couleur}`, "flottante", { selection })} />
          ))}
        </span>
      )}
    </div>
  );
}
