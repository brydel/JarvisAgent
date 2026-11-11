// Des objets du Board aux nœuds du canevas : types de nœuds, conversion stable (un objet inchangé garde son nœud,
// donc son rendu), état lu dans l'URL, et jeu d'essai de charge.
import type { Node } from "@xyflow/react";
import { FILTRES, type Filtre } from "../components/Coque";
import { TAILLES } from "../nodes/contexte";
import type { DonneesNoeud, ObjetBoard } from "../types";

const NOMS: Record<string, string> = {
  adhesif: "note adhésive", texte_libre: "texte", forme: "forme", trait: "trait", cadre: "cadre", fleche: "flèche",
};

/** Les cadres passent sous tout le reste (ils encadrent) ; l'ordre entre cadres suit leur z. */
const zDe = (o: ObjetBoard) => (o.type === "cadre" ? o.z - 1_000_000 : o.z);

export function versNoeud(o: ObjetBoard, demo: boolean, sources: number, estompe: boolean, precedent?: Node<DonneesNoeud>): Node<DonneesNoeud> {
  if (precedent && precedent.data.objet === o && precedent.data.sources === sources && (precedent.className === "estompe") === estompe) return precedent;
  const t = TAILLES[o.type]?.defaut ?? [400, 300];
  // une mise à jour distante reçue pendant un glisser ne ramène pas la carte sous le curseur à son ancienne place
  const enGlisser = Boolean(precedent?.dragging);
  const titre = o.meta.titre || o.contenu.slice(0, 40) || o.asset?.nom || "";
  return {
    id: o.id, type: o.type, position: enGlisser ? precedent!.position : { x: o.x, y: o.y }, data: { objet: o, demo, sources },
    width: o.largeur || t[0], height: o.hauteur || t[1], zIndex: zDe(o),
    // verrouillée : jamais déplaçable ; sinon l'outil courant décide (prop nodesDraggable du canevas)
    draggable: o.verrouille ? false : undefined, selected: precedent?.selected ?? false,
    className: estompe ? "estompe" : undefined, ...(enGlisser ? { dragging: true } : {}),
    ariaLabel: `${NOMS[o.type] ?? o.type}${titre ? ` : ${titre}` : ""}`,
  };
}

/** Vrai si l'objet passe le filtre de type, de priorité et de recherche (les objets rangés dans un dossier sont masqués). */
export function estVisible(o: ObjetBoard, filtre: Filtre, priorite: string, recherche: string): boolean {
  if (o.parent_id) return false;
  const f = FILTRES.find((x) => x.cle === filtre);
  if (f && f.types.length && !f.types.includes(o.type)) return false;
  if (priorite && o.priorite !== priorite) return false;
  const q = recherche.trim().toLowerCase();
  if (!q) return true;
  return [o.meta.titre, o.meta.description, o.contenu, o.asset?.nom, o.mission?.objectif, ...(o.meta.tags ?? [])].join(" ").toLowerCase().includes(q);
}

const FILTRES_VALIDES = new Set<string>(FILTRES.map((f) => f.cle));

/** État initial lu dans l'URL ; toute valeur inconnue est ignorée. */
export function lireUrl(): { filtre: Filtre; priorite: string; q: string; carte: string } {
  const p = new URLSearchParams(location.search);
  const f = p.get("filtre") ?? "";
  const pr = p.get("priorite") ?? "";
  const carte = p.get("carte") ?? "";
  return {
    filtre: (FILTRES_VALIDES.has(f) ? f : "tous") as Filtre,
    priorite: ["P1", "P2", "P3"].includes(pr) ? pr : "",
    q: (p.get("q") ?? "").slice(0, 200),
    carte: /^BO-[A-Za-z0-9-]{1,40}$/.test(carte) ? carte : "",
  };
}

/** Mode charge (démo, ?charge=N) : N cartes de types mixtes pour mesurer les performances — le même jeu qu'avant
 *  ce lot, pour comparer. Avec `tableau` (?tableau=1), trois objets sur dix sont des objets de tableau blanc
 *  (adhésifs, formes, traits de 40 points). Jamais en mode réel. */
export function genererCharge(n: number, tableau = false): ObjetBoard[] {
  const types: ObjetBoard["type"][] = tableau ? ["note", "image", "lien", "pdf", "audio", "video", "adhesif", "forme", "note", "trait"]
    : ["note", "image", "lien", "pdf", "audio", "video"];
  const cotes = Math.max(4, Math.ceil(Math.sqrt(n)));
  const couleurs = ["jaune", "rose", "vert", "cyan", "violet", "orange"];
  const formes = ["rectangle", "ellipse", "losange"] as const;
  return Array.from({ length: n }, (_, i) => {
    const type = types[i % types.length]!;
    const dessin = type === "adhesif" || type === "forme" || type === "trait";
    const [l, h] = dessin ? [220, 200] : TAILLES[type]?.defaut ?? [400, 300];
    const meta: ObjetBoard["meta"] = type === "adhesif" ? { couleur: couleurs[i % couleurs.length] }
      : type === "forme" ? { forme: formes[i % 3], couleur: couleurs[i % couleurs.length], epaisseur: 3 }
      : type === "trait" ? { outil: "crayon", couleur: couleurs[i % couleurs.length], epaisseur: 6, boite: [220, 200],
        points: Array.from({ length: 40 }, (_, k) => [10 + k * 5, 100 + Math.round(Math.sin((k + i) / 4) * 70), 50]).flat() }
      : { titre: `Carte ${i}`, url: type === "lien" ? "https://exemple.test" : undefined };
    return {
      id: `BO-charge${i}`, type, espace: "accueil", contenu: type === "note" ? `Note de charge ${i}\n- élément\n- autre` : type === "adhesif" ? `Idée ${i}` : "",
      x: 2000 + (i % cotes) * 520, y: (Math.floor(i / cotes)) * 420, largeur: l, hauteur: h, z: 1, priorite: dessin ? "" : (["P1", "P2", "P3", ""] as const)[i % 4]!,
      meta, asset_id: null, asset: null, mission_id: null, parent_id: null, verrouille: 0, version: 1, cree: 0, maj: 0,
    };
  });
}
