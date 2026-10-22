export function taille(octets: number): string {
  if (!octets) return "";
  if (octets < 1024) return `${octets} o`;
  const u = ["KB", "MB", "GB"];
  let v = octets / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${u[i]}`;
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

export function ilya(ts: number): string {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "à l'instant";
  if (s < 3600) return `Il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `Il y a ${Math.round(s / 3600)} h`;
  return `Il y a ${Math.round(s / 86400)} j`;
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
