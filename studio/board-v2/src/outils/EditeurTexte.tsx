// Édition de texte EN PLACE, dans une surcouche qui n'est PAS transformée. Le canevas est mis à l'échelle par
// `transform: scale(zoom)` : un champ éditable placé dedans a un curseur flou, une sélection décalée et un texte
// baveux à certains zooms. Ici le <textarea> vit hors du canevas ; on calcule sa boîte à l'écran et on multiplie
// sa taille de police par le zoom : même rendu que l'objet, curseur net, IME et correcteur du navigateur intacts.
// Tout ce qui est saisi ou collé reste du TEXTE (textarea : aucun HTML interprété).
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useStore } from "@xyflow/react";
import type { ServicesBoard } from "../commandes/contexte";
import { policeAdhesif } from "../nodes/Tableau";
import type { ObjetBoard } from "../types";
import { boiteDe } from "./espace";
import { contourDe, extremitesReelles } from "./fleche";
import type { Boite } from "./geometrie";

const transformation = (s: { transform: [number, number, number] }) => s.transform;
const egales = (a: [number, number, number], b: [number, number, number]) => a[0] === b[0] && a[1] === b[1] && a[2] === b[2];

interface Zone {
  boite: Boite;
  police: number;
  classe: string;
  /** champ édité : le texte de l'objet, ou le titre (cadre) */
  champ: "contenu" | "titre";
  uneLigne?: boolean;
  /** l'objet s'agrandit pour contenir le texte saisi */
  ajuste?: boolean;
}

function zoneDe(o: ObjetBoard, b: ServicesBoard, texte: string): Zone | null {
  const boite = boiteDe(o);
  switch (o.type) {
    case "adhesif": return { boite, police: policeAdhesif(o, texte), classe: "ed-adhesif", champ: "contenu" };
    case "texte_libre": return { boite, police: o.meta.taille_police ?? 28, classe: "ed-texte", champ: "contenu", ajuste: true };
    case "forme": return { boite, police: 16, classe: "ed-forme", champ: "contenu" };
    case "cadre": return { boite: { x: o.x, y: o.y - 34, largeur: Math.max(200, o.largeur), hauteur: 30 }, police: 15, classe: "ed-cadre", champ: "titre", uneLigne: true };
    case "fleche": {
      const [p1, p2] = extremitesReelles(o, (id) => {
        const c = b.objet(id);
        return c ? { boite: boiteDe(c), contour: contourDe(c) } : undefined;
      });
      return { boite: { x: (p1.x + p2.x) / 2 - 110, y: (p1.y + p2.y) / 2 - 16, largeur: 220, hauteur: 32 }, police: 14, classe: "ed-fleche", champ: "contenu", uneLigne: true };
    }
    default: return null;
  }
}

export function EditeurTexte({ objet, b, fermer }: { objet: ObjetBoard; b: ServicesBoard; fermer: () => void }) {
  const [tx, ty, zoom] = useStore(transformation, egales);
  const initial = objet.type === "cadre" ? objet.meta.titre ?? "" : objet.contenu;
  const [texte, setTexte] = useState(initial);
  const champ = useRef<HTMLTextAreaElement>(null);
  const fini = useRef(false);
  const zone = zoneDe(objet, b, texte);

  useLayoutEffect(() => {
    const el = champ.current;
    if (!el) return;
    el.focus({ preventScroll: true });
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const valider = (annuler = false) => {
    if (fini.current || !zone) return;
    fini.current = true;
    fermer();
    const valeur = (zone.uneLigne ? texte.replace(/\s*\n\s*/g, " ") : texte).slice(0, zone.champ === "titre" ? 120 : 50_000);
    if (annuler || valeur === initial) {
      // un texte libre resté vide n'a pas lieu d'être : il disparaît (comme dans tout tableau blanc)
      if (objet.type === "texte_libre" && !initial.trim()) void b.supprimer([objet.id]);
      return;
    }
    if (objet.type === "texte_libre" && !valeur.trim()) {
      void b.supprimer([objet.id]);
      return;
    }
    const el = champ.current;
    const taille = zone.ajuste && el ? {
      largeur: Math.round(Math.max(40, Math.min(4000, el.scrollWidth / zoom + 4))), hauteur: Math.round(Math.max(40, Math.min(4000, el.scrollHeight / zoom + 2))),
    } : {};
    void b.modifier([{ id: objet.id, champs: zone.champ === "titre" ? { meta: { ...objet.meta, titre: valeur.trim() || "Cadre" } } : { contenu: valeur, ...taille } }], "Texte");
  };
  // un clic ailleurs (canevas, barre, panneau) retire le focus : `onBlur` enregistre la saisie, elle n'est jamais perdue.
  // Si la fenêtre perd le focus sans que le champ le perde (changement d'onglet), on enregistre aussi.
  const validerRef = useRef(valider);
  validerRef.current = valider;
  useEffect(() => {
    const cache = () => document.visibilityState === "hidden" && validerRef.current();
    document.addEventListener("visibilitychange", cache);
    return () => document.removeEventListener("visibilitychange", cache);
  }, []);

  if (!zone) return null;
  const { boite } = zone;
  return (
    <textarea ref={champ} className={`editeur-texte ${zone.classe} teinte-${(typeof objet.meta.couleur === "string" && objet.meta.couleur) || (objet.type === "adhesif" ? "jaune" : "neutre")}`}
      aria-label={zone.champ === "titre" ? "Titre du cadre" : "Texte de l'objet"} value={texte} maxLength={zone.champ === "titre" ? 120 : 50_000}
      rows={zone.uneLigne ? 1 : undefined} spellCheck
      style={{
        left: boite.x * zoom + tx, top: boite.y * zoom + ty, width: boite.largeur * zoom, height: boite.hauteur * zoom,
        fontSize: zone.police * zoom, padding: zone.classe === "ed-adhesif" ? 16 * zoom : zone.classe === "ed-forme" ? 12 * zoom : undefined,
        ...(zone.ajuste ? { minWidth: boite.largeur * zoom, width: "auto", minHeight: boite.hauteur * zoom, height: "auto", fieldSizing: "content" } as object : {}),
      }}
      onChange={(e) => setTexte(e.target.value)}
      onBlur={() => valider()}
      onPointerDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Escape") { e.preventDefault(); valider(); }
        else if (e.key === "Enter" && (zone.uneLigne || e.ctrlKey || e.metaKey)) { e.preventDefault(); valider(); }
      }} />
  );
}
