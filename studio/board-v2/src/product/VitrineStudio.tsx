import { useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import "./vitrine.css";

export type ApercuStudio = {
  id: string;
  titre: string;
  detail?: string;
  image?: string | null;
  visuel?: ReactNode;
  ouvrir?: () => void;
};

type Props = {
  titre: string;
  description: string;
  idTitre?: string;
  actions?: ReactNode;
  apercus?: ApercuStudio[];
  libelleApercus?: string;
};

export function VitrineStudio({ titre, description, idTitre, actions, apercus = [], libelleApercus }: Props) {
  return <header className="studio-vitrine">
    <div className="studio-vitrine-texte">
      <h1 id={idTitre}>{titre}</h1>
      <p>{description}</p>
      {actions && <div className="studio-vitrine-actions">{actions}</div>}
    </div>
    {apercus.length > 0 && <CarrouselVitrine apercus={apercus} libelle={libelleApercus ?? `Aperçus · ${titre}`} />}
  </header>;
}

function CarrouselVitrine({ apercus, libelle }: { apercus: ApercuStudio[]; libelle: string }) {
  const [id, setId] = useState<string | null>(null);
  const geste = useRef<{ x: number; y: number } | null>(null);
  const index = Math.max(0, apercus.findIndex((apercu) => apercu.id === id));
  const actif = apercus[index];
  const total = apercus.length;
  if (!actif) return null;
  const aller = (decalage: number) => {
    const prochain = apercus[(index + decalage + total) % total];
    if (prochain) setId(prochain.id);
  };

  return <div className="studio-carrousel" role="region" aria-roledescription="carrousel" aria-label={libelle}
    onKeyDown={(e) => {
      if (total < 2 || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        aller(e.key === "ArrowLeft" ? -1 : 1);
      }
    }}>
    <div className="studio-carrousel-pile" data-cartes={Math.min(total, 3)}
      onTouchStart={(e) => {
        const contact = e.touches[0];
        geste.current = contact && e.touches.length === 1 ? { x: contact.clientX, y: contact.clientY } : null;
      }}
      onTouchCancel={() => { geste.current = null; }}
      onTouchEnd={(e) => {
        const debut = geste.current;
        geste.current = null;
        if (!debut || total < 2) return;
        const contact = e.changedTouches[0];
        if (!contact) return;
        const dx = contact.clientX - debut.x;
        if (Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(contact.clientY - debut.y) * 1.5) aller(dx > 0 ? -1 : 1);
      }}>
      <div className="studio-carrousel-cadre" key={actif.id} aria-hidden="true">
        {actif.image ? <img src={actif.image} alt="" decoding="async" draggable={false} /> : actif.visuel}
      </div>
    </div>
    <div className="studio-carrousel-bas">
      <div className="studio-carrousel-legende" aria-live="polite" aria-atomic="true">
        {actif.ouvrir ? <button type="button" className="studio-carrousel-ouvrir" onClick={actif.ouvrir}
          aria-label={`Ouvrir l’aperçu de ${actif.titre}`} title={actif.titre}><span>{actif.titre}</span><ArrowUpRight size={14} aria-hidden /></button>
          : <strong title={actif.titre}>{actif.titre}</strong>}
        {actif.detail && <small title={actif.detail}>{actif.detail}</small>}
      </div>
      {total > 1 && <div className="studio-carrousel-commandes">
        <button type="button" onClick={() => aller(-1)} aria-label="Aperçu précédent"><ChevronLeft size={16} aria-hidden /></button>
        <span className="tab-num">{index + 1} / {total}</span>
        <button type="button" onClick={() => aller(1)} aria-label="Aperçu suivant"><ChevronRight size={16} aria-hidden /></button>
      </div>}
    </div>
  </div>;
}
