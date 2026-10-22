import { memo, useEffect, useRef, useState } from "react";
import type { NodeProps, Node } from "@xyflow/react";
import { ExternalLink, FileText, Image as IconeImage, Link2, Maximize2 } from "lucide-react";
import { siClaude } from "simple-icons";
import type { DonneesNoeud } from "../types";
import { extension, taille } from "../lib/format";
import { useVisible } from "../lib/medias";
import { CardShell, Tags } from "./CardShell";
import { useActions } from "./contexte";

type P = NodeProps<Node<DonneesNoeud>>;

export const ImageNode = memo(function ImageNode({ data, selected }: P) {
  const o = data.objet;
  const a = useActions();
  const [erreur, setErreur] = useState(false);
  const src = o.asset?.url ?? (o.meta.demo_src as string | undefined);
  const dims = o.asset?.meta.largeur ? `${o.asset.meta.largeur} × ${o.asset.meta.hauteur}` : "";
  return (
    <CardShell objet={o} selected={selected} classe="c-image">
      <div className="visuel">
        {src && !erreur ? (
          <img src={src} alt={o.meta.titre || o.asset?.nom || "image"} loading="lazy" decoding="async" draggable={false}
            onError={() => setErreur(true)} />
        ) : (
          <div className="erreur-media" role="alert">Image illisible ou introuvable.</div>
        )}
      </div>
      <div className="pied">
        <span className="icone-tuile"><IconeImage /></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="titre-carte">{o.meta.titre || o.asset?.nom || "Image"}</div>
          <div className="meta-carte tab-num">{[o.meta.description, dims].filter(Boolean).join(" · ")}</div>
        </div>
        {src && (
          <button type="button" className="menu-carte nodrag" aria-label="Agrandir l'image" onClick={() => a.agrandir(src, o.meta.titre || "")}>
            <Maximize2 size={17} />
          </button>
        )}
      </div>
    </CardShell>
  );
});

export const LienNode = memo(function LienNode({ data, selected }: P) {
  const o = data.objet;
  const m = o.meta;
  const image = m.apercu_image?.url ?? (m.demo_src as string | undefined);
  const url = m.url || o.contenu;
  return (
    <CardShell objet={o} selected={selected} classe="c-lien">
      <div className={`apercu${image ? "" : " repli"}`}>
        {image ? <img src={image} alt="" loading="lazy" decoding="async" draggable={false} /> : <Link2 size={36} />}
        {url && /^https?:/.test(url) && (
          <a className="ouvrir-site nodrag" href={url} target="_blank" rel="noopener noreferrer nofollow" aria-label="Ouvrir le site"
            title="Ouvrir le site"><ExternalLink size={17} /></a>
        )}
      </div>
      <div className="corps">
        <span className="lien-favicon" aria-hidden="true">
          {m.favicon?.url ? <img src={m.favicon.url} alt="" /> : m.marque === "claude"
            ? <svg viewBox="0 0 24 24" width="24" height="24"><path d={siClaude.path} fill={`#${siClaude.hex}`} /></svg>
            : <Link2 size={22} />}
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="titre-carte">{m.titre || m.hote || url}</div>
          <div className="url">{url}</div>
        </div>
        {m.description && <div className="desc">{m.description}</div>}
        {m.apercu_erreur && <div className="desc">Aperçu indisponible : {m.apercu_erreur}</div>}
      </div>
      <div className="tags-lien"><Tags tags={m.tags} /></div>
    </CardShell>
  );
});

/** Vignettes des deux premières pages, rendues par pdf.js dans un <canvas> (chargé seulement si la carte est visible). */
function PagesPdf({ url, demo }: { url: string; demo?: string[] }) {
  const [ref, visible] = useVisible<HTMLDivElement>();
  const toiles = [useRef<HTMLCanvasElement>(null), useRef<HTMLCanvasElement>(null)];
  const [etat, setEtat] = useState<{ pages?: number; erreur?: string }>({});
  useEffect(() => {
    if (!visible || demo?.length) return;
    let annule = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
        pdfjs.GlobalWorkerOptions.workerSrc = worker;
        const doc = await pdfjs.getDocument({ url, withCredentials: true }).promise;
        if (annule) return;
        setEtat({ pages: doc.numPages });
        for (let i = 0; i < Math.min(2, doc.numPages); i++) {
          const page = await doc.getPage(i + 1);
          const vue = page.getViewport({ scale: 0.6 });
          const c = toiles[i]?.current;
          if (!c || annule) return;
          c.width = vue.width;
          c.height = vue.height;
          await page.render({ canvas: c, viewport: vue }).promise;
        }
      } catch (e) {
        if (!annule) setEtat({ erreur: "Aperçu PDF impossible" });
      }
    })();
    return () => {
      annule = true;
    };
  }, [visible, url, demo]);
  return (
    <div ref={ref} className="pages" aria-label={etat.pages ? `${etat.pages} pages` : "Aperçu des pages"}>
      {demo?.length ? demo.slice(0, 2).map((s) => <span key={s}><img src={s} alt="" loading="lazy" /></span>)
        : [0, 1].map((i) => <span key={i}><canvas ref={toiles[i]} /></span>)}
      {etat.erreur && <div className="erreur-media" role="alert">{etat.erreur}</div>}
    </div>
  );
}

export const PdfNode = memo(function PdfNode({ data, selected }: P) {
  const o = data.objet;
  const a = o.asset;
  return (
    <CardShell objet={o} selected={selected} classe="c-pdf">
      <div className="haut">
        <span className="icone-tuile"><FileText /></span>
        <div style={{ minWidth: 0 }}>
          <div className="titre-carte">{o.meta.titre || a?.nom || "Document"}</div>
          <div className="meta-carte tab-num">{[a && extension(a.mime, a.nom), a && taille(a.taille)].filter(Boolean).join(" · ")}</div>
          {o.meta.description && <div className="meta-carte" style={{ marginTop: 6, lineHeight: 1.35 }}>{o.meta.description}</div>}
        </div>
      </div>
      {a && <PagesPdf url={a.url} demo={o.meta.demo_pages} />}
      <div className="tags" style={{ padding: "14px 18px 0" }}>
        {(o.meta.tags ?? []).slice(0, 2).map((t, i) => <span key={t} className={`tag c${i % 2}`}>#{t}</span>)}
        {(o.meta.tags?.length ?? 0) > 2 && <span className="tag plus">+{(o.meta.tags?.length ?? 0) - 2}</span>}
        {a && (
          <a className="ouvrir-site nodrag" href={a.url} target="_blank" rel="noopener noreferrer" aria-label="Ouvrir le PDF"
            style={{ marginLeft: "auto" }}><ExternalLink size={17} /></a>
        )}
      </div>
    </CardShell>
  );
});

export const DossierNode = memo(function DossierNode({ data, selected }: P) {
  const o = data.objet;
  const a = useActions();
  const enfants = a.enfants(o.id);
  const demoVignettes = (o.meta.demo_vignettes as string[] | undefined) ?? [];
  const vignettes = demoVignettes.length ? demoVignettes
    : enfants.map((e) => e.asset?.vignette_url ?? (e.asset?.famille === "image" ? e.asset.url : null)).filter((x): x is string => Boolean(x));
  const total = (o.meta.demo_elements as number | undefined) ?? enfants.length;
  return (
    <CardShell objet={o} selected={selected} classe="c-dossier">
      <div className="haut-dossier">
        <svg className="icone-dossier" viewBox="0 0 42 34" aria-hidden="true">
          <path d="M2 6a4 4 0 0 1 4-4h10l4 4h16a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4Z" fill="#F5B83D" />
          <path d="M2 12h38v16a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4Z" fill="#F8C65A" />
        </svg>
        <div style={{ minWidth: 0 }}>
          <div className="titre-carte">{o.meta.titre || "Dossier"}</div>
          <div className="meta-carte">{total} élément{total > 1 ? "s" : ""}</div>
        </div>
      </div>
      <div className="colonne">
        <div className="vignettes">
          {vignettes.slice(0, 3).map((s) => <span key={s}><img src={s} alt="" loading="lazy" /></span>)}
          {total > 3 && <span className="plus">+{total - 3}</span>}
          {!vignettes.length && !total && <span className="meta-carte" style={{ width: "auto", background: "none" }}>Glisse des cartes ici</span>}
        </div>
      </div>
    </CardShell>
  );
});
