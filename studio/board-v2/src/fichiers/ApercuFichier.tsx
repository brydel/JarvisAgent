import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, X } from "lucide-react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import type { ObjetBoard } from "../types";
import { rendreNote, type NavigationWiki } from "../lib/markdown";
import { moteurPdf } from "../lib/pdf";
import { estNote } from "./graphe";

function Pdf({ url, titre }: { url: string; titre: string }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [erreur, setErreur] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let actif = true;
    let tache: PDFDocumentLoadingTask | undefined;
    void moteurPdf().then(async (pdf) => {
      if (!actif) return;
      tache = pdf.getDocument({ url, withCredentials: true });
      const ouvert = await tache.promise;
      if (actif) setDoc(ouvert);
    }).catch(() => { if (actif) setErreur("Aperçu PDF indisponible."); });
    return () => { actif = false; void tache?.destroy().catch(() => undefined); };
  }, [url]);
  useEffect(() => {
    if (!doc) return;
    let actif = true;
    let rendu: RenderTask | undefined;
    void doc.getPage(page).then(async (p) => {
      const c = canvas.current;
      if (!actif || !c) return;
      const dimensions = p.getViewport({ scale: 1 });
      const vue = p.getViewport({ scale: Math.min(1.75, 1040 / Math.max(dimensions.width, dimensions.height)) });
      c.width = Math.ceil(vue.width); c.height = Math.ceil(vue.height);
      rendu = p.render({ canvas: c, viewport: vue });
      await rendu.promise;
    }).catch(() => { if (actif) setErreur("Impossible d’afficher cette page du PDF."); });
    return () => { actif = false; rendu?.cancel(); };
  }, [page, doc]);
  if (erreur) return <p className="mf-apercu-message" role="alert">{erreur}</p>;
  return <div className="mf-pdf">
    <div className="mf-pdf-page"><canvas ref={canvas} aria-label={`${titre}, page ${page}`} /></div>
    <div className="mf-apercu-barre">
      <button className="p-icon-button" type="button" aria-label="Page PDF précédente" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={16} /></button>
      <span className="tab-num" role="status">{doc ? `Page ${page} / ${doc.numPages}` : "Chargement du PDF…"}</span>
      <button className="p-icon-button" type="button" aria-label="Page PDF suivante" disabled={!doc || page >= doc.numPages}
        onClick={() => setPage(page + 1)}><ChevronRight size={16} /></button>
    </div>
  </div>;
}

function Apercu({ objet, titre, grand, wiki }: { objet: ObjetBoard; titre: string; grand: boolean; wiki?: NavigationWiki }) {
  const url = objet.asset?.url || objet.meta.demo_src;
  const [zoom, setZoom] = useState(1);
  const [erreur, setErreur] = useState(false);
  if (erreur) return <p className="mf-apercu-message" role="alert">Aperçu indisponible.</p>;
  if (url && ["image", "capture"].includes(objet.type)) return <>
    <div className="mf-image" tabIndex={zoom > 1 ? 0 : undefined} aria-label={zoom > 1 ? "Image agrandie, défilable" : undefined}>
      <img src={url} alt={titre} style={{ width: `${zoom * 100}%`, maxWidth: zoom > 1 ? "none" : undefined }}
        onError={() => setErreur(true)} draggable={false} />
    </div>
    {grand && <div className="mf-apercu-barre">
      <button className="p-icon-button" type="button" aria-label="Réduire l’image" disabled={zoom <= 1} onClick={() => setZoom(zoom - .25)}><Minus size={16} /></button>
      <span className="tab-num">{Math.round(zoom * 100)} %</span>
      <button className="p-icon-button" type="button" aria-label="Agrandir l’image" disabled={zoom >= 3} onClick={() => setZoom(zoom + .25)}><Plus size={16} /></button>
    </div>}
  </>;
  if (url && objet.type === "video") return <video className="mf-video" controls playsInline preload="none"
    src={url} poster={objet.asset?.vignette_url ?? undefined} aria-label={titre} onError={() => setErreur(true)} />;
  if (url && objet.type === "audio") return <audio className="mf-audio" controls preload="none" src={url} aria-label={titre} onError={() => setErreur(true)} />;
  if (url && (objet.type === "pdf" || objet.asset?.mime === "application/pdf")) return <Pdf key={url} url={url} titre={titre} />;
  if ((objet.type === "document" || estNote(objet)) && objet.contenu.trim()) return <div className="mf-document">{rendreNote(objet.contenu, wiki)}</div>;
  return <p className="mf-apercu-message">Ce fichier n’a pas d’aperçu.</p>;
}

function Visionneuse({ objet, titre, fermer, wiki }: { objet: ObjetBoard; titre: string; fermer: () => void; wiki?: NavigationWiki }) {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => { d?.close(); };
  }, []);
  return <dialog ref={ref} className="mf-visionneuse" aria-label={titre} onCancel={(e) => { e.preventDefault(); fermer(); }}>
    <header><h2>{titre}</h2><button type="button" className="p-icon-button" aria-label="Fermer l’aperçu" onClick={fermer}><X size={20} /></button></header>
    <Apercu objet={objet} titre={titre} grand wiki={wiki} />
  </dialog>;
}

export function ApercuFichier({ objet, titre, wiki, editer }: { objet: ObjetBoard; titre: string; wiki?: NavigationWiki; editer?: () => void }) {
  const [grand, setGrand] = useState(false);
  const disponible = objet.asset?.url || objet.meta.demo_src || ((objet.type === "document" || estNote(objet)) && objet.contenu.trim());
  return <section className="mf-inspect-apercu" aria-label="Aperçu du fichier">
    <div className="mf-partie-entete"><h3>Aperçu</h3><div className="mf-inspect-actions">
      {editer && <button type="button" className="p-button p-quiet" onClick={editer}>Modifier la note</button>}
      {disponible && <button type="button" className="p-icon-button"
      aria-label="Ouvrir le grand aperçu" title="Ouvrir le grand aperçu" onClick={() => setGrand(true)}><Maximize2 size={16} /></button>}</div></div>
    {grand ? <Visionneuse objet={objet} titre={titre} fermer={() => setGrand(false)} wiki={wiki} /> : <Apercu objet={objet} titre={titre} grand={false} wiki={wiki} />}
  </section>;
}
