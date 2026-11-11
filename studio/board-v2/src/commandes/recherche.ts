// Recherche floue de la palette : sans accents ni casse, lettres dans l'ordre (« alg » trouve « Aligner à gauche »),
// avec une prime aux débuts de mots et aux lettres contiguës. Petit, déterministe, testé.

export function sansAccents(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

const debutDeMot = (t: string, j: number) => j === 0 || /[\s\-_/.:'’(]/.test(t[j - 1]!);

/** Parcours de `q` dans `t`. `initiales` : chaque lettre cherche d'abord un début de mot plus loin (« alg » →
 *  A·L·igner à G·auche) avant de se rabattre sur la prochaine occurrence. −1 si les lettres n'y sont pas dans l'ordre. */
function parcourir(q: string, t: string, initiales: boolean, depart = 0): number {
  let j = depart, total = 0, suite = 0, precedent = -2, premier = -1;
  for (let i = 0; i < q.length; i++) {
    let trouve = -1;
    if (initiales && i > 0) {
      for (let k = j; k < t.length; k++) if (t[k] === q[i] && debutDeMot(t, k)) { trouve = k; break; }
    }
    if (trouve < 0) trouve = t.indexOf(q[i]!, j);
    if (trouve < 0) return -1;
    suite = trouve === precedent + 1 ? suite + 1 : 1;
    total += 1 + (debutDeMot(t, trouve) ? 6 : 0) + (suite > 1 ? 3 * Math.min(suite, 4) : 0) + (trouve === i ? 2 : 0);
    if (premier < 0) premier = trouve;
    precedent = trouve;
    j = trouve + 1;
  }
  // des lettres éparpillées d'un bout à l'autre du texte ne sont pas une correspondance : du bruit dans la palette
  if (precedent - premier + 1 > Math.max(10, q.length * 4)) return -1;
  return total;
}

/** Score de `requete` dans `texte` : −1 si les lettres n'y sont pas dans l'ordre, sinon plus c'est haut, mieux c'est. */
export function score(requete: string, texte: string): number {
  const q = sansAccents(requete).replace(/\s+/g, "");
  const t = sansAccents(texte);
  if (!q) return 0;
  // trois lectures : au plus tôt, par initiales de mots, et à partir de la requête retrouvée d'un seul tenant
  const tenant = t.indexOf(q);
  const meilleur = Math.max(parcourir(q, t, false), parcourir(q, t, true), tenant > 0 ? parcourir(q, t, false, tenant) : -1);
  if (meilleur < 0) return -1;
  // la requête entière retrouvée telle quelle l'emporte sur des lettres dispersées
  const direct = t.indexOf(sansAccents(requete).trim());
  return meilleur + (direct === 0 ? 40 : direct > 0 ? 20 : 0) - Math.min(10, t.length / 20);
}

export interface Trouve<T> {
  element: T;
  score: number;
}

/** Classe `elements` par pertinence ; à score égal, l'ordre d'origine est conservé (tri stable). */
export function chercher<T>(requete: string, elements: readonly T[], texte: (e: T) => string, bonus?: (e: T) => number): Trouve<T>[] {
  const sorties: Trouve<T>[] = [];
  for (const element of elements) {
    const s = score(requete, texte(element));
    if (s >= 0) sorties.push({ element, score: s + (bonus?.(element) ?? 0) });
  }
  return sorties.sort((a, b) => b.score - a.score);
}
