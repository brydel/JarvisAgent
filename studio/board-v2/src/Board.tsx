// Le Board : assemble la couche de données (src/donnees), le registre de commandes (src/commandes), le canevas
// (src/board) et la coque (barres, panneau, dialogues). Les interactions vivent dans leurs modules ; ce fichier
// ne fait que les brancher.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReactFlow, type Edge, type Node } from "@xyflow/react";
import type { Source } from "./api";
import { Canevas } from "./board/Canevas";
import { genererCharge, lireUrl } from "./board/noeuds";
import { useClavier } from "./board/useClavier";
import { useIngestion } from "./board/useIngestion";
import { useServices } from "./board/useServices";
import type { ContexteBoard, OptionsToast, ServicesBoard } from "./commandes/contexte";
import { creerRegistreBoard } from "./commandes/index";
import { Palette } from "./commandes/Palette";
import { ContexteCommandes, type AccesCommandes } from "./commandes/react";
import { ActiviteDirecte } from "./components/ActiviteDirecte";
import { CommunauteAgents } from "./components/CommunauteAgents";
import { ConnexionsAgents } from "./components/ConnexionsAgents";
import { BarreAjout, BarreHaut, FILTRES, SaisieUrl, SousBarre, type Filtre } from "./components/Coque";
import { DialogueMission, type DemandeMission } from "./components/DialogueMission";
import { Panneau } from "./components/Panneau";
import { RuntimeAgents } from "./components/RuntimeAgents";
import { useBoard } from "./donnees/useBoard";
import type { DonneesLien } from "./edges/RelationEdge";
import { brancherTheme, ui, useUi } from "./etat/ui";
import { depuisTexte, depuisTransfert } from "./lib/ingestion";
import { ContexteActions, type ActionsBoard } from "./nodes/contexte";
import { indexDe, sousLePoint } from "./outils/espace";
import type { DonneesNoeud, EtatBoard, ObjetBoard } from "./types";

type Toast = { id: number; texte: string } & OptionsToast;

interface Props {
  source: Source;
  charge?: number;
}

export function Board({ source, charge }: Props) {
  const rf = useReactFlow<Node<DonneesNoeud>, Edge<DonneesLien>>();
  const initial = useMemo(() => lireUrl(), []);
  const [filtre, setFiltre] = useState<Filtre>(initial.filtre);
  const [prio, setPrio] = useState(initial.priorite);
  const [recherche, setRecherche] = useState(initial.q);
  const [dialogueMission, setDialogueMission] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const [saisieUrl, setSaisieUrl] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [visionneuse, setVisionneuse] = useState<{ src: string; titre: string } | null>(null);
  /** carte à sélectionner dès qu'elle existe (créée côté serveur, pas encore dans les nœuds) */
  const aSelectionner = useRef(new Set<string>());
  const zen = useUi((e) => e.zen);
  const presentation = useUi((e) => e.presentation !== null);
  const paletteOuverte = useUi((e) => e.palette);
  useEffect(() => brancherTheme(), []);

  // changer de projet = changer de Board : rechargement complet (flux, sélection et historique propres au Board)
  const changerEspace = useCallback((nom: string) => {
    const u = new URL(location.href);
    for (const cle of ["carte", "filtre", "q", "priorite"]) u.searchParams.delete(cle);
    if (nom === "accueil") u.searchParams.delete("espace");
    else u.searchParams.set("espace", nom);
    location.assign(u);
  }, []);

  const toast = useCallback((texte: string, opts: OptionsToast = {}) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, texte, ...opts }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), opts.action ? 7000 : 4000);
  }, []);

  /* ------------------------------------------------------------ données (src/donnees) ------------------ */
  // Chargement initial, flux incrémental repris au curseur, écritures optimistes versionnées : tout est dans la
  // couche de données. Aucune relecture complète ici, sauf le filet (trou dans le flux, reconnexion).
  const preparer = useCallback((e: EtatBoard) => (charge && source.demo
    ? { ...e, objets: [...e.objets, ...genererCharge(charge, new URLSearchParams(location.search).get("tableau") === "1")] } : e), [charge, source.demo]);
  const { etat, erreur, reglages, definirReglages, approbations, rafraichirApprobations, evenements, espaces, tick, store, file, sync,
    recharger: charger, creer: creerObjet } = useBoard(source, {
    conflit: (ids) => toast(ids.length > 1
      ? "Ces éléments ont été modifiés ailleurs : ta modification est annulée, voici leur dernière version"
      : "Cet élément a été modifié ailleurs : ta modification est annulée, voici sa dernière version", { erreur: true }),
    erreur: (m) => toast(`Non enregistré : ${m}`, { erreur: true }),
    evenement: (e) => {
      if (e.type !== "board_propositions") return;
      const n = Number(e.donnees.n ?? 0), l = Number(e.donnees.liens ?? 0);
      toast(`Jarvis a contextualisé un élément : ${n} action${n > 1 ? "s" : ""} proposée${n > 1 ? "s" : ""}`
        + (l ? `, ${l} lien${l > 1 ? "s" : ""} tracé${l > 1 ? "s" : ""}` : ""));
    },
  }, preparer);

  /* ------------------------------------------------------------ commandes et services ------------------- */
  const registre = useMemo(() => creerRegistreBoard({
    confirmer: (texte) => window.confirm(texte),
    surErreur: (x) => toast(x instanceof Error ? x.message : "action impossible", { erreur: true }),
  }), [toast]);
  const servicesRef = useRef<ServicesBoard | null>(null);
  const lireServices = useCallback(() => servicesRef.current!, []);
  const ingestion = useIngestion(source, file, lireServices);
  const b = useServices({
    source, store, file, sync, creerObjet, rf, historique: registre.historique, toast,
    ouvrirMission: () => setDialogueMission(true), saisirLien: () => setSaisieUrl(true),
    choisirFichiers: ingestion.choisirFichiers, collerPressePapiers: ingestion.collerPressePapiers,
    viserSelection: (ids) => { aSelectionner.current = new Set(ids); },
  });
  servicesRef.current = b;

  const objetsSelectionnes = useMemo(
    () => selection.map((id) => etat?.objets.find((o) => o.id === id) ?? store.objet(id)).filter((o): o is ObjetBoard => Boolean(o)),
    [selection, etat, store]);
  const selectionRef = useRef(objetsSelectionnes);
  selectionRef.current = objetsSelectionnes;

  const acces = useMemo<AccesCommandes>(() => {
    const contexte = (extra: Partial<Pick<ContexteBoard, "selection" | "lien" | "point">> = {}): ContexteBoard => ({
      // la sélection de React Flow fait foi si l'état React a un rendu de retard (suppression juste après un clic)
      selection: selectionRef.current.length ? selectionRef.current
        : rf.getNodes().filter((n) => n.selected).map((n) => n.data.objet), ui: ui.lire(), b, ...extra,
    });
    return { registre, contexte, executer: (id, origine, extra) => void registre.executer(id, contexte(extra), origine) };
  }, [registre, b, rf]);
  useClavier(acces);

  const actions = useMemo<ActionsBoard>(() => ({
    modifier: (id, champs) => void b.modifier([{ id, champs }], "Modification"),
    priorite: (id, p) => void b.modifier([{ id, champs: { priorite: p } }], "Priorité"),
    supprimer: (ids) => void b.supprimer(ids),
    dupliquer: (ids) => void b.dupliquer(ids),
    devant: (ids) => {
      const max = b.objets().reduce((m, o) => Math.max(m, o.z), 0);
      void b.modifier(ids.map((id, i) => ({ id, champs: { z: max + 1 + i } })), "Amener devant");
    },
    inspecter: (id) => b.inspecter(id),
    agrandir: (src, titre) => setVisionneuse({ src, titre }),
    sortirDuDossier: (id) => {
      const o = b.objet(id);
      const parent = o?.parent_id ? b.objet(o.parent_id) : undefined;
      void b.modifier([{ id, champs: { parent_id: null, x: (parent?.x ?? 0) + 40, y: (parent?.y ?? 0) + (parent?.hauteur ?? 150) + 40 } }], "Sortie du dossier");
    },
    enfants: (dossierId) => b.objets().filter((o) => o.parent_id === dossierId),
    contextualiser: (id) => b.contextualiser(id),
    objet: (id) => b.objet(id),
    sousLePoint: (p, sauf) => sousLePoint(indexDe(b.objets()), p, sauf),
    editer: (id) => ui.definir({ edition: id, outil: "selection" }),
  }), [b]);

  const lancerMission = useCallback(async (d: DemandeMission) => {
    const p = b.centreVue();
    const id = await source.lancerMission(d, p.x, p.y);  // une erreur reste affichée dans le dialogue
    toast(source.demo ? "Mode démo : aucune mission réelle n'est lancée" : "Mission créée : un exécutant va la prendre en charge");
    aSelectionner.current = new Set([id]);
    await sync.lireMaintenant([id]);
    b.selectionner([id]);
  }, [source, b, sync, toast]);

  const compteurs = useMemo(() => {
    const c = Object.fromEntries(FILTRES.map((f) => [f.cle, 0])) as Record<Filtre, number>;
    for (const o of etat?.objets ?? []) {
      if (o.parent_id) continue;
      c.tous += 1;
      for (const f of FILTRES) if (f.types.includes(o.type)) c[f.cle] += 1;
    }
    return c;
  }, [etat?.objets]);

  /* ------------------------------------------------------------ état dans l'URL -------------------------- */
  // filtre, priorité, recherche et carte sélectionnée : partageables et conservés au rechargement (replaceState :
  // l'historique du navigateur n'est pas rempli à chaque frappe)
  useEffect(() => {
    const u = new URL(location.href);
    const poser = (cle: string, v: string) => (v ? u.searchParams.set(cle, v) : u.searchParams.delete(cle));
    poser("filtre", filtre === "tous" ? "" : filtre);
    poser("priorite", prio);
    poser("q", recherche.trim());
    poser("carte", selection.length === 1 ? selection[0]! : "");
    if (u.href !== location.href) history.replaceState(history.state, "", u);
  }, [filtre, prio, recherche, selection]);

  const carteRestauree = useRef(false);
  useEffect(() => {
    if (carteRestauree.current || !etat || !initial.carte) return;
    carteRestauree.current = true;
    const o = etat.objets.find((x) => x.id === initial.carte);
    if (!o) return;
    setSelection([o.id]);  // le panneau s'ouvre tout de suite ; le canevas suit dès que ses nœuds existent
    window.setTimeout(() => b.selectionner([o.id]), 60);
    window.setTimeout(() => rf.setCenter(o.x + (o.largeur || 400) / 2, o.y + (o.hauteur || 300) / 2, { zoom: Math.max(0.7, rf.getZoom()), duration: 250 }), 120);
  }, [etat, initial.carte, rf, b]);

  /* ------------------------------------------------------------ rendu ------------------------------------ */
  const selectionne = objetsSelectionnes.length === 1 ? objetsSelectionnes[0]! : null;
  const vide = etat && !etat.objets.length;
  const immersif = zen || presentation;

  return (
    <ContexteCommandes.Provider value={acces}>
      <ContexteActions.Provider value={actions}>
        <div className={`app${source.demo ? "" : " avec-activite"}${zen ? " zen" : ""}${presentation ? " presentation" : ""}`}>
          {!immersif && <BarreHaut recherche={recherche} setRecherche={setRecherche} notifications={approbations.length} />}
          {!immersif && (
            <SousBarre projet={source.espace === "accueil" ? "Accueil" : source.espace} espaces={espaces} changerEspace={changerEspace}
              demo={source.demo} compteurs={compteurs} filtre={filtre} setFiltre={setFiltre} priorite={prio} setPriorite={setPrio}
              communaute={<><CommunauteAgents source={source}/><ConnexionsAgents source={source}/><RuntimeAgents source={source}/></>} />
          )}
          {!immersif && (
            <ActiviteDirecte source={source} inspecter={(id) => {
              if (etat?.objets.some((o) => o.id === id)) actions.inspecter(id);
              else toast("Cette mission est liée à un autre Board de projet. Ouvre ce projet pour voir sa carte.");
            }} />
          )}
          <div className="travail">
            <Canevas source={source} etat={etat} b={b} filtre={filtre} priorite={prio} recherche={recherche}
              selection={objetsSelectionnes} setSelection={setSelection} aSelectionner={aSelectionner}
              deposer={(transfert, ou) => void ingestion.ingerer(depuisTransfert(transfert), ou)}>
              {!immersif && <BarreAjout />}
              {saisieUrl && <SaisieUrl fermer={() => setSaisieUrl(false)} valider={(u) => { setSaisieUrl(false); void ingestion.ingerer(depuisTexte(u).length ? depuisTexte(u) : [{ sorte: "url", url: u }]); }} />}
              {vide && !immersif && (
                <div className="etat-vide">
                  <div>
                    <h2>Ton Board est prêt</h2>
                    Colle une image, un lien ou un texte (Ctrl+V), dépose des fichiers, dessine avec les outils du haut, ou ouvre la palette (Ctrl+K).
                    <div><button type="button" className="bouton primaire" onClick={() => acces.executer("ajouter.note", "bouton")}>Écrire une première note</button></div>
                  </div>
                </div>
              )}
              {erreur && <div className="etat-vide"><div role="alert"><h2>Board indisponible</h2>{erreur}<div><button type="button" className="bouton" onClick={() => void charger()}>Réessayer</button></div></div></div>}
              <div className="toasts" aria-live="polite">
                {toasts.map((t) => (
                  <div key={t.id} className={`toast${t.erreur ? " erreur" : ""}`}>{t.texte}
                    {t.action && <button type="button" onClick={t.action.faire}>{t.action.nom}</button>}</div>
                ))}
              </div>
              <input ref={ingestion.champFichier} type="file" multiple hidden onChange={(e) => {
                void ingestion.ingerer(Array.from(e.target.files ?? []).map((fichier) => ({ sorte: "fichier" as const, fichier })));
                e.target.value = "";
              }} />
            </Canevas>
            {!immersif && (
              <Panneau source={source} objet={selectionne} objets={etat?.objets ?? []} evenements={evenements} approbations={approbations} tick={tick}
                priorite={actions.priorite} modifierMeta={(o, meta) => void b.modifier([{ id: o.id, champs: { meta } }], "Étiquettes")}
                decider={async (id, accord) => { await source.decider(id, accord); rafraichirApprobations(); }}
                contextualiser={actions.contextualiser}
                reglages={reglages}
                regler={async (v) => {
                  try {
                    definirReglages(await source.regler(v));
                  } catch (x) {
                    toast(x instanceof Error ? x.message : "réglage refusé", { erreur: true });
                  }
                }}
                deciderProposition={async (o, i, d) => {
                  try {
                    const r = await source.deciderProposition(o.id, i, d);
                    toast(d === "ecarter" ? "Proposition écartée" : source.demo ? "Mode démo : aucune mission réelle n'est lancée"
                      : "Mission de préparation créée, reliée à l'élément");
                    await sync.lireMaintenant([o.id, ...(r.carte_id ? [r.carte_id] : [])]);
                    if (r.carte_id) actions.inspecter(r.carte_id);
                  } catch (x) {
                    toast(x instanceof Error ? x.message : "décision refusée", { erreur: true });
                  }
                }} />
            )}
          </div>
        </div>
        {paletteOuverte && <Palette fermer={() => ui.definir({ palette: false })} />}
        <DialogueMission ouvert={dialogueMission} demo={source.demo} fermer={() => setDialogueMission(false)} lancer={lancerMission} />
        {visionneuse && (
          <div className="visionneuse" role="dialog" aria-label={visionneuse.titre || "Image"} onClick={() => setVisionneuse(null)}
            onKeyDown={(e) => e.key === "Escape" && setVisionneuse(null)}>
            <img src={visionneuse.src} alt={visionneuse.titre} />
            <button type="button" className="bouton" autoFocus onClick={() => setVisionneuse(null)}>Fermer</button>
          </div>
        )}
      </ContexteActions.Provider>
    </ContexteCommandes.Provider>
  );
}
