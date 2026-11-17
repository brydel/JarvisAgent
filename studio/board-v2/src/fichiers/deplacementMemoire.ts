import type { Point } from "./GroupesMemoire";

export const idCentroide = (groupe: string) => "centroide:" + groupe;

/** Translate les seuls membres du lot, à partir d’un instantané du début du geste. */
export function translaterLot(positions: ReadonlyMap<string, Point>, origine: string, destination: Point,
  membres: readonly string[]) {
  const suite = new Map(positions);
  const depart = positions.get(origine);
  if (!depart) return suite;
  const dx = destination.x - depart.x, dy = destination.y - depart.y;
  for (const id of new Set([origine, ...membres])) {
    const point = positions.get(id);
    if (point) suite.set(id, { x: point.x + dx, y: point.y + dy });
  }
  return suite;
}

/** Les nouveaux membres suivent le décalage du centre déjà placé, sans modifier les points dessinés. */
export function positionsMemoire(points: ReadonlyMap<string, Point>, personnelles: ReadonlyMap<string, Point>,
  lots: ReadonlyMap<string, readonly string[]>) {
  const resultat = new Map([...personnelles, ...points]);
  for (const [centre, membres] of lots) {
    const origine = points.get(centre), place = personnelles.get(centre);
    if (!origine || !place) continue;
    for (const id of membres) {
      const point = points.get(id);
      if (point && !personnelles.has(id)) {
        resultat.set(id, { x: point.x + place.x - origine.x, y: point.y + place.y - origine.y });
      }
    }
  }
  for (const [id, point] of personnelles) {
    if (points.has(id)) resultat.set(id, point);
  }
  return resultat;
}
