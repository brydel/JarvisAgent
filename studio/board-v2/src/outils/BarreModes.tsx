// Barre des outils à modes (sélection, main, lasso, note adhésive, texte, cadre, formes, flèche, crayon, surligneur,
// gomme) + style du tracé + annuler / rétablir + palette. Chaque bouton est une commande du registre : libellé,
// raccourci (affiché dans l'info-bulle et en exposant) et état viennent de là. Flèches ← → : bouton suivant.
import { memo, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Command } from "lucide-react";
import { OUTILS } from "../commandes/catalogue/outils";
import { BoutonCommande, useCommandes } from "../commandes/react";
import { COULEURS, useUi } from "../etat/ui";

const EPAISSEURS = [2, 6, 12, 24];

function Style() {
  const { executer } = useCommandes();
  const couleur = useUi((e) => e.couleur);
  const epaisseur = useUi((e) => e.epaisseur);
  const [ouvert, setOuvert] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ouvert) return;
    const dehors = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOuvert(false); };
    const echap = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") setOuvert(false); };
    window.addEventListener("pointerdown", dehors, true);
    window.addEventListener("keydown", echap);
    return () => {
      window.removeEventListener("pointerdown", dehors, true);
      window.removeEventListener("keydown", echap);
    };
  }, [ouvert]);
  return (
    <div ref={ref} className="style-trace">
      <button type="button" className="bouton-style" aria-haspopup="dialog" aria-expanded={ouvert} aria-label={`Style du tracé : ${couleur}, épaisseur ${epaisseur}`}
        title="Couleur et épaisseur du tracé" onClick={() => setOuvert((v) => !v)}>
        <span className={`pastille teinte-${couleur}`} style={{ width: 8 + Math.min(14, epaisseur), height: 8 + Math.min(14, epaisseur) }} />
      </button>
      {ouvert && (
        <div className="popover-style" role="dialog" aria-label="Style du tracé">
          <div className="rangee" role="group" aria-label="Couleur">
            {COULEURS.map((c) => (
              <button key={c} type="button" className={`pastille teinte-${c}`} aria-label={`Couleur ${c}`} title={c} aria-pressed={couleur === c}
                onClick={() => executer(`style.couleur.${c}`, "bouton")} />
            ))}
          </div>
          <div className="rangee" role="group" aria-label="Épaisseur">
            {EPAISSEURS.map((e) => (
              <button key={e} type="button" className="choix-epaisseur" aria-label={`Épaisseur ${e}`} aria-pressed={epaisseur === e}
                onClick={() => executer(`style.epaisseur.${e}`, "bouton")}><span style={{ height: Math.max(2, e / 1.6) }} /></button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export const BarreModes = memo(function BarreModes() {
  const { executer } = useCommandes();
  const outil = useUi((e) => e.outil);
  const dessin = outil === "crayon" || outil === "surligneur" || outil === "fleche" || outil === "rectangle" || outil === "ellipse" || outil === "losange" || outil === "adhesif";
  const naviguer = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const boutons = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
    const i = boutons.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0) return;
    e.preventDefault();
    e.stopPropagation();
    boutons[(i + (e.key === "ArrowRight" ? 1 : -1) + boutons.length) % boutons.length]?.focus();
  };
  return (
    <div className="barre-modes nodrag nopan" role="toolbar" aria-label="Outils" onKeyDown={naviguer}>
      {OUTILS.map((o, i) => {
        const Icone = o.icone;
        return (
          <span key={o.id} className="groupe-mode">
            {i > 0 && OUTILS[i - 1]!.groupe !== o.groupe && <span className="sep" aria-hidden />}
            <button type="button" className="mode" aria-pressed={outil === o.id} aria-label={o.libelle} aria-keyshortcuts={o.touche.toUpperCase()}
              title={`${o.libelle} (${o.touche.toUpperCase()}) — ${o.aide}`} onClick={() => executer(`outil.${o.id}`, "bouton")}>
              <Icone size={16} aria-hidden /><kbd aria-hidden>{o.touche.toUpperCase()}</kbd>
            </button>
          </span>
        );
      })}
      {dessin && <><span className="sep" aria-hidden /><Style /></>}
      <span className="sep" aria-hidden />
      <BoutonCommande id="edition.annuler" classe="mode" taille={16} />
      <BoutonCommande id="edition.retablir" classe="mode" taille={16} />
      <BoutonCommande id="palette.ouvrir" classe="mode palette-bouton" taille={16}><Command size={16} aria-hidden /><kbd aria-hidden>K</kbd></BoutonCommande>
    </div>
  );
});
