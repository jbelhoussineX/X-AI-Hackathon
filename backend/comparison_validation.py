"""Validate the comparison contract without network calls or inference.

These checks establish structure and source provenance, not semantic truth.
Raise ContractError before any result is displayed as verified or persisted.
"""

from datetime import datetime
from urllib.parse import urlsplit


class ContractError(ValueError):
    """An input or model output violates the comparison contract."""


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def _fields(value, required, optional=()):
    _require(isinstance(value, dict), "Objet JSON attendu")
    _require(set(required) <= value.keys(), "Champs obligatoires manquants")
    _require(value.keys() <= set(required) | set(optional), "Champs inconnus")


def _text(value):
    _require(isinstance(value, str) and bool(value.strip()), "Texte non vide attendu")


def _snapshot(value):
    _fields(value, ("source_url", "retrieved_at", "retrieval_status", "scope", "text"))
    _text(value["source_url"])
    try:
        url = urlsplit(value["source_url"])
        _require(url.scheme in ("http", "https") and bool(url.hostname), "URL HTTP(S) requise")
        _require(url.username is None and url.password is None, "Identifiants interdits dans une URL")
    except ValueError as exc:
        raise ContractError("URL invalide") from exc
    _text(value["retrieved_at"])
    try:
        date = datetime.fromisoformat(value["retrieved_at"].replace("Z", "+00:00"))
        _require(date.tzinfo is not None, "Fuseau horaire requis")
    except ValueError as exc:
        raise ContractError("Date ISO 8601 avec fuseau requise") from exc
    _require(value["retrieval_status"] in ("ok", "partial", "unavailable"), "Statut de collecte invalide")
    _require(value["scope"] in ("full_document", "excerpts"), "Périmètre invalide")
    _require(isinstance(value["text"], str), "Contenu texte attendu")
    if value["retrieval_status"] == "unavailable":
        _require(not value["text"].strip(), "Source indisponible : contenu actuel vide attendu")


def validate_request(request):
    """Validate a bare ComparisonRequest (inside the Pipelex 'request' slot)."""
    _fields(request, ("document_id", "watch_topic", "current"), ("previous",))
    _text(request["document_id"])
    _text(request["watch_topic"])
    _snapshot(request["current"])
    if request.get("previous") is not None:
        _snapshot(request["previous"])
    return request


def _usable(snapshot):
    return snapshot is not None and snapshot["retrieval_status"] == "ok" and bool(snapshot["text"].strip())


def _evidence(items, request):
    _require(isinstance(items, list), "Liste de preuves attendue")
    versions = set()
    for evidence in items:
        _fields(evidence, ("version", "source_url", "retrieved_at", "quote"))
        version = evidence["version"]
        _require(version in ("previous", "current"), "Version de preuve invalide")
        snapshot = request.get(version)
        _require(_usable(snapshot), "Preuve sans version source exploitable")
        _text(evidence["quote"])
        _require(evidence["quote"] in snapshot["text"], "Citation absente du texte source")
        _require(evidence["source_url"] == snapshot["source_url"], "URL de preuve incorrecte")
        _require(evidence["retrieved_at"] == snapshot["retrieved_at"], "Date de preuve incorrecte")
        versions.add(version)
    return versions


def validate_report(request, report):
    """Reject invalid model outputs. Returns the report unchanged on success.

    Quotes can be authentic yet irrelevant: factual correctness still requires
    semantic assessment against the input, including in the evaluation cases.
    """
    validate_request(request)
    _fields(report, ("document_id", "change_type", "description", "changes", "evidence", "limitations"))
    _require(report["document_id"] == request["document_id"], "Identifiant différent de la demande")
    kind = report["change_type"]
    _require(kind in ("new_document", "modified", "unchanged", "unconfirmed"), "Type de changement invalide")
    _text(report["description"])
    _require(isinstance(report["changes"], list), "Liste de changements attendue")
    _require(isinstance(report["limitations"], list), "Liste de limites attendue")
    for limitation in report["limitations"]:
        _text(limitation)
    versions = _evidence(report["evidence"], request)
    previous, current = request.get("previous"), request["current"]

    if not _usable(current) or (previous is not None and not _usable(previous)):
        _require(kind == "unconfirmed", "Collecte inexploitable : unconfirmed obligatoire")

    if kind == "unconfirmed":
        _require(not report["changes"] and not report["evidence"], "unconfirmed ne doit pas affirmer de changements ni de preuves")
        _require(bool(report["limitations"]), "Motif de non-confirmation requis")
    elif kind == "new_document":
        _require(previous is None, "Document déjà connu")
        _require(not report["changes"] and versions == {"current"}, "Nouveau document : preuve actuelle requise, sans comparaison")
    else:
        _require(_usable(previous), "Ancienne version exploitable requise")
        _require(versions == {"previous", "current"}, "Preuves des deux versions requises")
        if kind == "modified":
            _require(bool(report["changes"]), "Au moins une différence requise")
            _require(previous["text"] != current["text"], "Textes identiques : modification impossible")
            for change in report["changes"]:
                _fields(change, ("description", "evidence"))
                _text(change["description"])
                _require(_evidence(change["evidence"], request) == {"previous", "current"}, "Chaque différence requiert les deux versions")
        else:
            _require(not report["changes"], "unchanged ne doit pas contenir de différence")
            _require(previous["scope"] == current["scope"] == "full_document", "Des extraits ne prouvent pas un document inchangé")

    if kind != "unconfirmed" and any(s and s["scope"] == "excerpts" for s in (previous, current)):
        _require(bool(report["limitations"]), "La portée limitée aux extraits doit être signalée")
    return report
