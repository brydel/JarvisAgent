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
  historique: { annuler: string | null; refaire: string | null };
}

function double(objets: ObjetBoard[], liens: LienBoard[] = []): Double {
  const d: Double = { objets, liens, journal: [], selection: [], toasts: [], historique: { annuler: "Geste", refaire: "Geste" }, b: null as unknown as ServicesBoard };
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
    historique: () => d.historique,
    relire: async (id, action, options) => { d.journal.push(`relire:${id}:${action}${options?.verdict ? `:${options.verdict}` : ""}`); return null; },
    allerA: (id) => { d.journal.push(`allerA:${id}`); },
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

describe("une commande indisponible dit pourquoi (raison du registre)", () => {
  const CONTEXTES = (d: Double): [string, ContexteBoard][] => [
    ["rien de sélectionné", ctx(d)], ["une note", ctx(d, ["A"])], ["deux cartes", ctx(d, ["A", "B"])], ["une mission", ctx(d, ["M"])],
    ["un trait", ctx(d, ["T"])], ["une relation", ctx(d, [], { lien: d.liens[0] })],
    ["en présentation", { ...ctx(d, ["A"]), ui: { ...d.b.ui.lire(), presentation: 0 } }],
  ];
  const jeu = () => {
    const d = double([carte("A"), carte("B", { x: 500 }), carte("M", { type: "mission" }), carte("T", { type: "trait" }), carte("C", { type: "cadre" })],
      [lien("L1", "A", "B")]);
    d.historique = { annuler: null, refaire: null };
    d.b.peutColler = () => false;
    return d;
  };

  it("toute commande proposée grisée (menu, barre flottante, palette) porte une phrase", () => {
    const d = jeu();
    let grisees = 0;
    for (const [nom, c] of CONTEXTES(d)) {
      for (const lieu of ["menu", "flottante", "palette"] as const) {
        for (const { cmd, etat } of registre.proposees(c, lieu)) {
          if (etat.disponible) continue;
          grisees += 1;
          expect(etat.raison, `${cmd.id} (${lieu}, ${nom})`).toMatch(/^[A-ZÀ-Ü].{12,}/);
        }
      }
    }
    expect(grisees).toBeGreaterThan(100);
  });

  it("les boutons fixes de l'interface ont toujours une raison quand ils sont grisés", () => {
    const d = jeu();
    const boutons = ["edition.annuler", "edition.retablir", "vue.zoomArriere", "vue.zoomAvant", "vue.ajuster", "affichage.grille",
      "affichage.theme.basculer", "presentation.demarrer", "palette.ouvrir"];
    for (const id of boutons) {
      for (const [nom, c] of CONTEXTES(d)) {
        const e = registre.etat(id, c);
        if (!e.disponible) expect(e.raison, `${id} (${nom})`).toBeTruthy();
      }
    }
    const sansCadre = double([carte("A")]);
    expect(registre.etat("presentation.demarrer", ctx(sansCadre)).raison).toMatch(/Aucun cadre sur ce Board/);
    expect(registre.etat("edition.annuler", ctx(d)).raison).toMatch(/^Rien à annuler/);
    expect(registre.etat("edition.retablir", ctx(d)).raison).toMatch(/^Rien à rétablir/);
  });

  it("la raison dépend du contexte : sélection, verrou, presse-papiers, présentation", () => {
    const d = jeu();
    const raison = (id: string, c: ContexteBoard) => registre.etat(id, c).raison;
    expect(raison("disposition.aligner.gauche", ctx(d, ["A"]))).toBe("Sélectionne au moins deux objets à aligner");
    expect(raison("disposition.repartir.horizontal", ctx(d, ["A", "B"]))).toBe("Sélectionne au moins trois objets à répartir");
    d.objets = d.objets.map((o) => (o.id === "B" ? { ...o, verrouille: 1 } : o));
    expect(raison("disposition.aligner.gauche", ctx(d, ["A", "B"]))).toMatch(/Trop d'objets verrouillés pour aligner/);
    expect(raison("edition.coller", ctx(d))).toMatch(/Presse-papiers du Board vide/);
    expect(raison("edition.dupliquer", ctx(d, ["M"]))).toMatch(/travail réel : elle ne se duplique pas/);
    expect(raison("carte.relier", ctx(d, ["T"]))).toMatch(/ne se relie pas/);
    expect(raison("edition.supprimer", ctx(d))).toBe("Sélectionne d'abord un objet du Board");
    const presentation = { ...ctx(d, ["A"]), ui: { ...d.b.ui.lire(), presentation: 0 } };
    expect(raison("edition.supprimer", presentation)).toMatch(/pendant la présentation/);
    expect(raison("outil.crayon", presentation)).toMatch(/pendant la présentation/);
    // hors sujet (aucune raison à donner) : la commande reste simplement absente des menus
    expect(registre.etat("edition.deselectionner", ctx(d))).toEqual({ disponible: false, raison: null, concerne: false });
  });

  it("menu et barre flottante : grisée seulement si la commande concerne la cible ; palette : dès qu'elle sait dire pourquoi", () => {
    const d = jeu();
    const grisees = (c: ContexteBoard, lieu: "menu" | "flottante" | "palette") => registre.proposees(c, lieu).filter((p) => !p.etat.disponible).map((p) => p.cmd.id);
    expect(grisees(ctx(d, ["A"]), "flottante")).toEqual([]);             // une note : rien de grisé, rien de bruyant
    expect(grisees(ctx(d, ["A", "B"]), "flottante")).toEqual(["disposition.repartir.horizontal", "disposition.repartir.vertical"]);
    expect(grisees(ctx(d, ["M"]), "menu")).toEqual(expect.arrayContaining(["edition.couper", "edition.dupliquer", "carte.relecture"]));
    expect(grisees(ctx(d), "menu")).toEqual(["edition.coller"]);
    expect(grisees(ctx(d), "palette")).toEqual(expect.arrayContaining(["edition.supprimer", "disposition.aligner.gauche", "carte.analyser", "relation.type.depend"]));
  });

  it("exécuter une commande indisponible ne fait rien et rend sa raison (raccourci, clic sur un bouton grisé)", async () => {
    const refus: string[] = [];
    const r = creerRegistreBoard({ journal: new JournalUsage(null), surRefus: (raison, cmd) => refus.push(`${cmd.id}: ${raison}`) });
    const d = jeu();
    expect(await r.executer("edition.annuler", ctx(d), "raccourci")).toBe("indisponible");
    expect(refus).toEqual(["edition.annuler: Rien à annuler : aucun geste n'a encore été fait sur ce Board"]);
    expect(d.journal).toEqual([]);
    expect(r.journal.usage("edition.annuler")).toBeUndefined();
    // au clavier : Ctrl+Z sans rien à annuler est un refus expliqué ; Échap ou Entrée sans objet restent silencieux
    expect(r.pourTouche({ key: "z", ctrlKey: true }, ctx(d))).toBeUndefined();
    expect(r.refusPourTouche({ key: "z", ctrlKey: true }, ctx(d))).toMatchObject({ raison: expect.stringMatching(/^Rien à annuler/) });
    expect(r.refusPourTouche({ key: "Escape" }, ctx(d))).toBeUndefined();
    expect(r.refusPourTouche({ key: "Enter" }, ctx(d))).toBeUndefined();
    expect(r.refusPourTouche({ key: "Delete" }, ctx(d))?.raison).toBe("Sélectionne d'abord un objet du Board");
    d.historique = { annuler: "Déplacement", refaire: null };
    expect(r.refusPourTouche({ key: "z", ctrlKey: true }, ctx(d))).toBeUndefined();
    expect(r.pourTouche({ key: "z", ctrlKey: true }, ctx(d))?.id).toBe("edition.annuler");
  });
});

describe("relations à effet : ce que les commandes en disent", () => {
  const bloquee = { bloquee: true, bloquee_par: [{ id: "M", titre: "Valider le budget", type: "mission" as const, lien_id: "L1", etat: "en cours" }],
    dependances: [{ id: "M", titre: "Valider le budget", type: "mission" as const, lien_id: "L1", suivi: true, termine: false, etat: "en cours" }],
    debloque: [], alimentee_par: [], alimente: [], inspiree_par: [] };

  it("« Analyser avec Jarvis » est grisée sur une carte bloquée, avec ce qui la bloque", async () => {
    const d = double([carte("N", { relations: bloquee }), carte("M", { type: "mission" })], [lien("L1", "N", "M", { style: "depend" })]);
    const e = registre.proposees(ctx(d, ["N"]), "flottante").find((p) => p.cmd.id === "carte.analyser")!.etat;
    expect(e).toMatchObject({ disponible: false, concerne: true });
    expect(e.raison).toBe("Bloquée par « Valider le budget » (en cours) : termine d'abord ce dont elle dépend, ou retire la relation « Dépend de »");
    expect(await registre.executer("carte.analyser", ctx(d, ["N"]))).toBe("indisponible");
    expect(d.journal).toEqual([]);
    expect(etatsCarte(d.b.objet("N")!).map((x) => [x.sorte, x.texte])).toEqual([["bloquee", "Bloquée"]]);
    expect(etatsCarte(d.b.objet("N")!)[0]!.raison).toContain("« Valider le budget » (en cours)");
    // débloquée (le serveur ne la dit plus bloquée) : la commande revient
    d.objets = [carte("N", { relations: { ...bloquee, bloquee: false, bloquee_par: [] } }), carte("M", { type: "mission" })];
    expect(registre.disponible("carte.analyser", ctx(d, ["N"]))).toBe(true);
    expect(etatsCarte(d.b.objet("N")!)).toEqual([]);
  });

  it("choisir un type de relation dit ce que ça change, avec les deux cartes nommées", async () => {
    const d = double([carte("A", { meta: { titre: "Synthèse" } }), carte("B", { meta: { titre: "Collecte" } })], [lien("L1", "A", "B")]);
    const c = ctx(d, [], { lien: d.liens[0] });
    await registre.executer("relation.type.depend", c, "menu");
    expect(d.journal).toEqual(['lien:L1:{"style":"depend"}']);
    expect(d.toasts[0]).toBe("Dépend de — « Synthèse » sera bloquée tant que « Collecte » n'est pas terminée : son lancement sera refusé.");
    await registre.executer("relation.type.alimente", c, "menu");
    expect(d.toasts[1]).toBe("Alimente — Le livrable (ou le contenu) de « Synthèse » sera joint, comme donnée, au travail de « Collecte ».");
    await registre.executer("relation.type.defaut", c, "menu");
    expect(d.toasts[2]).toMatch(/Simple repère/);
  });

  it("« Dépend de » est grisée si elle fermerait une boucle, avec le trajet", () => {
    const d = double([carte("A", { meta: { titre: "Alpha" } }), carte("B", { meta: { titre: "Bravo" } }), carte("C", { meta: { titre: "Charlie" } })],
      [lien("L1", "A", "B", { style: "depend" }), lien("L2", "B", "C", { style: "depend" }), lien("L3", "C", "A", { style: "inspire" })]);
    const e = registre.etat("relation.type.depend", ctx(d, [], { lien: d.liens[2] }));
    expect(e.disponible).toBe(false);
    expect(e.raison).toBe("Fermerait une boucle (« Charlie » → « Alpha » → « Bravo » → « Charlie ») : plus aucune de ces cartes ne pourrait démarrer");
    expect(registre.etat("relation.type.alimente", ctx(d, [], { lien: d.liens[2] })).disponible).toBe(true);
    expect(registre.etat("relation.type.depend", ctx(d, [], { lien: d.liens[0] })).disponible).toBe(true);  // déjà une dépendance
    expect(registre.etat("relation.type.depend", ctx(d)).raison).toMatch(/clic droit sur une flèche/);
  });
});

describe("catalogue des commandes du Board", () => {
  it("chaque commande a un identifiant « domaine.action », un libellé français et une catégorie", () => {
    const d = double([carte("A")]);
    const toutes = registre.toutes();
    expect(toutes.length).toBe(111);  // + les deux verdicts de relecture
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

  it("« faire relire » passe par la file du serveur ; demande ouverte : la retirer ou rendre un verdict", async () => {
    const artefacts = [{ id: "a", fournisseur: "claude", factice: 0, revue: "acceptee", contenu: "x" }];
    const d = double([carte("L", { artefacts })]);
    await registre.executer("carte.relecture", ctx(d, ["L"]));
    expect(d.journal).toEqual(["relire:L:demander"]);  // ni meta bricolée, ni commentaire : une vraie demande
    expect(registre.etat("carte.relecture.pret", ctx(d, ["L"]))).toMatchObject({ disponible: false, raison: expect.stringContaining("Aucune relecture n'est en attente") });
    // le serveur a enregistré la demande : la carte la porte, le libellé et les verdicts suivent
    const demande = { id: "RL-1", objet_id: "L", espace: "accueil", statut: "demandee", demande_par: "studio:humain", note: "", verdict: "", avis: "", rendu_par: "", cree: 1, maj: 1 } as const;
    d.objets = [carte("L", { artefacts, relecture: { ...demande } })];
    expect(etatsCarte(d.b.objet("L")!).map((e) => e.texte)).toEqual(["Relecture demandée"]);
    expect(etatsCarte(d.b.objet("L")!)[0]!.raison).toContain("Aucun agent n'est lancé");
    expect(libelleDe(registre.obtenir("carte.relecture")!, ctx(d, ["L"]))).toBe("Retirer la demande de relecture");
    await registre.executer("carte.relecture.corrections", ctx(d, ["L"]));
    await registre.executer("carte.relecture", ctx(d, ["L"]));
    expect(d.journal.slice(1)).toEqual(["relire:L:rendre:corrections", "relire:L:annuler"]);
    d.objets = [carte("L", { artefacts, relecture: { ...demande, statut: "rendue", verdict: "corrections", avis: "Prix faux" } })];
    expect(etatsCarte(d.b.objet("L")!).map((e) => [e.sorte, e.texte])).toEqual([["bloquee", "Corrections demandées"]]);
    d.objets = [carte("L", { artefacts, relecture: { ...demande, statut: "rendue", verdict: "pret" } })];
    expect(etatsCarte(d.b.objet("L")!).map((e) => [e.sorte, e.texte])).toEqual([["pret", "Relu : prêt"]]);
    // une mission sans livrable : la commande est montrée grisée, avec la raison
    const m = double([carte("M", { type: "mission" }), carte("N")]);
    expect(registre.proposees(ctx(m, ["M"]), "menu").find((p) => p.cmd.id === "carte.relecture")?.etat)
      .toEqual({ disponible: false, concerne: true, raison: "Cette mission n'a pas encore rendu de livrable : il n'y a rien à relire" });
    expect(registre.proposees(ctx(m, ["N"]), "menu").some((p) => p.cmd.id === "carte.relecture")).toBe(false);
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
