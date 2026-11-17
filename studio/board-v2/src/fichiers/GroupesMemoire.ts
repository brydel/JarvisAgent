import type { Entite, Relation } from "./graphe";
import { idCentroide } from "./deplacementMemoire";

export type Point = { x: number; y: number };
export type GroupeMemoire = { ancre: string; ids: string[]; titre?: string; projet?: string; explicite?: boolean; nature?: "session" | "hors_session" };

function empreinteGroupe(id: string) {
  let graine = 2166136261;
  for (const lettre of id) graine = Math.imul(graine ^ lettre.charCodeAt(0), 16777619);
  graine = Math.imul(graine ^ (graine >>> 16), 0x7feb352d);
  graine = Math.imul(graine ^ (graine >>> 15), 0x846ca68b);
  return (graine ^ (graine >>> 16)) >>> 0;
}

export function teintesGroupes(groupes: readonly GroupeMemoire[]) {
  const variables = new Map<string, string>();
  const styles: Record<string, string> = {};
  for (const groupe of [...groupes].sort((a, b) => a.ancre.localeCompare(b.ancre))) {
    const empreinte = empreinteGroupe(groupe.ancre);
    const variable = "--mf-groupe-" + empreinte;
    const angle = (empreinte / 0x100000000 * 360).toFixed(3);
    variables.set(groupe.ancre, variable);
    styles[variable] = `oklch(var(--mf-groupe-luminosite) 0.13 ${angle})`;
  }
  return { variables, styles };
}

export function voisinage(ids: readonly string[], relations: readonly Relation[]) {
  const graphe = new Map(ids.map((id) => [id, new Set<string>()]));
  for (const { source, cible } of relations) {
    if (source === cible || !graphe.has(source) || !graphe.has(cible)) continue;
    graphe.get(source)!.add(cible);
    graphe.get(cible)!.add(source);
  }
  return graphe;
}

export function distances(graphe: ReadonlyMap<string, ReadonlySet<string>>, origine: string) {
  const mesure = new Map([[origine, 0]]);
  const queue = [origine];
  for (let i = 0; i < queue.length; i += 1) {
    const id = queue[i]!;
    for (const ami of graphe.get(id) ?? []) {
      if (mesure.has(ami)) continue;
      mesure.set(ami, mesure.get(id)! + 1);
      queue.push(ami);
    }
  }
  return mesure;
}

// Des centres espacés d'au moins trois liens séparent les zones d'une même composante.
export function grouperMemoire(graphe: ReadonlyMap<string, ReadonlySet<string>>, preferes: ReadonlySet<string>,
  priorites?: ReadonlyMap<string, number>) {
  const groupes: GroupeMemoire[] = [];
  const visites = new Set<string>();
  const ordre = [...graphe.keys()].sort((a, b) => (priorites?.get(b) ?? Number(preferes.has(b)))
    - (priorites?.get(a) ?? Number(preferes.has(a))) || graphe.get(b)!.size - graphe.get(a)!.size || a.localeCompare(b));
  for (const id of ordre) {
    if (visites.has(id)) continue;
    const composante = distances(graphe, id);
    for (const noeud of composante.keys()) visites.add(noeud);
    const centres = [{ id, d: composante }];
    for (const candidat of ordre) {
      if (!composante.has(candidat) || graphe.get(candidat)!.size < 2) continue;
      if (centres.every((centre) => centre.d.get(candidat)! > 2)) centres.push({ id: candidat, d: distances(graphe, candidat) });
    }
    const membres = new Map(centres.map((centre) => [centre.id, [] as string[]]));
    for (const noeud of composante.keys()) {
      const proche = centres.reduce((a, b) => a.d.get(noeud)! <= b.d.get(noeud)! ? a : b);
      membres.get(proche.id)!.push(noeud);
    }
    for (const [ancre, ids] of membres) groupes.push({ ancre, ids });
  }
  return groupes;
}

export function contourMemoire(points: readonly Point[], marge = 26) {
  const triangles = points.flatMap(({ x, y }) => [
    { x: x - marge, y: y - marge }, { x: x - marge, y: y + marge },
    { x: x + marge, y: y - marge }, { x: x + marge, y: y + marge },
  ]).sort((a, b) => a.x - b.x || a.y - b.y);
  const demiContour = (ordre: readonly Point[]) => {
    const coque: Point[] = [];
    for (const point of ordre) {
      while (coque.length >= 2) {
        const a = coque.at(-2)!, b = coque.at(-1)!;
        if ((b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x) > 0) break;
        coque.pop();
      }
      coque.push(point);
    }
    return coque.slice(0, -1);
  };
  return [...demiContour(triangles), ...demiContour(triangles.reverse())];
}

/** Ces arcs représentent l’appartenance prouvée d’un même point à plusieurs sessions. */
export function relationsSessionsPartagees(entites: ReadonlyMap<string, Entite>, ids: readonly string[],
  groupes: readonly GroupeMemoire[]) {
  const sessions = new Set(groupes.filter((g) => g.explicite && g.nature === "session").map((g) => g.ancre));
  const resultat: Relation[] = [];
  for (const id of ids) {
    const appartenances = entites.get(id)?.sessionIds ?? [];
    if (appartenances.length < 2) continue;
    for (const session of new Set(appartenances)) {
      if (sessions.has(session)) resultat.push({ id: "appartenance:" + session + ":" + id,
        source: idCentroide(session), cible: id, style: "source", texte: "Élément partagé de la session" });
    }
  }
  return resultat;
}
