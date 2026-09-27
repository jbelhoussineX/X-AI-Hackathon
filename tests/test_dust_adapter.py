import json
import unittest
from copy import deepcopy
from pathlib import Path

from backend.comparison_validation import ContractError
from backend.dust.adapter import prepare_comparison, validate_dust_report


def fixture():
    report = json.loads((Path(__file__).parent / "fixtures/dust/report.json").read_text(encoding="utf-8"))
    snapshot = {"source_url": "https://example.org/fictif/texte", "retrieved_at": "2026-09-27T10:00:00Z",
                "retrieval_status": "ok", "scope": "excerpts", "text": "La consultation se termine le 20 octobre 2026."}
    return report, snapshot


def prepare(report, snapshot, **kwargs):
    return prepare_comparison(report, dust_document_id="dust-doc-1", stable_document_id="app-doc-001",
                              current_snapshot=snapshot, **kwargs)


class DustAdapterTests(unittest.TestCase):
    def test_valid_report(self):
        report, _ = fixture()
        self.assertEqual(validate_dust_report(report), report)

    def test_diagnostic_is_accepted_but_not_a_document(self):
        report = {"schema_version": "1.0", "topic": "Test technique", "scope": "Aucune recherche",
                  "documents": [], "contacts": [], "limitations": ["Test technique sans recherche documentaire"]}
        validate_dust_report(report)
        _, snapshot = fixture()
        with self.assertRaises(ContractError):
            prepare(report, snapshot, document_is_new=True)

    def test_schema_rejects_missing_extra_and_wrong_types(self):
        for mode in ("missing", "extra", "null", "version"):
            report, _ = fixture()
            if mode == "missing":
                del report["scope"]
            elif mode == "extra":
                report["surprise"] = True
            elif mode == "null":
                report["documents"] = None
            else:
                report["schema_version"] = "2.0"
            with self.assertRaises(ContractError):
                validate_dust_report(report)

    def test_duplicate_ids_rejected(self):
        report, _ = fixture()
        report["documents"].append(deepcopy(report["documents"][0]))
        with self.assertRaises(ContractError):
            validate_dust_report(report)

    def test_bad_date_and_no_content_evidence_rejected(self):
        for value in ("2026-02-30", "27/09/2026"):
            report, _ = fixture()
            report["documents"][0]["publication_date"] = value
            with self.assertRaises(ContractError):
                validate_dust_report(report)
        report, _ = fixture()
        report["documents"][0]["evidence"] = []
        with self.assertRaises(ContractError):
            validate_dust_report(report)

    def test_contact_reference_and_contact_proof(self):
        report, _ = fixture()
        contact = {"name": "Personne fictive", "role": "Rapporteur", "relation": "Rapporteur du texte",
                   "document_ids": ["unknown"], "contact_url": None,
                   "evidence": [{"purpose": "relation", "url": "https://example.org/personne",
                                 "excerpt": "Rapporteur du texte", "location": None}]}
        report["contacts"] = [contact]
        with self.assertRaises(ContractError):
            validate_dust_report(report)
        contact["document_ids"] = ["dust-doc-1"]
        validate_dust_report(report)
        contact["contact_url"] = "https://example.org/contact"
        with self.assertRaises(ContractError):
            validate_dust_report(report)

    def test_preserves_source_and_context_without_merging_urls(self):
        report, snapshot = fixture()
        original = deepcopy(report)
        result = prepare(report, snapshot, document_is_new=True)
        self.assertEqual(result["request"]["document_id"], "app-doc-001")
        self.assertEqual(result["request"]["current"], snapshot)
        self.assertNotIn("Résumé", result["request"]["current"]["text"])
        self.assertEqual(len(result["context"]["matched_evidence"]), 1)
        self.assertEqual(len(result["context"]["dust_document"]["evidence"]), 2)
        result["context"]["dust_document"]["title"] = "mutation"
        self.assertEqual(report, original)

    def test_quote_must_exist_in_fetched_source(self):
        report, snapshot = fixture()
        snapshot["text"] = "Contenu différent"
        with self.assertRaises(ContractError):
            prepare(report, snapshot, document_is_new=True)

    def test_metadata_is_not_invented(self):
        report, snapshot = fixture()
        del snapshot["retrieved_at"]
        with self.assertRaises(ContractError):
            prepare(report, snapshot, document_is_new=True)

    def test_known_document_requires_previous_same_source(self):
        report, snapshot = fixture()
        with self.assertRaises(ContractError):
            prepare(report, snapshot)
        previous = {**snapshot, "text": "La consultation se termine le 10 octobre 2026.", "retrieved_at": "2026-09-26T10:00:00Z"}
        result = prepare(report, snapshot, previous_snapshot=previous)
        self.assertEqual(result["request"]["previous"], previous)
        previous["source_url"] = "https://example.org/other"
        with self.assertRaises(ContractError):
            prepare(report, snapshot, previous_snapshot=previous)

    def test_failed_retrieval_remains_unavailable(self):
        report, snapshot = fixture()
        snapshot.update(retrieval_status="unavailable", text="")
        result = prepare(report, snapshot, document_is_new=True)
        self.assertEqual(result["request"]["current"]["retrieval_status"], "unavailable")
        self.assertEqual(result["request"]["current"]["text"], "")


if __name__ == "__main__":
    unittest.main()
