"""Aperçus de liens pour le Board V2 : titre, hôte, description, image Open Graph et favicon — sans risque SSRF.

Une page distante est une source NON FIABLE : on n'exécute ni n'injecte jamais son HTML ; on en extrait du texte
borné et deux images, re-téléversées dans le stockage du Board (le navigateur ne contacte jamais le site distant).

Protections :
- schémas http/https seulement, ports 80/443, pas d'identifiants dans l'URL ;
- l'hôte est résolu ici, et CHAQUE adresse doit être publique (pas de boucle locale, réseau privé, lien local,
  métadonnées cloud 169.254.169.254, multicast, réservé, IPv4 encapsulé dans IPv6) ;
- la connexion se fait vers l'adresse vérifiée (pas de seconde résolution : parade au DNS rebinding), avec le nom
  d'hôte pour TLS (vérification du certificat) et l'en-tête Host ;
- 3 redirections au plus, chacune revérifiée ; délai 6 s ; 1,5 Mo de HTML et 3 Mo par image au plus.
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

DELAI_S = 6
HTML_MAX = 1_500_000
IMAGE_MAX = 3 * 1024 * 1024
REDIRECTIONS_MAX = 3
AGENT = "JarvisStudio-apercu/1 (+https://github.com/brydel/JarvisAgent)"


class ApercuRefuse(ValueError):
    pass


def normaliser(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url, re.I):
            url = "https://" + url
        else:
            raise ApercuRefuse("adresse non reconnue (http ou https attendu)")
    p = urlsplit(url)
    if p.scheme.lower() not in ("http", "https"):
        raise ApercuRefuse("seuls http et https sont acceptés")
    if p.username or p.password:
        raise ApercuRefuse("une adresse avec identifiants n'est pas acceptée")
    if not p.hostname or len(url) > 2048:
        raise ApercuRefuse("adresse invalide")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def _publique(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if isinstance(a, ipaddress.IPv6Address) and (a.ipv4_mapped or a.sixtofour or a.teredo):
        inner = a.ipv4_mapped or a.sixtofour or (a.teredo[1] if a.teredo else None)
        if inner is None or not _publique(str(inner)):
            return False
    return a.is_global and not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
                                or a.is_unspecified)


def resoudre(hote: str, port: int, *, autoriser_prives: bool = False) -> str:
    """Adresse vérifiée à laquelle se connecter. Toutes les réponses DNS doivent être publiques."""
    try:
        infos = socket.getaddrinfo(hote, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ApercuRefuse(f"hôte introuvable : {hote}") from exc
    adresses = sorted({i[4][0] for i in infos})
    if not adresses:
        raise ApercuRefuse(f"hôte introuvable : {hote}")
    if not autoriser_prives and not all(_publique(a) for a in adresses):
        raise ApercuRefuse("adresse non publique refusée (réseau local, boucle locale ou métadonnées)")
    return adresses[0]


class _HTTPSVers(http.client.HTTPSConnection):
    """HTTPS vers une adresse déjà vérifiée, en présentant le nom d'hôte pour SNI et le certificat."""

    def __init__(self, ip: str, hote: str, port: int, timeout: float):
        super().__init__(ip, port, timeout=timeout, context=ssl.create_default_context())
        self._hote_tls = hote

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._hote_tls)


def recuperer(url: str, *, maximum: int, accepter: tuple[str, ...], autoriser_prives: bool = False
              ) -> tuple[str, str, bytes]:
    """(url finale, type MIME, octets). Lève ApercuRefuse si une règle n'est pas respectée."""
    for _ in range(REDIRECTIONS_MAX + 1):
        p = urlsplit(url)
        port = p.port or (443 if p.scheme == "https" else 80)
        if port not in (80, 443) and not autoriser_prives:
            raise ApercuRefuse("port non standard refusé")
        ip = resoudre(p.hostname, port, autoriser_prives=autoriser_prives)
        conn = (_HTTPSVers(ip, p.hostname, port, DELAI_S) if p.scheme == "https"
                else http.client.HTTPConnection(ip, port, timeout=DELAI_S))
        chemin = (p.path or "/") + (f"?{p.query}" if p.query else "")
        try:
            conn.request("GET", chemin, headers={"Host": p.netloc, "User-Agent": AGENT, "Accept": ", ".join(accepter),
                                                 "Accept-Encoding": "identity"})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                cible = r.getheader("Location") or ""
                url = normaliser(urljoin(url, cible))
                continue
            if r.status != 200:
                raise ApercuRefuse(f"le site répond {r.status}")
            mime = (r.getheader("Content-Type") or "").split(";")[0].strip().lower()
            if not any(mime.startswith(a) for a in accepter):
                raise ApercuRefuse(f"type de contenu inattendu : {mime or 'inconnu'}")
            corps = r.read(maximum + 1)
            if len(corps) > maximum:
                corps = corps[:maximum]  # le HTML utile (balises meta) est en tête ; une image tronquée est rejetée
                if not mime.startswith("text/"):
                    raise ApercuRefuse("ressource trop volumineuse")
            return url, mime, corps
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise ApercuRefuse(f"site injoignable ({type(exc).__name__})") from exc
        finally:
            conn.close()
    raise ApercuRefuse("trop de redirections")


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.icones: list[tuple[str, str]] = []
        self._titre = False
        self.titre = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            cle = (a.get("property") or a.get("name") or "").lower()
            if cle in ("og:title", "og:description", "og:image", "og:site_name", "description", "twitter:title",
                       "twitter:description", "twitter:image") and cle not in self.meta:
                self.meta[cle] = a.get("content", "")[:1000]
        elif tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            self.icones.append((a.get("sizes", ""), a["href"]))
        elif tag == "title":
            self._titre = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._titre = False

    def handle_data(self, data):
        if self._titre and len(self.titre) < 300:
            self.titre += data


def _texte(v: str, n: int) -> str:
    return re.sub(r"\s+", " ", html.unescape(v or "")).strip()[:n]


def apercu(url: str, *, enregistrer_image=None, autoriser_prives: bool = False) -> dict:
    """Aperçu d'une page. `enregistrer_image(chemin_temp, nom) -> asset` range une image récupérée (sinon ignorée).
    Ne lève pas pour une image manquante : un aperçu sans image reste utile ; lève ApercuRefuse pour la page."""
    url = normaliser(url)
    finale, mime, corps = recuperer(url, maximum=HTML_MAX, accepter=("text/html", "application/xhtml+xml"),
                                    autoriser_prives=autoriser_prives)
    parseur = _Meta()
    try:
        parseur.feed(corps.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — HTML hostile ou cassé : on garde ce qui a été lu
        pass
    m = parseur.meta
    hote = urlsplit(finale).hostname or ""
    sortie = {"url": finale, "hote": hote, "titre": _texte(m.get("og:title") or m.get("twitter:title") or parseur.titre, 200),
              "description": _texte(m.get("og:description") or m.get("description") or m.get("twitter:description"), 400),
              "site": _texte(m.get("og:site_name"), 80), "image": None, "favicon": None}
    if enregistrer_image:
        image = m.get("og:image") or m.get("twitter:image")
        icone = sorted(parseur.icones, key=lambda i: -_taille_icone(i[0]))[0][1] if parseur.icones else "/favicon.ico"
        for cle, cible in (("image", image), ("favicon", icone)):
            if not cible:
                continue
            try:
                adresse = normaliser(urljoin(finale, html.unescape(cible)))
                _, mime_img, octets = recuperer(adresse, maximum=IMAGE_MAX, accepter=("image/",),
                                                autoriser_prives=autoriser_prives)
                sortie[cle] = enregistrer_image(octets, f"{cle}-{hote}")
            except (ApercuRefuse, ValueError) as exc:
                sortie[f"{cle}_erreur"] = str(exc)[:120]
    return sortie


def _taille_icone(s: str) -> int:
    m = re.match(r"(\d+)x\d+", s or "")
    return int(m.group(1)) if m else 16


def ecrire_temp(octets: bytes, dossier: Path) -> Path:
    import tempfile
    dossier.mkdir(parents=True, exist_ok=True)
    fd, nom = tempfile.mkstemp(dir=dossier)
    with open(fd, "wb") as fh:
        fh.write(octets)
    return Path(nom)
