// Ingestion côté navigateur : ce qu'on colle ou dépose devient une liste d'éléments typés (jamais un bloc de texte
// concaténé). La validation qui compte est faite par le serveur (type reconnu par les octets, tailles, SSRF).
export type Element =
  | { sorte: "fichier"; fichier: File }
  | { sorte: "url"; url: string }
  | { sorte: "texte"; texte: string };

const URL_RE = /\bhttps?:\/\/[^\s<>"')]+/gi;
const MAX_ELEMENTS = 30;

export function depuisTexte(texte: string): Element[] {
  const t = texte.trim();
  if (!t) return [];
  const urls = t.match(URL_RE) ?? [];
  const reste = t.replace(URL_RE, "").replace(/[\s,;|]+/g, " ").trim();
  // une ou plusieurs adresses seules : une carte lien par adresse ; sinon une note (les liens restent dans le texte)
  if (urls.length && !reste) return [...new Set(urls)].slice(0, MAX_ELEMENTS).map((url) => ({ sorte: "url" as const, url }));
  return [{ sorte: "texte", texte: t.slice(0, 50_000) }];
}

export function depuisTransfert(dt: DataTransfer | null): Element[] {
  if (!dt) return [];
  const fichiers = Array.from(dt.files ?? []);
  if (fichiers.length) return fichiers.slice(0, MAX_ELEMENTS).map((fichier) => ({ sorte: "fichier" as const, fichier }));
  const uriList = dt.getData("text/uri-list");
  if (uriList) {
    const urls = uriList.split(/\r?\n/).filter((l) => l && !l.startsWith("#"));
    if (urls.length) return urls.slice(0, MAX_ELEMENTS).map((url) => ({ sorte: "url" as const, url }));
  }
  return depuisTexte(dt.getData("text/plain"));
}

/** Famille d'un fichier pour choisir la carte (le serveur re-vérifie par le contenu). */
export function familleFichier(f: File): "image" | "audio" | "video" | "pdf" | null {
  if (f.type.startsWith("image/") && f.type !== "image/svg+xml") return "image";
  if (f.type.startsWith("audio/")) return "audio";
  if (f.type.startsWith("video/")) return "video";
  if (f.type === "application/pdf" || /\.pdf$/i.test(f.name)) return "pdf";
  return null;
}

/** Positions en cascade autour d'un point, pour plusieurs éléments collés d'un coup. */
export function cascade(x: number, y: number, i: number): { x: number; y: number } {
  const col = i % 4;
  const ligne = Math.floor(i / 4);
  return { x: x + col * 520, y: y + ligne * 420 };
}
