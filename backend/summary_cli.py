"""Validate a Dust export offline, or explicitly synthesize it with Pipelex."""
import argparse
import json
from pathlib import Path
from time import monotonic

from backend.summary_service import prepare_summary, synthesize_report
from backend.pipelex_summary import analyze_summary
from backend.source_verification import verify_sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='Rapport citoyen_report JSON brut de Dust')
    parser.add_argument('--topic', required=True, help='Sujet choisi par l’utilisateur')
    parser.add_argument('--run', action='store_true', help='Exécuter réellement Pipelex (consomme des crédits)')
    parser.add_argument('--output', type=Path, help='Nouveau fichier JSON de sortie, nécessaire avec --run')
    args = parser.parse_args(argv)
    if args.run and args.output is None:
        parser.error('--output est requis avec --run')
    if not args.run and args.output is not None:
        parser.error('--output ne sert que pour une exécution --run')
    try:
        if args.output is not None and (args.output.exists() or not args.output.parent.is_dir()):
            raise ValueError('Choisir un nouveau fichier dans un dossier existant.')
        report = json.loads(args.report.read_text(encoding='utf-8-sig'))
        prepare_summary(args.topic, report)
        if not args.run:
            print(f"Rapport valide : {len(report['documents'])} document(s). Aucun appel Pipelex effectué.")
            return 0
        started = monotonic()
        verification = verify_sources(report)
        if report['documents'] and not verification.all_matched:
            print('Sources non confirmées : aucun appel Pipelex effectué.')
            return 1
        report = verification.report
        result = synthesize_report(args.topic, report, analyze_summary)
        envelope = {'mode': 'dust', 'report': result, 'duration_seconds': monotonic() - started}
        # This is a service result, not a fabricated UI execution history.
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(envelope, stream, ensure_ascii=False, indent=2)
        print(f'Synthèse enregistrée : {args.output}')
        return 0
    except Exception as exc:
        # Do not print HTTP errors/headers or source content; a timeout may still be running remotely.
        print(f'Échec ({type(exc).__name__}). Aucun succès de substitution. '
              'Si un appel a commencé, vérifier son état avant de le relancer.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
