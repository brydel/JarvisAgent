import { memo, useEffect, useRef, useState } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import { Maximize, Pause, Play, Plus } from "lucide-react";
import type { DonneesNoeud } from "../types";
import { duree, extension, taille } from "../lib/format";
import { annoncerLecture, formeOnde, surAutreLecture, useVisible } from "../lib/medias";
import { CardShell, MenuCarte, BadgePriorite } from "./CardShell";

type P = NodeProps<Node<DonneesNoeud>>;
const VITESSES = [1, 1.25, 1.5, 2, 0.75];

/** Le navigateur saura-t-il décoder ce type ? Vérifié AVANT de lancer la lecture (sinon certains échouent en silence). */
function decodable(mime: string | undefined, sorte: "audio" | "video"): boolean {
  if (!mime) return true;
  return document.createElement(sorte).canPlayType(mime) !== "";
}
const CODEC = "Format ou codec non pris en charge par ce navigateur. Ouvre le Board dans Chrome ou Edge, ou importe une version WebM / MP3.";

function messageErreur(m: HTMLMediaElement): string {
  const e = m.error;
  if (!e) return "Lecture impossible.";
  return e.code === 4 ? CODEC : e.code === 2 ? "Erreur réseau pendant le chargement."
    : e.code === 3 ? "Fichier endommagé (décodage impossible)." : "Lecture interrompue.";
}

/* ---------------------------------------------------------------- audio ------------------------------------ */
export const AudioNode = memo(function AudioNode({ data, selected }: P) {
  const o = data.objet;
  const a = o.asset;
  const src = a?.url ?? (o.meta.demo_src as string | undefined);
  const audio = useRef<HTMLAudioElement>(null);
  const toile = useRef<HTMLCanvasElement>(null);
  const [ref, visible] = useVisible<HTMLDivElement>();
  const [lecture, setLecture] = useState(false);
  const [t, setT] = useState(0);
  const [total, setTotal] = useState(a?.meta.duree ?? 0);
  const [vitesse, setVitesse] = useState(1);
  const [pics, setPics] = useState<number[] | null | undefined>(undefined);
  const [erreur, setErreur] = useState("");

  useEffect(() => surAutreLecture(o.id, () => audio.current?.pause()), [o.id]);
  useEffect(() => {
    if (visible && src) formeOnde(src).then(setPics);
  }, [visible, src]);
  useEffect(() => {
    const c = toile.current;
    if (!c || !pics) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr;
    c.height = h * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, w, h);
    const pas = w / pics.length;
    const fait = total ? t / total : 0;
    pics.forEach((v, i) => {
      const bh = Math.max(3, v * h * 0.95);
      g.fillStyle = i / pics.length <= fait ? "#8EA0FF" : i / pics.length < 0.62 ? "#5B6CFF" : "#3A4260";
      g.beginPath();
      g.roundRect(i * pas + pas * 0.25, (h - bh) / 2, Math.max(1.5, pas * 0.5), bh, 2);
      g.fill();
    });
  }, [pics, t, total]);

  const basculer = async () => {
    const m = audio.current;
    if (!m) return;
    if (!decodable(a?.mime, "audio")) {
      setErreur(CODEC);
      return;
    }
    if (m.paused) {
      annoncerLecture(o.id);
      try {
        await m.play();
      } catch {
        setErreur(messageErreur(m));
      }
    } else m.pause();
  };
  const chercher = (e: React.PointerEvent<HTMLDivElement>) => {
    const m = audio.current;
    if (!m || !total) return;
    const r = e.currentTarget.getBoundingClientRect();
    m.currentTime = Math.min(total, Math.max(0, ((e.clientX - r.left) / r.width) * total));
  };
  return (
    <CardShell objet={o} selected={selected} classe="c-audio" entete={false}>
      <div className="haut">
        <BadgePriorite p={o.priorite} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="titre-carte">{o.meta.titre || a?.nom || "Audio"}</div>
          <div className="meta-carte tab-num">{[a && extension(a.mime, a.nom), duree(total), a && taille(a.taille)].filter(Boolean).join(" · ")}</div>
        </div>
        <MenuCarte objet={o} />
      </div>
      <div className="lecteur" ref={ref}>
        <button type="button" className="bouton-lecture nodrag" onClick={basculer} aria-label={lecture ? "Pause" : "Lecture"}>
          {lecture ? <Pause size={24} fill="currentColor" /> : <Play size={24} fill="currentColor" style={{ marginLeft: 3 }} />}
        </button>
        <div className="onde nodrag nopan" onPointerDown={chercher} role="slider" aria-label="Position de lecture"
          aria-valuemin={0} aria-valuemax={Math.round(total)} aria-valuenow={Math.round(t)} tabIndex={0}
          onKeyDown={(e) => {
            const m = audio.current;
            if (!m) return;
            if (e.key === "ArrowRight") m.currentTime = Math.min(total, m.currentTime + 5);
            if (e.key === "ArrowLeft") m.currentTime = Math.max(0, m.currentTime - 5);
          }}>
          <canvas ref={toile} />
          {pics === null && <span className="indisponible">Forme d'onde non calculable pour ce fichier</span>}
        </div>
        <div className="temps tab-num">
          {duree(t)} / {duree(total)}
          <button type="button" className="vitesse nodrag" aria-label="Vitesse de lecture" onClick={() => {
            const v = VITESSES[(VITESSES.indexOf(vitesse) + 1) % VITESSES.length] ?? 1;
            setVitesse(v);
            if (audio.current) audio.current.playbackRate = v;
          }}>{vitesse}x ⌄</button>
          <span style={{ width: 18 }} />
          <Plus size={20} aria-hidden="true" />
        </div>
      </div>
      {src && (
        <audio ref={audio} src={src} preload="metadata" onPlay={() => setLecture(true)} onPause={() => setLecture(false)}
          onTimeUpdate={(e) => setT(e.currentTarget.currentTime)} onLoadedMetadata={(e) => {
            if (Number.isFinite(e.currentTarget.duration)) setTotal(e.currentTarget.duration);
          }}
          onEnded={() => setLecture(false)} onError={(e) => setErreur(messageErreur(e.currentTarget))} />
      )}
      {erreur && <div className="erreur-media" role="alert">{erreur}</div>}
    </CardShell>
  );
});

/* ---------------------------------------------------------------- vidéo ------------------------------------ */
export const VideoNode = memo(function VideoNode({ data, selected }: P) {
  const o = data.objet;
  const a = o.asset;
  const video = useRef<HTMLVideoElement>(null);
  const [actif, setActif] = useState(false);
  const [lecture, setLecture] = useState(false);
  const [t, setT] = useState(0);
  const [total, setTotal] = useState(a?.meta.duree ?? 0);
  const [erreur, setErreur] = useState("");
  const vignette = a?.vignette_url ?? (o.meta.demo_vignette as string | undefined);
  useEffect(() => surAutreLecture(o.id, () => video.current?.pause()), [o.id]);
  const demarrer = () => {
    if (!decodable(a?.mime, "video")) {
      setErreur(CODEC);
      return;
    }
    setActif(true);
    annoncerLecture(o.id);
    requestAnimationFrame(() => video.current?.play().catch(() => video.current && setErreur(messageErreur(video.current))));
  };
  const basculer = () => {
    const v = video.current;
    if (!v) return demarrer();
    if (v.paused) {
      annoncerLecture(o.id);
      v.play().catch(() => setErreur(messageErreur(v)));
    } else v.pause();
  };
  return (
    <CardShell objet={o} selected={selected} classe="c-video" ratio={false}>
      <div className="ecran">
        {actif && a ? (
          <video ref={video} src={a.url} poster={vignette ?? undefined} preload="metadata" playsInline className="nodrag"
            onPlay={() => setLecture(true)} onPause={() => setLecture(false)} onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => Number.isFinite(e.currentTarget.duration) && setTotal(e.currentTarget.duration)}
            onError={(e) => setErreur(messageErreur(e.currentTarget))} onClick={basculer} />
        ) : vignette ? <img src={vignette} alt="" loading="lazy" draggable={false} /> : null}
      </div>
      {!actif && <div className="voile" />}
      {!actif && (
        <>
          <button type="button" className="lecture-centre nodrag" onClick={demarrer} aria-label="Lire la vidéo">
            <Play size={26} fill="currentColor" style={{ marginLeft: 3 }} />
          </button>
          <div className="bas">
            <button type="button" className="petit-lecture nodrag" onClick={demarrer} aria-label="Lire la vidéo"><Play size={17} fill="currentColor" /></button>
            <div style={{ minWidth: 0 }}>
              <div className="titre-carte">{o.meta.titre || a?.nom || "Vidéo"}</div>
              <div className="meta-carte tab-num">{[a && extension(a.mime, a.nom), duree(total), a && taille(a.taille)].filter(Boolean).join(" · ")}</div>
            </div>
          </div>
        </>
      )}
      {actif && (
        <div className="controles nodrag nopan">
          <button type="button" onClick={basculer} aria-label={lecture ? "Pause" : "Lecture"}>{lecture ? <Pause size={16} /> : <Play size={16} />}</button>
          <input type="range" min={0} max={total || 0} step={0.1} value={t} aria-label="Position dans la vidéo"
            onChange={(e) => video.current && (video.current.currentTime = Number(e.target.value))} />
          <span className="tab-num">{duree(t)} / {duree(total)}</span>
          <button type="button" aria-label="Plein écran" onClick={() => video.current?.requestFullscreen?.()}><Maximize size={16} /></button>
        </div>
      )}
      {erreur && <div className="erreur-media" role="alert">{erreur}</div>}
    </CardShell>
  );
});
