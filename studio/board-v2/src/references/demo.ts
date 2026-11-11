// Jeu de démonstration de la Bibliothèque de références : sites FICTIFS, images de la maquette, recherche en mémoire.
// Rien n'est capturé ni envoyé ; le mode est signalé « DÉMO » dans la barre.
import type { Fiche, Filtres, Liste, Passage, Recherche, Reference } from "./api";

const JOUR = 86400;
const T0 = 1794268800; // date fixe : les captures de démonstration ne « vieillissent » pas à l'écran

function fiche(i: number, titre: string, url: string, collection: string, etiquettes: string[], description: string,
  palette: [string, number][], polices: Record<string, string>, sections: [string, number, string][], image: string): Fiche {
  const id = `RF-demo0000000${i}`;
  const fichier = (largeur: number, hauteur: number) => ({ asset_id: `AS-demo${i}`, url: image, sha256: `demo${i}`.padEnd(64, "0"), largeur, hauteur });
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
    avertissement: "Contenu de démonstration : sites fictifs.",
  };
}

const FICHES: Fiche[] = [
  fiche(1, "Atelier Lumière — studio de design", "https://atelier-lumiere.example/", "inspiration", ["studio", "éditorial"],
    "Sites élégants pour marques exigeantes.", [["#F7F3EC", 0.62], ["#1C1B19", 0.2], ["#C8553D", 0.06], ["#8A8578", 0.05]],
    { titre: "Fraunces", corps: "Inter" }, [
      ["Des sites qui respirent", 1, "Nous concevons des interfaces sobres, avec une grande place laissée au blanc et une hiérarchie typographique nette."],
      ["Nos prix", 2, "Trois formules claires, sans frais cachés. Le forfait vitrine démarre à 2 400 € ; le sur-mesure est chiffré après un atelier."],
      ["Typographie", 2, "Une police à empattement pour les titres, une linéale pour le corps du texte : le contraste porte la voix de la marque."],
    ], "/v2/demo/ressource-1.jpg"),
  fiche(2, "Nordkit — tableau de bord d'équipe", "https://nordkit.example/", "saas", ["tableau de bord", "sombre"],
    "Le suivi d'équipe sans réunion.", [["#0E1119", 0.58], ["#E8EAF2", 0.18], ["#5B6CFF", 0.09], ["#22D3EE", 0.03]],
    { titre: "Geist", corps: "Geist", code: "Geist Mono" }, [
      ["Le suivi d'équipe sans réunion", 1, "Un héros sombre, une capture du produit en perspective, et un seul appel à l'action : essayer gratuitement."],
      ["Tarifs", 2, "Gratuit jusqu'à cinq personnes, puis un prix par siège. Le tableau des formules met la formule recommandée en avant."],
      ["Preuves", 2, "Logos de clients en niveaux de gris, puis trois chiffres : temps gagné, réunions évitées, adoption en une semaine."],
    ], "/v2/demo/ressource-2.jpg"),
  fiche(3, "Maison Verdier — boutique de thés", "https://maison-verdier.example/", "e-commerce", ["boutique", "chaleureux"],
    "Thés d'origine, torréfiés à la commande.", [["#F3EDE2", 0.5], ["#2F3B2C", 0.24], ["#B98B4E", 0.08], ["#D9CBB3", 0.07]],
    { titre: "Cormorant Garamond", corps: "Work Sans" }, [
      ["Thés d'origine, torréfiés à la commande", 1, "Photographie plein cadre du produit, bouton d'achat visible sans défiler, livraison rappelée sous le prix."],
      ["La fiche produit", 2, "Galerie à gauche, récit de l'origine à droite, puis les notes de dégustation en pictogrammes et les avis vérifiés."],
      ["Le panier", 2, "Un tiroir latéral plutôt qu'une page : le total, les frais de port et le paiement en un geste restent toujours visibles."],
    ], "/v2/demo/ressource-3.jpg"),
  fiche(4, "Carnet de bord — portfolio d'illustratrice", "https://carnet-de-bord.example/", "inspiration", ["portfolio", "éditorial"],
    "Illustrations et carnets de voyage.", [["#FCFBF8", 0.66], ["#22201D", 0.14], ["#3D5AFE", 0.05], ["#E0457B", 0.03]],
    { titre: "Editorial New", corps: "Söhne" }, [
      ["Illustrations et carnets de voyage", 1, "Grille irrégulière d'images, légendes discrètes au survol, navigation réduite à trois mots."],
      ["À propos", 2, "Un portrait dessiné, une biographie de quatre phrases, et la liste des clients sous forme de simple texte."],
      ["Contact", 2, "Pas de formulaire : une adresse écrite en grand, que l'on copie d'un clic."],
    ], "/v2/demo/montagne.jpg"),
];

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
  if (racines.length) for (const r of retenues(f)) r.sections.forEach((s, position) => {
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
        capture_url: r.vignette_url, vignette_url: r.vignette_url, zone: null, lien: `/v2/?demo=1&vue=references&ref=${r.id}` } });
  });
  resultats.sort((a, b) => b.score - a.score);
  return { question: q, mode: "bm25", vecteurs: "desactive", moteur_mots: "demo", resultats: resultats.slice(0, 12), avertissement: "Démonstration." };
}
