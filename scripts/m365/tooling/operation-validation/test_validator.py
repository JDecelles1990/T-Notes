"""Synthetic packages only. Test failures and all attempts are saved by run_tests.py."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import validate_operation as v

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = ROOT / 'docs/contracts/m365'
PINS = ROOT / 'assets/m365/contract-review-pins.json'
REFERENCE = ROOT / 'scripts/m365/entra-id/user-identity'
ABI = '''[CmdletBinding()]
param(
[Parameter(Mandatory)][System.Collections.Generic.IReadOnlyDictionary[string,object]]$Context,
[Parameter(Mandatory)][System.Collections.Generic.IReadOnlyDictionary[string,object]]$Parameters,
[Parameter(Mandatory)][System.Threading.CancellationToken]$CancellationToken)
throw 'SYNTHETIC_SOURCE_NEVER_EXECUTED'
'''


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = v.Schemas(CONTRACT, PINS)
        cls.fixtures = {x['name']: x['instance'] for x in v.read(CONTRACT / 'examples/fixtures.json')['fixtures'] if x.get('valid')}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = Path(self.temp.name)
        self.package = self.library / 'test/fixture'
        self.package.mkdir(parents=True)
        self.manifest = copy.deepcopy(self.fixtures['user_identity.manifest'])
        self.manifest.update(script_id='M365.TEST.VALIDATOR', script_path='test/fixture/Test-Fixture.ps1', required_modules=[])
        (self.package / 'Test-Fixture.ps1').write_text(ABI, encoding='utf-8')
        self.write_manifest()

    def write_manifest(self):
        self.manifest['script_sha256'] = v.digest(self.package / 'Test-Fixture.ps1')
        (self.package / 'operation.manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        self.rehash()

    def rehash(self):
        files = {p.relative_to(self.package).as_posix(): v.digest(p) for p in self.package.rglob('*')
                 if p.is_file() and p.name != 'SHA256SUMS.json'}
        (self.package / 'SHA256SUMS.json').write_text(json.dumps({'algorithm': 'SHA-256', 'files': files}), encoding='utf-8')

    def validate(self, state='VALIDATED_CANDIDATE', **kwargs):
        return v.validate(self.package, CONTRACT, PINS, self.library, requested=state, **kwargs)

    def assertFails(self, report, name):
        self.assertEqual(report['final_disposition'], 'REJECTED', report)
        self.assertTrue(any(c['name'] == name and c['status'] == 'FAIL' for c in report['checks']), report)
        self.assertFalse(report['dispatchable'])

    def test_valid_candidate_never_dispatchable(self):
        report = self.validate()
        self.assertEqual(report['final_disposition'], 'VALIDATED_CANDIDATE', report)
        self.assertFalse(report['dispatchable'])

    def test_existing_reference_preserved(self):
        before = {p: v.digest(p) for p in REFERENCE.rglob('*') if p.is_file()}
        report = v.validate(REFERENCE, CONTRACT, PINS, ROOT / 'scripts/m365')
        self.assertEqual(report['validation_status'], 'PASS', report)
        self.assertEqual(report['package_kind'], 'NON_DISPATCHABLE_REFERENCE')
        self.assertEqual(before, {p: v.digest(p) for p in before})

    def test_missing_contract_field(self):
        del self.manifest['contract_version']
        self.write_manifest()
        self.assertFails(self.validate(), 'package_identity_and_manifest')

    def test_missing_required_manifest_field(self):
        del self.manifest['risk']
        self.write_manifest()
        self.assertFails(self.validate(), 'manifest_schema')

    def test_unsupported_version(self):
        self.manifest['contract_version'] = '9.0.0'
        self.write_manifest()
        self.assertFails(self.validate(), 'package_identity_and_manifest')

    def test_wrong_abi(self):
        path = self.package / 'Test-Fixture.ps1'
        path.write_text(ABI.replace('IReadOnlyDictionary[string,object]', 'hashtable'), encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'exact_callable_abi')

    def test_optional_abi(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI.replace('Mandatory', 'Mandatory=$false'), encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'exact_callable_abi')

    def test_reversed_generic_abi(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI.replace('IReadOnlyDictionary[string,object]', 'IReadOnlyDictionary[object,string]'), encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'exact_callable_abi')

    def test_abi_extra_parameter(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI.replace('$CancellationToken)', '$CancellationToken, [string]$Extra)'), encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'exact_callable_abi')

    def test_corrupt_manifest_duplicate_key(self):
        (self.package / 'operation.manifest.json').write_text('{"script_id":"a","script_id":"b"}', encoding='utf-8')
        self.rehash()
        self.assertFails(self.validate(), 'package_identity_and_manifest')

    def test_duplicate_ids(self):
        other = self.library / 'other'
        other.mkdir()
        (other / 'operation.manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        self.assertFails(self.validate(), 'unique_operation_identifiers')

    def test_reserved_parameter(self):
        self.manifest['parameters'] = [{'name': 'Context', 'type': 'string', 'required': False, 'description': 'Synthetic'}]
        self.write_manifest()
        self.assertFails(self.validate(), 'descriptor_semantics')

    def test_inverted_parameter(self):
        self.manifest['parameters'] = [{'name': 'Count', 'type': 'integer', 'required': False, 'description': 'Synthetic', 'minimum': 5, 'maximum': 1}]
        self.write_manifest()
        self.assertFails(self.validate(), 'descriptor_semantics')

    def test_default_type(self):
        self.manifest['parameters'] = [{'name': 'Count', 'type': 'integer', 'required': False, 'description': 'Synthetic', 'default': True}]
        self.write_manifest()
        self.assertFails(self.validate(), 'descriptor_semantics')

    def test_wrong_schema_reference(self):
        self.manifest['expected_output_schema'] = 'https://example.invalid/schema.json'
        self.write_manifest()
        self.assertFails(self.validate(), 'selected_payload_schema')

    def test_unknown_schema_definition(self):
        self.manifest['expected_output_schema'] = 'schemas/operation-data.schema.json#/$defs/not_present'
        self.write_manifest()
        self.assertFails(self.validate(), 'selected_payload_schema')

    def test_hash_mismatch(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI + '# changed', encoding='utf-8')
        self.assertFails(self.validate(), 'complete_file_inventory_and_hashes')

    def test_path_traversal(self):
        self.manifest['script_path'] = '../Test-Fixture.ps1'
        self.write_manifest()
        self.assertFails(self.validate(), 'contained_source_and_nonpromotion')

    def test_inventory_traversal(self):
        (self.package / 'SHA256SUMS.json').write_text(json.dumps({'algorithm':'SHA-256', 'files': {'../outside': '0'*64}}), encoding='utf-8')
        self.assertFails(self.validate(), 'complete_file_inventory_and_hashes')

    def test_untrusted_content(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI + "\nInvoke-Expression 'synthetic'", encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'static_policy_and_host_auth_boundary')

    def test_host_owned_auth(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI + '\nConnect-MgGraph', encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'static_policy_and_host_auth_boundary')

    def test_credential(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI + "\n$password = 'synthetic-only'", encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'static_policy_and_host_auth_boundary')

    def test_unexpected_executable(self):
        (self.package / 'Extra.exe').write_bytes(b'synthetic')
        self.rehash()
        self.assertFails(self.validate(), 'contained_source_and_nonpromotion')

    def test_unapproved_promotion(self):
        self.assertFails(self.validate(state='APPROVED_RELEASE'), 'external_release_verifier_required')

    def test_reference_promotion(self):
        shutil.rmtree(self.package)
        shutil.copytree(REFERENCE, self.package)
        (self.package / 'Get-UserIdentity.ps1').write_text(ABI, encoding='utf-8')
        self.assertFails(self.validate(), 'contained_source_and_nonpromotion')

    def test_dependency_hash_required(self):
        self.manifest['required_modules'] = [{'name': 'Synthetic.Module', 'minimum_version': '1.0.0'}]
        self.write_manifest()
        self.assertFails(self.validate(), 'declared_dependency_inventory')

    def test_write_confirmation(self):
        self.manifest['risk'] = 'write'
        self.manifest['approval_requirements']['confirmation_required'] = False
        self.write_manifest()
        self.assertFails(self.validate(), 'descriptor_semantics')

    def test_report_no_overwrite_or_input_writes(self):
        with self.assertRaises(ValueError):
            v.save_report({}, self.package / 'report.json', (self.package, CONTRACT))
        target = self.library / 'report.json'
        v.save_report({}, target, (self.package, CONTRACT))
        with self.assertRaises(FileExistsError):
            v.save_report({}, target, (self.package, CONTRACT))

    def test_release_states(self):
        passing = [{'status': 'PASS'}]
        self.assertEqual(v.disposition(passing, 'INDEPENDENT_REVIEW_REQUIRED'), 'INDEPENDENT_REVIEW_REQUIRED')
        self.assertEqual(v.disposition(passing, 'RETIRED'), 'RETIRED')
        self.assertEqual(v.disposition(passing, 'REJECTED'), 'REJECTED')
        self.assertEqual(v.disposition([{'status':'NOT RUN'}], 'VALIDATED_CANDIDATE'), 'DRAFT')
        self.assertEqual(v.disposition(passing, 'APPROVED_RELEASE'), 'REJECTED')

    def test_response_probes(self):
        probes = v.result_probes(self.manifest, self.schemas)
        self.assertEqual(len(probes), 9)
        self.assertTrue(all(passed for _, passed in probes), probes)

    def test_bad_contract_pin(self):
        pins = v.read(PINS)
        pins['schemas']['common'] = '0' * 64
        path = self.library / 'pins.json'
        path.write_text(json.dumps(pins), encoding='utf-8')
        with self.assertRaises(ValueError):
            v.Schemas(CONTRACT, path)

    def test_missing_schema_dependency_not_run(self):
        with patch.object(v, 'Schemas', side_effect=v.MissingDependency()):
            report = self.validate()
        self.assertEqual(report['final_disposition'], 'DRAFT')
        self.assertEqual(report['validation_status'], 'NOT RUN')

    def test_no_powershell_not_run(self):
        with patch.object(v.shutil, 'which', return_value=None):
            report = self.validate()
        self.assertEqual(report['final_disposition'], 'DRAFT')
        self.assertEqual(report['validation_status'], 'NOT RUN')

    def test_direct_dynamic_execution(self):
        (self.package / 'Test-Fixture.ps1').write_text(ABI + "\n& $Context['Command']", encoding='utf-8')
        self.write_manifest()
        self.assertFails(self.validate(), 'static_policy_and_host_auth_boundary')

    def test_schema_dependency_mismatch(self):
        pins = v.read(PINS)
        pins['schemas']['error'] = '0'*64
        path = self.library / 'pins.json'
        path.write_text(json.dumps(pins), encoding='utf-8')
        with self.assertRaises(ValueError):
            v.Schemas(CONTRACT, path)

    def test_script_manifest_reference_mismatch(self):
        self.manifest['script_sha256'] = '0'*64
        (self.package / 'operation.manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        self.rehash()
        self.assertFails(self.validate(), 'contained_source_and_nonpromotion')

    def test_parameter_duplicate_case(self):
        self.manifest['parameters'] = [dict(name=n, type='string', required=False, description='Synthetic') for n in ('Value', 'VALUE')]
        self.write_manifest()
        self.assertFails(self.validate(), 'descriptor_semantics')

    def test_response_binding_and_time(self):
        request = copy.deepcopy(self.fixtures['user_identity.request'])
        result = copy.deepcopy(self.fixtures['user_identity.success'])
        manifest = copy.deepcopy(self.fixtures['user_identity.manifest'])
        for key, value in [('completed_at', '2026-02-30T12:00:00Z'), ('operation_exit_code', 40),
                           ('correlation_id', '99999999-9999-4999-8999-999999999999')]:
            bad = copy.deepcopy(result)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(Exception):
                v.check_response(bad, request, manifest, self.schemas)


if __name__ == '__main__':
    unittest.main()
