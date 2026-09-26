"""Offline contract and service tests. All analyzer responses are fixtures."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from backend.comparison_service import compare_for_refresh
from backend.comparison_validation import ContractError, validate_report, validate_request

FIXTURES = Path(__file__).parent / "fixtures" / "political_watch"


def case(name):
    folder = FIXTURES / name
    request = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))["request"]
    report = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    return request, report


class ComparisonTests(unittest.TestCase):
    def test_four_reference_reports_satisfy_contract(self):
        for name in ("new_document", "modified", "unchanged", "unconfirmed"):
            with self.subTest(name=name):
                request, report = case(name)
                self.assertEqual(validate_report(request, report), report)

    def test_invented_quote_url_date_or_version_rejected(self):
        for field, value in (("quote", "Citation inventée"), ("source_url", "https://example.org/other"),
                             ("retrieved_at", "2020-01-01T00:00:00Z"), ("version", "invented")):
            with self.subTest(field=field):
                request, report = case("modified")
                report["evidence"][0][field] = value
                with self.assertRaises(ContractError):
                    validate_report(request, report)

    def test_evidence_of_each_change_is_checked(self):
        request, report = case("modified")
        report["changes"][0]["evidence"][0]["quote"] = "Une invention"
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_change_requires_both_versions(self):
        request, report = case("modified")
        report["changes"][0]["evidence"] = report["changes"][0]["evidence"][:1]
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_wrong_document_id_rejected(self):
        request, report = case("modified")
        report["document_id"] = "wrong"
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_missing_or_unknown_field_rejected(self):
        for mode in ("missing", "unknown"):
            request, report = case("modified")
            if mode == "missing":
                del report["changes"]
            else:
                report["confidence"] = 1
            with self.assertRaises(ContractError):
                validate_report(request, report)

    def test_bad_list_and_bad_status_rejected(self):
        for field, value in (("changes", {}), ("limitations", "aucune"), ("evidence", None), ("change_type", "deleted")):
            request, report = case("modified")
            report[field] = value
            with self.assertRaises(ContractError):
                validate_report(request, report)

    def test_no_new_document_when_previous_exists(self):
        request, report = case("new_document")
        request["previous"] = deepcopy(request["current"])
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_explicit_null_previous_accepted(self):
        request, report = case("new_document")
        request["previous"] = None
        validate_report(request, report)

    def test_excerpts_cannot_establish_unchanged(self):
        request, report = case("unchanged")
        request["current"]["scope"] = "excerpts"
        report["limitations"] = ["Extraits seulement"]
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_successfully_collected_excerpts_can_establish_change(self):
        request, report = case("modified")
        request["previous"]["scope"] = request["current"]["scope"] = "excerpts"
        report["limitations"] = ["Analyse limitée aux extraits transmis."]
        validate_report(request, report)
        report["limitations"] = []
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_partial_collection_forces_unconfirmed(self):
        for version in ("previous", "current"):
            request, report = case("modified")
            request[version]["retrieval_status"] = "partial"
            with self.assertRaises(ContractError):
                validate_report(request, report)
            _, unknown = case("unconfirmed")
            validate_report(request, unknown)

    def test_blank_text_forces_unconfirmed(self):
        request, report = case("new_document")
        request["current"]["text"] = "  "
        report["evidence"] = []
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_unconfirmed_requires_reason_and_no_claims(self):
        request, report = case("unconfirmed")
        report["limitations"] = []
        with self.assertRaises(ContractError):
            validate_report(request, report)
        request, report = case("unconfirmed")
        report["changes"] = [{"description": "Supprimé", "evidence": []}]
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_unavailable_source_cannot_carry_current_content(self):
        request, _ = case("unconfirmed")
        request["current"]["text"] = "Old content relabelled as fresh"
        with self.assertRaises(ContractError):
            validate_request(request)

    def test_identical_text_cannot_be_modified(self):
        request, report = case("modified")
        request["current"]["text"] = request["previous"]["text"]
        for citation in report["evidence"] + report["changes"][0]["evidence"]:
            citation["quote"] = request["previous"]["text"]
        with self.assertRaises(ContractError):
            validate_report(request, report)

    def test_invalid_date_and_credential_url_rejected(self):
        for field, value in (("retrieved_at", "2026-09-26T09:00:00"),
                             ("retrieved_at", "tomorrow"),
                             ("source_url", "https://user:secret@example.org/doc"),
                             ("source_url", "file:///private/document")):
            request, _ = case("new_document")
            request["current"][field] = value
            with self.assertRaises(ContractError):
                validate_request(request)

    def test_service_returns_candidate_snapshot_without_mutation(self):
        request, report = case("modified")
        before = deepcopy(request)
        calls = []
        def analyze(envelope):
            calls.append(envelope)
            return report
        result = compare_for_refresh(request, analyze)
        self.assertEqual(calls, [{"request": before}])
        self.assertEqual(request, before)
        self.assertEqual(result.snapshot_to_store, request["current"])
        result.snapshot_to_store["text"] = "changed externally"
        self.assertEqual(request, before)

    def test_unconfirmed_never_proposes_replacing_snapshot(self):
        request, report = case("unconfirmed")
        result = compare_for_refresh(request, lambda _: report)
        self.assertIsNone(result.snapshot_to_store)

    def test_analyzer_failure_propagates_without_mutation(self):
        request, _ = case("modified")
        before = deepcopy(request)
        def fail(_):
            raise TimeoutError("test failure")
        with self.assertRaises(TimeoutError):
            compare_for_refresh(request, fail)
        self.assertEqual(request, before)

    def test_analyzer_cannot_rewrite_input_to_validate_fabrication(self):
        request, report = case("modified")
        def tamper(envelope):
            envelope["request"]["current"]["text"] = "forged"
            report["evidence"][1]["quote"] = "forged"
            return report
        with self.assertRaises(ContractError):
            compare_for_refresh(request, tamper)

    def test_bad_input_rejected_before_analyzer_call(self):
        request, _ = case("modified")
        request["document_id"] = ""
        def forbidden(_):
            self.fail("Analyzer must not be called")
        with self.assertRaises(ContractError):
            compare_for_refresh(request, forbidden)


if __name__ == "__main__":
    unittest.main()
