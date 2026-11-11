// Menu contextuel (clic droit, ou touche Menu / Maj+F10) : les commandes du registre proposées « menu » et
// disponibles pour la cible — une carte, une relation, ou le canevas. Navigation au clavier, Échap pour fermer.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check } from "lucide-react";
import type { MenuOuvert } from "../etat/ui";
import type { ContexteBoard } from "./contexte";
import { afficher } from "./raccourcis";
import { useCommandes } from "./react";
import { libelleDe, raccourcisDe } from "./types";

export function MenuContextuel({ menu, extra, fermer }: {
  menu: MenuOuvert; extra: Partial<Pick<ContexteBoard, "selection" | "lien" | "point">>; fermer: () => void;
}) {
  const { registre, contexte, executer } = useCommandes();
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: menu.x, y: menu.y });
  const c = useMemo(() => contexte(extra), [contexte, extra]);
  const commandes = useMemo(() => registre.disponibles(c, "menu"), [registre, c]);

  // garde le menu dans la fenêtre, puis donne le focus à sa première entrée
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos({ x: Math.max(8, Math.min(menu.x, innerWidth - r.width - 8)), y: Math.max(8, Math.min(menu.y, innerHeight - r.height - 8)) });
    ref.current?.querySelector<HTMLElement>("[role^='menuitem']")?.focus();
  }, [menu.x, menu.y]);

  useEffect(() => {
    const dehors = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) fermer(); };
    window.addEventListener("pointerdown", dehors, true);
    window.addEventListener("blur", fermer);
    return () => {
      window.removeEventListener("pointerdown", dehors, true);
      window.removeEventListener("blur", fermer);
    };
  }, [fermer]);

  const deplacer = (sens: 1 | -1 | "debut" | "fin") => {
    const items = [...(ref.current?.querySelectorAll<HTMLElement>("[role^='menuitem']") ?? [])];
    const i = items.indexOf(document.activeElement as HTMLElement);
    const suivant = sens === "debut" ? 0 : sens === "fin" ? items.length - 1 : (i + sens + items.length) % items.length;
    items[suivant]?.focus();
  };

  if (!commandes.length) return null;
  return (
    <div ref={ref} className="menu-contextuel" role="menu" aria-label={c.lien ? "Actions de la relation" : c.selection.length ? "Actions de la sélection" : "Actions du canevas"}
      style={{ left: pos.x, top: pos.y }} onContextMenu={(e) => e.preventDefault()}
      onKeyDown={(e) => {
        if (e.key === "Escape") { e.stopPropagation(); fermer(); }
        else if (e.key === "ArrowDown") { e.preventDefault(); deplacer(1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); deplacer(-1); }
        else if (e.key === "Home") { e.preventDefault(); deplacer("debut"); }
        else if (e.key === "End") { e.preventDefault(); deplacer("fin"); }
        else if (e.key === "Tab") { e.preventDefault(); fermer(); }
      }}>
      {commandes.map((cmd, i) => {
        const Icone = cmd.icone;
        const r = raccourcisDe(cmd)[0];
        const coche = cmd.actif?.(c);
        return (
          <div key={cmd.id} role="presentation">
            {i > 0 && commandes[i - 1]!.categorie !== cmd.categorie && <div className="menu-separateur" role="separator" />}
            <button type="button" role={cmd.actif ? "menuitemcheckbox" : "menuitem"} aria-checked={cmd.actif ? Boolean(coche) : undefined}
              className={cmd.id === "edition.supprimer" || cmd.id === "relation.supprimer" ? "danger" : undefined}
              onClick={() => { fermer(); executer(cmd.id, "menu", extra); }}>
              <span className="menu-icone">{coche ? <Check size={15} aria-hidden /> : Icone ? <Icone size={15} aria-hidden /> : null}</span>
              <span className="menu-libelle">{libelleDe(cmd, c)}</span>
              {r && <kbd>{afficher(r)}</kbd>}
            </button>
          </div>
        );
      })}
    </div>
  );
}
