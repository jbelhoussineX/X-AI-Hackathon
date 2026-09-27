"""Diagnostic. --list-agents ne lance aucune génération LLM. --check en lance une."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.contracts import ReportError
from src.dust_client import DustError, Settings, list_agents, run_dust

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--list-agents', action='store_true')
group.add_argument('--check', action='store_true')
args = parser.parse_args()
try:
    if args.list_agents:
        for agent in list_agents(Settings.load(require_agent=False)):
            print(f"{agent['name']}\t{agent['id']}")
    else:
        report, cid = run_dust('TEST_TECHNIQUE_SANS_WEB. Ne lance aucun outil. Retourne le JSON du contrat : schema_version=1.0, topic=Test technique, scope=Aucune recherche, documents=[], contacts=[], limitations=[Test technique sans recherche documentaire].')
        print('Connexion et format JSON validés. La recherche web et la justesse factuelle restent à tester.')
        if cid:
            print('Identifiant de conversation :', cid)
except (DustError, ReportError) as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
