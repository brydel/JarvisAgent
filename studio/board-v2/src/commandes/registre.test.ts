// Registre de commandes, journal d'usage, raccourcis, recherche floue.
import { describe, expect, it, vi } from "vitest";
import { Historique } from "./historique";
import { JournalUsage, type Stockage } from "./journal";
import { afficher, deEvenement, normaliser } from "./raccourcis";
import { chercher, score } from "./recherche";
import { Registre } from "./registre";
import type { Commande } from "./types";

interface Ctx {
  selection: number;
  mode: "edition" | "lecture";
  trace: string[];
}
const ctx = (p: Partial<Ctx> = {}): Ctx => ({ selection: 0, mode: "edition", trace: [], ...p });

function memoire(): Stockage & { donnees: Map<string, string> } {
  const donnees = new Map<string, string>();
  return { donnees, getItem: (k) => donnees.get(k) ?? null, setItem: (k, v) => void donnees.set(k, v) };
}

const base: Commande<Ctx>[] = [
  { id: "edition.supprimer", libelle: "Supprimer", raccourci: ["suppr", "retour"], categorie: "Édition", niveau: "ecriture", emplacements: ["menu", "flottante"],
    disponible: (c) => c.selection > 0, executer: (c) => void c.trace.push("supprimer"),
    confirmation: (c) => (c.selection >= 10 ? `Supprimer ${c.selection} objets ?` : null) },
  { id: "presentation.quitter", libelle: "Quitter la présentation", raccourci: "echap", categorie: "Affichage", niveau: "lecture",
    disponible: (c) => c.mode === "lecture", executer: (c) => void c.trace.push("quitter") },
  { id: "edition.deselectionner", libelle: "Tout désélectionner", raccourci: "echap", categorie: "Édition", niveau: "lecture",
    disponible: (c) => c.selection > 0, executer: (c) => void c.trace.push("deselectionner") },
  { id: "affichage.theme", libelle: (c) => (c.mode === "lecture" ? "Thème jour" : "Thème nuit"), raccourci: "shift+d", categorie: "Affichage", niveau: "lecture",
    executer: (c) => void c.trace.push("theme"), annuler: (c) => void c.trace.push("theme-inverse") },
  { id: "donnees.purger", libelle: "Purger", categorie: "Édition", niveau: "sensible", executer: (c) => void c.trace.push("purger") },
];

describe("registre de commandes", () => {
  it("refuse un identifiant déclaré deux fois", () => {
    expect(() => new Registre<Ctx>().declarer([base[0]!, base[0]!])).toThrow(/deux fois/);
  });

  it("exécute seulement ce qui est disponible, et le journalise avec son origine", async () => {
    const journal = new JournalUsage(null);
    const r = new Registre<Ctx>({ journal }).declarer(base);
    const c = ctx();
    expect(await r.executer("edition.supprimer", c, "bouton")).toBe("indisponible");
    expect(await r.executer("inconnue", c)).toBe("inconnue");
    expect(journal.usage("edition.supprimer")).toBeUndefined();
    c.selection = 2;
    expect(await r.executer("edition.supprimer", c, "raccourci")).toBe("fait");
    expect(await r.executer("edition.supprimer", c, "menu")).toBe("fait");
    expect(c.trace).toEqual(["supprimer", "supprimer"]);
    expect(journal.usage("edition.supprimer")).toMatchObject({ n: 2, annulations: 0, origines: { raccourci: 1, menu: 1 } });
  });

  it("liste les commandes disponibles par emplacement", () => {
    const r = new Registre<Ctx>().declarer(base);
    expect(r.disponibles(ctx(), "menu").map((c) => c.id)).toEqual([]);
    expect(r.disponibles(ctx({ selection: 1 }), "menu").map((c) => c.id)).toEqual(["edition.supprimer"]);
    expect(r.disponibles(ctx({ selection: 1 })).map((c) => c.id)).toEqual(["edition.supprimer", "edition.deselectionner", "affichage.theme", "donnees.purger"]);
  });

  it("un raccourci partagé va à la première commande disponible", () => {
    const r = new Registre<Ctx>().declarer(base);
    const echap = { key: "Escape" };
    expect(r.pourTouche(echap, ctx())).toBeUndefined();
    expect(r.pourTouche(echap, ctx({ selection: 1 }))?.id).toBe("edition.deselectionner");
    expect(r.pourTouche(echap, ctx({ selection: 1, mode: "lecture" }))?.id).toBe("presentation.quitter");
    expect(r.pourTouche({ key: "Backspace" }, ctx({ selection: 1 }))?.id).toBe("edition.supprimer");
    expect(r.pourTouche({ key: "D", shiftKey: true }, ctx())?.id).toBe("affichage.theme");
    expect(r.raccourcisPartages().map(([k]) => k)).toEqual(["echap"]);
  });

  it("une commande sensible, ou qui le demande pour ce contexte, exige une confirmation explicite", async () => {
    const confirmer = vi.fn(() => false);
    const r = new Registre<Ctx>({ confirmer }).declarer(base);
    const c = ctx({ selection: 12 });
    expect(await r.executer("edition.supprimer", c)).toBe("refuse");
    expect(confirmer).toHaveBeenCalledWith("Supprimer 12 objets ?", expect.objectContaining({ id: "edition.supprimer" }));
    expect(await r.executer("donnees.purger", c)).toBe("refuse");
    expect(c.trace).toEqual([]);
    expect(r.journal.usage("donnees.purger")).toBeUndefined();
    confirmer.mockReturnValue(true);
    expect(await r.executer("donnees.purger", c)).toBe("fait");
    // sans fonction de confirmation : refus par défaut (jamais d'action sensible sans réponse)
    expect(await new Registre<Ctx>().declarer(base).executer("donnees.purger", ctx())).toBe("refuse");
    c.selection = 3;
    confirmer.mockClear();
    expect(await r.executer("edition.supprimer", c)).toBe("fait");
    expect(confirmer).not.toHaveBeenCalled();
  });

  it("une commande avec `annuler` entre dans l'historique ; l'annulation est comptée dans le journal", async () => {
    const r = new Registre<Ctx>().declarer(base);
    const c = ctx();
    await r.executer("affichage.theme", c, "palette");
    expect(r.historique.etat().annuler).toBe("Thème nuit");
    expect(await r.annuler()).toMatchObject({ ok: true, commande: "affichage.theme" });
    expect(c.trace).toEqual(["theme", "theme-inverse"]);
    expect(r.journal.usage("affichage.theme")).toMatchObject({ n: 1, annulations: 1 });
    await r.refaire();
    expect(c.trace).toEqual(["theme", "theme-inverse", "theme"]);
  });

  it("les écritures déposées pendant une commande portent son identifiant", async () => {
    const historique = new Historique();
    const r = new Registre<Ctx>({ historique }).declarer([{ id: "edition.dupliquer", libelle: "Dupliquer", categorie: "Édition", niveau: "ecriture",
      executer: async () => {
        await Promise.resolve();
        historique.ajouter({ libelle: "Duplication", annuler: async () => undefined, refaire: async () => undefined });
      } }]);
    await r.executer("edition.dupliquer", ctx(), "raccourci");
    await r.annuler();
    expect(r.journal.usage("edition.dupliquer")).toMatchObject({ n: 1, annulations: 1 });
  });

  it("une commande qui échoue est signalée, pas propagée", async () => {
    const surErreur = vi.fn();
    const r = new Registre<Ctx>({ surErreur }).declarer([{ id: "x.casse", libelle: "Casse", categorie: "Édition", niveau: "ecriture",
      executer: () => { throw new Error("boum"); } }]);
    expect(await r.executer("x.casse", ctx())).toBe("erreur");
    expect(surErreur).toHaveBeenCalledOnce();
  });
});

describe("journal d'usage", () => {
  it("persiste, relit, et rend les récents du plus récent au plus ancien", () => {
    const stock = memoire();
    let t = 1000;
    const j = new JournalUsage(stock, "cle", () => t);
    j.noter("a", "bouton");
    t = 2000;
    j.noter("b", "raccourci");
    t = 3000;
    j.noter("a", "palette");
    j.noterAnnulation("a");
    expect(j.recents(5)).toEqual(["a", "b"]);
    const relu = new JournalUsage(stock, "cle", () => 4000);
    expect(relu.usage("a")).toEqual({ id: "a", n: 2, annulations: 1, dernier: 3000, origines: { bouton: 1, palette: 1 } });
    expect(relu.exporter()).toMatchObject({ version: 1, depuis: 1000, genere: 4000, commandes: [{ id: "a", n: 2 }, { id: "b", n: 1 }] });
  });

  it("ne contient que des identifiants de commandes : aucun contenu de carte", () => {
    const j = new JournalUsage(null);
    j.noter("edition.copier", "raccourci");
    expect(Object.keys(j.exporter().commandes[0]!).sort()).toEqual(["annulations", "dernier", "id", "n", "origines"]);
  });

  it("survit à un stockage illisible ou refusé", () => {
    const casse: Stockage = { getItem: () => "{pas du json", setItem: () => { throw new Error("quota"); } };
    const j = new JournalUsage(casse);
    expect(() => j.noter("a", "bouton")).not.toThrow();
    expect(j.usage("a")?.n).toBe(1);
  });
});

describe("raccourcis", () => {
  it("normalise, reconnaît et affiche", () => {
    expect(normaliser("Shift+Mod+Z")).toBe("mod+shift+z");
    expect(deEvenement({ key: "z", ctrlKey: true, shiftKey: true })).toBe("mod+shift+z");
    expect(deEvenement({ key: "K", metaKey: true })).toBe("mod+k");
    expect(deEvenement({ key: "Shift", shiftKey: true })).toBe("");
    expect(deEvenement({ key: "Delete" })).toBe("suppr");
    expect(deEvenement({ key: "ArrowRight" })).toBe("droite");
    expect(deEvenement({ key: " " })).toBe("espace");
    expect(afficher("mod+shift+z", false)).toBe("Ctrl+Maj+Z");
    expect(afficher("mod+shift+z", true)).toBe("⌘⇧Z");
    expect(afficher("suppr", false)).toBe("Suppr");
  });

  it("lit les chiffres par touche physique (Maj+1 = « ! » sur un clavier, « 1 » sur un autre)", () => {
    expect(deEvenement({ key: "!", code: "Digit1", shiftKey: true })).toBe("shift+1");
    expect(deEvenement({ key: "1", code: "Digit1", shiftKey: true })).toBe("shift+1");
    expect(deEvenement({ key: "&", code: "Digit1" })).toBe("1");
  });

  it("un caractère obtenu avec Maj n'est pas un raccourci « Maj+… »", () => {
    expect(deEvenement({ key: "+", shiftKey: true })).toBe("+");
    expect(deEvenement({ key: "]" })).toBe("]");
  });
});

describe("recherche floue", () => {
  const libelles = ["Aligner à gauche", "Aligner en haut", "Thème nuit", "Exporter la sélection en PNG", "Outil : Note adhésive", "Tout sélectionner"];
  const trouver = (q: string) => chercher(q, libelles, (x) => x).map((r) => r.element);

  it("ignore accents et casse, accepte les lettres dans l'ordre", () => {
    expect(trouver("theme")[0]).toBe("Thème nuit");
    expect(trouver("ALG")[0]).toBe("Aligner à gauche");
    expect(trouver("png")).toEqual(["Exporter la sélection en PNG"]);
    expect(trouver("zzz")).toEqual([]);
    expect(score("gauche aligner", "Aligner à gauche")).toBe(-1);
  });

  it("préfère les débuts de mots et la requête retrouvée telle quelle", () => {
    expect(trouver("sel")[0]).toBe("Tout sélectionner");
    expect(score("note", "Outil : Note adhésive")).toBeGreaterThan(score("note", "Niveau de détail des cartes"));
  });

  it("un bonus d'usage départage sans renverser une bien meilleure correspondance", () => {
    const r = chercher("ali", libelles, (x) => x, (x) => (x === "Aligner en haut" ? 5 : 0));
    expect(r[0]!.element).toBe("Aligner en haut");
    const r2 = chercher("theme", libelles, (x) => x, (x) => (x === "Tout sélectionner" ? 6 : 0));
    expect(r2[0]!.element).toBe("Thème nuit");
  });
});
