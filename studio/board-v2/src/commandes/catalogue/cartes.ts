// Cartes intelligentes : chaque type de carte déclare ici ses actions contextuelles. Elles apparaissent dans la barre
// flottante au-dessus de la sélection et dans le menu contextuel, et restent trouvables dans la palette.
// Aucune de ces actions ne lance un agent ni un effet externe sans que le libellé le dise.
import { FileCheck2, FileWarning, ImageDown, Link2, ListTodo, Minimize2, PanelRight, ScanSearch, Spline, ThumbsUp, Trash2 } from "lucide-react";
import { cartesProches, estLivrable } from "../../cartes/etat";
import { COULEURS, type NomCouleur } from "../../etat/ui";
import { TAILLES } from "../../nodes/contexte";
import { TYPES_TABLEAU, boiteDe } from "../../outils/espace";
import type { ObjetBoard, Priorite, StyleLien } from "../../types";
import { EFFETS, creeraitBoucle, phraseBlocage, phraseConcrete } from "../../relations/effets";
import { RAISON_SELECTION, RAISON_UNE_CARTE, deType, enLecture, raisonLecture, raisonSelection, un, type ContexteBoard } from "../contexte";
import type { Commande } from "../types";

const CONTEXTUALISABLES = new Set(["note", "texte", "lien", "image", "capture", "pdf", "document", "audio", "video"]);
const INSPIRANTS = ["lien", "capture", "image", "pdf", "document", "video", "audio", "note"];
const titreDe = (o: ObjetBoard) => o.meta.titre || o.mission?.objectif || o.asset?.nom || o.contenu.split("\n")[0]?.slice(0, 60) || o.type;
const cartes = (c: ContexteBoard) => c.selection.filter((o) => !TYPES_TABLEAU.has(o.type));
const dessins = (c: ContexteBoard) => c.selection.filter((o) => TYPES_TABLEAU.has(o.type) && o.type !== "cadre");

export const NOMS_RELATION: Record<StyleLien, string> = {
  defaut: EFFETS.defaut.nom, inspire: EFFETS.inspire.nom, alimente: EFFETS.alimente.nom, utilise: EFFETS.utilise.nom, depend: EFFETS.depend.nom,
};
const RAISON_RELATION = "Vise d'abord une relation : clic droit sur une flèche entre deux cartes";
const nomCarte = (c: ContexteBoard, id: string) => {
  const o = c.b.objet(id);
  return o ? titreDe(o) : id;
};
/** Boucle que fermerait « dépend de » sur la relation visée (pré-contrôle : le serveur refuse de toute façon). */
const boucle = (c: ContexteBoard) => (c.lien ? creeraitBoucle(c.b.liens(), c.lien.source_id, c.lien.cible_id, c.lien.id) : null);
const NOMS_COULEUR: Record<NomCouleur, string> = {
  "": "Sans couleur", neutre: "Neutre", indigo: "Indigo", violet: "Violet", rose: "Rose", orange: "Orange", jaune: "Jaune", vert: "Vert", cyan: "Cyan", gris: "Gris",
};

const priorites: Commande<ContexteBoard>[] = (["P1", "P2", "P3", ""] as Priorite[]).map((p, i) => ({
  id: `carte.priorite.${p || "aucune"}`, libelle: p ? `Priorité ${p}` : "Sans priorité", raccourci: p ? String(i + 1) : "0",
  categorie: "Carte", niveau: "ecriture", emplacements: ["menu"], motsCles: "prioriser urgence",
  disponible: (c) => !enLecture(c) && cartes(c).length > 0 && cartes(c).length === c.selection.length,
  raison: (c) => raisonSelection(c) ?? "La priorité se pose sur des cartes, pas sur un tracé, une forme ou un cadre",
  actif: (c) => c.selection.every((o) => o.priorite === p),
  executer: (c) => c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { priorite: p } })), "Priorité"),
}));

const couleurs: Commande<ContexteBoard>[] = (["", ...COULEURS] as NomCouleur[]).map((couleur) => ({
  id: `style.couleur.${couleur || "aucune"}`, libelle: `Couleur : ${NOMS_COULEUR[couleur]}`, categorie: "Carte", niveau: "ecriture",
  motsCles: "teinte fond trait style accent",
  // « sans couleur » retire l'accent d'une carte : il lui faut une sélection (un tracé a toujours une couleur)
  disponible: (c) => !enLecture(c) && (couleur !== "" || c.selection.length > 0),
  raison: (c) => raisonLecture(c) ?? RAISON_SELECTION,
  actif: (c) => (c.selection.length ? c.selection.every((o) => (o.meta.couleur ?? "") === couleur) : c.ui.couleur === couleur),
  // avec une sélection : recolore les objets ; sans : choisit la couleur des prochains tracés
  executer: (c) => {
    if (couleur) c.b.ui.definir({ couleur });
    return c.selection.length ? c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { meta: { ...o.meta, couleur } } })), "Couleur") : undefined;
  },
}));

const epaisseurs: Commande<ContexteBoard>[] = ([[2, "fin"], [6, "moyen"], [12, "épais"], [24, "très épais"]] as const).map(([epaisseur, nom]) => ({
  id: `style.epaisseur.${epaisseur}`, libelle: `Trait ${nom}`, categorie: "Carte", niveau: "ecriture", motsCles: "épaisseur taille style",
  disponible: (c) => !enLecture(c) && (!c.selection.length || dessins(c).length === c.selection.length),
  raison: (c) => raisonLecture(c) ?? "L'épaisseur du trait ne s'applique qu'aux tracés, formes et flèches",
  actif: (c) => (c.selection.length ? c.selection.every((o) => o.meta.epaisseur === epaisseur) : c.ui.epaisseur === epaisseur),
  executer: (c) => {
    c.b.ui.definir({ epaisseur });
    return c.selection.length ? c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { meta: { ...o.meta, epaisseur } } })), "Épaisseur") : undefined;
  },
}));

const relations: Commande<ContexteBoard>[] = (Object.keys(NOMS_RELATION) as StyleLien[]).map((style) => ({
  id: `relation.type.${style}`, libelle: `Relation : ${NOMS_RELATION[style]}`, icone: Spline, categorie: "Carte", niveau: "ecriture", emplacements: ["menu"],
  motsCles: `lien flèche type effet ${style === "depend" ? "bloque bloquer dépendance prérequis" : style === "alimente" ? "livrable contexte joindre" : style === "inspire" ? "référence citation" : ""}`,
  disponible: (c) => Boolean(c.lien) && !enLecture(c) && !(style === "depend" && c.lien!.style !== "depend" && boucle(c)),
  concerne: (c) => Boolean(c.lien),
  raison: (c) => {
    if (!c.lien) return RAISON_RELATION;
    const b = raisonLecture(c) ? null : style === "depend" ? boucle(c) : null;
    return raisonLecture(c) ?? (b ? `Fermerait une boucle (${b.map((id) => `« ${nomCarte(c, id)} »`).join(" → ")}) : plus aucune de ces cartes ne pourrait démarrer` : null);
  },
  actif: (c) => c.lien?.style === style,
  // le type a un effet réel côté serveur : le message dit lequel, avec les deux cartes nommées
  executer: async (c) => {
    const l = c.lien!;
    await c.b.modifierLien(l.id, { style });
    c.b.toast(`${NOMS_RELATION[style]} — ${phraseConcrete(style, nomCarte(c, l.source_id), nomCarte(c, l.cible_id))}`);
  },
}));

export const commandesCartes: Commande<ContexteBoard>[] = [
  { id: "carte.ouvrir", libelle: "Ouvrir les détails", icone: PanelRight, raccourci: "entree", categorie: "Carte", niveau: "lecture", emplacements: ["flottante", "menu"],
    disponible: (c) => c.ui.presentation === null && cartes(c).length === 1 && c.selection.length === 1,
    raison: (c) => (c.ui.presentation !== null ? "Les détails sont masqués pendant la présentation" : RAISON_UNE_CARTE), executer: (c) => c.b.inspecter(un(c)!.id) },
  { id: "carte.relier", libelle: "Relier à…", icone: Link2, raccourci: "shift+l", categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "relation lien flèche connecter",
    disponible: (c) => !enLecture(c) && c.selection.length === 1 && !["trait", "cadre", "fleche"].includes(c.selection[0]!.type),
    concerne: (c) => c.selection.length === 1,
    raison: (c) => raisonLecture(c) ?? (c.selection.length !== 1 ? "Sélectionne une seule carte : c'est le départ de la relation"
      : "Un trait, un cadre ou une flèche libre ne se relie pas : relie des cartes ou des formes"),
    executer: (c) => {
      c.b.ui.definir({ liaison: un(c)!.id, outil: "selection" });
      c.b.toast("Clique la carte à relier (Échap pour annuler)");
    } },
  { id: "carte.analyser", libelle: "Analyser avec Jarvis", icone: ScanSearch, categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "contextualiser résumé propositions ia",
    // une carte bloquée par une dépendance non terminée ne se lance pas : le serveur refuse, l'interface le dit avant
    disponible: (c) => !enLecture(c) && Boolean(un(c)) && CONTEXTUALISABLES.has(un(c)!.type) && !un(c)!.relations?.bloquee,
    concerne: (c) => Boolean(un(c)) && CONTEXTUALISABLES.has(un(c)!.type),
    raison: (c) => {
      const o = un(c);
      if (raisonLecture(c) || !o) return raisonLecture(c) ?? RAISON_UNE_CARTE;
      if (!CONTEXTUALISABLES.has(o.type)) return "Jarvis analyse les notes, liens, images, documents, audios et vidéos — pas ce type d'objet";
      return `${phraseBlocage(o.relations) ?? "Carte bloquée"} : termine d'abord ce dont elle dépend, ou retire la relation « Dépend de »`;
    },
    executer: (c) => c.b.contextualiser(un(c)!.id) },
  { id: "carte.tacheInspiree", libelle: "Créer une tâche inspirée de ceci", icone: ListTodo, categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "todo à faire action",
    disponible: (c) => !enLecture(c) && Boolean(deType(c, ...INSPIRANTS)),
    raison: (c) => raisonLecture(c) ?? "Sélectionne une seule carte source : lien, capture, image, document, média ou note",
    // une note « Tâche », reliée à sa source par « Inspire » : rien n'est confié à un agent
    executer: (c) => c.b.grouper("Tâche inspirée", async () => {
      const src = un(c)!;
      const titre = titreDe(src);
      const origine = src.meta.url ? `\n\nSource : ${src.meta.url}` : "";
      const id = await c.b.creer({ type: "note", contenu: `- [ ] À faire, d'après « ${titre} »${origine}`, x: Math.round(src.x + src.largeur + 80), y: Math.round(src.y),
        largeur: 408, hauteur: 260, priorite: src.priorite, meta: { titre: `Tâche : ${titre}`.slice(0, 80), tags: ["tâche"] }, analyser: false }, "Tâche inspirée");
      await c.b.lier(src.id, id, "inspire");
      c.b.selectionner([id]);
      c.b.toast("Tâche notée et reliée à sa source. Rien n'est confié à un agent : « Lancer une mission » le fait.");
    }) },
  { id: "carte.proches", libelle: "Trouver des cartes proches", icone: ScanSearch, categorie: "Carte", niveau: "lecture", emplacements: ["flottante", "menu"],
    motsCles: "similaires semblables liées",
    disponible: (c) => Boolean(un(c)) && cartes(c).length === 1, raison: () => RAISON_UNE_CARTE,
    // proximité de vocabulaire calculée ici, sans modèle : dit comme tel
    executer: (c) => {
      const src = un(c)!;
      const proches = cartesProches(src, c.b.objets());
      if (!proches.length) {
        c.b.toast("Aucune carte ne partage de mots avec celle-ci");
        return;
      }
      c.b.selectionner([src.id, ...proches.map((p) => p.objet.id)]);
      c.b.cadrer([src, ...proches.map((p) => p.objet)].map(boiteDe).reduce((a, b) => {
        const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
        return { x, y, largeur: Math.max(a.x + a.largeur, b.x + b.largeur) - x, hauteur: Math.max(a.y + a.hauteur, b.y + b.hauteur) - y };
      }), 0.15);
      c.b.toast(`${proches.length} carte${proches.length > 1 ? "s" : ""} proche${proches.length > 1 ? "s" : ""} par le vocabulaire (${proches[0]!.communs.slice(0, 3).join(", ")}…)`);
    } },
  { id: "carte.relecture", libelle: (c) => (un(c)?.relecture?.statut === "demandee" ? "Retirer la demande de relecture" : "Faire relire"), icone: FileCheck2,
    categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"], motsCles: "revue vérifier livrable",
    disponible: (c) => !enLecture(c) && Boolean(un(c)) && estLivrable(un(c)!),
    concerne: (c) => un(c)?.type === "mission",
    raison: (c) => raisonLecture(c) ?? (!un(c) ? RAISON_UNE_CARTE
      : un(c)!.type === "mission" ? "Cette mission n'a pas encore rendu de livrable : il n'y a rien à relire"
        : "Seule une carte qui porte un livrable se fait relire"),
    // la demande entre dans la file du serveur (lisible par le chef : jarvis board relectures) ; aucun agent n'est lancé
    executer: async (c) => {
      const o = un(c)!;
      const ouverte = o.relecture?.statut === "demandee";
      const r = await c.b.relire(o.id, ouverte ? "annuler" : "demander");
      if (r) c.b.toast(ouverte ? "Demande de relecture retirée." : "Relecture demandée : elle est dans la file du chef. Aucun agent n'est lancé par cette demande.");
    } },
  ...(["pret", "corrections"] as const).map((verdict): Commande<ContexteBoard> => ({
    id: `carte.relecture.${verdict}`, libelle: verdict === "pret" ? "Relecture : livrable prêt" : "Relecture : corrections demandées",
    icone: verdict === "pret" ? ThumbsUp : FileWarning, categorie: "Carte", niveau: "ecriture", emplacements: ["menu"], motsCles: "verdict revue valider refuser",
    disponible: (c) => !enLecture(c) && un(c)?.relecture?.statut === "demandee",
    raison: (c) => raisonLecture(c) ?? (un(c) ? "Aucune relecture n'est en attente sur cette carte : demande-la d'abord (« Faire relire »)" : RAISON_UNE_CARTE),
    executer: async (c) => {
      const r = await c.b.relire(un(c)!.id, "rendre", { verdict });
      if (r) c.b.toast(verdict === "pret" ? "Verdict enregistré : livrable prêt." : "Verdict enregistré : corrections demandées. Rien n'est relancé automatiquement.");
    },
  })),
  { id: "carte.compacte", libelle: (c) => (un(c)?.meta.compact ? "Taille normale" : "Vignette compacte"), icone: Minimize2, categorie: "Carte", niveau: "ecriture",
    emplacements: ["menu"], disponible: (c) => !enLecture(c) && cartes(c).length === 1 && c.selection.length === 1,
    raison: (c) => raisonLecture(c) ?? RAISON_UNE_CARTE,
    executer: (c) => {
      const o = un(c)!;
      const [largeur, hauteur] = TAILLES[o.type]?.defaut ?? [408, 320];
      return c.b.modifier([{ id: o.id, champs: o.meta.compact ? { meta: { ...o.meta, compact: false }, largeur, hauteur }
        : { meta: { ...o.meta, compact: true }, largeur: 240, hauteur: 96 } }], "Format de la carte");
    } },
  { id: "carte.sortirDuDossier", libelle: "Sortir du dossier", categorie: "Carte", niveau: "ecriture",
    disponible: (c) => !enLecture(c) && Boolean(un(c)?.parent_id),
    raison: (c) => raisonLecture(c) ?? "Cette commande s'applique à une carte rangée dans un dossier",
    executer: (c) => {
      const o = un(c)!;
      const dossier = c.b.objet(o.parent_id!);
      return c.b.modifier([{ id: o.id, champs: { parent_id: null, x: (dossier?.x ?? 0) + 40, y: (dossier?.y ?? 0) + (dossier?.hauteur ?? 150) + 40 } }], "Sortie du dossier");
    } },
  ...priorites,
  ...couleurs,
  ...epaisseurs,
  ...relations,
  { id: "relation.supprimer", libelle: "Supprimer la relation", icone: Trash2, categorie: "Carte", niveau: "ecriture", emplacements: ["menu"],
    disponible: (c) => Boolean(c.lien) && !enLecture(c), raison: (c) => (c.lien ? raisonLecture(c) : RAISON_RELATION),
    executer: (c) => c.b.supprimerLien(c.lien!.id) },
  { id: "export.png", libelle: (c) => (deType(c, "cadre") ? "Exporter ce cadre en PNG" : "Exporter la sélection en PNG"), icone: ImageDown,
    raccourci: "mod+shift+e", categorie: "Export", niveau: "lecture", emplacements: ["flottante", "menu"], motsCles: "image capture télécharger",
    disponible: (c) => c.selection.length > 0, raison: () => "Sélectionne d'abord ce que tu veux exporter (une carte, plusieurs, ou un cadre)",
    executer: (c) => {
      const cadre = deType(c, "cadre");
      return c.b.exporterPng(c.selection.map((o) => o.id), cadre ? titreDe(cadre) : "selection");
    } },
];
