// Raccourcis clavier : une seule écriture (« mod+shift+z ») pour déclarer, reconnaître et afficher.
// « mod » = Ctrl (Windows, Linux) ou ⌘ (Mac). Les chiffres sont lus par touche physique (Maj+1 donne « ! » ou « 1 »
// selon le clavier), les lettres par caractère (Ctrl+Z reste Ctrl+Z sur un clavier AZERTY).

const ORDRE = ["mod", "alt", "shift"] as const;

/** Forme canonique : modificateurs triés, minuscules. « Shift+Mod+Z » → « mod+shift+z ». */
export function normaliser(raccourci: string): string {
  const parties = raccourci.toLowerCase().split("+").map((p) => p.trim()).filter(Boolean);
  const touche = parties.filter((p) => !(ORDRE as readonly string[]).includes(p)).pop() ?? "";
  const mods = ORDRE.filter((m) => parties.includes(m));
  return [...mods, touche].join("+");
}

export interface ToucheClavier {
  key: string;
  code?: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
}

const NOMS: Record<string, string> = {
  " ": "espace", escape: "echap", delete: "suppr", backspace: "retour", enter: "entree",
  arrowleft: "gauche", arrowright: "droite", arrowup: "haut", arrowdown: "bas",
};

/** Raccourci canonique d'un événement clavier ; « » pour une touche de modification seule. */
export function deEvenement(e: ToucheClavier): string {
  let touche = e.key.toLowerCase();
  if (["control", "meta", "alt", "shift", "dead", "altgraph"].includes(touche)) return "";
  const chiffre = /^(?:Digit|Numpad)(\d)$/.exec(e.code ?? "");
  if (chiffre) touche = chiffre[1]!;
  touche = NOMS[touche] ?? touche;
  const mods = [e.ctrlKey || e.metaKey ? "mod" : "", e.altKey ? "alt" : "", e.shiftKey ? "shift" : ""].filter(Boolean);
  // « ? », « + »… : la majuscule fait partie du caractère, pas du raccourci
  if (!chiffre && touche.length === 1 && !/[a-z0-9]/.test(touche)) return [...mods.filter((m) => m !== "shift"), touche].join("+");
  return [...mods, touche].join("+");
}

const AFFICHAGE: Record<string, string> = {
  echap: "Échap", suppr: "Suppr", retour: "⌫", entree: "Entrée", espace: "Espace", gauche: "←", droite: "→", haut: "↑", bas: "↓",
};

export function estMac(plateforme = typeof navigator === "undefined" ? "" : navigator.platform): boolean {
  return /mac|iphone|ipad/i.test(plateforme);
}

/** Texte montré à l'utilisateur : « Ctrl+Maj+Z », ou « ⌘⇧Z » sur Mac. */
export function afficher(raccourci: string, mac = estMac()): string {
  const parties = normaliser(raccourci).split("+");
  const touche = parties.pop() ?? "";
  const nom = AFFICHAGE[touche] ?? (touche.length === 1 || /^f\d{1,2}$/.test(touche) ? touche.toUpperCase() : touche);
  if (mac) return parties.map((m) => (m === "mod" ? "⌘" : m === "alt" ? "⌥" : "⇧")).join("") + nom;
  return [...parties.map((m) => (m === "mod" ? "Ctrl" : m === "alt" ? "Alt" : "Maj")), nom].join("+");
}

/** Vrai si la cible est un champ de saisie : les raccourcis du Board ne s'y appliquent pas. */
export function dansChamp(t: EventTarget | null): boolean {
  return typeof Element !== "undefined" && t instanceof Element
    && Boolean(t.closest("input, textarea, select, [contenteditable='true'], [contenteditable='']"));
}
