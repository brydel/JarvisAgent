// Palette de commandes (Ctrl/⌘+K) : toutes les commandes disponibles dans le contexte courant, recherche floue,
// récents en tête, raccourci affiché. Clavier : ↑ ↓ pour choisir, Entrée pour exécuter, Échap pour fermer.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Search } from "lucide-react";
import type { ContexteBoard } from "./contexte";
import { Touches, useCommandes } from "./react";
import { chercher } from "./recherche";
import { libelleDe, raccourcisDe, type Commande } from "./types";

interface Ligne {
  cmd: Commande<ContexteBoard>;
  libelle: string;
  groupe: string;
  /** commande indisponible : la phrase du registre qui dit pourquoi */
  raison: string | null;
}

export function Palette({ fermer }: { fermer: () => void }) {
  const { registre, contexte, executer } = useCommandes();
  const [requete, setRequete] = useState("");
  const [actif, setActif] = useState(0);
  const liste = useRef<HTMLDivElement>(null);
  // contexte figé à l'ouverture : la palette propose ce qui était possible au moment de l'appel
  const c = useMemo(() => contexte(), [contexte]);

  const lignes = useMemo<Ligne[]>(() => {
    const dispo = registre.disponibles(c).filter((x) => x.id !== "palette.ouvrir");
    const q = requete.trim();
    if (!q) {
      const parId = new Map(dispo.map((x) => [x.id, x]));
      const recents = registre.journal.recents(5).map((id) => parId.get(id)).filter((x): x is Commande<ContexteBoard> => Boolean(x));
      const vus = new Set(recents.map((x) => x.id));
      return [...recents.map((cmd) => ({ cmd, libelle: libelleDe(cmd, c), groupe: "Récents", raison: null })),
        ...dispo.filter((x) => !vus.has(x.id)).map((cmd) => ({ cmd, libelle: libelleDe(cmd, c), groupe: cmd.categorie, raison: null }))];
    }
    // en recherche : les commandes indisponibles qui savent dire pourquoi sont trouvées aussi, grisées, après les autres
    const raisons = new Map(registre.proposees(c, "palette").filter((p) => !p.etat.disponible && p.cmd.id !== "palette.ouvrir")
      .map((p) => [p.cmd.id, p.etat.raison] as const));
    const texte = (x: Commande<ContexteBoard>) => `${libelleDe(x, c)} ${x.categorie} ${x.motsCles ?? ""}`;
    // une commande souvent utilisée remonte un peu (journal local), sans jamais passer devant une bien meilleure correspondance
    const trouvees = chercher(q, dispo, texte, (x) => Math.min(6, Math.log2(1 + (registre.journal.usage(x.id)?.n ?? 0)))).slice(0, 40);
    const grisees = chercher(q, registre.toutes().filter((x) => raisons.has(x.id)), texte).slice(0, 8);
    return [...trouvees.map(({ element }) => ({ cmd: element, libelle: libelleDe(element, c), groupe: "", raison: null })),
      ...grisees.map(({ element }) => ({ cmd: element, libelle: libelleDe(element, c), groupe: "", raison: raisons.get(element.id) ?? null }))];
  }, [registre, c, requete]);

  useEffect(() => setActif(0), [requete]);
  useEffect(() => {
    liste.current?.querySelector<HTMLElement>("[aria-selected='true']")?.scrollIntoView({ block: "nearest" });
  }, [actif]);

  const lancer = (l: Ligne | undefined) => {
    if (!l || l.raison !== null) return;  // indisponible : la ligne dit pourquoi, rien ne s'exécute
    fermer();
    // après la fermeture : le focus revient au canevas avant l'exécution (plein écran, saisie d'un lien…)
    window.setTimeout(() => executer(l.cmd.id, "palette"), 0);
  };

  return (
    <div className="palette-fond" onPointerDown={(e) => e.target === e.currentTarget && fermer()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Palette de commandes">
        <div className="palette-saisie">
          <Search size={16} aria-hidden />
          <input autoFocus value={requete} placeholder="Commande" role="combobox" aria-expanded="true" aria-controls="palette-liste"
            aria-activedescendant={lignes[actif] ? `palette-${lignes[actif]!.cmd.id}` : undefined} aria-label="Chercher une commande" maxLength={80}
            onChange={(e) => setRequete(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActif((i) => Math.min(lignes.length - 1, i + 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setActif((i) => Math.max(0, i - 1)); }
              else if (e.key === "Home") { e.preventDefault(); setActif(0); }
              else if (e.key === "End") { e.preventDefault(); setActif(lignes.length - 1); }
              else if (e.key === "Enter") { e.preventDefault(); lancer(lignes[actif]); }
              else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fermer(); }
            }} />
          <kbd>Échap</kbd>
        </div>
        <div className="palette-liste" id="palette-liste" role="listbox" aria-label="Commandes" ref={liste}>
          {lignes.map((l, i) => {
            const Icone = l.cmd.icone;
            const r = raccourcisDe(l.cmd)[0];
            const titre = l.groupe && l.groupe !== lignes[i - 1]?.groupe ? l.groupe : "";
            return (
              <div key={l.cmd.id} role="presentation">
                {titre && <div className="palette-groupe" role="presentation">{titre}</div>}
                <div id={`palette-${l.cmd.id}`} role="option" aria-selected={i === actif} aria-disabled={l.raison !== null || undefined}
                  className={`palette-ligne${l.raison !== null ? " indisponible" : ""}`} onPointerMove={() => setActif(i)} onClick={() => lancer(l)}>
                  <span className="palette-icone">{Icone ? <Icone size={16} aria-hidden /> : null}</span>
                  <span className="palette-libelle">{l.libelle}{l.raison !== null && <small className="palette-raison">Indisponible : {l.raison}</small>}</span>
                  {l.cmd.actif?.(c) && <Check size={16} className="palette-coche" aria-label="actif" />}
                  {!l.groupe && <span className="palette-categorie">{l.cmd.categorie}</span>}
                  {r && <Touches raccourci={r} />}
                </div>
              </div>
            );
          })}
          {!lignes.length && <div className="palette-vide" role="status">Aucune commande pour « {requete} ». Essaie « aligner », « thème » ou « exporter ».</div>}
        </div>
        <div className="palette-pied"><span><kbd>↑</kbd><kbd>↓</kbd> choisir</span><span><kbd>Entrée</kbd> exécuter</span>
          <span className="palette-compte tab-num">{lignes.length} commande{lignes.length > 1 ? "s" : ""}</span></div>
      </div>
    </div>
  );
}
