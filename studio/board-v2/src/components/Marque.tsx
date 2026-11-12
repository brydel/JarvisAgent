// Marque Jarvis : un anneau ouvert et son point, à plat, dans la couleur du texte (suit le thème). Ni dégradé ni lueur.
export function Marque({ taille = 20 }: { taille?: number }) {
  return (
    <svg width={taille} height={taille} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M24.5 8.2A12 12 0 1 0 27.6 19" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="16" cy="16" r="3.5" fill="currentColor" />
    </svg>
  );
}
