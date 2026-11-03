"""Real Windows/Python/PowerShell tests against pinned synthetic fixtures only."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest

from ..contracts import Rejected, bind_parameters, strict_json, sanitize
from ..host import Engine, SchemaValidator, Catalog, digest
from ..win_process import PinnedFiles

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = json.loads((ROOT / "tests/fixture-pins.json").read_text())
        cls.base = json.loads((ROOT / "examples/request.json").read_text())
        cls._has_failure = False
        env_out = os.environ.get("TNOTES_TEST_OUTPUT_DIR")
        if env_out:
            cls.output_dir = Path(env_out)
            cls.output_dir.mkdir(parents=True, exist_ok=True)
            cls._owns_temp = False
        else:
            cls._temp_obj = tempfile.TemporaryDirectory(prefix="tnotes-engine-test-")
            cls.output_dir = Path(cls._temp_obj.name)
            cls._owns_temp = True

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_owns_temp", False) and hasattr(cls, "_temp_obj"):
            if getattr(cls, "_has_failure", False):
                cls._temp_obj._finalizer.detach()
                print(f"[test_engine] Retained test diagnostics in: {cls.output_dir}")
            else:
                cls._temp_obj.cleanup()

    def setUp(self):
        self.last_execution = None

    def tearDown(self):
        outcome = getattr(self, "_outcome", None)
        if outcome:
            for _, err in getattr(outcome, "errors", []):
                if err:
                    EngineTests._has_failure = True

    def engine(self, variant="good", on_started=None):
        pin = self.pins[variant]
        if variant == "native_nested":
            # The inherited worker reads catalog.json. Give both sides the same
            # explicitly pinned test catalog in an external repo-shaped copy.
            # Do not change the candidate's base registry or worker dispatch.
            if not hasattr(self, "nested_root"):
                root = self.output_dir / "native-fixture" / "prototypes" / "m365_official_engine"
                if not root.exists():
                    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
                    shutil.copytree(ROOT.parents[1] / "docs/contracts/m365",
                                    root.parents[1] / "docs/contracts/m365")
                    self.assertEqual(digest(root / pin["file"]), pin["sha256"])
                    (root / "catalog.json").write_bytes((root / "tests/catalogs/native_nested.json").read_bytes())
                    anchor = json.loads((root / pin["file"]).read_text())
                    anchor["inventory_path"] = "catalog.json"
                    anchor["inventory_sha256"] = digest(root / "catalog.json")
                    (root / "trust-anchor.json").write_text(json.dumps(anchor, indent=2) + "\n", encoding="utf-8")
                self.nested_root = root
            return Engine(self.nested_root, digest(self.nested_root / "trust-anchor.json"), on_started=on_started)
        return Engine(ROOT, pin["sha256"], pin["file"], on_started=on_started)

    def request(self, scenario="success", variant="good", delay=0):
        request = copy.deepcopy(self.base)
        request["parameters"] = {"Scenario": scenario, "DelayMs": delay}
        if variant in {"timeout", "fault_timeout"}:
            request["release_binding"]["manifest_sha256"] = digest(ROOT / "tests/fixtures/manifest-timeout.json")
        if variant == "native_nested":
            request["release_binding"]["manifest_sha256"] = digest(ROOT / "tests/fixtures/manifest-native_nested.json")
            request["target"] = {"kind": "object_id", "value": "44444444-4444-4444-8444-444444444444"}
        return request

    def execute(self, scenario="success", variant="good", request=None, cancellation=None, on_started=None):
        self.last_execution = self.engine(variant, on_started).execute(request or self.request(scenario, variant), cancellation)
        return self.last_execution

    def assert_schema(self, response):
        pin = self.pins["good"]
        with PinnedFiles() as locked:
            catalog = Catalog(ROOT, pin["sha256"], locked)
            SchemaValidator(catalog).validate([(catalog.schemas["execution-result.schema.json"]["$id"], response)])

    def test_success(self):
        result = self.execute()
        self.assertIsNone(result.error_code)
        self.assertEqual(result.response["status"], "success")
        self.assertEqual(result.logical_exit_code, 0)
        self.assertEqual(result.process_exit_code, 0)
        self.assertEqual(result.telemetry["final_job_active"], 0)
        self.assert_schema(result.response)
        (self.output_dir / "response-success.json").write_text(json.dumps(result.response, indent=2) + "\n", encoding="utf-8")

    def test_unknown_operation(self):
        request = self.request(); request["script_id"] = "M365.UNKNOWN.OPERATION"
        result = self.execute(request=request)
        self.assertEqual(result.error_code, "INVALID_PARAMETER")
        self.assertFalse(result.telemetry["dispatched"])

    def test_invalid_parameters(self):
        for value in (True, -1, 15001, "2"):
            request = self.request(); request["parameters"]["DelayMs"] = value
            result = self.execute(request=request)
            self.assertEqual(result.error_code, "INVALID_PARAMETER")
            self.assertFalse(result.telemetry["dispatched"])
        request = self.request(); request["parameters"]["Unknown"] = "arbitrary"
        self.assertEqual(self.execute(request=request).error_code, "INVALID_PARAMETER")

    def test_invalid_target(self):
        request = self.request(); request["target"]["value"] = "*"
        result = self.execute(request=request)
        self.assertEqual(result.error_code, "INVALID_PARAMETER")
        self.assertIsNone(result.response)

    def test_object_id_target(self):
        request = self.request(); request["target"] = {"kind": "object_id", "value": "44444444-4444-4444-8444-444444444444"}
        self.assertEqual(self.execute(request=request).response["status"], "success")

    def test_untrusted_script_path(self):
        result = self.execute(variant="untrusted")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertFalse(result.telemetry["dispatched"])

    def test_traversal_path(self):
        self.assertEqual(self.execute(variant="traversal").error_code, "CONTRACT_VIOLATION")

    def test_script_hash_mismatch(self):
        result = self.execute(variant="hash_mismatch")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertFalse(result.telemetry["dispatched"])

    def test_dependency_hash_mismatch(self):
        result = self.execute(variant="dependency_mismatch")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertIsNone(result.response)

    def test_missing_trust_anchor_evidence(self):
        for expected in (None, "", "not-a-sha256", "0" * 64):
            result = Engine(ROOT, expected).execute(self.request())
            self.last_execution = result
            self.assertEqual(result.error_code, "CONTRACT_VIOLATION")

    def test_request_version_mismatch(self):
        request = self.request(); request["contract_version"] = "0.2.0-proposed.1"
        result = self.execute(request=request)
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertIsNone(result.response)

    def test_response_version_mismatch(self):
        self.assertEqual(self.execute("bad_version", "fault").error_code, "CONTRACT_VIOLATION")

    def test_bad_descriptor(self):
        self.assertEqual(self.execute(variant="bad_descriptor").error_code, "CONTRACT_VIOLATION")

    def test_structured_error(self):
        result = self.execute("error")
        self.assertEqual(result.response["status"], "error")
        self.assertEqual(result.response["errors"][0]["code"], "ACCESS_DENIED")
        self.assertEqual(result.logical_exit_code, 20)
        self.assertEqual(result.process_exit_code, 0)
        self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", json.dumps(result.response))
        self.assert_schema(result.response)
        (self.output_dir / "response-error.json").write_text(json.dumps(result.response, indent=2) + "\n", encoding="utf-8")

    def test_partial(self):
        result = self.execute("partial")
        self.assertEqual(result.response["status"], "partial")
        self.assertIsNone(result.response["data"]["account_enabled"])
        self.assertEqual(result.logical_exit_code, 2)
        self.assertEqual(result.process_exit_code, 0)
        (self.output_dir / "response-partial.json").write_text(json.dumps(result.response, indent=2) + "\n", encoding="utf-8")

    def test_nonzero_process_exit(self):
        result = self.execute("process_nonzero", "fault")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertEqual(result.process_exit_code, 23)
        self.assertEqual(result.response["operation_outcome"], "unknown")
        self.assertIsNone(result.response["data"])

    def test_invalid_protocol(self):
        for mode in ("malformed", "duplicate_keys", "invalid_utf8", "two_envelopes", "console_noise"):
            result = self.execute(mode, "fault")
            self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
            self.assertIsNone(result.response["data"])
            self.assertEqual(result.telemetry["final_job_active"], 0)

    def test_extra_operation_output(self):
        self.assertEqual(self.execute("extra_output").response["errors"][0]["code"], "CONTRACT_VIOLATION")

    def test_terminating_error(self):
        result = self.execute("throw")
        self.assertEqual(result.response["errors"][0]["code"], "INTERNAL_ERROR")
        self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", json.dumps(result.response))

    def test_timeout(self):
        result = self.execute(variant="timeout", request=self.request("delay", "timeout", 15000))
        self.assertEqual(result.error_code, "TIMEOUT")
        self.assertEqual(result.response["status"], "timeout")
        self.assertEqual(result.logical_exit_code, 40)
        self.assertTrue(result.telemetry["control_sent"])
        self.assertEqual(result.telemetry["final_job_active"], 0)
        self.assert_schema(result.response)

    def test_cancellation(self):
        event = threading.Event()
        result = self.execute(request=self.request("delay", delay=15000), cancellation=event,
                              on_started=lambda: threading.Timer(2, event.set).start())
        self.assertEqual(result.error_code, "CANCELLED")
        self.assertTrue(result.telemetry["control_sent"])
        self.assertFalse(result.telemetry["forced"])
        self.assertEqual(result.telemetry["final_job_active"], 0)

    def test_cancellation_before_dispatch(self):
        event = threading.Event(); event.set()
        result = self.execute(cancellation=event)
        self.assertEqual(result.error_code, "CANCELLED")
        self.assertEqual(result.response["operation_outcome"], "not_started")
        self.assertFalse(result.telemetry["dispatched"])

    def test_child_process_cleanup(self):
        event = threading.Event()
        result = self.execute("child_hang", "fault", cancellation=event,
                              on_started=lambda: threading.Timer(2, event.set).start())
        self.assertEqual(result.error_code, "CANCELLED")
        self.assertGreaterEqual(result.telemetry["max_job_active"], 3)  # Worker + hidden conhost + test child.
        self.assertTrue(result.telemetry["forced"])
        self.assertEqual(result.telemetry["final_job_active"], 0)

    def test_output_limit(self):
        result = self.execute("oversize", "fault")
        self.assertEqual(result.error_code, "OUTPUT_LIMIT")
        self.assertTrue(result.telemetry["forced"])
        self.assertEqual(result.telemetry["final_job_active"], 0)

    def test_input_limit(self):
        request = self.request(); request["parameters"]["Scenario"] = "x" * 65536
        self.assertEqual(self.execute(request=request).error_code, "OUTPUT_LIMIT")

    def test_missing_executable(self):
        result = self.execute(variant="missing_executable")
        self.assertEqual(result.error_code, "MODULE_MISSING")
        self.assertIsNone(result.process_exit_code)

    def test_correlation_consistency(self):
        result = self.execute("bad_correlation", "fault")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertEqual(result.response["correlation_id"], self.base["correlation_id"])

    def test_wrong_logical_exit(self):
        self.assertEqual(self.execute("wrong_logical_exit", "fault").error_code, "CONTRACT_VIOLATION")

    def test_impossible_calendar_date(self):
        self.assertEqual(self.execute("bad_date", "fault").error_code, "CONTRACT_VIOLATION")

    def test_sensitive_data_handling(self):
        for mode in ("stderr_secret", "unknown_payload"):
            result = self.execute(mode, "fault")
            self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
            self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", json.dumps(result.response) + json.dumps(result.telemetry))
        result = self.execute("leak_data", "fault")
        self.assertEqual(result.response["data"]["display_name"], "[REDACTED]")

    def test_immutable_abi(self):
        result = self.execute("immutable")
        self.assertEqual(result.response["status"], "success")

    def test_recovery_after_malformed_output(self):
        engine = self.engine("fault")
        self.assertEqual(engine.execute(self.request("malformed")).error_code, "CONTRACT_VIOLATION")
        result = engine.execute(self.request())
        self.last_execution = result
        self.assertEqual(result.response["status"], "success")

    def test_descriptor_semantics(self):
        descriptor = {"name": "Count", "type": "integer", "required": True, "minimum": 1, "maximum": 3, "default": 2}
        self.assertEqual(bind_parameters([descriptor], {}), {"Count": 2})
        for value in (True, 0, 4, "2"):
            with self.assertRaises(Rejected):
                bind_parameters([descriptor], {"Count": value})
        with self.assertRaises(Rejected):
            bind_parameters([descriptor, {**descriptor, "name": "COUNT"}], {})

    def test_remaining_descriptor_types(self):
        cases = [({"name": "Enabled", "type": "boolean", "required": True}, True, 1),
                 ({"name": "Ratio", "type": "number", "required": True, "minimum": 0, "maximum": 1}, 0.5, False),
                 ({"name": "Labels", "type": "string_array", "required": True, "max_items": 2, "item_max_length": 4}, ["test"], ["too-long"])]
        for descriptor, good, bad in cases:
            name = descriptor["name"]
            self.assertEqual(bind_parameters([descriptor], {name: good}), {name: good})
            with self.assertRaises(Rejected):
                bind_parameters([descriptor], {name: bad})

    def test_write_operations_not_supported(self):
        result = self.execute(variant="write_risk")
        self.assertEqual(result.error_code, "ACCESS_DENIED")
        self.assertFalse(result.telemetry["dispatched"])

    def test_wrong_context(self):
        request = self.request(); request["tenant_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        result = self.execute(request=request)
        self.assertEqual(result.error_code, "TENANT_MISMATCH")
        self.assertFalse(result.telemetry["dispatched"])

    def test_sensitive_request_rejected_without_echo(self):
        request = self.request(); request["target"]["value"] = "password=mock-secret@example.invalid"
        result = self.execute(request=request)
        self.assertEqual(result.error_code, "INVALID_PARAMETER")
        self.assertIsNone(result.response)

    def test_pinned_file_cannot_be_opened_for_write(self):
        path = ROOT / "scripts/Fixture-Operation.ps1"
        with PinnedFiles() as locked:
            locked.pin(path, digest(path))
            with self.assertRaises(OSError):
                # Opening a non-truncating handle tests denial without writing bytes.
                with path.open("r+b"):
                    pass


    def test_s1_old_mixed_unknown_request_versions(self):
        for version in ("0.3.0-proposed.1", "0.3.0-proposed.1-mixed", "0.3.1", "0.3"):
            with self.subTest(version=version):
                request = self.request(); request["contract_version"] = version
                result = self.execute(request=request)
                self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
                self.assertIsNone(result.response)

    def test_s1_mixed_response_version(self):
        self.assertEqual(self.execute("mixed_version", "fault").error_code, "CONTRACT_VIOLATION")

    def test_s1_wrong_executable_hash(self):
        result = self.execute(variant="executable_mismatch")
        self.assertEqual(result.error_code, "CONTRACT_VIOLATION")
        self.assertIsNone(result.response)

    def test_s1_ticket_context_object(self):
        request = self.request(); request["ticket_context"] = {"ticket_id":"123"}
        result = self.execute(request=request)
        self.assertIsNone(result.error_code)
        self.assertEqual(result.response["correlation_id"], request["correlation_id"])

    def test_s1_null_nested_ticket_id_rejected(self):
        request = self.request(); request["ticket_context"] = {"ticket_id":None}
        result = self.execute(request=request)
        self.assertIsNone(result.response)
        self.assertEqual(result.error_code, "INVALID_PARAMETER")

    def test_s1_official_schemas_and_cancel_versions(self):
        from ..contracts import VERSION, COMMON
        self.assertEqual(VERSION, "0.3.0")
        frame = dict(message_type="cancel", contract_version=VERSION,
                     correlation_id=self.base["correlation_id"], company_id=self.base["company_id"],
                     session_generation=1, reason="user_cancel")
        with PinnedFiles() as locked:
            catalog = Catalog(ROOT, self.pins["good"]["sha256"], locked)
            validator = SchemaValidator(catalog)
            validator.validate([(COMMON+"#/$defs/cancel_control",frame)])
            for version in ("0.3.0-proposed.1", "0.3.0-mixed", "0.3.1"):
                bad = copy.deepcopy(frame); bad["contract_version"] = version
                with self.assertRaises(Rejected):
                    validator.validate([(COMMON+"#/$defs/cancel_control",bad)])

    def assert_native_rejected(self, scenario, variant="good"):
        result = self.execute(scenario, variant)
        self.assertIsNone(result.error_code)  # Actual worker response, not host rejection.
        self.assertEqual(result.process_exit_code, 0)
        self.assertEqual(result.logical_exit_code, 10)
        self.assertEqual(result.response["origin"], "worker")
        self.assertEqual(result.response["status"], "error")
        self.assertEqual(result.response["operation_outcome"], "failed")
        self.assertIsNone(result.response["data"])
        self.assertEqual([e["code"] for e in result.response["errors"]], ["CONTRACT_VIOLATION"])
        self.assertEqual(result.telemetry["stderr_bytes"], 0)
        self.assertEqual(result.telemetry["final_job_active"], 0)
        self.assert_schema(result.response)
        (self.output_dir / (scenario + ".json")).write_text(json.dumps(result.response, indent=2) + "\n", encoding="utf-8")

    def test_native_valid_return_and_data(self):
        result = self.execute()
        self.assertIsNone(result.error_code)
        self.assertEqual(result.response["status"], "success")
        self.assertEqual(result.response["data"]["display_name"], "Synthetic Fixture")
        self.assertEqual(result.logical_exit_code, 0)

    def test_native_nullable_error_and_partial(self):
        error = self.execute("error")
        self.assertEqual(error.response["status"], "error")
        self.assertIsNone(error.response["data"])
        partial = self.execute("partial")
        self.assertEqual(partial.response["status"], "partial")
        self.assertIsNone(partial.response["data"]["account_enabled"])
        self.assertEqual(partial.logical_exit_code, 2)

    def test_native_valid_nested_values(self):
        result = self.execute("native_nested_valid", "native_nested")
        self.assertIsNone(result.error_code)
        self.assertEqual(result.response["status"], "success")
        self.assertEqual(result.logical_exit_code, 0)
        self.assertEqual(result.response["data"]["returned_count"], 2)
        self.assertIsNone(result.response["data"]["events"][0]["app_display_name"])
        self.assertEqual(result.response["data"]["events"][0], result.response["data"]["events"][1])
        self.assertEqual(result.telemetry["final_job_active"], 0)

    def test_native_hashtable_data(self):
        self.assert_native_rejected("native_hashtable")

    def test_native_datetime(self):
        self.assert_native_rejected("native_datetime")

    def test_native_datetimeoffset(self):
        self.assert_native_rejected("native_datetimeoffset")

    def test_native_enum(self):
        self.assert_native_rejected("native_enum", "native_nested")

    def test_native_nested_object(self):
        self.assert_native_rejected("native_nested_object", "native_nested")

    def test_native_nested_array(self):
        self.assert_native_rejected("native_nested_array", "native_nested")

    def test_native_nested_dictionary(self):
        self.assert_native_rejected("native_nested_dictionary", "native_nested")

    def test_native_null_success_data(self):
        self.assert_native_rejected("native_null_data")

    def test_native_null_nonnullable_field(self):
        self.assert_native_rejected("native_null_field")

    def test_native_null_nested_field(self):
        self.assert_native_rejected("native_nested_null", "native_nested")

    def test_native_object_cycle(self):
        self.assert_native_rejected("native_cycle")

    def test_native_array_cycle(self):
        self.assert_native_rejected("native_array_cycle")

    def test_native_depth(self):
        self.assert_native_rejected("native_depth")

    def test_native_unsupported_container(self):
        self.assert_native_rejected("native_container")

    def test_native_nonfinite(self):
        self.assert_native_rejected("native_nonfinite")

    def test_native_getter_not_evaluated(self):
        self.assert_native_rejected("native_getter")

    def test_native_outer_dictionary(self):
        self.assert_native_rejected("native_outer_dictionary")

    def test_native_type_method_not_evaluated(self):
        self.assert_native_rejected("native_type_method")
