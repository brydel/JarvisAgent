// Avatars ORIGINAUX des agents : buste stylisé en SVG, teinte fixée par le rôle (ou par l'identifiant d'instance),
// anneau de statut. Ce n'est ni une photo, ni le logo d'un fournisseur déguisé en personne.
import { memo, useId } from "react";
import { siClaude } from "simple-icons";

const TEINTES: { motif: RegExp; h: number }[] = [
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

export const Avatar = memo(function Avatar({ id, role, taille = 64, statut, point, fournisseur, titre }: Props) {
  const h = teinte(role, id);
  const g = useId().replace(/:/g, "");
  const variante = hachage(id) % 3;
  return (
    <span className="avatar" style={{ width: taille, height: taille }} title={titre} role="img" aria-label={titre}>
      <svg width={taille} height={taille} viewBox="0 0 64 64" aria-hidden="true">
        <defs>
          <radialGradient id={`f${g}`} cx="50%" cy="30%" r="75%">
            <stop offset="0" stopColor={`hsl(${h} 70% 46%)`} />
            <stop offset="1" stopColor={`hsl(${h} 70% 14%)`} />
          </radialGradient>
          <linearGradient id={`p${g}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={`hsl(${h} 60% 78%)`} />
            <stop offset="1" stopColor={`hsl(${h} 55% 52%)`} />
          </linearGradient>
          <linearGradient id={`v${g}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={`hsl(${h} 45% 30%)`} />
            <stop offset="1" stopColor={`hsl(${h} 55% 18%)`} />
          </linearGradient>
        </defs>
        <circle cx="32" cy="32" r="32" fill={`url(#f${g})`} />
        <path d={variante === 1 ? "M8 64c2-13 11-19 24-19s22 6 24 19Z" : "M10 64c1-12 10-18 22-18s21 6 22 18Z"} fill={`url(#v${g})`} />
        <path d="M27 40h10v7c-3 2-7 2-10 0Z" fill={`hsl(${h} 50% 58%)`} />
        <ellipse cx="32" cy="28" rx="10.5" ry="12.5" fill={`url(#p${g})`} />
        {variante === 0 && <path d="M21.5 25c0-8 4.7-12.5 10.5-12.5S42.5 17 42.5 25c-3-4-6-5.5-10.5-5.5S24.5 21 21.5 25Z" fill={`hsl(${h} 45% 22%)`} />}
        {variante === 2 && <path d="M21.6 27c-1-9 4-14.5 10.4-14.5 6.6 0 11.4 5.5 10.4 14.5-1.6-5-4.4-8-10.4-8s-8.8 3-10.4 8Z" fill={`hsl(${h} 35% 16%)`} />}
        <ellipse cx="28" cy="23" rx="4" ry="2.5" fill="white" opacity="0.18" />
      </svg>
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
