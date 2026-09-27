"""Provider-independent report contract; no network or database writes."""

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from backend.comparison_validation import ContractError

SCHEMA_PATH = Path(__file__).with_name("report_schema.json")


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


def validate_report(report):
    """Check schema, dates, identifiers, references and minimum evidence.

    Does not assert that the model really opened the cited pages or that its summary
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
