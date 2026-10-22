// Médias : un seul lecteur actif à la fois ; formes d'onde calculées à partir du fichier réel (jamais inventées) ;
// visibilité pour différer le travail coûteux.
import { useEffect, useRef, useState } from "react";

const EVT = "jarvis:lecture";

/** Signale le début d'une lecture : les autres lecteurs se mettent en pause. */
export function annoncerLecture(id: string) {
  window.dispatchEvent(new CustomEvent(EVT, { detail: id }));
}
export function surAutreLecture(id: string, pause: () => void) {
  const f = (e: Event) => {
    if ((e as CustomEvent<string>).detail !== id) pause();
  };
  window.addEventListener(EVT, f);
  return () => window.removeEventListener(EVT, f);
}

/** Vrai dès que l'élément a été visible (puis reste vrai : on ne refait pas le travail). */
export function useVisible<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || visible) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver((entrees) => {
      if (entrees.some((e) => e.isIntersecting)) {
        setVisible(true);
        io.disconnect();
      }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);
  return [ref, visible];
}

const cacheOndes = new Map<string, Promise<number[] | null>>();
const ONDE_MAX_OCTETS = 40 * 1024 * 1024;

/** Pics normalisés (0–1) du fichier audio, calculés par Web Audio. null si impossible (taille, codec). */
export function formeOnde(url: string, barres = 72): Promise<number[] | null> {
  const cle = `${url}#${barres}`;
  let p = cacheOndes.get(cle);
  if (!p) {
    p = (async () => {
      try {
        const r = await fetch(url, { credentials: "same-origin" });
        const n = Number(r.headers.get("Content-Length") || 0);
        if (!r.ok || n > ONDE_MAX_OCTETS) return null;
        const buf = await r.arrayBuffer();
        const Ctx = window.OfflineAudioContext;
        const ctx = new Ctx(1, 1, 44100);
        const audio = await ctx.decodeAudioData(buf);
        const data = audio.getChannelData(0);
        const pas = Math.max(1, Math.floor(data.length / barres));
        const pics: number[] = [];
        for (let i = 0; i < barres; i++) {
          let max = 0;
          for (let j = i * pas; j < Math.min(data.length, (i + 1) * pas); j += 16) max = Math.max(max, Math.abs(data[j] ?? 0));
          pics.push(max);
        }
        const plafond = Math.max(...pics, 0.0001);
        return pics.map((v) => v / plafond);
      } catch {
        return null;
      }
    })();
    cacheOndes.set(cle, p);
  }
  return p;
}
