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
  const tete = el("div", { class: "carte-tete" },
    el("span", { text: `${o.type} · ${heure(o.cree)}` }),
    statut ? el("span", { class: `puce s-${statut}`, text: STATUTS[statut] || statut }) : el("span", { text: "sans analyse" }));
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

async function toutCharger() {
  try {
    await Promise.all([chargerBoard(), chargerApprobations(), chargerExecution()]);
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
