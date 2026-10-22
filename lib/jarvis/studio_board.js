// Jarvis Studio — Board. Aucune donnée n'est gardée ici : tout est relu du serveur, qui relit la base des missions.
// Les contenus (notes, artefacts) sont affichés avec textContent : jamais interprétés comme du HTML.
"use strict";

const ESPACE = "accueil";
const ENTETE = { "Content-Type": "application/json", "X-Jarvis-Studio": "1" };
const $ = (id) => document.getElementById(id);
const etat = { objets: new Map(), flux: null, rechargement: null };

const LIBELLES = {
  board_objet: "objet ajouté", board_deplace: "objet déplacé", mission_creee: "mission créée",
  tache_creee: "tâche créée", tache_etat: "tâche", artefact: "artefact reçu", mission_etat: "mission",
  approbation: "approbation", resultat_perime: "résultat périmé refusé", arret_urgence: "arrêt d'urgence",
  executant_enrole: "exécutant enrôlé", executant_revoque: "exécutant révoqué", budget_inference: "budget",
};
const STATUTS = { OPEN: "en cours", SUCCEEDED: "réussie", FAILED: "échouée", CANCELLED: "annulée", EXPIRED: "expirée" };

function el(tag, attrs = {}, ...enfants) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
  }
  for (const e of enfants) if (e) n.append(e);
  return n;
}

async function api(chemin, options = {}) {
  const r = await fetch(chemin, { credentials: "same-origin", ...options });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { afficherPorte(); throw new Error(data.erreur || "session requise"); }
  if (!r.ok) throw new Error(data.erreur || `erreur ${r.status}`);
  return data;
}
const poster = (chemin, corps) => api(chemin, { method: "POST", headers: ENTETE, body: JSON.stringify(corps) });

function afficherPorte() { $("espace").hidden = true; $("porte").hidden = false; $("etat-global").textContent = "non connecté"; }
function heure(ts) { return new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); }
const REVUES = { acceptee: "acceptée", refusee: "refusée", en_cours: "en cours" };
function signaler(msg) { $("etat-global").textContent = msg; }

// --- Board ---------------------------------------------------------------------------------------
function carte(o) {
  const statut = o.mission_statut;
  const droite = el("span", { class: "droite" });
  if (statut) {
    const bouton = el("button", { type: "button", class: "lien-insp", text: "Inspecter", "aria-label": `Inspecter la mission ${o.mission_id}` });
    bouton.addEventListener("pointerdown", (ev) => ev.stopPropagation());  // ne démarre pas un déplacement
    bouton.addEventListener("click", () => inspecter(o.mission_id));
    droite.append(el("span", { class: `puce s-${statut}`, text: STATUTS[statut] || statut }), bouton);
  } else droite.append(el("span", { text: "sans analyse" }));
  const tete = el("div", { class: "carte-tete" }, el("span", { text: `${o.type} · ${heure(o.cree)}` }), droite);
  const corps = el("div", { class: "carte-corps", text: o.contenu });
  const pied = el("div", { class: "carte-pied" });
  const arts = o.artefacts || [];
  if (o.mission_id && !arts.length) pied.append(el("span", { class: "dim", text: statut === "OPEN" ? "analyse en attente d'un exécutant…" : "aucun artefact" }));
  for (const a of arts) {
    const resume = el("summary", {}, el("span", { text: `Analyse · ${a.fournisseur} · revue ${REVUES[a.revue] || a.revue}` }));
    if (a.factice) resume.append(el("span", { class: "factice", title: "Produit sans IA, pour les tests", text: "FACTICE" }));
    const d = el("details", { class: `artefact ${a.revue === "refusee" ? "refusee" : ""}` }, resume, el("div", { class: "texte", text: a.contenu }));
    if (a.revue === "acceptee") d.open = arts.filter((x) => x.revue === "acceptee").length === 1;
    pied.append(d);
  }
  const n = el("article", { class: "carte", tabindex: "0", "aria-label": `${o.type} : ${o.contenu.slice(0, 60)}` }, tete, corps);
  if (o.mission_id) n.append(pied);
  n.style.left = `${o.x}px`; n.style.top = `${o.y}px`;
  n.dataset.id = o.id;
  rendreDeplacable(n, tete, o);
  return n;
}

function rendreDeplacable(n, poignee, o) {
  let depart = null;
  poignee.addEventListener("pointerdown", (ev) => {
    depart = { x: ev.clientX, y: ev.clientY, ox: o.x, oy: o.y };
    poignee.setPointerCapture(ev.pointerId); n.classList.add("saisie");
  });
  poignee.addEventListener("pointermove", (ev) => {
    if (!depart) return;
    o.x = Math.max(0, depart.ox + ev.clientX - depart.x); o.y = Math.max(0, depart.oy + ev.clientY - depart.y);
    n.style.left = `${o.x}px`; n.style.top = `${o.y}px`;
  });
  poignee.addEventListener("pointerup", () => {
    if (!depart) return;
    const bouge = depart.ox !== o.x || depart.oy !== o.y;
    depart = null; n.classList.remove("saisie");
    if (bouge) enregistrerPosition(o);
  });
  let attente = null;
  n.addEventListener("keydown", (ev) => {
    const pas = ev.shiftKey ? 64 : 16;
    const d = { ArrowLeft: [-pas, 0], ArrowRight: [pas, 0], ArrowUp: [0, -pas], ArrowDown: [0, pas] }[ev.key];
    if (!d || ev.target !== n) return;
    ev.preventDefault();
    o.x = Math.max(0, o.x + d[0]); o.y = Math.max(0, o.y + d[1]);
    n.style.left = `${o.x}px`; n.style.top = `${o.y}px`;
    clearTimeout(attente); attente = setTimeout(() => enregistrerPosition(o), 400);
  });
}

function enregistrerPosition(o) {
  poster(`/api/board/${o.id}/position`, { x: o.x, y: o.y }).catch((e) => signaler(`déplacement non enregistré : ${e.message}`));
}

async function chargerBoard() {
  const { objets } = await api(`/api/board?espace=${encodeURIComponent(ESPACE)}`);
  const canevas = $("canevas");
  const focus = document.activeElement?.dataset?.id;
  const ouverts = new Set([...canevas.querySelectorAll("details[open]")].map((d) => d.closest(".carte").dataset.id + d.textContent.length));
  canevas.replaceChildren(...objets.map(carte));
  etat.objets = new Map(objets.map((o) => [o.id, o]));
  $("vide").hidden = objets.length > 0;
  for (const d of canevas.querySelectorAll("details")) if (ouverts.has(d.closest(".carte").dataset.id + d.textContent.length)) d.open = true;
  if (focus) canevas.querySelector(`[data-id="${CSS.escape(focus)}"]`)?.focus();
}

function placeLibre() {
  const n = etat.objets.size;
  return { x: 40 + (n % 4) * 330, y: 40 + Math.floor(n / 4) * 300 };
}

// --- Panneau -------------------------------------------------------------------------------------
async function chargerApprobations() {
  const { approbations } = await api("/api/approbations");
  $("nb-approbations").textContent = approbations.length;
  const ul = $("approbations");
  if (!approbations.length) { ul.replaceChildren(el("li", { class: "dim", text: "Rien à décider." })); return; }
  ul.replaceChildren(...approbations.map((p) => {
    const oui = el("button", { class: "primaire", type: "button", text: "Approuver" });
    const non = el("button", { class: "danger", type: "button", text: "Refuser" });
    const decider = async (accord) => {
      oui.disabled = non.disabled = true;
      try { await poster(`/api/approbations/${p.id}`, { accord }); } catch (e) { signaler(e.message); }
      await toutCharger();
    };
    oui.addEventListener("click", () => decider(true)); non.addEventListener("click", () => decider(false));
    return el("li", {},
      el("div", { text: `${p.niveau} · ${p.type} · ${p.tache_id}` }),
      el("div", { class: "extrait", text: p.travail }),
      el("div", { class: "actions" }, oui, non));
  }));
}

async function chargerExecution() {
  const x = await api("/api/execution");
  const lignes = [];
  if (x.arret_urgence) lignes.push(el("div", { class: "ko", text: "Arrêt d'urgence posé : aucune tâche n'est confiée." }));
  if (!x.executants.length) lignes.push(el("div", { class: "dim", text: "Aucun exécutant enrôlé : jarvis mission enroler" }));
  for (const e of x.executants) {
    lignes.push(el("div", { class: "rangee" },
      el("span", { text: `${e.nom} (${e.fournisseurs.join(", ")})` }),
      el("span", { class: e.revoque ? "ko" : e.actif ? "ok" : "dim", text: e.revoque ? "révoqué" : e.actif ? "actif" : "inactif" })));
  }
  if (x.executants.length && !x.executants.some((e) => e.actif && !e.revoque)) {
    lignes.push(el("div", { class: "dim", text: "Lance l'exécutant : jarvis mission executer --fois 1000 --attente 3" }));
  }
  for (const c of x.connexions) {
    lignes.push(el("div", { class: "rangee" },
      el("span", { text: `${c.fournisseur} · ${c.mode_auth}${c.payant ? " · payant" : ""}` }),
      el("span", { class: c.disponible ? "ok" : "ko", text: c.disponible ? "disponible" : `indisponible${c.raison ? " : " + c.raison.slice(0, 40) : ""}` })));
  }
  const file = Object.entries(x.taches).map(([s, n]) => `${s} ${n}`).join(" · ");
  lignes.push(el("div", { class: "dim", text: file ? `Tâches : ${file}` : "Aucune tâche." }));
  $("execution").replaceChildren(...lignes);
}

async function chargerMissions() {
  const { missions } = await api("/api/missions");
  const ul = $("missions");
  if (!missions.length) { ul.replaceChildren(el("li", { class: "dim", text: "Aucune mission." })); return; }
  ul.replaceChildren(...missions.slice(0, 12).map((m) => {
    const b = el("button", { type: "button" },
      el("span", {}, el("span", { class: `puce s-${m.statut}`, text: STATUTS[m.statut] || m.statut }),
        el("span", { class: "dim", text: `  ${heure(m.cree)} · ${m.source}` })),
      el("span", { class: "objectif", text: m.objectif }));
    b.addEventListener("click", () => inspecter(m.id));
    return el("li", {}, b);
  }));
}

// --- Inspecteur de mission -----------------------------------------------------------------------
const ETATS = {
  CREATED: "créée", VALIDATED: "validée", WAITING_APPROVAL: "attend une approbation", QUEUED: "en file",
  WAITING_PROVIDER: "attend un fournisseur", LEASED: "confiée", RUNNING: "en cours", REVIEW: "en revue",
  RETRY_SCHEDULED: "nouvel essai prévu", SUCCEEDED: "réussie", FAILED: "échouée", CANCELLED: "annulée", EXPIRED: "expirée",
};
const DECISIONS = { en_attente: "en attente", accordee: "accordée", refusee: "refusée", caduque: "caduque (tâche terminée)" };
const ISSUES = { reussi: "réussie", echec: "échec", fournisseur_indisponible: "fournisseur indisponible", bail_expire: "bail expiré" };

function duree(debut, fin) {
  if (!fin) return "—";
  const s = Math.max(0, fin - debut);
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

function blocTache(t) {
  const enCours = t.statut === "LEASED" || t.statut === "RUNNING";
  const tete = el("header", {},
    el("b", { text: t.id }), el("span", { text: `${t.type} · ${t.niveau}` }),
    el("span", { class: `puce s-${t.statut}`, text: ETATS[t.statut] || t.statut }),
    el("span", { class: "meta", text: `essai ${t.essais}/${t.essais_max} · ${t.fournisseur_choisi || t.fournisseur}` +
      `${t.parent_id ? ` · sous-tâche de ${t.parent_id}` : ""}` }));
  const bail = el("section", {}, el("h3", { text: "Bail" }));
  if (!t.bail_jeton) bail.append(el("div", { class: "bail dim", text: "Jamais confiée à un exécutant." }));
  else if (enCours && t.bail_expire) {
    const reste = Math.round(t.bail_expire - Date.now() / 1000);
    bail.append(el("div", { class: "bail", text: `n° ${t.bail_jeton} détenu par ${t.bail_executant}, ` +
      (reste >= 0 ? `expire dans ${reste} s` : `expiré depuis ${-reste} s (sera repris au prochain balayage)`) }));
  } else bail.append(el("div", { class: "bail dim", text: `Dernier bail : n° ${t.bail_jeton} (${t.bail_executant || "—"}), libéré.` }));
  if (t.raison) bail.append(el("div", { class: "meta", text: `Dernière raison : ${t.raison}` }));

  const tent = el("section", {}, el("h3", { text: `Tentatives (${t.tentatives.length})` }));
  if (!t.tentatives.length) tent.append(el("div", { class: "dim", text: "Aucune." }));
  else {
    const corps = el("tbody");
    for (const a of t.tentatives) {
      const issue = a.issue || "encours";
      corps.append(el("tr", {},
        el("td", { text: `n° ${a.bail_jeton}` }), el("td", { text: a.executant_nom || a.executant_id }),
        el("td", { text: a.fournisseur }), el("td", { text: heure(a.debut) }), el("td", { text: duree(a.debut, a.fin) }),
        el("td", { class: `i-${issue}`, text: ISSUES[issue] || "en cours" }), el("td", { text: a.erreur || "" })));
    }
    tent.append(el("div", { class: "defile" }, el("table", { class: "tableau" },
      el("thead", {}, el("tr", {}, ...["Bail", "Exécutant", "Fournisseur", "Début", "Durée", "Issue", "Erreur"].map((h) => el("th", { text: h })))),
      corps)));
  }

  const trans = el("section", {}, el("h3", { text: "Transitions" }),
    el("ol", { class: "chrono" }, ...t.transitions.map((x) => el("li", {},
      el("span", { text: heure(x.ts) }),
      el("span", { text: `${ETATS[x.de] || x.de} → ${ETATS[x.vers] || x.vers}` }),
      el("span", { class: "raison", text: x.raison || "" })))));

  const blocs = [tete, bail, tent, trans];
  if (t.approbations.length) {
    blocs.push(el("section", {}, el("h3", { text: "Approbations" }), ...t.approbations.map((p) =>
      el("div", { class: "meta", text: `${p.id} : ${DECISIONS[p.statut] || p.statut}${p.decide_par ? ` par ${p.decide_par} à ${heure(p.decide)}` : ""} (demandée par ${p.demandeur})` }))));
  }
  if (t.artefacts.length) {
    const s = el("section", {}, el("h3", { text: `Artefacts (${t.artefacts.length})` }));
    for (const a of t.artefacts) {
      const resume = el("summary", {}, el("span", { text: `${a.id} · tentative ${a.tentative_id} · ${a.fournisseur} · revue ${REVUES[a.revue] || a.revue}` }));
      if (a.factice) resume.append(el("span", { class: "factice", text: "FACTICE" }));
      s.append(el("details", { class: `artefact ${a.revue === "refusee" ? "refusee" : ""}` }, resume,
        el("div", { class: "texte", text: a.contenu }), el("div", { class: "meta", text: `empreinte sha256 ${a.empreinte.slice(0, 16)}…` })));
    }
    blocs.push(s);
  }
  return el("article", { class: "tache" }, ...blocs);
}

async function inspecter(missionId, { garderOuvert = false } = {}) {
  const d = $("inspecteur");
  try {
    const m = await api(`/api/missions/${encodeURIComponent(missionId)}/inspection`);
    etat.inspectee = m;
    $("insp-titre").textContent = m.objectif;
    $("insp-sur").replaceChildren(
      el("span", { class: `puce s-${m.statut}`, text: STATUTS[m.statut] || m.statut }),
      el("span", { text: m.id }), el("span", { text: `source ${m.source}` }), el("span", { text: `par ${m.demandeur}` }),
      el("span", { text: `créée ${heure(m.cree)}` }), el("span", { text: `corrélation ${m.correlation_id}` }));
    $("insp-annuler").hidden = m.statut !== "OPEN";
    $("insp-corps").replaceChildren(...m.taches.map(blocTache));
    if (!d.open && !garderOuvert) d.showModal();
  } catch (e) { signaler(`inspecteur : ${e.message}`); }
}

function concerneInspectee(e) {
  const m = etat.inspectee;
  if (!m || !$("inspecteur").open) return false;
  return e.mission_id === m.id || m.taches.some((t) => t.id === e.tache_id);
}

async function toutCharger() {
  try {
    await Promise.all([chargerBoard(), chargerApprobations(), chargerExecution(), chargerMissions()]);
    signaler(`à jour · ${heure(Date.now() / 1000)}`);
  } catch (e) { signaler(e.message); }
}

function rechargerBientot() {
  clearTimeout(etat.rechargement);
  etat.rechargement = setTimeout(toutCharger, 250);
}

// --- Flux d'événements (SSE) ---------------------------------------------------------------------
function decrire(e) {
  const d = e.donnees || {};
  if (e.type === "tache_etat") return `${d.de} → ${d.vers}`;
  if (e.type === "mission_etat") return d.vers;
  if (e.type === "artefact") return `${d.fournisseur}${d.factice ? " (factice)" : ""}`;
  if (e.type === "approbation") return `${d.decision} par ${d.par}`;
  return "";
}

function ouvrirFlux() {
  const source = new EventSource("/api/flux?apres=0");
  etat.flux = source;
  const liste = $("flux");
  source.onopen = () => $("point-flux").classList.add("vivant");
  source.onerror = () => $("point-flux").classList.remove("vivant");  // le navigateur se reconnecte avec Last-Event-ID
  source.onmessage = (m) => {
    const e = JSON.parse(m.data);
    const ligne = el("li", {}, el("span", { text: `${heure(e.ts)} ` }), el("b", { text: LIBELLES[e.type] || e.type }),
      el("span", { text: ` ${decrire(e)} ${e.tache_id || e.mission_id || ""}` }));
    liste.prepend(ligne);
    while (liste.children.length > 80) liste.lastChild.remove();
    if (e.type !== "board_deplace") rechargerBientot();
    if (concerneInspectee(e)) {
      clearTimeout(etat.rechargementInsp);
      etat.rechargementInsp = setTimeout(() => inspecter(etat.inspectee.id, { garderOuvert: true }), 250);
    }
  };
}

// --- Démarrage -----------------------------------------------------------------------------------
async function demarrer() {
  const jeton = location.hash.slice(1);
  if (jeton) {
    history.replaceState(null, "", "/");  // le jeton quitte l'adresse affichée
    try { await poster("/api/session", { jeton }); } catch { afficherPorte(); return; }
  }
  const { authentifie } = await fetch("/api/session", { credentials: "same-origin" }).then((r) => r.json());
  if (!authentifie) { afficherPorte(); return; }
  $("porte").hidden = true; $("espace").hidden = false;
  $("insp-fermer").addEventListener("click", () => $("inspecteur").close());
  $("inspecteur").addEventListener("close", () => { etat.inspectee = null; });
  $("insp-annuler").addEventListener("click", async () => {
    const m = etat.inspectee;
    if (!m || !confirm(`Annuler la mission ${m.id} ? Les tâches non terminées seront annulées.`)) return;
    try { await poster(`/api/missions/${m.id}/annuler`, {}); } catch (e) { signaler(e.message); }
    await inspecter(m.id, { garderOuvert: true });
  });
  $("form-ajout").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const bouton = ev.submitter; bouton.disabled = true;
    try {
      await poster("/api/board", { espace: ESPACE, type: $("type").value, contenu: $("contenu").value, ...placeLibre() });
      $("contenu").value = "";
      await toutCharger();
    } catch (e) { signaler(e.message); } finally { bouton.disabled = false; }
  });
  await toutCharger();
  ouvrirFlux();
  setInterval(chargerExecution, 15000);  // signes de vie des exécutants (pas d'événement à chaque battement)
}

demarrer();
