// Chargé à la demande (morceau séparé) : les dessins Notionists pèsent ~300 kB et ne doivent pas retarder l'ouverture.
import { createAvatar } from "@dicebear/core";
import * as notionists from "@dicebear/notionists";

/** Avatar Notionists (DiceBear ; dessins de Zoish sous CC0, code MIT) calculé localement en SVG : aucune requête réseau. */
export function dessiner(graine: string, fond: string): string {
  return createAvatar(notionists, { seed: graine, size: 96, radius: 50, backgroundColor: [fond] }).toDataUri();
}
