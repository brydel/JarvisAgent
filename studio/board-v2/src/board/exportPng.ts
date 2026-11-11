// Export PNG d'une sélection ou d'un cadre (modern-screenshot, MIT). On capture le calque du canevas recadré sur
// la zone, à l'échelle 2 (bornée à 4 096 px de côté). Les iframes et les vidéos ne se capturent pas (contenu d'une
// autre origine, image courante protégée) : elles sont remplacées, le temps de la capture, par un SUBSTITUT statique
// (vignette de la vidéo si elle existe, sinon un bloc étiqueté). Le DOM est toujours remis en état.
import { domToBlob } from "modern-screenshot";
import type { Boite } from "../outils/geometrie";

export const COTE_MAX = 4096;

/** Échelle de capture : 2 par défaut, réduite pour que le plus grand côté ne dépasse pas `max` pixels. */
export function echelleExport(zone: Pick<Boite, "largeur" | "hauteur">, max = COTE_MAX): number {
  return Math.min(2, max / Math.max(1, zone.largeur, zone.hauteur));
}

/** Nom de fichier sûr : lettres, chiffres, tirets (jamais de chemin ni de caractère de contrôle). */
export function nomDeFichier(nom: string): string {
  const propre = nom.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60).toLowerCase();
  return `${propre || "board"}.png`;
}

/** Remplace iframes et vidéos par des substituts statiques ; rend la fonction qui remet tout en place. */
export function poserSubstituts(racine: ParentNode): () => void {
  const retours: (() => void)[] = [];
  for (const media of racine.querySelectorAll<HTMLIFrameElement | HTMLVideoElement>("iframe, video")) {
    const substitut = document.createElement("div");
    substitut.className = "substitut-export";
    substitut.textContent = media instanceof HTMLVideoElement ? "Vidéo (non capturée)" : "Contenu intégré (non capturé)";
    substitut.style.width = `${media.offsetWidth}px`;
    substitut.style.height = `${media.offsetHeight}px`;
    const vignette = media instanceof HTMLVideoElement ? media.poster : "";
    // seulement une vignette servie par le Board lui-même (même origine) : jamais d'adresse externe dans un style
    if (vignette && new URL(vignette, location.href).origin === location.origin) substitut.style.backgroundImage = `url("${encodeURI(vignette)}")`;
    const avant = media.style.display;
    media.before(substitut);
    media.style.display = "none";
    retours.push(() => {
      substitut.remove();
      media.style.display = avant;
    });
  }
  return () => retours.forEach((f) => f());
}

export interface DemandeExport {
  /** calque transformé du canevas (.react-flow__viewport) */
  calque: HTMLElement;
  /** zone à capturer, en coordonnées du canevas */
  zone: Boite;
  /** identifiants des objets à garder ; null : tout ce qui est dans la zone (export d'un cadre) */
  garder: ReadonlySet<string> | null;
  fond: string;
}

export async function capturer({ calque, zone, garder, fond }: DemandeExport): Promise<Blob> {
  const echelle = echelleExport(zone);
  const largeur = Math.ceil(zone.largeur * echelle), hauteur = Math.ceil(zone.hauteur * echelle);
  const remettre = poserSubstituts(calque);
  try {
    return await domToBlob(calque, {
      width: largeur, height: hauteur, backgroundColor: fond, scale: 1, type: "image/png",
      style: { transform: `translate(${-zone.x * echelle}px, ${-zone.y * echelle}px) scale(${echelle})`, transformOrigin: "0 0", width: `${largeur}px`, height: `${hauteur}px` },
      filter: (n) => {
        if (!(n instanceof Element)) return true;
        if (n.classList.contains("react-flow__handle") || n.classList.contains("react-flow__resize-control") || n.classList.contains("fleche-bout")) return false;
        if (garder && n.classList.contains("react-flow__node")) return garder.has(n.getAttribute("data-id") ?? "");
        if (garder && n.classList.contains("react-flow__edges")) return false;
        return true;
      },
    });
  } finally {
    remettre();
  }
}

export function telechargerBlob(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nom;
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}
