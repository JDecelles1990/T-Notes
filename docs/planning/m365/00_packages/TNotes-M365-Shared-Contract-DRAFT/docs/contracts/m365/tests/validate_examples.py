"""Local schema and fixture smoke tests; run from any working directory.

Requires: python -m pip install jsonschema
Not a substitute for PowerShell, UI, authorization, or tenant tests.
"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
EXAMPLES = ROOT / "examples"
MAPPING = {
    "entra-user-snapshot.manifest.json": "script-manifest.schema.json",
    "entra-user-snapshot.request.json": "execution-request.schema.json",
    "entra-user-snapshot.success.json": "execution-result.schema.json",
    "entra-user-snapshot.failure.json": "execution-result.schema.json",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    for name in SCHEMAS.iterdir():
        if name.name.endswith(".schema.json"):
            Draft202012Validator.check_schema(load(name))
    for example, schema in MAPPING.items():
        validator = Draft202012Validator(load(SCHEMAS / schema), format_checker=FormatChecker())
        instance = load(EXAMPLES / example)
        validator.validate(instance)
        print("PASS", example)
    request = load(EXAMPLES / "entra-user-snapshot.request.json")
    success = load(EXAMPLES / "entra-user-snapshot.success.json")
    failure = load(EXAMPLES / "entra-user-snapshot.failure.json")
    manifest = load(EXAMPLES / "entra-user-snapshot.manifest.json")
    assert request["contract_version"] == success["contract_version"] == failure["contract_version"] == manifest["contract_version"]
    assert request["request_id"] == success["request_id"] == failure["request_id"]
    assert request["context"]["tenant_id"] == success["tenant_id"] == failure["tenant_id"]
    assert request["script_id"] == success["script_id"] == failure["script_id"] == manifest["script_id"]
    expected_parameters = {x["name"] for x in manifest["parameters"]}
    assert set(request["parameters"]) == expected_parameters
    for bad in [dict(request, password="DO_NOT_STORE"), dict(request, contract_version="wrong"), dict(request, parameters={"Password":"a-secret"})]:
        assert not Draft202012Validator(load(SCHEMAS / "execution-request.schema.json")).is_valid(bad)
    for bad in [dict(success, status="success", errors=[{"code":"BAD","message":"bad","retryable":False}]),dict(success, unexpected=True)]:
        assert not Draft202012Validator(load(SCHEMAS / "execution-result.schema.json")).is_valid(bad)
    print("PASS negative shape and contract-version checks")
    print("PASS cross-document fixture identity checks")
    print("NOTE live Microsoft 365, Pester, Qt GUI and auth validation: NOT RUN")


if __name__ == "__main__":
    run()
