"""Pure functions: no Dust/Pipelex calls, fetching or database writes."""

import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from backend.comparison_validation import ContractError, validate_request

SCHEMA_PATH = Path(__file__).with_name("structured_response_format.json")


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def _check_schema(value, schema, path="$report"):
    """Validate only the keywords used by the committed schema; fail closed.

    This is not a general JSON Schema engine. New keywords require an explicit
    implementation or replacement with a full JSON Schema validator.
    """
    allowed = {"type", "enum", "properties", "required", "additionalProperties", "items"}
    _require(not (schema.keys() - allowed), "Mot-clé de schéma non pris en charge")
    types = schema["type"]
    types = [types] if isinstance(types, str) else types
    checks = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
              "string": lambda x: isinstance(x, str), "null": lambda x: x is None}
    _require(all(t in checks for t in types), "Type de schéma non pris en charge")
    _require(any(checks[t](value) for t in types), f"{path} : type invalide")
    if "enum" in schema:
        _require(value in schema["enum"], f"{path} : valeur non autorisée")
    if isinstance(value, dict):
        fields = schema["properties"]
        _require(set(schema["required"]) <= value.keys(), f"{path} : champs manquants")
        _require(schema["additionalProperties"] is False, "Schéma fermé attendu")
        _require(value.keys() <= fields.keys(), f"{path} : champs inconnus")
        for name, item in value.items():
            _check_schema(item, fields[name], f"{path}.{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_schema(item, schema["items"], f"{path}[{index}]")


def _url(value):
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    _require(bool(valid), "URL HTTP(S) sans identifiants requise")


def _date(value):
    if value is None:
        return
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, "Date YYYY-MM-DD requise")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("Date de calendrier invalide") from exc


def validate_dust_report(report):
    """Check schema, dates, identifiers, references and minimum evidence.

    Does not assert that Dust really opened the cited pages or that its summary
    is true. An empty report (including the technical diagnostic) is permitted.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))["json_schema"]["schema"]
    _check_schema(report, schema)
    _require(bool(report["topic"].strip()) and bool(report["scope"].strip()), "Sujet et périmètre requis")
    ids = [doc["id"] for doc in report["documents"]]
    _require(all(item.strip() for item in ids) and len(set(ids)) == len(ids), "Identifiants documentaires vides ou dupliqués")
    for doc in report["documents"]:
        _require(bool(doc["title"].strip()), "Titre vide")
        _date(doc["publication_date"])
        _date(doc["stage_date"])
        _require(any(e["purpose"] == "contenu" for e in doc["evidence"]), "Document sans preuve de contenu")
    for contact in report["contacts"]:
        refs = contact["document_ids"]
        _require(bool(refs) and set(refs) <= set(ids) and len(refs) == len(set(refs)), "Références de contact invalides")
        _require(any(e["purpose"] == "relation" for e in contact["evidence"]), "Relation du contact non étayée")
        if contact["contact_url"] is not None:
            _url(contact["contact_url"])
            _require(any(e["purpose"] == "contact" and e["url"] == contact["contact_url"] for e in contact["evidence"]), "URL de contact non étayée")
    for entity in report["documents"] + report["contacts"]:
        for evidence in entity["evidence"]:
            _url(evidence["url"])
            _require(bool(evidence["excerpt"].strip()), "Extrait vide")
    return report


def prepare_comparison(report, *, dust_document_id, stable_document_id,
                       current_snapshot, previous_snapshot=None, document_is_new=False):
    """Prepare a single source comparison from externally retrieved content.

    The application supplies stable identity and actual retrieval metadata.
    Never derive retrieval success or timestamps from an LLM response.
    Previous/current must refer to the same URL. A known document without a
    comparable previous source is rejected rather than labelled new_document.
    Only evidence from the selected URL is used; other URLs remain in context.
    """
    validate_dust_report(report)
    matches = [doc for doc in report["documents"] if doc["id"] == dust_document_id]
    _require(len(matches) == 1, "Document Dust introuvable")
    _require(type(document_is_new) is bool, "document_is_new doit être booléen")
    _require(document_is_new == (previous_snapshot is None), "État antérieur requis pour un document connu")
    request = {"document_id": stable_document_id, "watch_topic": report["topic"],
               "current": deepcopy(current_snapshot)}
    if previous_snapshot is not None:
        request["previous"] = deepcopy(previous_snapshot)
    validate_request(request)
    if previous_snapshot is not None:
        _require(previous_snapshot["source_url"] == current_snapshot["source_url"], "Versions de sources différentes : comparaison manuelle requise")
    doc = matches[0]
    evidence = [deepcopy(e) for e in doc["evidence"] if e["url"] == current_snapshot["source_url"]]
    _require(bool(evidence), "Aucune preuve Dust pour cette URL")
    if current_snapshot["retrieval_status"] == "ok":
        _require(all(e["excerpt"] in current_snapshot["text"] for e in evidence), "Citation Dust absente de la source récupérée")
    # Keep generated summaries and contact metadata out of source text.
    return {
        "request": request,
        "context": {
            "dust_document": deepcopy(doc),
            "matched_evidence": evidence,
            "contacts": deepcopy([c for c in report["contacts"] if dust_document_id in c["document_ids"]]),
            "report_scope": report["scope"],
            "limitations": deepcopy(report["limitations"]),
        },
    }
