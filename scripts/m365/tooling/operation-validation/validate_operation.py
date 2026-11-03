"""Offline operation validation. No application imports or operation execution."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION = '0.3.0-proposed.1'
HERE = Path(__file__).resolve().parent
STATES = ('DRAFT', 'VALIDATED_CANDIDATE', 'INDEPENDENT_REVIEW_REQUIRED',
          'APPROVED_RELEASE', 'REJECTED', 'RETIRED')
RESERVED = {s.casefold() for s in ('Context Parameters CancellationToken Verbose Debug '
    'ErrorAction WarningAction InformationAction ProgressAction ErrorVariable WarningVariable '
    'InformationVariable OutVariable OutBuffer PipelineVariable WhatIf Confirm').split()}


class MissingDependency(Exception):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, code):
    if not condition:
        raise ValueError(code)


def read(path):
    require(path.stat().st_size <= 4 * 1024 * 1024, 'FILE_TOO_LARGE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('NONFINITE_JSON')
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=invalid)


def contained(root, relative):
    require(isinstance(relative, str) and len(relative) <= 240 and
            re.fullmatch(r'[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*', relative) and
            all(p not in ('', '.', '..') for p in relative.split('/')), 'UNSAFE_PATH')
    target = root / relative
    # Reject links/junctions even if they happen to resolve inside the root.
    for part in (root, *target.parents, target):
        if part == root or root in part.parents:
            require(not part.is_symlink() and not part.is_junction(), 'REPARSE_PATH')
    require(target.resolve().is_relative_to(root.resolve()), 'PATH_ESCAPE')
    require(target.is_file(), 'MISSING_FILE')
    return target


class Schemas:
    def __init__(self, root, pins):
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            from referencing import Registry, Resource
        except ImportError as exc:
            raise MissingDependency('JSONSCHEMA_UNAVAILABLE') from exc
        self.root = root
        self.validator_type, self.formats = Draft202012Validator, FormatChecker()
        identity = read(pins)
        require(identity['contract_version'] == VERSION, 'CONTRACT_PIN_VERSION')
        self.schemas, self.hashes = {}, {str(pins): digest(pins)}
        for relative in ('CONTRACT.md', 'README.md', 'CONTRACT_CORRECTION_HANDOFF.md', 'examples/fixtures.json'):
            path = contained(root, relative)
            self.hashes[str(path)] = digest(path)
        registry = Registry()  # default retrieval fails; no network resolver
        for name in ('common', 'company-profile', 'error', 'execution-request',
                     'execution-result', 'operation-data', 'script-manifest'):
            path = contained(root, f'schemas/{name}.schema.json')
            require(digest(path) == identity['schemas'][name], 'CONTRACT_HASH_MISMATCH')
            schema = read(path)
            Draft202012Validator.check_schema(schema)
            require(schema['$id'] == f'https://tnotes.invalid/m365/{VERSION}/schemas/{name}.schema.json',
                    'SCHEMA_ID_MISMATCH')
            self.schemas[name] = schema
            self.hashes[str(path)] = digest(path)
            registry = registry.with_resource(schema['$id'], Resource.from_contents(schema))
        self.registry = registry
        ids = {v['$id'] for v in self.schemas.values()}
        def refs(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == '$ref':
                        require(value.split('#')[0] in ids or value.startswith('#'), 'NONLOCAL_SCHEMA_REF')
                    refs(value)
            elif isinstance(node, list):
                for child in node:
                    refs(child)
        for schema in self.schemas.values():
            refs(schema)

    def validate(self, name, value):
        self.validator_type(self.schemas[name], registry=self.registry,
                            format_checker=self.formats).validate(value)

    def payload(self, reference, value):
        require(isinstance(reference, str) and re.fullmatch(
            r'schemas/[a-z-]+\.schema\.json#/\$defs/[a-z_]+', reference), 'BAD_SCHEMA_REFERENCE')
        filename, fragment = reference.split('#')
        name = filename.removeprefix('schemas/').removesuffix('.schema.json')
        require(name in self.schemas, 'UNKNOWN_SCHEMA')
        require(fragment.removeprefix('/$defs/') in self.schemas[name].get('$defs', {}), 'UNKNOWN_DEFINITION')
        if value is not None:
            self.validator_type({'$ref': self.schemas[name]['$id'] + '#' + fragment},
                                registry=self.registry, format_checker=self.formats).validate(value)


def parameter_value(value, spec):
    kind = spec['type']
    valid = {'string': isinstance(value, str), 'integer': type(value) is int,
             'number': type(value) in (int, float), 'boolean': type(value) is bool,
             'string_array': isinstance(value, list) and all(isinstance(x, str) for x in value)}[kind]
    if not valid:
        return False
    if kind in ('integer', 'number'):
        if not math.isfinite(value) or not spec.get('minimum', -math.inf) <= value <= spec.get('maximum', math.inf):
            return False
        if kind == 'integer' and not -(2**63) <= value < 2**63:
            return False
    if kind == 'string' and not spec.get('min_length', 0) <= len(value) <= spec.get('max_length', 4096):
        return False
    if kind == 'string_array' and (not spec.get('min_items', 0) <= len(value) <= spec.get('max_items', 1000) or
            not all(spec.get('item_min_length', 0) <= len(x) <= spec.get('item_max_length', 4096) for x in value)):
        return False
    return 'allowed_values' not in spec or any(type(value) is type(x) and value == x for x in spec['allowed_values'])


def descriptors(manifest, schemas):
    names = set()
    for spec in manifest['parameters']:
        schemas.validator_type({'$ref': schemas.schemas['common']['$id'] + '#/$defs/parameter'},
                              registry=schemas.registry).validate(spec)
        name = spec['name'].casefold()
        require(name not in names and name not in RESERVED, 'CONFLICTING_PARAMETER')
        names.add(name)
        for low, high in (('minimum', 'maximum'), ('min_length', 'max_length'),
                          ('min_items', 'max_items'), ('item_min_length', 'item_max_length')):
            require(spec.get(low, -math.inf) <= spec.get(high, math.inf), 'INVERTED_BOUNDS')
        if 'default' in spec:
            require(parameter_value(spec['default'], spec), 'INVALID_DEFAULT')
        if 'allowed_values' in spec:
            scalar = {k: v for k, v in spec.items() if k != 'allowed_values'}
            require(all(parameter_value(x, scalar) for x in spec['allowed_values']), 'INVALID_ENUM')
    modules = [x['name'].casefold() for x in manifest['required_modules']]
    require(len(set(modules)) == len(modules), 'DUPLICATE_MODULE')
    services = manifest['connection_requirements']
    require(not manifest['graph_scopes'] or 'Graph' in services, 'UNDECLARED_GRAPH')
    require(all(x['service'] in services for x in manifest['required_roles']), 'UNDECLARED_ROLE_SERVICE')
    if manifest['risk'] != 'read_only':
        require(manifest['approval_requirements']['confirmation_required'], 'WRITE_CONFIRMATION_REQUIRED')


def inspect_script(script, pwsh):
    run = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
                          str(HERE / 'Inspect-Operation.ps1'), '-SourcePath', str(script)],
                         capture_output=True, text=True, encoding='utf-8', timeout=30)
    require(run.returncode == 0, 'AST_HELPER_FAILED')
    return json.loads(run.stdout)


def check_abi(ast):
    require(ast['parse_errors'] == 0 and not ast['using_count'] and not ast['requires'], 'PARSE_OR_LOAD_DIRECTIVE')
    params = ast['parameters']
    require([p['name'] for p in params] == ['Context', 'Parameters', 'CancellationToken'], 'ABI_NAMES')
    for p in params:
        expected = 'System.Threading.CancellationToken' if p['name'] == 'CancellationToken' else None
        actual = p['type']
        require(actual == expected if expected else actual.startswith('System.Collections.Generic.IReadOnlyDictionary`2')
                and p['generic_arguments'] == ['System.String', 'System.Object'], 'ABI_TYPE')
        attrs = [re.sub(r'\s', '', x).casefold() for x in p['attributes']]
        require(any(a in ('[parameter(mandatory)]', '[parameter(mandatory=$true)]') for a in attrs), 'ABI_MANDATORY')
        require(not p['default'] and len(attrs) == 2, 'ABI_CONSTRAINTS')


def check_security(ast, text, manifest):
    forbidden = {'invoke-expression', 'iex', 'start-process', 'invoke-command', 'add-type',
                 'connect-mggraph', 'disconnect-mggraph', 'connect-exchangeonline',
                 'disconnect-exchangeonline', 'get-credential', 'import-module', 'ipmo',
                 'powershell', 'powershell.exe', 'pwsh', 'pwsh.exe', 'cmd', 'cmd.exe',
                 'invoke-webrequest', 'invoke-restmethod', 'curl', 'wget'}
    for cmd in ast['commands']:
        name = (cmd['name'] or '').casefold().split('\\')[-1]
        require(name and cmd['invocation'] not in ('Dot', 'Ampersand'), 'DYNAMIC_EXECUTION')
        require(name not in forbidden, 'PROHIBITED_COMMAND')
        if manifest['risk'] == 'read_only':
            require(not re.match(r'^(set|remove|new|add|update|clear|enable|disable|grant|revoke|send)-(mg|exo|mailbox|user)', name),
                    'READ_ONLY_WRITE_COMMAND')
    require(not re.search(r'(?i)(?:password|client_secret|access_token|refresh_token)\s*[=:]\s*[\x22\x27][^\x22\x27]+', text),
            'EMBEDDED_CREDENTIAL_PATTERN')
    require(not re.search(r'(?i)\b(?:PySide6|sqlite3|System\.Diagnostics\.Process|DownloadString|FromBase64String|DllImport)\b|'
                          r'\bsrc\.(?:ui|services|repositories)\b|\$env:', text), 'HOST_COUPLING_OR_UNSAFE_API')
    # Heuristic policy deliberately cannot establish safety or effective authorization.


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', value), 'INVALID_TIMESTAMP')
    return datetime.fromisoformat(value)


def check_response(result, request, manifest, schemas):
    schemas.validate('execution-request', request)
    schemas.validate('execution-result', result)
    for key in ('contract_version', 'script_id', 'correlation_id', 'company_id', 'tenant_id',
                'admin_identity_ref', 'session_generation', 'target', 'release_binding'):
        require(result[key] == request[key], 'RESPONSE_BINDING')
    require(result['script_id'] == manifest['script_id'], 'RESPONSE_OPERATION')
    require(timestamp(result['completed_at']) >= timestamp(result['started_at']), 'REVERSED_TIME')
    schemas.payload(manifest['expected_output_schema'], result['data'])
    status = result['status']
    codes = {x['code'] for x in result['errors']}
    logical = {'success': 0, 'partial': 2, 'cancelled': 40, 'timeout': 40}.get(status)
    if logical is None:
        logical = 30
        for number, group in ((50, {'INTERNAL_ERROR'}), (20, {'AUTH_REQUIRED', 'TENANT_MISMATCH', 'ACCOUNT_MISMATCH', 'ACCESS_DENIED'}),
                              (10, {'INVALID_PARAMETER', 'CONTRACT_VIOLATION'}), (40, {'TIMEOUT', 'CANCELLED'})):
            if codes & group:
                logical = number
                break
    require(result['operation_exit_code'] == logical, 'LOGICAL_EXIT')
    if result['data'] is not None:
        kind = request['target']['kind']
        field = manifest['target_policy']['output_binding']['upn_field' if kind == 'upn' else 'object_id_field']
        actual, expected = result['data'].get(field), request['target']['value']
        require(isinstance(actual, str) and (actual.casefold() == expected.casefold() if kind == 'upn' else actual == expected),
                'TARGET_BINDING')


def result_probes(manifest, schemas):
    # Derive schema-specific positives from the reviewed SYNTHETIC contract fixtures.
    fixtures = read(contained(schemas.root, 'examples/fixtures.json'))['fixtures']
    candidates = {f['name']: f['instance'] for f in fixtures if f.get('valid') is True}
    source = next((name.removesuffix('.manifest') for name, value in candidates.items()
                   if name.endswith('.manifest') and value.get('expected_output_schema') == manifest['expected_output_schema']), None)
    require(source is not None, 'NO_SYNTHETIC_OUTPUT_FIXTURE')
    request, success = copy.deepcopy(candidates[source + '.request']), copy.deepcopy(candidates[source + '.success'])
    request['script_id'] = success['script_id'] = manifest['script_id']
    probes = [('success', success, True)]
    error = copy.deepcopy(success)
    error.update(status='error', operation_outcome='failed', operation_exit_code=30, data=None,
                 errors=[{'code': 'TARGET_NOT_FOUND', 'message': 'Synthetic absence.', 'retryable': False}])
    probes.append(('failure', error, True))
    partial = copy.deepcopy(success)
    partial.update(status='partial', operation_outcome='partially_succeeded', operation_exit_code=2,
                   warnings=[{'code': 'PROPERTY_UNAVAILABLE', 'message': 'Synthetic missing optional property.'}])
    probes.append(('partial', partial, True))
    cancel = copy.deepcopy(error)
    cancel.update(status='cancelled', operation_outcome='unknown', operation_exit_code=40,
                  errors=[{'code': 'CANCELLED', 'message': 'Synthetic cancellation.', 'retryable': False}])
    probes.append(('cancellation', cancel, True))
    for name, key, value in [('missing_field', 'status', None), ('invalid_type', 'duration_ms', '1'),
                              ('wrong_correlation', 'correlation_id', '99999999-9999-4999-8999-999999999999'),
                              ('invalid_timestamp', 'completed_at', '2026-02-30T12:00:00Z')]:
        bad = copy.deepcopy(success)
        if name == 'missing_field':
            del bad[key]
        else:
            bad[key] = value
        probes.append((name, bad, False))
    bad = copy.deepcopy(success)
    bad['data'] = {}
    probes.append(('missing_payload_fields', bad, False))
    outcomes = []
    for name, result, expected in probes:
        accepted = True
        try:
            check_response(result, request, manifest, schemas)
        except Exception:
            accepted = False
        outcomes.append((name, accepted == expected))
    return outcomes


def disposition(checks, requested):
    require(requested in STATES, 'UNKNOWN_STATE')
    if requested == 'APPROVED_RELEASE':
        return 'REJECTED'  # no built-in approval verifier/signing authority
    if requested == 'RETIRED':
        return 'RETIRED'
    if any(c['status'] == 'FAIL' for c in checks) or requested == 'REJECTED':
        return 'REJECTED'
    if any(c['status'] == 'NOT RUN' and c.get('blocking', True) for c in checks):
        return 'DRAFT'
    return 'INDEPENDENT_REVIEW_REQUIRED' if requested == 'INDEPENDENT_REVIEW_REQUIRED' else 'VALIDATED_CANDIDATE'


def validate(package, contract_root, pins, library_root, requested='VALIDATED_CANDIDATE', pwsh=None, catalog=None):
    package, contract_root, library_root = (p.resolve() for p in (package, contract_root, library_root))
    report = {'report_version': 1, 'scope': 'OFFLINE_STATIC_AND_SYNTHETIC_ONLY',
              'operation_id': None, 'contract_version': None, 'package_path': str(package),
              'contract_root': str(contract_root), 'contract_status': 'PROPOSED_NOT_APPROVED',
              'requested_state': requested, 'dispatchable': False, 'checks': [], 'source_hashes': {},
              'runtime_versions': {'python': sys.version.split()[0]}, 'started_at': utc()}
    def check(category, name, work, blocking=True):
        try:
            value = work()
            report['checks'].append({'category': category, 'name': name, 'status': 'PASS', 'blocking': blocking})
            return value
        except MissingDependency:
            report['checks'].append({'category': category, 'name': name, 'status': 'NOT RUN',
                                     'blocking': blocking, 'reason': 'REQUIRED_DEPENDENCY_UNAVAILABLE'})
            return None
        except Exception as exc:
            # Never serialize untrusted source fragments or validation exception contents.
            report['checks'].append({'category': category, 'name': name, 'status': 'FAIL',
                                     'blocking': blocking, 'reason': str(exc) if type(exc) is ValueError and
                                      re.fullmatch('[A-Z_]+', str(exc)) else type(exc).__name__})
            return None
    def not_run(category, name, blocking=True):
        report['checks'].append({'category': category, 'name': name, 'status': 'NOT RUN', 'blocking': blocking})
    schemas = check('contract', 'pinned_local_schemas', lambda: Schemas(contract_root, pins))
    if schemas:
        report['source_hashes'].update(schemas.hashes)
        report['runtime_versions']['jsonschema'] = importlib.metadata.version('jsonschema')
    reference = (package / 'operation.design.json').is_file()
    report['package_kind'] = 'NON_DISPATCHABLE_REFERENCE' if reference else 'MANIFEST_PACKAGE'
    def load():
        require(package.is_dir() and package.is_relative_to(library_root), 'PACKAGE_ROOT')
        path = contained(package, 'operation.design.json' if reference else 'operation.manifest.json')
        design = read(path)
        report['operation_id'], report['contract_version'] = design.get('script_id'), design.get('contract_version')
        require(design.get('contract_version') == VERSION, 'UNSUPPORTED_VERSION')
        require(re.fullmatch(r'M365\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*', design.get('script_id', '')), 'BAD_ID')
        if not reference:
            return design
        require(design.get('status') == 'PROVISIONAL_REFERENCE_ONLY_NOT_A_MANIFEST', 'REFERENCE_STATUS')
        require('script_path' not in design and 'script_sha256' not in design, 'REFERENCE_PROMOTION')
        # Projection in memory only. Placeholder hashes are explicitly NOT approval.
        fixtures = read(contained(contract_root, 'examples/fixtures.json'))['fixtures']
        template = copy.deepcopy(next(f['instance'] for f in fixtures if f['name'] == 'user_identity.manifest'))
        required = set(template) - {'title', 'description', 'tags', 'subcategory', 'script_path', 'script_version', 'script_sha256', 'execution_mode'}
        require(required <= set(design), 'MISSING_DESIGN_FIELDS')
        for key in set(template) & set(design):
            template[key] = design[key]
        template['script_path'] = (package.relative_to(library_root) / design['reference_source']).as_posix().removesuffix('.reference')
        return template
    manifest = check('identity', 'package_identity_and_manifest', load)
    if schemas and manifest:
        check('identity', 'manifest_schema', lambda: schemas.validate('script-manifest', manifest))
        check('parameters', 'descriptor_semantics', lambda: descriptors(manifest, schemas))
        check('contract', 'selected_payload_schema', lambda: schemas.payload(manifest['expected_output_schema'], None))
    def inventory():
        index = read(contained(package, 'SHA256SUMS.json'))
        require(index.get('algorithm') == 'SHA-256' and isinstance(index['files'], dict) and index['files'], 'HASH_INVENTORY')
        for relative, expected in index['files'].items():
            path = contained(package, relative)
            observed = digest(path)
            report['source_hashes'][str(path)] = observed
            require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) and observed == expected, 'HASH_MISMATCH')
        actual = set()
        for path in package.rglob('*'):
            require(not path.is_symlink() and not path.is_junction(), 'REPARSE_PATH')
            if path.is_file():
                actual.add(path.relative_to(package).as_posix())
        require(actual == set(index['files']) | {'SHA256SUMS.json'}, 'UNINVENTORIED_CONTENT')
        report['source_hashes'][str(package / 'SHA256SUMS.json')] = digest(package / 'SHA256SUMS.json')
        return index
    index = check('integrity', 'complete_file_inventory_and_hashes', inventory)
    def source():
        design = read(contained(package, 'operation.design.json')) if reference else manifest
        path = contained(package, design['reference_source']) if reference else contained(library_root, manifest['script_path'])
        require(path.is_relative_to(package), 'SCRIPT_OUTSIDE_PACKAGE')
        if reference:
            require(path.name.endswith('.ps1.reference'), 'REFERENCE_EXTENSION')
            require(not any(p.suffix.casefold() in ('.ps1', '.psm1', '.psd1', '.exe', '.dll', '.bat', '.cmd', '.com', '.vbs')
                            for p in package.iterdir() if p.is_file()), 'UNAUTHORIZED_EXECUTABLE_PROMOTION')
            require("throw 'PROVISIONAL_REFERENCE_ONLY'" in path.read_text(encoding='utf-8'), 'REFERENCE_GUARD')
            test_scripts = {'tests/UserIdentity.Tests.ps1', 'tests/Run-OfflineTests.ps1', 'tests/OfflineHarness.ps1'}
            require(all(p.relative_to(package).as_posix() in test_scripts for p in package.rglob('*.ps1')), 'UNEXPECTED_REFERENCE_EXECUTABLE')
        else:
            require(path.suffix == '.ps1' and digest(path) == manifest['script_sha256'], 'SCRIPT_HASH')
            # No unreviewed secondary executable entrypoints.
            require(not any(p != path and p.suffix.casefold() in ('.ps1', '.psm1', '.psd1', '.exe', '.dll', '.bat', '.cmd')
                            for p in package.rglob('*') if p.is_file()), 'UNEXPECTED_EXECUTABLE')
        require(index is not None and path.relative_to(package).as_posix() in index['files'], 'SCRIPT_NOT_IN_INVENTORY')
        return path
    script = check('security', 'contained_source_and_nonpromotion', source) if manifest else None
    def duplicates():
        if catalog:
            rows = read(catalog)['operations']
            ids = [row['script_id'].casefold() for row in rows]
        else:
            ids = []
            for name in ('operation.design.json', 'operation.manifest.json'):
                for path in library_root.rglob(name):
                    require(not path.is_symlink(), 'CATALOG_LINK')
                    item = read(path)
                    ids.append(item['script_id'].casefold())
        require(len(ids) == len(set(ids)), 'DUPLICATE_OPERATION_ID')
    check('identity', 'unique_operation_identifiers', duplicates)
    def dependencies():
        modules = manifest['required_modules']
        if reference:
            report['declared_dependencies'] = modules
            # Reference declares versions; installed module bytes have not been verified.
            not_run('dependencies', 'installed_module_hashes_and_sdk_compatibility', False)
            return
        lock = read(contained(package, 'dependency-hashes.json')) if modules else {'modules': []}
        require({m['name'].casefold() for m in modules} == {m['name'].casefold() for m in lock['modules']}, 'DEPENDENCY_SET')
        require(len(lock['modules']) == len(modules), 'DUPLICATE_DEPENDENCY')
        for module in lock['modules']:
            spec = next(m for m in modules if m['name'].casefold() == module['name'].casefold())
            require(module['minimum_version'] == spec['minimum_version'] and module['files'], 'DEPENDENCY_VERSION')
            for relative, expected in module['files'].items():
                path = contained(package, relative)
                require(digest(path) == expected and index['files'][relative] == expected, 'DEPENDENCY_HASH')
    if manifest:
        check('dependencies', 'declared_dependency_inventory', dependencies)
    pwsh = pwsh or shutil.which('pwsh')
    if script and pwsh:
        ast = check('abi', 'powershell_ast', lambda: inspect_script(script, pwsh))
        if ast:
            report['runtime_versions'].update(powershell=ast['powershell'], pester=ast['pester'])
            check('abi', 'exact_callable_abi', lambda: check_abi(ast))
            if reference:
                check('security', 'unconditional_reference_guard', lambda: require(
                    ast['first_statement'] == "throw 'PROVISIONAL_REFERENCE_ONLY'", 'REFERENCE_GUARD'))
            check('security', 'static_policy_and_host_auth_boundary', lambda: check_security(ast, script.read_text(encoding='utf-8'), manifest))
    else:
        not_run('abi', 'powershell_ast_dependency_or_source_unavailable')
    if schemas and manifest:
        outcomes = check('results', 'synthetic_probe_setup', lambda: result_probes(manifest, schemas))
        if outcomes:
            for name, passed in outcomes:
                check('results', name, lambda passed=passed: require(passed, 'PROBE_MISMATCH'))
    else:
        not_run('results', 'synthetic_schema_probes')
    not_run('security', 'independent_security_review_and_live_auth', False)
    not_run('tests', 'operation_behavior_tests_not_executed_by_static_validator', False)
    if reference:
        check('release', 'reference_remains_unapproved', lambda: require(requested != 'APPROVED_RELEASE', 'UNAUTHORIZED_APPROVAL'))
    else:
        # A package's own release claims cannot supply independent authority.
        check('release', 'external_release_verifier_required', lambda: require(requested != 'APPROVED_RELEASE', 'UNSUPPORTED_APPROVAL_VERIFICATION'))
        not_run('release', 'external_approval_evidence_missing_or_unverified', False)
    report['final_disposition'] = disposition(report['checks'], requested)
    report['validation_status'] = ('FAIL' if any(c['status'] == 'FAIL' for c in report['checks']) else
                                   'NOT RUN' if report['final_disposition'] == 'DRAFT' else 'PASS')
    report['blocking_findings'] = [c for c in report['checks'] if c['blocking'] and c['status'] != 'PASS']
    report['completed_at'] = utc()
    report['source_hashes'].update({str(p): digest(p) for p in HERE.iterdir() if p.suffix in ('.py', '.ps1')})
    return report


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def save_report(report, destination, protected):
    destination = destination.resolve()
    require(not any(destination.is_relative_to(p.resolve()) for p in protected), 'OUTPUT_INSIDE_PROTECTED_INPUT')
    require(not any((parent / name).exists() for parent in destination.parents for name in
                    ('operation.design.json', 'operation.manifest.json', 'SHA256SUMS.json')), 'OUTPUT_INSIDE_OPERATION_PACKAGE')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--library-root', type=Path, required=True)
    parser.add_argument('--contract-root', type=Path, required=True)
    parser.add_argument('--contract-pins', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--state', choices=STATES, default='VALIDATED_CANDIDATE')
    parser.add_argument('--pwsh')
    args = parser.parse_args()
    try:
        report = validate(args.package, args.contract_root, args.contract_pins, args.library_root,
                          args.state, args.pwsh, args.catalog)
        save_report(report, args.report, (args.package, args.contract_root))
        print(json.dumps({'report': str(args.report), 'status': report['validation_status'],
                          'disposition': report['final_disposition'], 'dispatchable': False}))
        return {'PASS': 0, 'FAIL': 1, 'NOT RUN': 2}[report['validation_status']]
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'reason': type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
