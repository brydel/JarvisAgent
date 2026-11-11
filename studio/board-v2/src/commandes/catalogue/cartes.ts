// Cartes intelligentes : chaque type de carte déclare ici ses actions contextuelles. Elles apparaissent dans la barre
// flottante au-dessus de la sélection et dans le menu contextuel, et restent trouvables dans la palette.
// Aucune de ces actions ne lance un agent ni un effet externe sans que le libellé le dise.
import { FileCheck2, ImageDown, Link2, ListTodo, Minimize2, PanelRight, ScanSearch, Sparkles, Spline, Trash2 } from "lucide-react";
import { cartesProches, estLivrable } from "../../cartes/etat";
import { COULEURS, type NomCouleur } from "../../etat/ui";
import { TAILLES } from "../../nodes/contexte";
import { TYPES_TABLEAU, boiteDe } from "../../outils/espace";
import type { ObjetBoard, Priorite, StyleLien } from "../../types";
import { deType, enLecture, un, type ContexteBoard } from "../contexte";
import type { Commande } from "../types";

const CONTEXTUALISABLES = new Set(["note", "texte", "lien", "image", "capture", "pdf", "document", "audio", "video"]);
const INSPIRANTS = ["lien", "capture", "image", "pdf", "document", "video", "audio", "note"];
const titreDe = (o: ObjetBoard) => o.meta.titre || o.mission?.objectif || o.asset?.nom || o.contenu.split("\n")[0]?.slice(0, 60) || o.type;
const cartes = (c: ContexteBoard) => c.selection.filter((o) => !TYPES_TABLEAU.has(o.type));
const dessins = (c: ContexteBoard) => c.selection.filter((o) => TYPES_TABLEAU.has(o.type) && o.type !== "cadre");

export const NOMS_RELATION: Record<StyleLien, string> = {
  defaut: "Relation simple", inspire: "Inspire", alimente: "Alimente", utilise: "Utilisé par", depend: "Dépend de",
};
const NOMS_COULEUR: Record<NomCouleur, string> = {
  "": "Sans couleur", neutre: "Neutre", indigo: "Indigo", violet: "Violet", rose: "Rose", orange: "Orange", jaune: "Jaune", vert: "Vert", cyan: "Cyan", gris: "Gris",
};

const priorites: Commande<ContexteBoard>[] = (["P1", "P2", "P3", ""] as Priorite[]).map((p, i) => ({
  id: `carte.priorite.${p || "aucune"}`, libelle: p ? `Priorité ${p}` : "Sans priorité", raccourci: p ? String(i + 1) : "0",
  categorie: "Carte", niveau: "ecriture", emplacements: ["menu"], motsCles: "prioriser urgence",
  disponible: (c) => !enLecture(c) && cartes(c).length > 0 && cartes(c).length === c.selection.length,
  actif: (c) => c.selection.every((o) => o.priorite === p),
  executer: (c) => c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { priorite: p } })), "Priorité"),
}));

const couleurs: Commande<ContexteBoard>[] = (["", ...COULEURS] as NomCouleur[]).map((couleur) => ({
  id: `style.couleur.${couleur || "aucune"}`, libelle: `Couleur : ${NOMS_COULEUR[couleur]}`, categorie: "Carte", niveau: "ecriture",
  motsCles: "teinte fond trait style accent",
  // « sans couleur » retire l'accent d'une carte : il lui faut une sélection (un tracé a toujours une couleur)
  disponible: (c) => !enLecture(c) && (couleur !== "" || c.selection.length > 0),
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
  actif: (c) => (c.selection.length ? c.selection.every((o) => o.meta.epaisseur === epaisseur) : c.ui.epaisseur === epaisseur),
  executer: (c) => {
    c.b.ui.definir({ epaisseur });
    return c.selection.length ? c.b.modifier(c.selection.map((o) => ({ id: o.id, champs: { meta: { ...o.meta, epaisseur } } })), "Épaisseur") : undefined;
  },
}));

const relations: Commande<ContexteBoard>[] = (Object.keys(NOMS_RELATION) as StyleLien[]).map((style) => ({
  id: `relation.type.${style}`, libelle: `Relation : ${NOMS_RELATION[style]}`, icone: Spline, categorie: "Carte", niveau: "ecriture", emplacements: ["menu"],
  motsCles: "lien flèche type",
  disponible: (c) => Boolean(c.lien) && !enLecture(c),
  actif: (c) => c.lien?.style === style,
  executer: (c) => c.b.modifierLien(c.lien!.id, { style }),
}));

export const commandesCartes: Commande<ContexteBoard>[] = [
  { id: "carte.ouvrir", libelle: "Ouvrir les détails", icone: PanelRight, raccourci: "entree", categorie: "Carte", niveau: "lecture", emplacements: ["flottante", "menu"],
    disponible: (c) => c.ui.presentation === null && cartes(c).length === 1 && c.selection.length === 1, executer: (c) => c.b.inspecter(un(c)!.id) },
  { id: "carte.relier", libelle: "Relier à…", icone: Link2, raccourci: "shift+l", categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "relation lien flèche connecter",
    disponible: (c) => !enLecture(c) && c.selection.length === 1 && !["trait", "cadre", "fleche"].includes(c.selection[0]!.type),
    executer: (c) => {
      c.b.ui.definir({ liaison: un(c)!.id, outil: "selection" });
      c.b.toast("Clique la carte à relier (Échap pour annuler)");
    } },
  { id: "carte.analyser", libelle: "Analyser avec Jarvis", icone: Sparkles, categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "contextualiser résumé propositions ia",
    disponible: (c) => !enLecture(c) && Boolean(un(c)) && CONTEXTUALISABLES.has(un(c)!.type), executer: (c) => c.b.contextualiser(un(c)!.id) },
  { id: "carte.tacheInspiree", libelle: "Créer une tâche inspirée de ceci", icone: ListTodo, categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"],
    motsCles: "todo à faire action",
    disponible: (c) => !enLecture(c) && Boolean(deType(c, ...INSPIRANTS)),
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
    disponible: (c) => Boolean(un(c)) && cartes(c).length === 1,
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
  { id: "carte.relecture", libelle: (c) => (un(c)?.meta.relecture ? "Retirer la demande de relecture" : "Faire relire"), icone: FileCheck2,
    categorie: "Carte", niveau: "ecriture", emplacements: ["flottante", "menu"], motsCles: "revue vérifier livrable",
    disponible: (c) => !enLecture(c) && Boolean(un(c)) && estLivrable(un(c)!),
    // pose la demande sur la carte (visible de tous, commentée) ; ne lance aucun agent
    executer: async (c) => {
      const o = un(c)!;
      if (o.meta.relecture) {
        const { relecture: _, ...meta } = o.meta;
        await c.b.modifier([{ id: o.id, champs: { meta } }], "Demande de relecture retirée");
        return;
      }
      await c.b.modifier([{ id: o.id, champs: { meta: { ...o.meta, relecture: { demandee: Math.round(Date.now() / 1000), par: "humain" } } } }], "Demande de relecture");
      await c.b.commenter(o.id, "Relecture demandée.");
      c.b.toast("Relecture demandée : la carte le signale. Aucun agent n'est lancé par cette demande.");
    } },
  { id: "carte.compacte", libelle: (c) => (un(c)?.meta.compact ? "Taille normale" : "Vignette compacte"), icone: Minimize2, categorie: "Carte", niveau: "ecriture",
    emplacements: ["menu"], disponible: (c) => !enLecture(c) && cartes(c).length === 1 && c.selection.length === 1,
    executer: (c) => {
      const o = un(c)!;
      const [largeur, hauteur] = TAILLES[o.type]?.defaut ?? [408, 320];
      return c.b.modifier([{ id: o.id, champs: o.meta.compact ? { meta: { ...o.meta, compact: false }, largeur, hauteur }
        : { meta: { ...o.meta, compact: true }, largeur: 240, hauteur: 96 } }], "Format de la carte");
    } },
  { id: "carte.sortirDuDossier", libelle: "Sortir du dossier", categorie: "Carte", niveau: "ecriture",
    disponible: (c) => !enLecture(c) && Boolean(un(c)?.parent_id),
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
    disponible: (c) => Boolean(c.lien) && !enLecture(c), executer: (c) => c.b.supprimerLien(c.lien!.id) },
  { id: "export.png", libelle: (c) => (deType(c, "cadre") ? "Exporter ce cadre en PNG" : "Exporter la sélection en PNG"), icone: ImageDown,
    raccourci: "mod+shift+e", categorie: "Export", niveau: "lecture", emplacements: ["flottante", "menu"], motsCles: "image capture télécharger",
    disponible: (c) => c.selection.length > 0,
    executer: (c) => {
      const cadre = deType(c, "cadre");
      return c.b.exporterPng(c.selection.map((o) => o.id), cadre ? titreDe(cadre) : "selection");
    } },
];
