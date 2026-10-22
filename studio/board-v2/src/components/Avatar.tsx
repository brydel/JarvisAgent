// Avatars des agents : personnages Notionists (DiceBear ; dessins de Zoish sous CC0, code MIT), générés dans le
// navigateur à partir du rôle, fond teinté par le rôle, anneau de statut. Ni une photo, ni le logo d'un fournisseur.
import { memo, useEffect, useState } from "react";
import { siClaude } from "simple-icons";

const TEINTES: { motif: RegExp; h: number }[] = [
  { motif: /chef/i, h: 252 },
  { motif: /analy|recherche|veille/i, h: 232 },
  { motif: /design|ui|ux|maquette/i, h: 282 },
  { motif: /dev|code|backend|frontend|ing/i, h: 172 },
  { motif: /r[ée]dac|contenu|doc/i, h: 28 },
  { motif: /test|qa|revue/i, h: 340 },
];

function hachage(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return Math.abs(h);
}

export function teinte(role: string, id: string): number {
  return TEINTES.find((t) => t.motif.test(role))?.h ?? hachage(id) % 360;
}

export type StatutAgent = "actif" | "attente" | "termine" | "echec";
const ANNEAU: Record<StatutAgent, string> = { actif: "#5B6CFF", attente: "#E2B93B", termine: "#3FB984", echec: "#E5486F" };

interface Props {
  id: string;
  role: string;
  taille?: number;
  statut?: StatutAgent;
  point?: boolean;
  fournisseur?: string;
  titre?: string;
}

/** Graine stable par PERSONNAGE (le rôle, sinon l'identifiant) : le Chef a toujours le même visage. */
function graine(role: string, id: string): string {
  return (role || id).trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "") || "agent";
}

function hex(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const c = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * c).toString(16).padStart(2, "0");
  };
  return `${f(0)}${f(8)}${f(4)}`;
}

const dessins = new Map<string, string>();
let module: Promise<typeof import("./dessinAvatar")> | null = null;

/** Dessin mis en cache par personnage ; tant qu'il se charge, un disque teinté occupe la place (aucun saut de mise en page). */
function useDessin(cle: string, h: number): string | undefined {
  const k = `${cle}|${h}`;
  const [uri, setUri] = useState(() => dessins.get(k));
  useEffect(() => {
    if (dessins.has(k)) {
      setUri(dessins.get(k));
      return;
    }
    let actif = true;
    module ??= import("./dessinAvatar");
    module.then((m) => {
      if (!dessins.has(k)) dessins.set(k, m.dessiner(cle, hex(h, 62, 72)));
      if (actif) setUri(dessins.get(k));
    }).catch(() => undefined);
    return () => {
      actif = false;
    };
  }, [k, cle, h]);
  return uri;
}

export const Avatar = memo(function Avatar({ id, role, taille = 64, statut, point, fournisseur, titre }: Props) {
  const cle = graine(role, id);
  const h = teinte(role, cle);
  const uri = useDessin(cle, h);
  return (
    <span className="avatar" style={{ width: taille, height: taille, background: `#${hex(h, 62, 72)}`, borderRadius: "50%" }}
      title={titre} role="img" aria-label={titre}>
      {uri && <img src={uri} width={taille} height={taille} alt="" draggable={false} decoding="async" />}
      {statut && <span className="anneau" style={{ borderColor: ANNEAU[statut] }} />}
      {point && <span className="point" />}
      {fournisseur && <MarqueFournisseur fournisseur={fournisseur} />}
    </span>
  );
});

/** Logo officiel quand il est disponible sous licence vérifiée (simple-icons, CC0) ; sinon un badge texte. */
export function MarqueFournisseur({ fournisseur }: { fournisseur: string }) {
  if (fournisseur === "claude") {
    return (
      <span className="marque-fournisseur" title="Claude Code">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d={siClaude.path} fill={`#${siClaude.hex}`} /></svg>
      </span>
    );
  }
  if (fournisseur === "codex") {
    // Le logo OpenAI n'est pas dans simple-icons (retiré à la demande d'OpenAI) : aucun logo inventé.
    return <span className="marque-fournisseur texte" title="OpenAI Codex">CX</span>;
  }
  if (fournisseur === "factice") return <span className="marque-fournisseur texte" title="Fournisseur factice (tests)">F</span>;
  return null;
}
