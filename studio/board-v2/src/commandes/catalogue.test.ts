// Le catalogue réel du Board, exécuté contre un double des services : chaque commande est cohérente (libellé,
// catégorie, raccourcis sans collision involontaire) et fait ce qu'elle annonce — sans réseau ni React.
import { beforeEach, describe, expect, it } from "vitest";
import type { Modification, NouvelObjet } from "../api";
import { cartesProches, estLivrable, etatsCarte, provenance } from "../cartes/etat";
import { carte, lien } from "../donnees/essais";
import { StoreUi } from "../etat/ui";
import type { LienBoard, ObjetBoard } from "../types";
import type { ContexteBoard, ServicesBoard } from "./contexte";
import { creerRegistreBoard, type RegistreBoard } from "./index";
import { JournalUsage } from "./journal";
import { libelleDe, raccourcisDe } from "./types";

interface Double {
  b: ServicesBoard;
  objets: ObjetBoard[];
  liens: LienBoard[];
  journal: string[];
  selection: string[];
  toasts: string[];
}

function double(objets: ObjetBoard[], liens: LienBoard[] = []): Double {
  const d: Double = { objets, liens, journal: [], selection: [], toasts: [], b: null as unknown as ServicesBoard };
  const ui = new StoreUi({ theme: "nuit", minicarte: true, grille: false, guides: true, couleur: "indigo", epaisseur: 6 });
  let n = 0;
  d.b = {
    demo: false, ui,
    objet: (id) => d.objets.find((o) => o.id === id), objets: () => d.objets, liens: () => d.liens,
    visibles: () => d.objets.filter((o) => !o.parent_id).map((o) => o.id),
    modifier: async (mods: Modification[], libelle) => {
      d.journal.push(`modifier:${libelle}`);
      d.objets = d.objets.map((o) => {
        const m = mods.find((x) => x.id === o.id);
        if (!m) return o;
        const { verrouille, ...reste } = m.champs;
        return { ...o, ...reste, ...(verrouille === undefined ? {} : { verrouille: verrouille ? 1 : 0 }) } as ObjetBoard;
      });
    },
    creer: async (o: NouvelObjet, libelle = "Ajout") => {
      const id = `N${++n}`;
      d.journal.push(`creer:${o.type}:${libelle}`);
      d.objets = [...d.objets, carte(id, { ...o, meta: o.meta ?? {}, contenu: o.contenu ?? "" } as Partial<ObjetBoard>)];
      return id;
    },
    supprimer: async (ids) => { d.journal.push(`supprimer:${ids.join(",")}`); d.objets = d.objets.filter((o) => !ids.includes(o.id)); },
    dupliquer: async (ids) => { d.journal.push(`dupliquer:${ids.join(",")}`); return ids.map((id) => `${id}'`); },
    lier: async (s, c, style = "defaut") => { d.journal.push(`lier:${s}>${c}:${style}`); return "L1"; },
    modifierLien: async (id, champs) => { d.journal.push(`lien:${id}:${JSON.stringify(champs)}`); },
    supprimerLien: async (id) => { d.journal.push(`supprimerLien:${id}`); },
    commenter: async (id, texte) => { d.journal.push(`commenter:${id}:${texte}`); },
    grouper: (libelle, f) => { d.journal.push(`groupe:${libelle}`); return f(); },
    annuler: async () => { d.journal.push("annuler"); }, retablir: async () => { d.journal.push("retablir"); },
    copier: (ids) => { d.journal.push(`copier:${ids.join(",")}`); }, coller: async () => { d.journal.push("coller"); }, peutColler: () => true,
    selectionner: (ids) => { d.selection = ids; }, inspecter: (id) => { d.journal.push(`inspecter:${id}`); },
    ajuster: () => { d.journal.push("ajuster"); }, zoomer: (f) => { d.journal.push(`zoomer:${f}`); }, zoomA: (z) => { d.journal.push(`zoomA:${z}`); },
    cadrer: (z) => { d.journal.push(`cadrer:${z.x},${z.y}`); }, montrer: (z) => { d.journal.push(`montrer:${z.x},${z.y}`); }, centreVue: () => ({ x: 0, y: 0 }),
    toast: (t) => { d.toasts.push(t); }, ouvrirMission: () => { d.journal.push("mission"); }, saisirLien: () => { d.journal.push("lien"); },
    choisirFichiers: (a) => { d.journal.push(`fichiers:${a}`); }, collerPressePapiers: async () => { d.journal.push("pressePapiers"); },
    contextualiser: (id) => { d.journal.push(`analyser:${id}`); }, exporterPng: async (ids, nom) => { d.journal.push(`png:${ids.join(",")}:${nom}`); },
    pleinEcran: async (actif) => { ui.definir({ pleinEcran: actif }); },
  };
  return d;
}

const ctx = (d: Double, selection: string[] = [], extra: Partial<ContexteBoard> = {}): ContexteBoard =>
  ({ selection: selection.map((id) => d.b.objet(id)!), ui: d.b.ui.lire(), b: d.b, ...extra });

let registre: RegistreBoard;
beforeEach(() => {
  registre = creerRegistreBoard({ journal: new JournalUsage(null), confirmer: () => true });
});

describe("catalogue des commandes du Board", () => {
  it("chaque commande a un identifiant « domaine.action », un libellé français et une catégorie", () => {
    const d = double([carte("A")]);
    const toutes = registre.toutes();
    expect(toutes.length).toBe(109);
    for (const c of toutes) {
      expect(c.id).toMatch(/^[a-z]+(\.[a-zA-Z0-9]+)+$/);
      expect(libelleDe(c, ctx(d, ["A"])).length).toBeGreaterThan(3);
      expect(["Outils", "Édition", "Disposition", "Carte", "Affichage", "Navigation", "Ajouter", "Export"]).toContain(c.categorie);
      expect(["lecture", "ecriture", "sensible"]).toContain(c.niveau);
    }
  });

  it("les seuls raccourcis partagés le sont par des commandes qui s'excluent", () => {
    const partages = Object.fromEntries(registre.raccourcisPartages());
    expect(Object.keys(partages).sort()).toEqual(["echap", "entree"]);
    expect(partages.echap).toEqual(["presentation.quitter", "affichage.concentration.quitter", "affichage.zen.quitter", "outil.revenir", "edition.deselectionner"]);
    expect(partages.entree).toEqual(["presentation.suivante", "carte.ouvrir"]);
  });

  it("une touche par outil, et Échap revient à la sélection", async () => {
    const d = double([]);
    for (const [touche, outil] of Object.entries({ v: "selection", h: "main", n: "adhesif", t: "texte", r: "rectangle", o: "ellipse", d: "losange", a: "fleche", p: "crayon", s: "surligneur", e: "gomme", f: "cadre", l: "lasso" })) {
      const cmd = registre.pourTouche({ key: touche }, ctx(d));
      expect(cmd?.id).toBe(`outil.${outil}`);
      await registre.executer(cmd!.id, ctx(d), "raccourci");
      expect(d.b.ui.lire().outil).toBe(outil);
    }
    expect(registre.pourTouche({ key: "Escape" }, ctx(d))?.id).toBe("outil.revenir");
    await registre.executer("outil.revenir", ctx(d));
    expect(d.b.ui.lire().outil).toBe("selection");
    expect(registre.pourTouche({ key: "Escape" }, ctx(d))).toBeUndefined();
  });

  it("édition : supprimer, dupliquer, verrouiller, aligner, répartir, encadrer, grouper", async () => {
    const d = double([carte("A", { x: 0, y: 0, largeur: 100, hauteur: 100 }), carte("B", { x: 300, y: 50, largeur: 100, hauteur: 100 }),
      carte("C", { x: 900, y: 10, largeur: 100, hauteur: 100 }), carte("M", { type: "mission" })]);
    expect(registre.disponible("edition.supprimer", ctx(d))).toBe(false);
    await registre.executer("disposition.aligner.haut", ctx(d, ["A", "B", "C"]), "flottante");
    expect(d.objets.slice(0, 3).map((o) => o.y)).toEqual([0, 0, 0]);
    await registre.executer("disposition.repartir.horizontal", ctx(d, ["A", "B", "C"]), "flottante");
    expect(d.b.objet("B")!.x).toBe(450);
    expect(registre.disponible("disposition.repartir.horizontal", ctx(d, ["A", "B"]))).toBe(false);
    await registre.executer("edition.verrouiller", ctx(d, ["A"]));
    expect(d.b.objet("A")!.verrouille).toBe(1);
    expect(libelleDe(registre.obtenir("edition.verrouiller")!, ctx(d, ["A"]))).toBe("Déverrouiller");
    // une carte de mission ne se recopie pas : la duplication l'ignore
    await registre.executer("edition.dupliquer", ctx(d, ["B", "M"]));
    expect(d.journal).toContain("dupliquer:B");
    expect(registre.disponible("edition.dupliquer", ctx(d, ["M"]))).toBe(false);
    await registre.executer("edition.encadrer", ctx(d, ["B", "C"]));
    const cadre = d.objets.find((o) => o.type === "cadre")!;
    expect([cadre.x, cadre.y, cadre.largeur, cadre.hauteur]).toEqual([402, -72, 646, 220]);
    await registre.executer("edition.grouper", ctx(d, ["B", "C"]));
    expect(d.b.objet("B")!.parent_id).toBe(d.objets.find((o) => o.type === "dossier")!.id);
    expect(d.journal.filter((j) => j.startsWith("groupe:"))).toEqual(["groupe:Groupe"]);
    await registre.executer("edition.supprimer", ctx(d, ["C"]), "raccourci");
    expect(d.b.objet("C")).toBeUndefined();
  });

  it("tout sélectionner ne prend que ce qui est affiché", async () => {
    const d = double([carte("A"), carte("B"), carte("range", { parent_id: "D" })]);
    await registre.executer(registre.pourTouche({ key: "a", ctrlKey: true }, ctx(d))!.id, ctx(d), "raccourci");
    expect(d.selection).toEqual(["A", "B"]);
  });

  it("supprimer dix objets ou plus demande confirmation", async () => {
    const d = double(Array.from({ length: 12 }, (_, i) => carte(`O${i}`)));
    const refus = creerRegistreBoard({ journal: new JournalUsage(null), confirmer: () => false });
    expect(await refus.executer("edition.supprimer", ctx(d, d.objets.map((o) => o.id)))).toBe("refuse");
    expect(d.objets).toHaveLength(12);
    expect(await refus.executer("edition.supprimer", ctx(d, ["O1", "O2"]))).toBe("fait");
  });

  it("cartes intelligentes : les actions proposées dépendent du type et des données", () => {
    const d = double([carte("lien", { type: "lien", meta: { url: "https://exemple.test", titre: "Article" } }),
      carte("tache", { type: "tache", meta: { issue: "ENG-1" } }), carte("livrable", { artefacts: [{ id: "a", fournisseur: "claude", factice: 0, revue: "", contenu: "x" }] }),
      carte("rond", { type: "forme", meta: { forme: "ellipse" } }), carte("cadre", { type: "cadre" }), carte("trait", { type: "trait" })]);
    const flottantes = (id: string) => registre.disponibles(ctx(d, [id]), "flottante").map((c) => c.id);
    expect(flottantes("lien")).toEqual(expect.arrayContaining(["carte.ouvrir", "carte.relier", "carte.analyser", "carte.tacheInspiree", "carte.proches"]));
    expect(flottantes("lien")).not.toContain("carte.relecture");
    expect(flottantes("tache")).toEqual(expect.arrayContaining(["carte.ouvrir", "carte.relier"]));
    expect(flottantes("tache")).not.toContain("carte.tacheInspiree");
    expect(flottantes("livrable")).toContain("carte.relecture");
    expect(flottantes("rond")).toEqual(expect.arrayContaining(["carte.relier", "edition.dupliquer", "export.png"]));
    expect(flottantes("rond")).not.toContain("carte.ouvrir");
    expect(flottantes("cadre")).toEqual(expect.arrayContaining(["affichage.concentration", "presentation.demarrer", "export.png"]));
    expect(flottantes("trait")).not.toContain("carte.relier");
    // la priorité au clavier ne s'applique qu'aux cartes
    expect(registre.pourTouche({ key: "1", code: "Digit1" }, ctx(d, ["tache"]))?.id).toBe("carte.priorite.P1");
    expect(registre.pourTouche({ key: "1", code: "Digit1" }, ctx(d, ["rond"]))).toBeUndefined();
  });

  it("« créer une tâche inspirée » pose une note reliée par « Inspire », sans lancer d'agent", async () => {
    const d = double([carte("lien", { type: "lien", x: 100, y: 50, largeur: 400, priorite: "P1", meta: { url: "https://exemple.test/a", titre: "Article de fond" } })]);
    await registre.executer("carte.tacheInspiree", ctx(d, ["lien"]), "flottante");
    const note = d.objets.find((o) => o.id === "N1")!;
    expect(note).toMatchObject({ type: "note", x: 580, priorite: "P1", meta: { titre: "Tâche : Article de fond", tags: ["tâche"] } });
    expect(note.contenu).toContain("https://exemple.test/a");
    expect(d.journal).toEqual(["groupe:Tâche inspirée", "creer:note:Tâche inspirée", "lier:lien>N1:inspire"]);
    expect(d.journal.some((j) => j.startsWith("analyser") || j === "mission")).toBe(false);
    expect(d.toasts[0]).toMatch(/Rien n'est confié à un agent/);
  });

  it("« faire relire » pose la demande sur la carte et la commente ; relancée, elle la retire", async () => {
    const d = double([carte("L", { artefacts: [{ id: "a", fournisseur: "claude", factice: 0, revue: "", contenu: "x" }] })]);
    await registre.executer("carte.relecture", ctx(d, ["L"]));
    expect(d.b.objet("L")!.meta.relecture).toMatchObject({ par: "humain" });
    expect(d.journal).toEqual(["modifier:Demande de relecture", "commenter:L:Relecture demandée."]);
    expect(etatsCarte(d.b.objet("L")!).map((e) => e.texte)).toEqual(["Relecture demandée"]);
    expect(libelleDe(registre.obtenir("carte.relecture")!, ctx(d, ["L"]))).toBe("Retirer la demande de relecture");
    await registre.executer("carte.relecture", ctx(d, ["L"]));
    expect(d.b.objet("L")!.meta.relecture).toBeUndefined();
  });

  it("« trouver des cartes proches » sélectionne par vocabulaire commun, et le dit", async () => {
    const d = double([carte("A", { contenu: "Refonte du tunnel de paiement mobile", meta: { tags: ["paiement"] } }),
      carte("B", { contenu: "Bug paiement mobile sur Safari" }), carte("C", { contenu: "Recette de tarte aux pommes" })]);
    await registre.executer("carte.proches", ctx(d, ["A"]));
    expect(d.selection).toEqual(["A", "B"]);
    expect(d.toasts[0]).toMatch(/1 carte proche par le vocabulaire/);
    await registre.executer("carte.proches", ctx(d, ["C"]));
    expect(d.toasts[1]).toBe("Aucune carte ne partage de mots avec celle-ci");
  });

  it("relations : le type se choisit, il n'a pas d'effet métier ici", async () => {
    const d = double([carte("A"), carte("B")], [lien("L", "A", "B")]);
    const c = ctx(d, [], { lien: d.liens[0] });
    expect(registre.disponibles(c, "menu").map((x) => x.id)).toEqual(["relation.type.defaut", "relation.type.inspire", "relation.type.alimente", "relation.type.utilise", "relation.type.depend", "relation.supprimer"]);
    await registre.executer("relation.type.depend", c, "menu");
    expect(d.journal).toEqual([`lien:L:{"style":"depend"}`]);
    expect(registre.disponible("relation.type.depend", ctx(d, ["A"]))).toBe(false);
  });

  it("affichage : thème, zen, concentration, présentation au clavier", async () => {
    const d = double([carte("c2", { type: "cadre", x: 2000, y: 0, largeur: 800, hauteur: 600, meta: { titre: "Deux" } }),
      carte("c1", { type: "cadre", x: 0, y: 0, largeur: 800, hauteur: 600, meta: { titre: "Un" } }), carte("A")]);
    await registre.executer("affichage.theme.jour", ctx(d), "palette");
    expect(d.b.ui.lire().theme).toBe("jour");
    await registre.executer("affichage.zen", ctx(d));
    expect(registre.pourTouche({ key: "Escape" }, ctx(d))?.id).toBe("affichage.zen.quitter");
    await registre.executer("affichage.zen.quitter", ctx(d));
    await registre.executer("affichage.concentration", ctx(d, ["c1"]));
    expect(d.b.ui.lire().focus).toBe("c1");
    expect(registre.pourTouche({ key: "Escape" }, ctx(d, ["c1"]))?.id).toBe("affichage.concentration.quitter");
    await registre.executer("affichage.concentration.quitter", ctx(d));
    // présentation : les cadres dans l'ordre de lecture, flèches du clavier, écritures suspendues
    expect(registre.pourTouche({ key: "ArrowRight" }, ctx(d))).toBeUndefined();
    await registre.executer("presentation.demarrer", ctx(d));
    expect(d.b.ui.lire()).toMatchObject({ presentation: 0, focus: "c1", pleinEcran: true });
    expect(registre.pourTouche({ key: "ArrowRight" }, ctx(d))?.id).toBe("presentation.suivante");
    await registre.executer("presentation.suivante", ctx(d), "raccourci");
    await registre.executer("presentation.suivante", ctx(d), "raccourci");  // déjà au dernier : reste dessus
    expect(d.b.ui.lire()).toMatchObject({ presentation: 1, focus: "c2" });
    expect(registre.pourTouche({ key: "Delete" }, ctx(d, ["A"]))).toBeUndefined();
    expect(registre.pourTouche({ key: "p" }, ctx(d))).toBeUndefined();
    await registre.executer(registre.pourTouche({ key: "Escape" }, ctx(d))!.id, ctx(d));
    expect(d.b.ui.lire()).toMatchObject({ presentation: null, focus: null, pleinEcran: false });
    expect(d.journal.filter((j) => j.startsWith("cadrer"))).toEqual(["cadrer:0,0", "cadrer:0,0", "cadrer:2000,0", "cadrer:2000,0"]);
  });

  it("navigation au clavier : Alt+flèche va à l'objet voisin dans cette direction", async () => {
    const d = double([carte("centre", { x: 0, y: 0, largeur: 100, hauteur: 100 }), carte("droite", { x: 400, y: 20, largeur: 100, hauteur: 100 }),
      carte("loin", { x: 900, y: 0, largeur: 100, hauteur: 100 }), carte("bas", { x: 30, y: 500, largeur: 100, hauteur: 100 }), carte("range", { x: 200, y: 0, parent_id: "D" })]);
    const aller = async (touche: string, depuis: string[]) => {
      const cmd = registre.pourTouche({ key: touche, altKey: true }, ctx(d, depuis));
      await registre.executer(cmd!.id, ctx(d, depuis), "raccourci");
      return d.selection[0];
    };
    expect(await aller("ArrowRight", ["centre"])).toBe("droite");  // le plus proche dans l'axe, pas « loin » ni l'objet rangé
    expect(await aller("ArrowRight", ["droite"])).toBe("loin");
    expect(await aller("ArrowDown", ["centre"])).toBe("bas");
    expect(await aller("ArrowLeft", ["loin"])).toBe("droite");
    d.selection = [];
    expect(await aller("ArrowUp", ["centre"])).toBeUndefined();     // rien au-dessus : la sélection ne change pas
    expect(d.journal.filter((j) => j.startsWith("montrer"))).toHaveLength(4);
  });

  it("couleur et épaisseur : style des prochains tracés, ou recoloration de la sélection", async () => {
    const d = double([carte("F", { type: "forme", meta: { forme: "ellipse", couleur: "indigo" } })]);
    await registre.executer("style.couleur.rose", ctx(d));
    expect(d.b.ui.lire().couleur).toBe("rose");
    expect(d.journal).toEqual([]);
    await registre.executer("style.couleur.vert", ctx(d, ["F"]));
    expect(d.b.objet("F")!.meta).toEqual({ forme: "ellipse", couleur: "vert" });
    await registre.executer("style.epaisseur.12", ctx(d, ["F"]));
    expect(d.b.objet("F")!.meta.epaisseur).toBe(12);
  });

  it("les commandes sont toutes annoncées avec leur raccourci réel (pas de raccourci fantôme)", () => {
    const d = double([carte("A")]);
    for (const c of registre.toutes()) {
      for (const r of raccourcisDe(c)) expect(r, c.id).toMatch(/^(mod\+)?(alt\+)?(shift\+)?([a-z0-9]|[\]\[.=+\-/]|f10|contextmenu|echap|entree|espace|suppr|retour|gauche|droite|haut|bas)$/);
    }
    expect(registre.pourTouche({ key: "k", ctrlKey: true }, ctx(d))?.id).toBe("palette.ouvrir");
    expect(registre.pourTouche({ key: "z", metaKey: true, shiftKey: true }, ctx(d))?.id).toBe("edition.retablir");
  });
});

describe("état et provenance d'une carte : données réelles seulement", () => {
  const mission = (p: Partial<NonNullable<ObjetBoard["mission"]>> = {}): NonNullable<ObjetBoard["mission"]> =>
    ({ id: "M", objectif: "x", statut: "RUNNING", cree: 1000, taches: [], faites: 0, total: 0, progression: 0, agents: [], approbations_en_attente: 0, ...p });
  const tache = (statut: string, raison = "") => ({ id: "T", type: "analyse", niveau: "L1", statut, fournisseur_choisi: null, fournisseur: "", essais: 1, raison });

  it("une carte sans rien de particulier n'affiche rien", () => {
    expect(etatsCarte(carte("A"))).toEqual([]);
    expect(provenance(carte("A"))).toBeNull();
    expect(provenance(carte("A", { auteur: "studio" }))).toBeNull();
  });

  it("en attente de toi, bloquée, périmée", () => {
    expect(etatsCarte(carte("A", { mission: mission({ approbations_en_attente: 2 }) }))[0]).toMatchObject({ sorte: "attente", texte: "Attend ta décision" });
    expect(etatsCarte(carte("A", { type: "plan", meta: { statut: "en_attente" } }))[0]).toMatchObject({ sorte: "attente", texte: "Plan à valider" });
    expect(etatsCarte(carte("A", { meta: { propositions: [{ titre: "t", pourquoi: "p", niveau: "L1", statut: "proposee" }] } }))[0]!.sorte).toBe("attente");
    expect(etatsCarte(carte("A", { meta: { propositions: [{ titre: "t", pourquoi: "p", niveau: "L1", statut: "lancee" }] } }))).toEqual([]);
    expect(etatsCarte(carte("A", { mission: mission({ taches: [tache("FAILED", "quota dépassé")] }) }))[0]).toMatchObject({ sorte: "bloquee", raison: "Tâche en échec : quota dépassé" });
    expect(etatsCarte(carte("A", { mission: mission({ taches: [tache("WAITING_PROVIDER")] }) }))[0]).toMatchObject({ sorte: "bloquee", texte: "Sans exécutant" });
    expect(etatsCarte(carte("A", { type: "tache", meta: { statut: "bloqué" } }))[0]!.sorte).toBe("bloquee");
    expect(etatsCarte(carte("A", { type: "tache", meta: { statut: "terminé" } }))).toEqual([]);
    // périmée : texte modifié après le lancement de l'analyse affichée
    const analysee = { mission: mission({ cree: 1000 }), meta: { jarvis_resume: "résumé", historique: [{ ts: 2000, extrait: "avant" }] } };
    expect(etatsCarte(carte("A", analysee))[0]).toMatchObject({ sorte: "perimee" });
    expect(etatsCarte(carte("A", { ...analysee, meta: { ...analysee.meta, historique: [{ ts: 500, extrait: "avant" }] } }))).toEqual([]);
    expect(etatsCarte(carte("A", { meta: { historique: [{ ts: 2000, extrait: "avant" }] } }))).toEqual([]);  // jamais analysée : rien à périmer
  });

  it("provenance : auteur humain ou agent, modèle connu, version, sources", () => {
    expect(provenance(carte("A", { auteur: "chef", version: 3, maj: 5000 }), 2)).toEqual(
      { auteur: "Jarvis (chef)", agent: true, modele: undefined, date: 5000, modifiee: true, version: 3, sources: 2 });
    expect(provenance(carte("A", { meta: { source: "telegram" } }))).toMatchObject({ auteur: "Telegram", agent: false });
    expect(provenance(carte("A", { artefacts: [{ id: "a", fournisseur: "claude", factice: 0, revue: "", contenu: "" }] }))?.modele).toBe("claude");
    expect(provenance(carte("A", { type: "tache", meta: { modele: "fable-5" } }))?.modele).toBe("fable-5");
    expect(provenance(carte("A"), 1)).toMatchObject({ sources: 1, auteur: undefined });
    expect(estLivrable(carte("A", { meta: { livrable_de: "BO-1" } }))).toBe(true);
    expect(estLivrable(carte("A"))).toBe(false);
  });

  it("cartes proches : jamais la carte elle-même, ni les dessins, ni ce qui est rangé", () => {
    const src = carte("S", { contenu: "architecture du moteur de recherche" });
    const proches = cartesProches(src, [src, carte("ok", { contenu: "moteur de recherche plein texte" }),
      carte("range", { contenu: "moteur de recherche", parent_id: "D" }), carte("forme", { type: "forme", contenu: "moteur recherche" })]);
    expect(proches.map((p) => p.objet.id)).toEqual(["ok"]);
    expect(proches[0]!.communs.sort()).toEqual(["moteur", "recherche"]);
  });
});
