// Jeu de démonstration de la Bibliothèque de références : sites FICTIFS, recherche en mémoire. Leurs captures sont de vraies
// captures de pages écrites pour l'occasion avec la palette et les polices de chaque fiche (scripts/references-demo.mjs).
// Rien n'est capturé ni envoyé ; le mode est signalé « DÉMO » dans la barre.
import type { Fiche, Filtres, Liste, Observation, Passage, Recherche, Reference } from "./api";

const JOUR = 86400;
const T0 = 1794268800; // date fixe : les captures de démonstration ne « vieillissent » pas à l'écran

function fiche(i: number, titre: string, url: string, collection: string, etiquettes: string[], description: string,
  palette: [string, number][], polices: Record<string, string>, sections: [string, number, string][], site: string): Fiche {
  const id = `RF-demo0000000${i}`;
  const image = `/v2/demo/ref-${site}-bureau.jpg`;
  const fichier = (largeur: number, hauteur: number) => ({ asset_id: `AS-demo${i}`, url: `/v2/demo/ref-${site}-${largeur < 800 ? "mobile" : "bureau"}.jpg`, sha256: `demo${i}`.padEnd(64, "0"), largeur, hauteur });
  return {
    id, type: "site", source: url, url, titre, description, collection, etiquettes, statut: "prete", raison: "", supprime: false,
    cree: T0 - i * JOUR, maj: T0 - i * JOUR, capture_le: T0 - i * JOUR, vignette_url: image,
    palette: palette.map(([hex, part]) => ({ hex, part })), polices, fragments: sections.length,
    fichiers: { bureau_vue: fichier(1440, 900), bureau_page: fichier(1440, 900), mobile_vue: fichier(390, 844), mobile_page: fichier(390, 844) },
    sections: sections.map(([t, niveau, texte], k) => ({ titre: t, niveau, zone: { y: k * 300, hauteur: 300 }, caracteres: texte.length, extrait: texte })),
    couleurs_css: { fond: palette[0]![0], texte: palette[1]![0], accent: palette[2]![0] },
    polices_declarees: Array.from(new Set(Object.values(polices))),
    structure: { entete: true, navigation: 5, principal: true, pied: true, sections: sections.filter((s) => s[1] > 0).map((s) => s[0]), images: 6 + i, boutons: 3,
      formulaires: 1, hauteur_page: 3200, heros: { titre: sections[0]![0], appel_action: "Commencer", visible_d_emblee: true } },
    liens: [{ url: `${url}tarifs`, texte: "Tarifs", externe: false, zone: "entete" }, { url: `${url}a-propos`, texte: "À propos", externe: false, zone: "entete" }],
    langue: "fr", tronquee: false, empreinte: `demo${i}`.padEnd(64, "0"),
    index: { fragments: sections.length, vecteurs: 0, modele: "", dimension: 0, version_index: 1 },
    observations: [
      { id: `OB-demo${i}structure`, type: "structure", titre: "Hiérarchie de la page", texte: sections[0]![2],
        preuve: { reference_id: id, capture_le: T0 - i * JOUR, capture_url: image }, nature: "donnee_non_fiable" },
      { id: `OB-demo${i}palette`, type: "palette", titre: "Palette du premier écran",
        texte: palette.map(([hex, part]) => `${hex} · ${Math.round(part * 100)} %`).join("\n"),
        ecran: "bureau", preuve: { reference_id: id, capture_le: T0 - i * JOUR, capture_url: image }, nature: "donnee_non_fiable" },
    ],
    avertissement: "Contenu de démonstration : sites fictifs.",
  };
}

const FICHES: Fiche[] = [
  fiche(1, "Atelier Lumière — studio de design", "https://atelier-lumiere.example/", "inspiration", ["studio", "éditorial"],
    "Sites élégants pour marques exigeantes.", [["#F7F3EC", 0.62], ["#1C1B19", 0.2], ["#C8553D", 0.06], ["#8A8578", 0.05]],
    { titre: "Newsreader", corps: "Inter" }, [
      ["Des sites qui respirent", 1, "Nous concevons des interfaces sobres, avec une grande place laissée au blanc et une hiérarchie typographique nette."],
      ["Nos prix", 2, "Trois formules claires, sans frais cachés. Le forfait vitrine démarre à 2 400 € ; le sur-mesure est chiffré après un atelier."],
      ["Typographie", 2, "Une police à empattement pour les titres, une linéale pour le corps du texte : le contraste porte la voix de la marque."],
    ], "atelier"),
  fiche(2, "Nordkit — tableau de bord d'équipe", "https://nordkit.example/", "saas", ["tableau de bord", "sombre"],
    "Le suivi d'équipe sans réunion.", [["#0E1119", 0.58], ["#E8EAF2", 0.18], ["#4CC38A", 0.09], ["#232838", 0.06]],
    { titre: "Inter", corps: "Inter", code: "IBM Plex Mono" }, [
      ["Le suivi d'équipe sans réunion", 1, "Un héros sombre, la vue « Cette semaine » du produit qui monte du bas de l'écran, et un seul appel à l'action : essayer gratuitement."],
      ["Tarifs", 2, "Gratuit jusqu'à cinq personnes, puis un prix par siège. Le tableau des formules met la formule recommandée en avant."],
      ["Preuves", 2, "Logos de clients en niveaux de gris, puis trois chiffres : temps gagné, réunions évitées, adoption en une semaine."],
    ], "nordkit"),
  fiche(3, "Maison Verdier — boutique de thés", "https://maison-verdier.example/", "e-commerce", ["boutique", "chaleureux"],
    "Thés d'origine, torréfiés à la commande.", [["#F3EDE2", 0.5], ["#2F3B2C", 0.24], ["#B98B4E", 0.08], ["#D9CBB3", 0.07]],
    { titre: "Bitstream Charter", corps: "Instrument Sans" }, [
      ["Thés d'origine, torréfiés à la commande", 1, "Photographie plein cadre du produit, bouton d'achat visible sans défiler, livraison rappelée sous le prix."],
      ["La fiche produit", 2, "Galerie à gauche, récit de l'origine à droite, puis les notes de dégustation en pictogrammes et les avis vérifiés."],
      ["Le panier", 2, "Un tiroir latéral plutôt qu'une page : le total, les frais de port et le paiement en un geste restent toujours visibles."],
    ], "verdier"),
  fiche(4, "Carnet de bord — portfolio d'illustratrice", "https://carnet-de-bord.example/", "inspiration", ["portfolio", "éditorial"],
    "Illustrations et carnets de voyage.", [["#FCFBF8", 0.66], ["#22201D", 0.14], ["#E0457B", 0.05], ["#F2B544", 0.04]],
    { titre: "Instrument Sans", corps: "IBM Plex Mono" }, [
      ["Illustrations et carnets de voyage", 1, "Grille irrégulière d'images, légendes discrètes sous chacune, navigation réduite à trois mots."],
      ["À propos", 2, "Un portrait dessiné, une biographie de quatre phrases, et la liste des clients sous forme de simple texte."],
      ["Contact", 2, "Pas de formulaire : une adresse écrite en grand, que l'on copie d'un clic."],
    ], "carnet"),
];

function exempleLocal(i: number, type: Reference["type"], titre: string, texte: string, visuel?: string): Fiche {
  const id = `RF-demo0000000${i}`;
  return { ...FICHES[0]!, id, type, titre, url: "", source: "Démonstration", description: texte,
    collection: "atelier", etiquettes: [], recapturable: false, vignette_url: visuel ?? null, fichiers: {},
    polices: {}, couleurs_css: {}, polices_declarees: [], palette: [], structure: null, liens: [], observations: [],
    releve: undefined,
    sections: [{ titre, niveau: 2, zone: null, caracteres: texte.length, extrait: texte }], fragments: 1,
    index: { fragments: 1, vecteurs: 0, modele: "", dimension: 0, version_index: 1 } };
}

const composant = exempleLocal(5, "composant", "Carte de sélection lumineuse",
  "Un halo suit le pointeur. Le titre reste lisible au repos et un contour signale la sélection au clavier.");
composant.perimetre = { type: "element" };
composant.releve = { bureau: {
  mesures: { largeur: 320, hauteur: 200, elements_observes: 3, conteneurs_flex: 0, conteneurs_grid: 1, controles_sans_libelle_apparent: 0 },
  elements: [{ role: "button", nom: "Choisir la collection", largeur: 320, hauteur: 200, affichage: "grid", espacement: "12px", rayon: "16px", police: "Geist", taille: "16px" }],
  mouvements: [{ nature: "transition CSS", duree: "180 ms", courbe: "ease-out", propriete: "opacity" }],
} };
composant.observations = [
  { id: "OB-demo5element", type: "element", titre: "Choisir la collection", ecran: "bureau",
    texte: "Bouton · 320 × 200 px\nDisposition en grille · espacement 12 px · rayon 16 px\nGeist 16 px",
    preuve: { reference_id: composant.id, capture_le: composant.capture_le }, nature: "donnee_non_fiable" },
  { id: "OB-demo5mouvement", type: "mouvement", titre: "Transition d’opacité", ecran: "bureau",
    texte: "Transition CSS · 180 ms · ease-out",
    preuve: { reference_id: composant.id, capture_le: composant.capture_le }, nature: "donnee_non_fiable" },
];
const lumiere = FICHES[0]!;
const preuveLumiere = { reference_id: lumiere.id, capture_le: lumiere.capture_le, capture_url: lumiere.fichiers.bureau_page!.url };
const grilleLumiere = {
  role: "main", nom: "", largeur: 1440, hauteur: 576, affichage: "grid", espacement: "64px", rayon: "0px",
  police: "Inter", taille: "16px", alignement: "normal / end", colonnes: "639.219px 608.781px",
  selecteur: "main", x: 0, y: 78, padding: "56px 64px 0px", couleur: "#1C1B19", fond: "rgba(0, 0, 0, 0)",
};
const titreLumiere = {
  role: "h1", nom: "", largeur: 639, hauteur: 180, affichage: "block", espacement: "normal", rayon: "0px",
  police: "Newsreader", taille: "92px", alignement: "start", selecteur: "h1", parent_selecteur: "main > div",
  x: 64, y: 304, interligne: "90.16px", graisse: "400", couleur: "#1C1B19",
};
lumiere.releve = {
  bureau: {
    mesures: { largeur: 1440, hauteur: 900, elements_observes: 2, conteneurs_grid: 1, conteneurs_flex: 0 },
    elements: [grilleLumiere, titreLumiere],
    mouvements: [],
    echantillon: { examines: 2, limite: 450, tronque: false },
    tokens: { espacement: [{ valeur: "64px", occurrences: 1 }], typographie: [{ valeur: "Newsreader · 92px / 90.16px", occurrences: 1 }] },
  },
  mobile: {
    mesures: { largeur: 390, hauteur: 844, elements_observes: 2, conteneurs_grid: 1, conteneurs_flex: 0 },
    elements: [{ ...grilleLumiere, largeur: 390, hauteur: 720, espacement: "32px", colonnes: "350px", padding: "24px 20px 0px" },
      { ...titreLumiere, largeur: 350, hauteur: 153, taille: "52px", interligne: "50.96px" }],
    mouvements: [],
    echantillon: { examines: 2, limite: 450, tronque: false },
  },
};
lumiere.observations = [
  ...lumiere.observations!,
  { id: "OB-demo1grille", type: "element", titre: "Grille principale", ecran: "bureau",
    texte: "Affichage CSS : grid\nColonnes : 639.219px 608.781px\nEspacement : 64px\nAlignement : normal / end\nSélecteur CSS : main",
    element: grilleLumiere,
    preuve: { ...preuveLumiere, zone: { y: 78, hauteur: 576 } }, nature: "donnee_non_fiable" },
  { id: "OB-demo1titre", type: "element", titre: "Titre de la section d’ouverture", ecran: "bureau",
    texte: "Police : Newsreader\nTaille : 92px\nInterligne : 90.16px\nGraisse : 400\nSélecteur CSS : h1",
    element: titreLumiere,
    preuve: { ...preuveLumiere, zone: { y: 304, hauteur: 180 } }, nature: "donnee_non_fiable" },
  { id: "OB-demo1mobile", type: "element", titre: "Grille principale sur mobile", ecran: "mobile",
    texte: "Affichage CSS : grid\nColonnes : 350px\nEspacement : 32px\nSélecteur CSS : main",
    element: lumiere.releve.mobile!.elements[0],
    preuve: { ...preuveLumiere, capture_url: lumiere.fichiers.mobile_page!.url }, nature: "donnee_non_fiable" },
  { id: "OB-demo1responsive", type: "comparaison", titre: "La composition change sur mobile",
    texte: "La grille passe de deux colonnes sur ordinateur à une colonne sur mobile. L’espacement passe de 64px à 32px, et le titre de 92px à 52px.",
    preuve: preuveLumiere, nature: "donnee_non_fiable" },
  { id: "OB-demo1typo", type: "typographie", titre: "Rôles typographiques",
    texte: "Titres : Newsreader\nCorps : Inter", preuve: preuveLumiere, nature: "donnee_non_fiable" },
];
FICHES.push(composant);

const norme = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/œ/g, "oe").toLowerCase();
const retenues = (f: Filtres) => FICHES.filter((r) => (f.collection === null || r.collection === f.collection) && (!f.etiquette || r.etiquettes.includes(f.etiquette)));
const facettes = (valeurs: string[]) => Object.entries(valeurs.reduce<Record<string, number>>((a, v) => ({ ...a, [v]: (a[v] ?? 0) + 1 }), {})).map(([nom, n]) => ({ nom, n }));

export function listerDemo(f: Filtres): Liste {
  const resume = ({ fichiers: _f, sections: _s, liens: _l, structure: _st, ...r }: Fiche): Reference => r;
  return { references: retenues(f).map(resume), total: FICHES.length, collections: facettes(FICHES.map((r) => r.collection)).sort((a, b) => a.nom.localeCompare(b.nom)),
    etiquettes: facettes(FICHES.flatMap((r) => r.etiquettes)).sort((a, b) => b.n - a.n),
    moteur: { mots: "fts5", vecteurs: false, modele: "", fragments_vectorises: 0, capture: false } };
}
export function voirDemo(id: string): Promise<Fiche> {
  const r = FICHES.find((x) => x.id === id);
  return r ? Promise.resolve(r) : Promise.reject(new Error("Référence inconnue."));
}
export function chercherDemo(q: string, f: Filtres): Recherche {
  const racines = (norme(q).match(/[0-9a-z]+/g) ?? []).filter((m) => m.length > 2).map((m) => (m.length > 4 ? m.replace(/(es|s|x|e)$/, "") : m));
  const resultats: Passage[] = [];
  if (racines.length) for (const r of retenues(f)) {
    const passages: { titre: string; extrait: string; observation?: Observation }[] = [
      ...r.sections,
      ...(r.observations ?? []).map((o) => ({ titre: o.titre, extrait: o.texte, observation: o })),
    ];
    passages.forEach((s, position) => {
    const texte = s.extrait;
    const n = norme(texte);
    const motif = () => new RegExp(`(?<![0-9a-z])(?:${racines.join("|")})[0-9a-z]*`, "g");
    const surlignages: [number, number][] = Array.from(n.matchAll(motif()), (m) => [m.index, m.index + m[0].length]);
    const titre: [number, number][] = Array.from(norme(s.titre).matchAll(motif()), (m) => [m.index, m.index + m[0].length]);
    const dansLeTitre = titre.length;
    if (!surlignages.length && !dansLeTitre) return;
    resultats.push({ fragment_id: `FR-demo${r.id.slice(-1)}${position}`.padEnd(15, "0"), reference_id: r.id, score: surlignages.length + 2 * dansLeTitre,
      rangs: { mots: 1, vecteurs: null }, section: s.titre, section_surlignages: titre, position, extrait: { texte, surlignages },
      citation: { reference_id: r.id, titre: r.titre, url: r.url, type: r.type, collection: r.collection, section: s.titre, capture_le: r.capture_le,
        capture_url: s.observation?.preuve.capture_url ?? r.vignette_url, vignette_url: r.vignette_url,
        zone: s.observation?.preuve.zone ?? null,
        ...(s.observation ? { observation_id: s.observation.id } : {}),
        lien: `/v2/?demo=1&vue=references&ref=${r.id}${s.observation ? "&observation=" + s.observation.id : ""}` } });
    });
  }
  resultats.sort((a, b) => b.score - a.score);
  return { question: q, mode: "bm25", vecteurs: "desactive", moteur_mots: "demo", resultats: resultats.slice(0, 12), avertissement: "Démonstration." };
}
