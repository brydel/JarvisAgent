// Ingestion : ce qui arrive de l'extérieur (fichiers déposés, presse-papiers, adresse saisie) devient des cartes.
// Tout texte reste du texte ; une adresse n'est acceptée que si lib/ingestion.ts la reconnaît (http/https).
import { useCallback, useEffect, useRef, type RefObject } from "react";
import type { Source } from "../api";
import type { ServicesBoard } from "../commandes/contexte";
import { dansChamp } from "../commandes/raccourcis";
import type { FileEcritures } from "../donnees/ecritures";
import { cascade, depuisTexte, depuisTransfert, familleFichier, type Element } from "../lib/ingestion";
import { TAILLES } from "../nodes/contexte";
import type { Point } from "../outils/geometrie";
import { MARQUEUR_PRESSE_PAPIERS } from "./useServices";

export interface Ingestion {
  ingerer(elements: Element[], ou?: Point): Promise<void>;
  collerPressePapiers(): Promise<void>;
  choisirFichiers(accept: string): void;
  champFichier: RefObject<HTMLInputElement | null>;
}

export function useIngestion(source: Source, file: FileEcritures, b: () => ServicesBoard): Ingestion {
  const champFichier = useRef<HTMLInputElement>(null);

  const ingerer = useCallback(async (elements: Element[], ou?: Point) => {
    if (!elements.length) return;
    const s = b();
    const base = ou ?? s.centreVue();
    let i = 0;
    const fichiers = elements.filter((e) => e.sorte === "fichier").length;
    if (fichiers) s.toast(`Téléversement de ${fichiers} fichier${fichiers > 1 ? "s" : ""}…`);
    for (const e of elements) {
      const p = cascade(base.x, base.y, i++);
      try {
        if (e.sorte === "texte") {
          await s.creer({ type: "note", contenu: e.texte, ...p, largeur: 408, hauteur: 320, meta: { titre: e.texte.split("\n")[0]?.slice(0, 60) || "Note" } });
        } else if (e.sorte === "url") {
          let hote = e.url;
          try { hote = new URL(e.url).hostname; } catch { /* adresse brute */ }
          const id = await s.creer({ type: "lien", contenu: e.url, ...p, largeur: 434, hauteur: 356, meta: { url: e.url, hote, titre: hote } });
          source.apercu(e.url).then(async (a) => {
            await file.modifier([{ id, champs: { meta: { url: a.url, hote: a.hote, titre: a.titre || a.hote, description: a.description, site: a.site,
              apercu_image: a.image, favicon: a.favicon } } }]);
          }).catch(async (x: Error) => {
            await file.modifier([{ id, champs: { meta: { url: e.url, hote, titre: hote, apercu_erreur: x.message } } }]);
          });
        } else {
          const famille = familleFichier(e.fichier);
          if (!famille) {
            s.toast(`« ${e.fichier.name} » : type non pris en charge (image, audio, vidéo, PDF)`, { erreur: true });
            continue;
          }
          const a = await source.televerser(e.fichier);
          const [l, h] = TAILLES[famille]?.defaut ?? [400, 300];
          const ratio = a.meta.largeur && a.meta.hauteur ? a.meta.hauteur / a.meta.largeur : 0;
          await s.creer({ type: famille, ...p, largeur: l, hauteur: famille === "image" && ratio ? Math.round(l * ratio) + 72 : h,
            asset_id: a.id, meta: { titre: e.fichier.name.replace(/\.[^.]+$/, "") } });
        }
      } catch (x) {
        s.toast(x instanceof Error ? x.message : "ajout impossible", { erreur: true });
      }
    }
  }, [source, file, b]);

  // Coller (Ctrl+V) : les objets copiés dans le Board, sinon fichiers et images du presse-papiers, adresse, texte
  useEffect(() => {
    const surColler = (e: ClipboardEvent) => {
      if (dansChamp(e.target)) return;
      const texte = e.clipboardData?.getData("text/plain") ?? "";
      if (texte.startsWith(MARQUEUR_PRESSE_PAPIERS) && b().peutColler()) {
        e.preventDefault();
        void b().coller();
        return;
      }
      const elements = depuisTransfert(e.clipboardData);
      if (elements.length) {
        e.preventDefault();
        void ingerer(elements);
      }
    };
    window.addEventListener("paste", surColler);
    return () => window.removeEventListener("paste", surColler);
  }, [ingerer, b]);

  const collerPressePapiers = useCallback(async () => {
    const s = b();
    try {
      const items = await navigator.clipboard.read();
      const elements: Element[] = [];
      for (const it of items) {
        const typeImage = it.types.find((t) => t.startsWith("image/"));
        if (typeImage) {
          const blob = await it.getType(typeImage);
          elements.push({ sorte: "fichier", fichier: new File([blob], `presse-papiers.${typeImage.split("/")[1]}`, { type: typeImage }) });
        } else if (it.types.includes("text/plain")) {
          elements.push(...depuisTexte(await (await it.getType("text/plain")).text()));
        }
      }
      if (elements.length) void ingerer(elements, s.centreVue());
      else s.toast("Presse-papiers vide");
    } catch {
      s.toast("Accès au presse-papiers refusé : utilise Ctrl+V sur le Board", { erreur: true });
    }
  }, [ingerer, b]);

  const choisirFichiers = useCallback((accept: string) => {
    if (!champFichier.current) return;
    champFichier.current.accept = accept;
    champFichier.current.click();
  }, []);

  return { ingerer, collerPressePapiers, choisirFichiers, champFichier };
}
