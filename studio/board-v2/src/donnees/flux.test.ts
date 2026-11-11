import { describe, expect, it, vi } from "vitest";
import type { Evenement } from "../types";
import { FauxFlux, Horloge } from "./essais";
import { ClientFlux } from "./flux";

const ev = (seq: number, prec: number, type = "board_maj"): Evenement => ({ seq, prec, type, mission_id: null, tache_id: null, ts: 0, donnees: { objet_id: "A", espace: "accueil" } });

function monter(filetMs?: number) {
  const ouverts: FauxFlux[] = [];
  const horloge = new Horloge();
  const recus: number[] = [];
  const surTrou = vi.fn();
  const flux = new ClientFlux({
    url: (apres) => `/api/flux?apres=${apres}&espace=accueil`,
    ouvrir: (url) => {
      const f = new FauxFlux(url);
      ouverts.push(f);
      return f;
    },
    surEvenement: (e) => recus.push(e.seq),
    surTrou,
    minuterie: horloge,
    delaiMin: 1000,
    delaiMax: 8000,
    filetMs,
  });
  return { flux, ouverts, horloge, recus, surTrou };
}

describe("client de flux avec reprise", () => {
  it("s'ouvre au curseur du chargement, jamais à zéro", () => {
    const { flux, ouverts } = monter();
    flux.demarrer(4812);
    expect(ouverts[0]!.url).toBe("/api/flux?apres=4812&espace=accueil");
  });

  it("chaîne continue : chaque événement est remis, aucune relecture complète", () => {
    const { flux, ouverts, recus, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.ouvrir();
    ouverts[0]!.pousser("message", ev(12, 10));
    ouverts[0]!.pousser("message", ev(15, 12));
    expect(recus).toEqual([12, 15]);
    expect(flux.curseur).toBe(15);
    expect(surTrou).not.toHaveBeenCalled();
  });

  it("les messages « curseur » font avancer le point de reprise (événements d'autres Boards filtrés par le serveur)", () => {
    const { flux, ouverts, recus, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.pousser("curseur", { seq: 40, prec: 10 });
    ouverts[0]!.pousser("message", ev(41, 40));
    expect(flux.curseur).toBe(41);
    expect(recus).toEqual([41]);
    expect(surTrou).not.toHaveBeenCalled();
  });

  it("trou de séquence : signalé une fois, l'événement est quand même remis et la chaîne repart de lui", () => {
    const { flux, ouverts, recus, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.pousser("message", ev(12, 10));
    ouverts[0]!.pousser("message", ev(20, 17));   // 17 n'a jamais été reçu
    ouverts[0]!.pousser("message", ev(21, 20));
    expect(surTrou).toHaveBeenCalledTimes(1);
    expect(surTrou).toHaveBeenCalledWith("trou");
    expect(recus).toEqual([12, 20, 21]);
  });

  it("événement déjà vu (reprise large) : ignoré", () => {
    const { flux, ouverts, recus } = monter();
    flux.demarrer(10);
    ouverts[0]!.pousser("message", ev(12, 10));
    ouverts[0]!.pousser("message", ev(12, 10));
    ouverts[0]!.pousser("message", ev(11, 10));
    expect(recus).toEqual([12]);
  });

  it("resynchronisation demandée par le serveur : relecture complète et nouveau point de reprise", () => {
    const { flux, ouverts, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.pousser("resync", { seq: 9000 });
    expect(surTrou).toHaveBeenCalledWith("resync");
    expect(flux.curseur).toBe(9000);
  });

  it("coupure passagère : le navigateur réessaie seul (Last-Event-ID), on ne rouvre rien et on ne relit rien", () => {
    const { flux, ouverts, horloge, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.ouvrir();
    ouverts[0]!.echouer(false);
    ouverts[0]!.ouvrir();
    horloge.avancer(60_000);
    expect(ouverts).toHaveLength(1);
    expect(surTrou).not.toHaveBeenCalled();
  });

  it("connexion fermée pour de bon : réouverture au dernier numéro reçu, attente croissante, relecture à la reprise", () => {
    const { flux, ouverts, horloge, surTrou } = monter();
    flux.demarrer(10);
    ouverts[0]!.ouvrir();
    ouverts[0]!.pousser("message", ev(12, 10));
    ouverts[0]!.echouer(true);
    expect(ouverts[0]!.ferme).toBe(true);
    expect(horloge.enAttente).toEqual([1000]);
    horloge.avancer(1000);
    expect(ouverts[1]!.url).toBe("/api/flux?apres=12&espace=accueil");
    ouverts[1]!.echouer(true);
    expect(horloge.enAttente).toEqual([2000]);
    horloge.avancer(2000);
    ouverts[2]!.echouer(true);                       // troisième échec : on prévient (le Board affichera l'erreur du serveur)
    expect(surTrou).toHaveBeenCalledTimes(1);
    expect(horloge.enAttente).toEqual([4000]);
    horloge.avancer(4000);
    ouverts[3]!.echouer(true);
    expect(horloge.enAttente).toEqual([8000]);
    horloge.avancer(8000);
    ouverts[4]!.echouer(true);
    expect(horloge.enAttente).toEqual([8000]);       // plafonné
    horloge.avancer(8000);
    ouverts[5]!.ouvrir();                            // le serveur est revenu
    expect(surTrou).toHaveBeenCalledTimes(2);
    expect(surTrou).toHaveBeenLastCalledWith("reconnexion");
    ouverts[5]!.pousser("message", ev(13, 12));
    expect(flux.curseur).toBe(13);
    expect(surTrou).toHaveBeenCalledTimes(2);        // la chaîne a repris exactement où elle s'était arrêtée
  });

  it("flux coupé (jamais connecté) : relecture périodique en mode dégradé, arrêtée dès que le flux s'ouvre", () => {
    const { flux, ouverts, horloge, surTrou } = monter(10_000);
    flux.demarrer(10);
    ouverts[0]!.echouer(false);                      // le navigateur réessaie en boucle, sans jamais aboutir
    horloge.avancer(10_000);
    horloge.avancer(10_000);
    expect(surTrou.mock.calls).toEqual([["filet"], ["filet"]]);
    ouverts[0]!.ouvrir();                            // le flux passe enfin
    horloge.avancer(60_000);
    expect(surTrou).toHaveBeenCalledTimes(2);        // connecté : plus aucune relecture périodique
    ouverts[0]!.echouer(false);                      // nouvelle coupure : le filet reprend
    horloge.avancer(10_000);
    expect(surTrou).toHaveBeenCalledTimes(3);
    flux.arreter();
    horloge.avancer(60_000);
    expect(surTrou).toHaveBeenCalledTimes(3);
  });

  it("flux connecté : aucune relecture périodique, même après des heures", () => {
    const { flux, ouverts, horloge, surTrou } = monter(10_000);
    flux.demarrer(10);
    ouverts[0]!.ouvrir();
    horloge.avancer(6 * 3600_000);
    expect(surTrou).not.toHaveBeenCalled();
  });

  it("arrêt : plus de réouverture ni de message traité", () => {
    const { flux, ouverts, horloge, recus } = monter();
    flux.demarrer(10);
    ouverts[0]!.echouer(true);
    flux.arreter();
    horloge.avancer(60_000);
    expect(ouverts).toHaveLength(1);
    ouverts[0]!.pousser("message", ev(12, 10));
    expect(recus).toEqual([]);
  });

  it("message illisible : ignoré sans casser le flux", () => {
    const { flux, ouverts, recus } = monter();
    flux.demarrer(10);
    for (const f of [(ouverts[0] as unknown as { ecouteurs: Map<string, ((e: { data: string }) => void)[]> }).ecouteurs.get("message")![0]!]) f({ data: "{pas du json" });
    ouverts[0]!.pousser("message", ev(12, 10));
    expect(recus).toEqual([12]);
  });
});
