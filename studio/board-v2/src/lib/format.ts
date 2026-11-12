/** La même mention partout où l'écran montre des données de démonstration. Ce n'est pas un crédit : pas de filet. */
export const MENTION_DEMO = "Démonstration · données fictives, rien n'est lancé";

export function taille(octets: number): string {
  if (!octets) return "";
  if (octets < 1024) return `${octets} o`;
  const u = ["Ko", "Mo", "Go"];
  let v = octets / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 ? v.toFixed(1).replace(".", ",") : Math.round(v)} ${u[i]}`;
}

export function duree(s: number | undefined): string {
  if (!s || !Number.isFinite(s)) return "00:00";
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const x = t % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(x)}` : `${p(m)}:${p(x)}`;
}

/** Le relatif ne sert que dans un fil d'activité, en minuscules. */
export function ilya(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
}

// Une seule écriture des dates dans tout le produit (fr-CA) : « 12 nov. » pour l'année en cours, « 12 nov. 2025 » sinon.
const JOUR = new Intl.DateTimeFormat("fr-CA", { day: "numeric", month: "short" });
const JOUR_AN = new Intl.DateTimeFormat("fr-CA", { day: "numeric", month: "short", year: "numeric" });
const HEURE = new Intl.DateTimeFormat("fr-CA", { hour: "2-digit", minute: "2-digit", hour12: false });

/** Date : « 12 nov. », avec l'année si ce n'est pas l'année en cours. `ts` en secondes. */
export function dateCourte(ts: number, maintenant = Date.now()): string {
  const d = new Date(ts * 1000);
  return (d.getFullYear() === new Date(maintenant).getFullYear() ? JOUR : JOUR_AN).format(d);
}

/** Date et heure : « 12 nov. · 04:11 ». `ts` en secondes. */
export function dateHeure(ts: number, maintenant = Date.now()): string {
  const h = HEURE.formatToParts(new Date(ts * 1000));
  const p = (t: string) => h.find((x) => x.type === t)?.value ?? "00";
  return `${dateCourte(ts, maintenant)} · ${p("hour")}:${p("minute")}`;
}

export function extension(mime: string, nom: string): string {
  const e = nom.split(".").pop() ?? "";
  if (e && e.length <= 4) return e.toUpperCase();
  return (mime.split("/")[1] ?? "").toUpperCase();
}

export const LIBELLE_TYPE: Record<string, string> = {
  analyse_document: "Analyse du document", recherche: "Recherche", design: "Design", developpement: "Développement",
  tests: "Tests", envoi_candidature: "Envoi de candidature",
};

export function libelleTache(t: { type: string; libelle?: string }): string {
  return t.libelle || LIBELLE_TYPE[t.type] || t.type.replace(/_/g, " ");
}
