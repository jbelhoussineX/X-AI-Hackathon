"""Validate a saved Dust response locally: python -m backend.dust report.json."""

import argparse
import json
from pathlib import Path

from backend.comparison_validation import ContractError
from backend.dust.adapter import validate_dust_report


def main():
    parser = argparse.ArgumentParser(description="Valider une réponse Dust localement, sans appel API.")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        validate_dust_report(report)
    except (OSError, UnicodeError, ValueError) as exc:
        # Avoid printing the body of an untrusted/private report.
        message = str(exc) if isinstance(exc, ContractError) else type(exc).__name__
        parser.exit(1, f"Rapport refusé : {message}\n")
    print(f"Contrat valide : {len(report['documents'])} document(s), {len(report['contacts'])} contact(s).")
    print("La véracité des informations et la lecture des sources ne sont pas certifiées.")


if __name__ == "__main__":
    main()
