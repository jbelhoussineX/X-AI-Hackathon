"""Interface B de Repères citoyens — à lancer avec Streamlit.

Commande : python -m streamlit run interface_b.py --server.address 127.0.0.1
Ce fichier peut fonctionner SEUL en démonstration, sans clé, sans Dust ni Pipelex.
En mode réel, seul `appeler_service_a()` dépend du code de votre équipe.
Les veilles de cette version restent dans la session : pas de SQLite ni de planificateur.
"""
from __future__ import annotations

# 1. IMPORTS ET CONSTANTES : aucun appel réseau ni lecture de .env à l'import.
import copy
import hashlib
import html
import importlib
import ipaddress
import json
import math
from datetime import date, datetime, timezone
from typing import Any, MutableMapping
from urllib.parse import urlsplit
from uuid import uuid4

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None  # Les tests de logique restent exécutables sans installer Streamlit.

NOM_APPLICATION = "Repères citoyens"
SOUS_TITRE = "Des sujets qui vous concernent. Des sources pour comprendre."
MAX_VEILLES = 12
MAX_HISTORIQUE = 10
MAX_APPELS_SESSION = 10  # Frein local, PAS un plafond de facturation du fournisseur.

#Les différentes catégories qu'on veut remonter à l'utilisateur
CATEGORIES = {
    "proposition_de_loi": "Proposition de loi",
    "projet_de_loi": "Projet de loi",
    "declaration": "Déclaration",
    "programme": "Programme",
}

PREUVES = {"contenu": "Contenu", "statut": "Étape de procédure", "relation": "Lien avec le sujet", "contact": "Contact"}


class ErreurInterface(ValueError):
    """Erreur courte et contrôlée, dont le texte peut être affiché sans révéler de clé."""


# 2. STYLE : ne modifier que cette chaîne pour ajuster les couleurs et la typographie.
STYLE = """
<style>
:root { --encre:#173537; --accent:#14766D; --papier:#F7F8F4; --bord:#DCE5DE; }
.stApp { background:var(--papier); color:var(--encre); }
[data-testid="stHeader"] { background:rgba(247,248,244,.94); }
.block-container { max-width:1210px; padding-top:2.4rem; padding-bottom:3rem; }
[data-testid="stSidebar"] { background:#163B3B; }
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stRadio label p,
[data-testid="stSidebar"] .stCheckbox label p { color:#E9F4ED; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#C4D9D0; }
[data-testid="stSidebar"] hr { border-color:#365656; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding:.35rem 0; }
.brand { font-size:25px; line-height:1.12; font-weight:750; color:#FFF; letter-spacing:-.7px; }
.brand em { font-style:normal; color:#AFDBC4; }
.brand-tag { color:#BCD3CB; font-size:11px; letter-spacing:2px; margin:14px 0 28px; }
.eyebrow { font-size:11px; font-weight:750; letter-spacing:2px; color:var(--accent); margin:0 0 12px; }
.hero-title { font-family:Georgia, 'Times New Roman', serif; font-size:clamp(32px,3.5vw,48px);
 line-height:1.1; letter-spacing:-1.5px; font-weight:normal; margin:0 0 16px; color:var(--encre); }
.hero-sub { font-size:15px; line-height:1.6; color:#536867; max-width:780px; margin:0 0 24px; }
.tag { display:inline-block; border:1px solid #C9DCD2; border-radius:20px;
 background:#EBF4ED; padding:5px 11px; font-size:11px; color:#27574A; margin:0 5px 8px 0; }
.tag-warning { border-color:#E5D6B6; background:#FFF7E5; color:#765714; }
.safe-text { color:#365052; line-height:1.65; font-size:14px; overflow-wrap:anywhere; white-space:pre-wrap; }
.safe-small { color:#617472; font-size:12px; line-height:1.55; overflow-wrap:anywhere; white-space:pre-wrap; }
.doc-title { color:var(--encre); font-size:20px; line-height:1.35; font-weight:650; margin:4px 0 12px; overflow-wrap:anywhere; }
.card-title { font-size:16px; font-weight:700; color:var(--encre); margin-bottom:8px; }
.empty { border:1px dashed #B8CFC4; background:#F0F5EF; border-radius:14px; padding:25px; margin:16px 0; }
.empty-title { font-family:Georgia,serif; font-size:24px; color:var(--encre); margin-bottom:7px; }
.meta-box { border-left:3px solid #92B8A4; padding-left:14px; margin:12px 0; }
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:14px; }
[data-testid="stForm"] { background:#FFF; border-color:var(--bord); padding:24px; }
[data-testid="stMetric"] { border:1px solid var(--bord); background:#FFF; padding:17px 20px; border-radius:13px; }
[data-testid="stMetricValue"] { color:var(--encre); }
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea { color:var(--encre); background:#FFF; }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
 background:var(--accent); color:white; border-color:var(--accent); border-radius:9px; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
 background:#FFF; color:var(--encre); border-color:#C9D8CE; border-radius:9px; }
[data-testid="stButton"] button:hover { border-color:var(--accent); }
.footer { color:#697C77; font-size:11px; border-top:1px solid var(--bord); padding-top:17px; margin-top:36px; }
@media (max-width:700px) { .block-container { padding:1.5rem 1rem; } .hero-title { font-size:32px; } }
</style>
"""


# 3. PETITS CONTRÔLES INDÉPENDANTS DU DESSIN DE L'INTERFACE.
def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def texte_sur(value: Any) -> str:
    """Échappe tout contenu provenant de l'utilisateur ou du modèle avant affichage HTML."""
    return html.escape(str(value), quote=True)


def texte(value: str, petit: bool = False) -> None:
    classe = "safe-small" if petit else "safe-text"
    st.markdown(f'<div class="{classe}">{texte_sur(value)}</div>', unsafe_allow_html=True)


def etiquette(value: str, avertissement: bool = False) -> None:
    classe = "tag tag-warning" if avertissement else "tag"
    st.markdown(f'<span class="{classe}">{texte_sur(value)}</span>', unsafe_allow_html=True)


def url_publique(value: Any) -> bool:
    """Contrôle syntaxique, sans téléchargement ni résolution DNS. Ne prouve pas l'authenticité."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        p = urlsplit(value)
        host = (p.hostname or "").rstrip(".").lower()
        if p.scheme != "https" or not host or p.username is not None or p.password is not None:
            return False
        if p.port not in (None, 443) or "%" in host:
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host
    except (ValueError, TypeError):
        return False


def date_iso(value: Any, vide: bool = False) -> str | None:
    if value is None and vide:
        return None
    if not isinstance(value, str):
        raise ErreurInterface("Une date doit être écrite AAAA-MM-JJ, ou rester inconnue.")
    try:
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError
        return value
    except ValueError as exc:
        raise ErreurInterface("Une date reçue n'est pas valide.") from exc


def date_lisible(value: str | None) -> str:
    if not value:
        return "Non renseignée"
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return "Non renseignée"


def instant_lisible(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")
    except (ValueError, AttributeError):
        return "Date non renseignée"


def verifier_requete(sujet: str, debut: str, fin: str) -> dict: #vérifier les erreurs de requêtes 
    sujet = " ".join(sujet.split())
    if not 3 <= len(sujet) <= 300:
        raise ErreurInterface("Écris un sujet de 3 à 300 caractères.")
    date_iso(debut)
    date_iso(fin)
    if debut > fin:
        raise ErreurInterface("La date de début doit précéder la date de fin.")
    return {"topic": sujet, "start": debut, "end": fin}


def _chaine(value: Any, max_length: int = 20000, vide: bool = False) -> str:
    if not isinstance(value, str) or len(value) > max_length or (not vide and not value.strip()):
        raise ErreurInterface("La réponse contient un texte manquant ou trop long.")
    return value


def _liste(value: Any, maximum: int) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise ErreurInterface("La réponse ne respecte pas le format de liste convenu.")
    return value


def _preuves(items: Any) -> list[dict]:
    result = []
    for e in _liste(items, 20):
        if not isinstance(e, dict) or e.get("purpose") not in PREUVES:
            raise ErreurInterface("Un extrait ne précise pas quelle information il justifie.")
        if not url_publique(e.get("url")):
            raise ErreurInterface("Une source contient un lien non autorisé ; le résultat n'est pas affiché.")
        result.append({
            "purpose": e["purpose"], "url": e["url"],
            "excerpt": _chaine(e.get("excerpt"), 5000),
            "location": None if e.get("location") is None else _chaine(e["location"], 1000),
        })
    return result


def verifier_sortie(result: Any, mode_attendu: str) -> dict:
    """Valide la structure puis ne conserve QUE les champs destinés à l'affichage.

    Ne contrôle pas la vérité des affirmations ni la présence des extraits dans les pages.
    Ne conserve pas d'éventuels champs privés, traces internes ou raisonnement du modèle.
    """
    if not isinstance(result, dict) or result.get("mode") != mode_attendu:
        raise ErreurInterface("Mode inattendu : une réponse fictive ne peut pas devenir un résultat réel.")
    r = result.get("report")
    if not isinstance(r, dict) or r.get("schema_version") != "1.0":
        raise ErreurInterface("Le service doit renvoyer le rapport schema_version 1.0 prévu avec A.")
    report = {
        "schema_version": "1.0", "topic": _chaine(r.get("topic"), 2000),
        "scope": _chaine(r.get("scope")), "documents": [], "contacts": [],
        "limitations": [_chaine(x) for x in _liste(r.get("limitations"), 40)],
    }
    ids: set[str] = set()
    for d in _liste(r.get("documents"), 4):
        if not isinstance(d, dict) or d.get("kind") not in CATEGORIES:
            raise ErreurInterface("Catégorie de document absente ou inconnue.")
        ident = _chaine(d.get("id"), 200)
        if ident in ids:
            raise ErreurInterface("Deux documents portent le même identifiant.")
        ids.add(ident)
        evidence = _preuves(d.get("evidence"))
        purposes = {e["purpose"] for e in evidence}
        if "contenu" not in purposes:
            raise ErreurInterface("Un document ne contient pas d'extrait justificatif.")
        stage = None if d.get("stage") is None else _chaine(d["stage"], 2000)
        stage_date = date_iso(d.get("stage_date"), vide=True)
        if stage is not None and "statut" not in purposes:
            raise ErreurInterface("L'étape de procédure annoncée n'a pas de source associée.")
        if stage is None and stage_date is not None:
            raise ErreurInterface("Une date de procédure est fournie sans étape correspondante.")
        report["documents"].append({
            "id": ident, "title": _chaine(d.get("title"), 2000), "kind": d["kind"],
            "publication_date": date_iso(d.get("publication_date"), vide=True),
            "summary": _chaine(d.get("summary")), "stage": stage, "stage_date": stage_date,
            "evidence": evidence, "uncertainties": [_chaine(x) for x in _liste(d.get("uncertainties"), 30)],
        })
    for c in _liste(r.get("contacts"), 3):
        if not isinstance(c, dict):
            raise ErreurInterface("La fiche d'interlocuteur est mal formée.")
        references = [_chaine(x, 200) for x in _liste(c.get("document_ids"), 4)]
        if not references or not set(references).issubset(ids):
            raise ErreurInterface("Un interlocuteur n'est pas relié à un document présent.")
        evidence = _preuves(c.get("evidence"))
        if not any(e["purpose"] == "relation" for e in evidence):
            raise ErreurInterface("Le lien d'un interlocuteur avec le sujet n'est pas sourcé.")
        contact_url = c.get("contact_url")
        if contact_url is not None:
            if not url_publique(contact_url) or not any(
                e["purpose"] == "contact" and e["url"] == contact_url for e in evidence
            ):
                raise ErreurInterface("La page de contact n'est pas accompagnée de sa source.")
        report["contacts"].append({
            "name": _chaine(c.get("name"), 500), "role": _chaine(c.get("role"), 2000),
            "relation": _chaine(c.get("relation")), "document_ids": references,
            "contact_url": contact_url, "evidence": evidence,
        })
    if not report["documents"] and not report["limitations"]:
        raise ErreurInterface("Une recherche vide doit expliquer ses limites.")
    duration = result.get("duration_seconds")
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        duration = None
    return {"mode": mode_attendu, "report": report, "duration_seconds": duration}


# 4. DONNÉES DE DÉMONSTRATION : fixes, fictives, sans personne ni mesure réelle.
def creer_demonstration(requete: dict) -> dict:
    def preuve(purpose: str, excerpt: str, name: str = "document") -> dict:
        return {"purpose": purpose, "url": f"https://example.org/{name}-fictif", "excerpt": excerpt, "location": "Exemple d'interface, sans source réelle"}
    report = {
        "schema_version": "1.0", "topic": requete["topic"],
        "scope": "EXEMPLE FICTIF. Les fiches ci-dessous sont fixes et ne répondent pas réellement au sujet ni à la période saisis.",
        "documents": [
            {
                "id": "FICTIF-001", "title": "Exemple fictif — accès aux équipements publics",
                "kind": "proposition_de_loi", "publication_date": "2026-09-10",
                "summary": "Cette fiche inventée montre où apparaîtra le résumé d'un texte. Elle ne décrit aucune proposition déposée et ne permet de conclure à aucune mesure réelle.",
                "stage": "Étape fictive utilisée pour tester l'affichage", "stage_date": "2026-09-12",
                "evidence": [preuve("contenu", "Extrait inventé pour illustrer la présentation d'un passage source."), preuve("statut", "Étape inventée ; aucune procédure réelle n'est décrite.", "dossier")],
                "uncertainties": ["Données inventées. Les liens sont des exemples non documentaires."],
            },
            {
                "id": "FICTIF-002", "title": "Exemple fictif — information des usagers",
                "kind": "projet_de_loi", "publication_date": "2026-09-06",
                "summary": "Cette seconde fiche illustre un résultat dont l'étape de procédure est inconnue. L'interface conserve cette incertitude au lieu de fabriquer un statut.",
                "stage": None, "stage_date": None,
                "evidence": [preuve("contenu", "Ce passage est fictif et sert uniquement aux tests de l'interface.", "document-2")],
                "uncertainties": ["L'étape de procédure n'est volontairement pas renseignée."],
            },
        ],
        "contacts": [{
            "name": "Organisme de démonstration — fictif", "role": "Interlocuteur fictif",
            "relation": "Cette relation inventée permet de tester l'affichage du lien entre un organisme et un document.",
            "document_ids": ["FICTIF-001"], "contact_url": None,
            "evidence": [preuve("relation", "Relation inventée pour vérifier la présence d'une justification.")],
        }],
        "limitations": [
            "Aucune recherche web ni aucun appel IA n'ont été effectués.",
            "Aucun nom, document ou événement présenté dans ces fiches ne constitue une information politique réelle.",
            "La veille quotidienne et la sauvegarde SQLite ne sont pas connectées dans cette interface.",
        ],
    }
    return {"mode": "demo", "report": report, "duration_seconds": 0.0}


# 5. POINT DE CONNEXION AVEC A : SEULE CETTE FONCTION DÉPEND DE VOTRE DÉPÔT.
def appeler_service_a(requete: dict, mode: str = "pipelex") -> dict:
    """Adaptez l'import avec A si votre dépôt utilise un autre chemin.

    Même signature et même rapport : src.service.search(topic, start, end, mode='pipelex').
    Cette fonction n'essaie pas plusieurs imports et ne relance pas une requête qui échoue.
    """
    try:
        module = importlib.import_module("src.service")
        fonction = getattr(module, "search")
        if not callable(fonction):
            raise AttributeError
    except (ImportError, AttributeError) as exc:
        raise ErreurInterface(
            "Service de A introuvable ou incomplet. Fais confirmer le chemin de la fonction search. "
            "Le mode Démonstration fonctionne sans ce service."
        ) from exc
    try:
        return fonction(requete["topic"], requete["start"], requete["end"], mode=mode)
    except Exception as exc:
        from src.pipelex_client import PipelexError
        from src.contracts import ReportError
        if isinstance(exc, (PipelexError, ReportError)):
            raise ErreurInterface(str(exc)) from None
        # Ne pas afficher str(exc) : une erreur du service pourrait contenir une clé ou un en-tête.
        categorie = type(exc).__name__
        raise ErreurInterface(
            f"Le service de recherche a échoué ({categorie}). Aucun résultat fictif ne le remplace. "
            "Demande à A de contrôler les accès et les journaux expurgés. Avant de relancer, "
            "vérifie l'activité du fournisseur ; un délai local n'annule pas forcément une génération distante."
        ) from None


# 6. ÉTAT DE LA SESSION : temporaire, sans fichier caché ni fausse base persistante.
def initialiser_etat(etat: MutableMapping) -> None:
    defaults = {"b_page": "Recherche", "b_mode": "demo", "b_last": None, "b_history": [],
                "b_watches": [], "b_live_attempts": 0, "b_error": None, "b_consent": False}
    for key, value in defaults.items():
        if key not in etat:
            etat[key] = copy.deepcopy(value)
    if etat["b_mode"] not in ("demo", "pipelex"):
        etat["b_mode"] = "demo"
    if "b_next_page" in etat:
        etat["b_page"] = etat.pop("b_next_page")


def conserver_resultat(etat: MutableMapping, requete: dict, resultat: dict) -> dict:
    item = {"id": uuid4().hex, "request": copy.deepcopy(requete), "completed_at_utc": maintenant(),
            "result": copy.deepcopy(resultat)}
    etat["b_last"] = item
    etat["b_history"] = [item, *etat["b_history"]][:MAX_HISTORIQUE]
    return item


def ajouter_veille(etat: MutableMapping, requete: dict, mode: str) -> tuple[str, bool]:
    requete = verifier_requete(requete["topic"], requete["start"], requete["end"])
    if mode not in ("demo", "pipelex", "dust"):
        raise ErreurInterface("Mode de veille inconnu.")
    identity = json.dumps([requete["topic"].casefold(), requete["start"], requete["end"], mode], ensure_ascii=False)
    ident = hashlib.sha256(identity.encode()).hexdigest()[:16]
    if any(v["id"] == ident for v in etat["b_watches"]):
        return ident, False
    if len(etat["b_watches"]) >= MAX_VEILLES:
        raise ErreurInterface(f"Limite de {MAX_VEILLES} veilles dans cette session. Retire-en une avant d'en ajouter.")
    etat["b_watches"] = [*etat["b_watches"], {
        "id": ident, "request": requete, "mode": mode, "created_at_utc": maintenant(),
        "last_success_utc": None, "last_error": None,
    }]
    return ident, True


def retirer_veille(etat: MutableMapping, ident: str) -> None:
    etat["b_watches"] = [v for v in etat["b_watches"] if v["id"] != ident]


def lancer_recherche(requete: dict, mode: str) -> bool:
    """Appel uniquement après clic explicite ; aucun appel lors d'une simple navigation."""
    etat = st.session_state
    etat["b_error"] = None
    etat["b_last"] = None  # Un résultat précédent ne doit pas masquer l'échec du nouvel essai.
    try:
        if mode in ("pipelex", "dust"):
            if not etat.get("b_consent", False):
                raise ErreurInterface("Confirme dans le menu l'utilisation de l'accès partenaire avant la recherche réelle.")
            if etat["b_live_attempts"] >= MAX_APPELS_SESSION:
                raise ErreurInterface("Limite de dix essais réels dans cette session. Vérifiez les crédits avant de poursuivre.")
            etat["b_live_attempts"] += 1
            with st.spinner("Recherche en cours. Cette attente n'est pas un journal des actions de l'agent."):
                raw = appeler_service_a(requete, mode)
        else:
            raw = creer_demonstration(requete)
        result = verifier_sortie(raw, mode)
        if mode in ("pipelex", "dust"):
            for d in result["report"]["documents"]:
                publication = d["publication_date"]
                if publication and not requete["start"] <= publication <= requete["end"]:
                    raise ErreurInterface("Un document daté est hors de la période de publication demandée. A doit contrôler le filtrage.")
                if publication is None:
                    d["uncertainties"].append("Date de publication inconnue : appartenance à la période non confirmée.")
        conserver_resultat(etat, requete, result)
        return True
    except ErreurInterface as exc:
        etat["b_error"] = str(exc)
    except Exception:
        etat["b_error"] = "Erreur inattendue dans l'interface. Aucun ancien résultat ni exemple fictif n'est présenté comme une réussite."
    return False


# 7. COMPOSANTS VISUELS RÉUTILISABLES.
def titre_page(surtitre: str, titre: str, description: str) -> None:
    st.markdown(f'<div class="eyebrow">{texte_sur(surtitre)}</div><h1 class="hero-title">{texte_sur(titre)}</h1>'
                f'<p class="hero-sub">{texte_sur(description)}</p>', unsafe_allow_html=True)


def vide(titre: str, description: str) -> None:
    st.markdown(f'<div class="empty"><div class="empty-title">{texte_sur(titre)}</div>'
                f'<div class="safe-text">{texte_sur(description)}</div></div>', unsafe_allow_html=True)


def afficher_preuves(preuves: list[dict], fictif: bool) -> None: 
    for i, e in enumerate(preuves, start=1):
        etiquette(f"{i:02d} · {PREUVES[e['purpose']]}")
        texte(e["excerpt"])
        if e["location"]:
            texte(e["location"], petit=True)
        if fictif:
            texte("Lien fictif, non ouvert : " + e["url"], petit=True)
        elif url_publique(e["url"]):
            st.link_button(f"Ouvrir la source {i} · {urlsplit(e['url']).hostname}", e["url"])
        st.divider()


def afficher_document(d: dict, fictif: bool) -> None:
    with st.container(border=True):
        etiquette(("FICTIF · " if fictif else "") + CATEGORIES[d["kind"]], fictif)
        st.markdown(f'<div class="doc-title">{texte_sur(d["title"])}</div>', unsafe_allow_html=True)
        texte("Publication : " + date_lisible(d["publication_date"]), petit=True)
        texte(d["summary"])
        st.markdown('<div class="meta-box"><div class="safe-small">ÉTAPE RAPPORTÉE DANS LE RÉSULTAT</div>'
                    f'<div class="safe-text">{texte_sur(d["stage"] or "Non confirmée")}</div></div>', unsafe_allow_html=True)
        if d["stage_date"]:
            texte("Date de l'étape : " + date_lisible(d["stage_date"]), petit=True)
        with st.expander(f"Sources et extraits · {len(d['evidence'])}"):
            st.caption("Extraits reçus : leur fidélité aux pages reste à vérifier.")
            afficher_preuves(d["evidence"], fictif)
        for point in d["uncertainties"]:
            texte("À noter : " + point, petit=True)


def afficher_contact(c: dict, fictif: bool) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="card-title">{texte_sur(c["name"])}</div>', unsafe_allow_html=True)
        texte(c["role"], petit=True)
        texte(c["relation"])
        texte("Documents associés : " + ", ".join(c["document_ids"]), petit=True)
        if fictif:
            etiquette("INTERLOCUTEUR FICTIF", True)
        elif c["contact_url"]:
            st.link_button("Ouvrir la page de contact publique", c["contact_url"])
        else:
            st.caption("Aucune page de contact confirmée. Aucune adresse n'est déduite du nom.")
        with st.expander("Voir les sources de cette relation"):
            afficher_preuves(c["evidence"], fictif)


def afficher_resultat(item: dict, prefixe: str = "current") -> None:
    result, requete = item["result"], item["request"]
    r = result["report"]
    fictif = result["mode"] == "demo"
    st.divider()
    st.subheader("Résultats de la dernière recherche" if prefixe == "current" else "Résultats enregistrés dans la session")
    texte(requete["topic"])
    texte(f"Du {date_lisible(requete['start'])} au {date_lisible(requete['end'])} · France", petit=True)
    if fictif:
        st.warning("DÉMONSTRATION FICTIVE : ces fiches fixes ne sont pas des résultats de recherche. Aucun appel IA.")
    else:
        st.info("Réponse reçue du service de l'équipe. Les contrôles de structure ne prouvent pas l'exactitude des sources.")
    texte("Exécution terminée le " + instant_lisible(item["completed_at_utc"]) + ". Ce n'est pas une date de vérification indépendante des sources.", petit=True)
    if result["duration_seconds"] is not None and not fictif:
        texte(f"Durée rapportée par le service : {result['duration_seconds']:.1f} s.", petit=True)
    texte(r["scope"])
    sources = {e["url"] for d in r["documents"] for e in d["evidence"]}
    sources.update(e["url"] for c in r["contacts"] for e in c["evidence"])
    a, b, c = st.columns(3)
    a.metric("Documents reçus", len(r["documents"]))
    b.metric("Interlocuteurs", len(r["contacts"]))
    c.metric("Liens cités", len(sources))
    documents, contacts, limites = st.tabs(["Documents", "Interlocuteurs", "Périmètre et limites"])
    with documents:
        # Filtre local : ne lance aucune nouvelle recherche.
        options = ["Toutes les catégories", *dict.fromkeys(CATEGORIES[d["kind"]] for d in r["documents"])]
        categorie = st.selectbox("Filtrer les fiches déjà reçues", options, key=f"{prefixe}_filter_{item['id']}")
        liste = sorted(r["documents"], key=lambda d: d["publication_date"] or "", reverse=True)
        for d in liste:
            if categorie == "Toutes les catégories" or CATEGORIES[d["kind"]] == categorie:
                afficher_document(d, fictif)
        if not liste:
            vide("Aucun document retrouvé", "Cela ne prouve pas l'absence de texte ou de position sur le sujet. Consulte le périmètre et les limites.")
    with contacts:
        for contact in sorted(r["contacts"], key=lambda c: c["name"].casefold()):
            afficher_contact(contact, fictif)
        if not r["contacts"]:
            vide("Aucun interlocuteur documenté", "Le résultat ne contient pas de relation suffisamment étayée à afficher.")
    with limites:
        for point in r["limitations"]:
            texte("• " + point)
        st.caption("Tri descriptif : documents par date ; interlocuteurs par ordre alphabétique. Aucun classement politique.")
    left, right = st.columns(2)
    with left:
        if st.button("Conserver cette recherche dans Mes veilles", key=f"save_{prefixe}_{item['id']}", width="stretch"):
            try:
                _, cree = ajouter_veille(st.session_state, requete, result["mode"])
                st.success("Veille ajoutée pour cette session uniquement." if cree else "Cette veille existe déjà dans la session.")
            except ErreurInterface as exc:
                st.error(str(exc))
    with right:
        contenu = json.dumps(item, ensure_ascii=False, indent=2, allow_nan=False)
        st.download_button("Exporter ce résultat en JSON", contenu, file_name="resultat_fictif.json" if fictif else "recherche_citoyenne.json",
                           mime="application/json", key=f"export_{prefixe}_{item['id']}", width="stretch", on_click="ignore")


# 8. ÉCRAN RECHERCHE : formulaire, résultat et petit historique temporaire.
def page_recherche(mode: str) -> None:
    titre_page("RECHERCHE DOCUMENTAIRE / FRANCE", "Un sujet. Des documents. Des repères.", SOUS_TITRE)
    if mode == "demo":
        st.warning("Mode démonstration : des données fictives pour construire l'interface sans crédits ni clé API.")
    else:
        st.info("Recherche réelle via Pipelex et OpenAI : 3 à 4 appels de modèle, avec recherche web. Les crédits API sont utilisés uniquement après ton clic.")
    with st.form("b_search_form"):
        st.subheader("Quel sujet souhaites-tu explorer ?")
        sujet = st.text_input("Sujet de recherche", max_chars=300, placeholder="Ex. : accessibilité des transports publics", key="b_topic")
        a, b, c = st.columns([1, 1, 1])
        debut = a.date_input("Publié à partir du", value=date(2024, 1, 1), key="b_start")
        fin = b.date_input("Publié jusqu'au", value=date.today(), key="b_end")
        c.text_input("Territoire", value="France", disabled=True)
        st.caption("Première version : textes parlementaires. La période filtre la publication, pas la dernière étape de procédure. Ne saisis pas de données personnelles.")
        submit = st.form_submit_button("Afficher l'exemple fictif" if mode == "demo" else "Rechercher les documents", type="primary", width="stretch")
    if submit:
        try:
            requete = verifier_requete(sujet, debut.isoformat(), fin.isoformat())
            lancer_recherche(requete, mode)
        except ErreurInterface as exc:
            st.session_state["b_last"] = None
            st.session_state["b_error"] = str(exc)
    if st.session_state["b_error"]:
        st.error(st.session_state["b_error"])
    item = st.session_state["b_last"]
    if item and item["result"]["mode"] == mode:
        afficher_resultat(item)
    else:
        vide("Tout commence par un sujet précis.", "Saisis quelques mots et une période. Les résultats apparaîtront ici après ton clic. Le mode démonstration permet de tester sans connecter le service de A.")
    historique = [x for x in st.session_state["b_history"] if x["result"]["mode"] == mode]
    if historique:
        with st.expander(f"Historique de cette session · {len(historique)}"):
            st.caption("Aucune sauvegarde en base. Ouvrir un ancien résultat ne relance pas l'agent.")
            for entry in historique:
                texte(entry["request"]["topic"] + " — " + instant_lisible(entry["completed_at_utc"]), petit=True)
                if st.button("Réafficher ce résultat", key="history_" + entry["id"]):
                    st.session_state["b_last"] = copy.deepcopy(entry)
                    st.session_state["b_error"] = None
                    st.rerun()


# 9. ÉCRAN MES VEILLES : interface fonctionnelle en session, sans simulation de planification.
def page_veilles(mode: str) -> None:
    titre_page("SUIVI PERSONNEL / SESSION LOCALE", "Garder ses sujets à portée de main.",
               "Conserve une recherche et relance-la manuellement. La base persistante et la veille quotidienne seront connectées par A et C.")
    st.warning("SESSION UNIQUEMENT : ces veilles peuvent être perdues si la session est réinitialisée. Ce n'est pas encore une base SQLite ni un compte utilisateur.")
    with st.expander("Créer une veille dans cette session"):
        with st.form("b_watch_form"):
            sujet = st.text_input("Sujet à suivre", max_chars=300, key="b_watch_topic")
            a, b = st.columns(2)
            debut = a.date_input("Début de la période de publication", value=date(2024, 1, 1), key="b_watch_start")
            fin = b.date_input("Fin de la période de publication", value=date.today(), key="b_watch_end")
            st.caption("Cette période reste fixe lors d'une actualisation manuelle. Le suivi jusqu'à la date du jour sera à définir avec A.")
            submit = st.form_submit_button("Ajouter une veille de session", type="primary")
        if submit:
            try:
                query = verifier_requete(sujet, debut.isoformat(), fin.isoformat())
                _, cree = ajouter_veille(st.session_state, query, mode)
                st.success("Veille de session ajoutée." if cree else "Cette veille est déjà présente.")
            except ErreurInterface as exc:
                st.error(str(exc))
    liste = [v for v in st.session_state["b_watches"] if v["mode"] == mode]
    if not liste:
        vide("Aucune veille pour ce mode", "Crée une veille ci-dessus ou conserve une recherche depuis l'écran Recherche. Les veilles fictives restent séparées des recherches réelles.")
    for v in liste:
        q = v["request"]
        with st.container(border=True):
            etiquette("DÉMO FICTIVE" if mode == "demo" else "ACTUALISATION MANUELLE", mode == "demo")
            st.markdown(f'<div class="doc-title">{texte_sur(q["topic"])}</div>', unsafe_allow_html=True)
            texte(f"France · publication du {date_lisible(q['start'])} au {date_lisible(q['end'])}", petit=True)
            texte("Dernière exécution réussie : " + (instant_lisible(v["last_success_utc"]) if v["last_success_utc"] else "Pas encore exécutée"), petit=True)
            if v["last_error"]:
                st.warning("La dernière tentative a échoué. L'ancienne date de réussite est conservée.")
            st.checkbox("Actualisation quotidienne — non connectée", value=False, disabled=True, key="daily_" + v["id"])
            st.caption("Aucun déclenchement programmé. Cette interface ne mesure pas encore les différences entre deux recherches.")
            a, b = st.columns([2, 1])
            if a.button("Relancer l'exemple fictif" if mode == "demo" else "Actualiser manuellement", key="refresh_" + v["id"], width="stretch"):
                ok = lancer_recherche(q, mode)
                v["last_error"] = None if ok else st.session_state["b_error"]
                if ok:
                    v["last_success_utc"] = st.session_state["b_last"]["completed_at_utc"]
                    st.session_state["b_next_page"] = "Recherche"
                    st.rerun()
                else:
                    st.error(st.session_state["b_error"])
            with b:
                with st.expander("Retirer cette veille"):
                    st.caption("Retire le sujet de cette session. L'historique reste disponible jusqu'à son effacement.")
                    if st.button("Confirmer le retrait", key="delete_" + v["id"]):
                        retirer_veille(st.session_state, v["id"])
                        st.rerun()
    if liste:
        export = {"format": "interface-b-watches-v1", "storage": "session_only", "exported_at_utc": maintenant(), "watches": liste}
        st.download_button("Exporter les paramètres de ces veilles", json.dumps(export, ensure_ascii=False, indent=2),
                           file_name="parametres_veilles_session.json", mime="application/json", on_click="ignore")
        st.caption("Export de secours des paramètres uniquement. L'import et la synchronisation en base ne sont pas implémentés.")


# 10. AIDE : limites affichées dans le produit, pas seulement dans le README.
def page_aide() -> None:
    titre_page("MODE D'EMPLOI", "Comprendre la recherche et ses limites.", "Des résultats sourcés à relire, sans recommandation politique.")
    with st.container(border=True):
        st.subheader("Déjà disponible")
        st.write("Formulaire, recherche Pipelex/OpenAI, résultats, extraits, contacts, filtres locaux, export JSON, historique et veilles de session.")
        st.subheader("À connecter avec A et C")
        st.write("Sauvegarde SQLite, comparaison entre actualisations et déclenchement quotidien.")
        st.caption("Une recherche consulte des sources officielles, évalue les informations manquantes et peut faire un seul complément avant de produire le rapport.")
    with st.expander("Comprendre les sources et les dates"):
        st.write("Une source citée n'est pas automatiquement une source vérifiée. L'étape de procédure, le résumé et le contact peuvent avoir des preuves différentes.")
        st.write("La date d'exécution indique quand la requête s'est terminée. Elle ne prouve pas que chaque page a été revérifiée indépendamment.")
    with st.expander("Données et confidentialité"):
        st.write("L'historique et les veilles restent dans cette session. En mode réel, le sujet et les sources sont transmis à OpenAI. Pipelex tourne sur cet ordinateur. Aucun profil politique n'est construit.")
        st.write("Les exports restent sous ton contrôle. Ne saisis pas d'informations sensibles. Aucune clé API ne doit être saisie dans cette interface.")
    with st.expander("Effacer les données de cette session"):
        st.write("Cela efface l'historique, les résultats et les veilles ici, pas les conversations chez un fournisseur ni les fichiers exportés.")
        if st.button("Confirmer l'effacement de la session", key="b_clear_session"):
            st.session_state["b_last"] = None
            st.session_state["b_history"] = []
            st.session_state["b_watches"] = []
            st.session_state["b_error"] = None
            # Ne pas réinitialiser le compteur d'appels ni le consentement pour contourner le frein.
            st.success("Résultats, historique et veilles de session effacés.")


# 11. POINT D'ENTRÉE : l'écran choisi, jamais une recherche automatique.
def main() -> None:
    if st is None:
        raise SystemExit("Streamlit manque. Installe requirements-ui.txt, puis lance : python -m streamlit run interface_b.py")
    st.set_page_config(page_title=NOM_APPLICATION, page_icon="📑", layout="wide", initial_sidebar_state="expanded")
    st.markdown(STYLE, unsafe_allow_html=True)
    initialiser_etat(st.session_state)
    with st.sidebar:
        st.markdown('<div class="brand">repères<br><em>citoyens.</em></div><div class="brand-tag">CHERCHER · COMPRENDRE · SUIVRE</div>', unsafe_allow_html=True)
        st.radio("Navigation", ["Recherche", "Mes veilles", "Aide"], key="b_page")
        st.divider()
        st.radio("Source des résultats", ["demo", "pipelex"], key="b_mode",
                 format_func=lambda x: "Démonstration · sans IA" if x == "demo" else "Recherche réelle · Pipelex + OpenAI")
        mode = st.session_state["b_mode"]
        if mode == "pipelex":
            st.checkbox("J'autorise cette recherche à utiliser les crédits API OpenAI lors de mon clic.", key="b_consent")
            st.caption(f"Essais réels dans cette session : {st.session_state['b_live_attempts']}/{MAX_APPELS_SESSION}. Ce compteur n'est pas un plafond fournisseur.")
        else:
            st.caption("Aucune clé nécessaire. Toutes les fiches d'exemple sont inventées.")
        st.divider()
        st.caption("Interface B · prototype local\n\nBase et actualisation quotidienne : à connecter.")
    # Un message d'erreur ou résultat de l'autre mode ne doit pas sembler appartenir au mode actuel.
    if st.session_state.get("b_previous_mode", mode) != mode:
        st.session_state["b_error"] = None
    st.session_state["b_previous_mode"] = mode
    page = st.session_state["b_page"]
    if page == "Recherche":
        page_recherche(mode)
    elif page == "Mes veilles":
        page_veilles(mode)
    else:
        page_aide()
    st.markdown('<div class="footer">REPÈRES CITOYENS · Prototype de hackathon · Informations sourcées, sans recommandation politique · Pas de veille automatique dans cette version.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
