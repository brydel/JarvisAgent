import { describe, expect, it, vi } from "vitest";
import type { Evenement } from "../types";
import { FauxServeur, Horloge, carte, lien, souffler } from "./essais";
import { StoreBoard } from "./store";
import { Synchroniseur, planifier } from "./synchro";

let seq = 100;
const ev = (type: string, donnees: Record<string, unknown>, mission_id: string | null = null): Evenement =>
  ({ seq: ++seq, type, mission_id, tache_id: null, ts: 0, donnees });

async function monter(objets = [carte("A"), carte("B")], liens = [lien("L1", "A", "B")]) {
  const serveur = new FauxServeur(objets, liens);
  const store = new StoreBoard();
  const horloge = new Horloge();
  const surApplique = vi.fn(), surErreur = vi.fn();
  const sync = new Synchroniseur(serveur, store, { espace: "accueil", delai: 60, lot: 100, minuterie: horloge, surApplique, surErreur });
  await sync.recharger();
  return { serveur, store, horloge, sync, surApplique, surErreur };
}

describe("planifier : d'un événement au plus petit changement", () => {
  const store = new StoreBoard();
  store.remplacer({ espace: "accueil", objets: [carte("A", { version: 3 }), carte("M", { mission_id: "MI-1" })], liens: [lien("L1", "A", "M", { version: 2 })] });

  it("ignore les événements des autres espaces", () => {
    const p = planifier(ev("board_maj", { objet_id: "A", espace: "autre projet", version: 9 }), store, "accueil");
    expect(p).toEqual({ objets: [], liens: [], retirerObjets: [], retirerLiens: [], reglages: false, complet: false });
  });

  it("ignore l'écho de sa propre écriture (version déjà connue)", () => {
    expect(planifier(ev("board_maj", { objet_id: "A", espace: "accueil", version: 3 }), store, "accueil").objets).toEqual([]);
  });

  it("relit UN objet quand sa version a avancé, ou quand il est nouveau", () => {
    expect(planifier(ev("board_maj", { objet_id: "A", espace: "accueil", version: 4 }), store, "accueil").objets).toEqual(["A"]);
    expect(planifier(ev("board_objet", { objet_id: "N", espace: "accueil", version: 1 }), store, "accueil").objets).toEqual(["N"]);
  });

  it("événement sans version (commentaire, mission rattachée) : relu", () => {
    expect(planifier(ev("board_commentaire", { objet_id: "A", espace: "accueil" }), store, "accueil").objets).toEqual(["A"]);
  });

  it("suppression : retrait local sans lecture ; restauration : relecture des cartes", () => {
    expect(planifier(ev("board_supprime", { objets: ["A", "X"], espace: "accueil" }), store, "accueil")).toMatchObject({ retirerObjets: ["A", "X"], objets: [] });
    expect(planifier(ev("board_restaure", { objets: ["Z"], espace: "accueil" }), store, "accueil").objets).toEqual(["Z"]);
  });

  it("relations : relue si nouvelle ou plus récente, retirée si supprimée, ignorée si déjà connue", () => {
    expect(planifier(ev("board_lien", { lien_id: "L9", espace: "accueil", version: 1 }), store, "accueil").liens).toEqual(["L9"]);
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 2 }), store, "accueil").liens).toEqual([]);
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 3 }), store, "accueil").liens).toEqual(["L1"]);
    expect(planifier(ev("board_lien_maj", { lien_id: "L1", espace: "accueil", version: 3, supprime: true }), store, "accueil").retirerLiens).toEqual(["L1"]);
  });

  it("avancement d'une mission : seules ses cartes sont relues ; mission d'un autre Board : rien", () => {
    expect(planifier(ev("tache_etat", { de: "QUEUED", vers: "RUNNING" }, "MI-1"), store, "accueil").objets).toEqual(["M"]);
    expect(planifier(ev("tache_etat", { de: "QUEUED", vers: "RUNNING" }, "MI-autre"), store, "accueil").objets).toEqual([]);
  });

  it("réglages et téléversements ne déclenchent aucune lecture d'objet", () => {
    expect(planifier(ev("reglages_board", { auto_analyse: false }), store, "accueil")).toMatchObject({ reglages: true, objets: [], complet: false });
    expect(planifier(ev("board_fichier", { asset_id: "AS-1" }), store, "accueil")).toMatchObject({ objets: [], complet: false });
  });

  it("événement d'un ancien processus (sans espace ni version) : l'objet est relu, le serveur tranchera", () => {
    expect(planifier(ev("board_maj", { objet_id: "A", champs: ["meta"] }), store, "accueil").objets).toEqual(["A"]);
  });

  it("événement du Board impossible à cibler : relecture complète en dernier recours", () => {
    expect(planifier(ev("board_inconnu", { espace: "accueil" }), store, "accueil").complet).toBe(true);
  });
});

describe("synchroniseur", () => {
  it("un événement distant = une lecture ciblée d'un objet, jamais un rechargement du Board", async () => {
    const { serveur, store, horloge, sync, surApplique } = await monter();
    serveur.ailleurs("A", { x: 77 });
    sync.surEvenement(ev("board_maj", { objet_id: "A", espace: "accueil", version: 2 }));
    expect(serveur.appels.lire).toBe(0);       // regroupé : rien avant la fin du délai
    horloge.avancer(60);
    await souffler();
    expect(serveur.demandes).toEqual([{ objets: ["A"], liens: [] }]);
    expect(serveur.appels.charger).toBe(1);    // le seul chargement complet est celui du démarrage
    expect(store.objet("A")!.x).toBe(77);
    expect(surApplique).toHaveBeenCalled();
    expect(sync.compteurs).toEqual({ complets: 1, cibles: 1 });
  });

  it("une rafale d'événements est regroupée en une seule requête, sans doublon", async () => {
    const { serveur, horloge, sync } = await monter();
    serveur.ailleurs("A", { x: 1 });
    serveur.ailleurs("B", { x: 2 });
    for (let i = 0; i < 20; i++) sync.surEvenement(ev("board_maj", { objet_id: i % 2 ? "A" : "B", espace: "accueil", version: 2 }));
    sync.surEvenement(ev("board_lien", { lien_id: "L7", espace: "accueil", version: 1 }));
    horloge.avancer(60);
    await souffler();
    expect(serveur.appels.lire).toBe(1);
    expect(serveur.demandes[0]).toEqual({ objets: ["B", "A"], liens: ["L7"] });
  });

  it("événements d'un autre espace et échos de ses propres écritures : zéro requête", async () => {
    const { serveur, horloge, sync } = await monter();
    sync.surEvenement(ev("board_maj", { objet_id: "A", espace: "autre", version: 5 }));
    sync.surEvenement(ev("board_maj", { objet_id: "A", espace: "accueil", version: 1 }));
    horloge.avancer(1000);
    await souffler();
    expect(serveur.appels.lire).toBe(0);
    expect(serveur.appels.charger).toBe(1);
  });

  it("suppression distante : appliquée sans aucune requête", async () => {
    const { serveur, store, sync } = await monter();
    sync.surEvenement(ev("board_supprime", { objets: ["A"], espace: "accueil" }));
    expect(store.lire().objets.map((o) => o.id)).toEqual(["B"]);
    expect(store.lire().liens).toEqual([]);
    expect(serveur.appels.lire).toBe(0);
  });

  it("les gros lots sont découpés", async () => {
    const objets = Array.from({ length: 250 }, (_, i) => carte(`C${i}`));
    const { serveur, sync } = await monter(objets, []);
    await sync.lireMaintenant(objets.map((o) => o.id));
    expect(serveur.demandes.map((d) => d.objets!.length)).toEqual([100, 100, 50]);
  });

  it("lecture ciblée impossible : filet = chargement complet", async () => {
    const { serveur, horloge, sync } = await monter();
    serveur.panne = new Error("coupure");
    sync.surEvenement(ev("board_maj", { objet_id: "A", espace: "accueil", version: 2 }));
    horloge.avancer(60);
    await souffler(12);
    expect(serveur.appels.charger).toBe(2);
  });

  it("chargement complet impossible : erreur remontée, état local conservé", async () => {
    const { serveur, store, sync, surErreur } = await monter();
    serveur.panne = new Error("Session absente ou expirée");
    await sync.recharger();
    expect(surErreur).toHaveBeenCalledWith("Session absente ou expirée");
    expect(store.lire().objets).toHaveLength(2);
  });

  it("deux demandes de rechargement rapprochées ne font qu'une lecture", async () => {
    const { serveur, sync } = await monter();
    await Promise.all([sync.recharger(), sync.recharger(), sync.recharger()]);
    expect(serveur.appels.charger).toBe(2);
  });

  it("les lectures passent une par une : une réponse lente ne remplace pas une plus récente", async () => {
    const { serveur, store, sync } = await monter();
    const ordre: string[] = [];
    const lire = serveur.lire.bind(serveur);
    let debloquer!: () => void;
    const verrou = new Promise<void>((r) => { debloquer = r; });
    let premier = true;
    serveur.lire = async (d) => {
      const r = await lire(d);
      if (premier) {
        premier = false;
        await verrou;                         // la première réponse traîne
      }
      ordre.push(`x=${r.objets[0]!.x}`);
      return r;
    };
    serveur.ailleurs("A", { x: 1 });
    const p1 = sync.lireMaintenant(["A"]);
    await souffler();
    serveur.ailleurs("A", { x: 2 });
    const p2 = sync.lireMaintenant(["A"]);
    debloquer();
    await Promise.all([p1, p2]);
    expect(ordre).toEqual(["x=1", "x=2"]);
    expect(store.objet("A")!.x).toBe(2);
  });

  it("arrêté : plus aucune lecture", async () => {
    const { serveur, horloge, sync } = await monter();
    sync.surEvenement(ev("board_maj", { objet_id: "A", espace: "accueil", version: 2 }));
    sync.arreter();
    horloge.avancer(1000);
    await souffler();
    expect(serveur.appels.lire).toBe(0);
  });
});
