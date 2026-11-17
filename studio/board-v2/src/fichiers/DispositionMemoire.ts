import type { Relation } from "./graphe";
import type { GroupeMemoire } from "./GroupesMemoire";

type Point = { x: number; y: number };
const ANGLE_DORE = Math.PI * (3 - Math.sqrt(5));
const ITERATIONS = 72;

export function centresMemoire(groupes: readonly GroupeMemoire[], centre: string | null) {
  const explicites = groupes.filter((g) => g.explicite).sort((a, b) => a.ancre.localeCompare(b.ancre));
  if (explicites.length) {
    const resultat = new Map<string, Point>();
    const rayon = explicites.length === 1 ? 0 : Math.max(430, 200 * Math.sqrt(explicites.length));
    explicites.forEach((g, i) => {
      const angle = i / explicites.length * 2 * Math.PI - Math.PI / 2;
      resultat.set(g.ancre, { x: Math.round(rayon * Math.cos(angle) * 1000) / 1000,
        y: Math.round(rayon * Math.sin(angle) * 1000) / 1000 });
    });
    groupes.filter((g) => !g.explicite && g.ids.length > 1).forEach((g, i) => {
      const distance = 110 + 70 * Math.sqrt(i);
      resultat.set(g.ancre, { x: distance * Math.cos(i * ANGLE_DORE), y: distance * Math.sin(i * ANGLE_DORE) });
    });
    return resultat;
  }
  const lies = groupes.filter((g) => g.ids.length > 1);
  const principal = lies.find((g) => g.ids.includes(centre ?? "")) ?? lies[0];
  const resultat = new Map<string, Point>();
  let satellite = 0;
  for (const groupe of lies) {
    const rang = groupe === principal ? 0 : ++satellite;
    const rayon = 285 * Math.sqrt(rang);
    resultat.set(groupe.ancre, { x: rayon * Math.cos(rang * ANGLE_DORE), y: rayon * Math.sin(rang * ANGLE_DORE) });
  }
  return resultat;
}

export function disposerMemoire(ids: string[], relations: Relation[], centre: string | null, groupes: readonly GroupeMemoire[] = []): Map<string, Point> {
  const ordre = [...ids].sort();
  const index = new Map(ordre.map((id, i) => [id, i]));
  const racine = centre === null ? undefined : index.get(centre);
  const centres = centresMemoire(groupes, centre);
  const cibles = new Map<string, Point>();
  for (const groupe of groupes) {
    const cible = centres.get(groupe.ancre);
    if (cible) for (const id of groupe.ids) cibles.set(id, cible);
  }
  const points = ordre.map((id, i) => {
    const cible = cibles.get(id) ?? { x: 0, y: 0 };
    const rayon = i === racine ? 0 : 36 * Math.sqrt(i + 1);
    return { x: cible.x + rayon * Math.cos(i * ANGLE_DORE), y: cible.y + rayon * Math.sin(i * ANGLE_DORE), vx: 0, vy: 0 };
  });
  const ressorts = new Map<string, [number, number]>();
  for (const r of relations) {
    const a = index.get(r.source), b = index.get(r.cible);
    if (a === undefined || b === undefined || a === b) continue;
    ressorts.set(Math.min(a, b) + ":" + Math.max(a, b), [a, b]);
  }

  // La projection bornée et ses centroïdes sont stabilisés avant affichage.
  for (let tour = 0; tour < ITERATIONS; tour += 1) {
    const refroidissement = 1 - tour / ITERATIONS;
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i]!;
      const cible = cibles.get(ordre[i]!) ?? { x: 0, y: 0 };
      a.vx -= (a.x - cible.x) * .018;
      a.vy -= (a.y - cible.y) * .022;
      for (let j = i + 1; j < points.length; j += 1) {
        const b = points[j]!;
        const dx = b.x - a.x, dy = b.y - a.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const force = Math.min(26, 22_000 / (distance * distance) + Math.max(0, 58 - distance) * .18);
        const fx = dx / distance * force, fy = dy / distance * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }
    for (const [i, j] of ressorts.values()) {
      const a = points[i]!, b = points[j]!;
      const dx = b.x - a.x, dy = b.y - a.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const force = (distance - 100) * .09;
      const fx = dx / distance * force, fy = dy / distance * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }
    points.forEach((p, i) => {
      p.x += i === racine ? 0 : Math.max(-17, Math.min(17, p.vx)) * refroidissement;
      p.y += i === racine ? 0 : Math.max(-17, Math.min(17, p.vy)) * refroidissement;
      p.vx *= .58;
      p.vy *= .58;
    });
  }
  return new Map(ordre.map((id, i) => [id, { x: points[i]!.x, y: points[i]!.y }]));
}
