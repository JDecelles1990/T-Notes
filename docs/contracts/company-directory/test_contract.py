"""Isolated schema/design checks; no merge engine, GUI, storage or network."""

import json
from pathlib import Path
import unittest

from validate_design import (
    DesignValidationError, MAX_BYTES, parse_document, validate_bytes,
    validate_schema, validate_semantics,
)

HERE = Path(__file__).resolve().parent


class ContractDesignTests(unittest.TestCase):
    def test_exchange_fixtures(self):
        cases = json.loads((HERE / "exchange-fixtures.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["name"]):
                raw = case.get("raw_json", json.dumps(case.get("document"))).encode("utf-8")
                if case["accept"]:
                    document = validate_bytes(raw)
                    self.assertEqual(validate_bytes(json.dumps(document).encode()), document)
                else:
                    with self.assertRaises(DesignValidationError):
                        validate_bytes(raw)

    def test_semantics_are_distinct_from_schema(self):
        cases = json.loads((HERE / "exchange-fixtures.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            if case["name"] in {"duplicate-tenant", "duplicate-company-id", "duplicate-upn-casefold", "dangling-default", "domain-cross-tenant", "timestamp-reversed"}:
                with self.subTest(case=case["name"]):
                    validate_schema(case["document"])
                    with self.assertRaises(DesignValidationError):
                        validate_semantics(case["document"])

    def test_golden_documents_are_valid(self):
        scenarios = json.loads((HERE / "merge-golden-fixtures.json").read_text(encoding="utf-8"))["scenarios"]
        for scenario in scenarios:
            for side in ("local", "imported", "expected"):
                with self.subTest(scenario=scenario["name"], side=side):
                    validate_bytes(json.dumps(scenario[side]).encode())
        # This validates example documents, NOT a merge implementation.

    def test_size_and_utf8_limits(self):
        for raw in (b"x" * (MAX_BYTES + 1), b"\xff"):
            with self.assertRaises(DesignValidationError):
                parse_document(raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
