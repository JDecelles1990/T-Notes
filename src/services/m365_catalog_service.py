"""Read-only M365 presentation catalog. No execution, auth or database capability."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import stat


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "docs/contracts/m365"
VERSION = "0.3.0"
SCHEMAS = ("common", "script-manifest", "execution-request", "execution-result",
           "error", "company-profile", "operation-data")
RESERVED = set("context parameters cancellationtoken verbose debug erroraction warningaction "
               "informationaction progressaction errorvariable warningvariable informationvariable "
               "outvariable outbuffer pipelinevariable whatif confirm".split())


class CatalogError(ValueError):
    """A safe local metadata rejection, never an execution result."""


def _reject(message="Invalid catalog metadata."):
    raise CatalogError(message)


def _json(path: Path, limit=65536):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _reject("Duplicate JSON keys.")
            result[key] = value
        return result

    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit or raw.startswith(b"\xef\xbb\xbf"):
            _reject("Metadata exceeds its limit or has a BOM.")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: _reject("Nonfinite metadata."))
        def check(item, depth=0):
            if depth > 20 or isinstance(item, float) and not math.isfinite(item):
                _reject("Invalid metadata nesting or number.")
            for child in (item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()):
                check(child, depth + 1)
        check(data)
        if not isinstance(data, dict):
            _reject()
        return data, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError("Metadata cannot be read as strict bounded JSON.") from exc


def _contained(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_./-]*", relative):
        _reject("Invalid relative library path.")
    if any(part in ("", ".", "..") or part.endswith(".") for part in relative.split("/")):
        _reject("Invalid library path segments.")
    # Check the root and each ancestor too: resolve() alone hides junctions.
    candidate = root / relative
    for path in (candidate, *candidate.parents):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _reject("Linked or reparse library paths are unavailable.")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        _reject("Library file is outside its root.")
    return resolved


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str
    icon: str
    order: int
    kind: str


@dataclass(frozen=True)
class Operation:
    id: str
    title: str
    description: str
    category_ids: tuple[str, ...]
    risk: str
    lifecycle: str
    search_text: str
    details: str
    disabled_reasons: tuple[str, ...]

    @property
    def eligible(self):
        return False  # This service cannot authorize anything, including future manifests.


class ManifestValidator:
    """Provisional schema compatibility only; pins are review identity, not approval."""

    def __init__(self, contract_root: Path, pins_path: Path):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        pins, _ = _json(pins_path)
        if pins.get("contract_version") != VERSION or set(pins.get("schemas", {})) != set(SCHEMAS):
            _reject("Contract review inventory is invalid.")
        self.schemas = {}
        registry = Registry()  # No retrieve callback: unknown/remote refs fail closed.
        prefix = f"https://tnotes.invalid/m365/{VERSION}/schemas/"
        for name in SCHEMAS:
            path = _contained(contract_root, f"schemas/{name}.schema.json")
            schema, digest = _json(path, 262144)
            if digest != pins["schemas"][name] or schema.get("$id") != prefix + name + ".schema.json":
                _reject("Contract review identity changed; re-review required.")
            Draft202012Validator.check_schema(schema)
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
            self.schemas[name] = schema
        self.validator = Draft202012Validator(self.schemas["script-manifest"], registry=registry)
        self.registry = registry

    def validate(self, manifest):
        if not self.validator.is_valid(manifest):
            _reject("Manifest does not match the provisional contract schema.")
        if manifest["graph_scopes"] and "Graph" not in manifest["connection_requirements"]:
            _reject("Graph scopes require a Graph connection.")
        if any(role["service"] not in manifest["connection_requirements"] for role in manifest["required_roles"]):
            _reject("RBAC service has no connection requirement.")
        schema_path, pointer = manifest["expected_output_schema"].split("#", 1)
        name = schema_path.removeprefix("schemas/").removesuffix(".schema.json")
        selected = self.schemas.get(name)
        if selected is None:
            _reject("Unknown output schema.")
        for part in pointer.lstrip("/").split("/"):
            if not isinstance(selected, dict) or part not in selected:
                _reject("Unknown output schema definition.")
            selected = selected[part]
        # Entry schemas deliberately delegate their definitions to common.schema.json.
        for _ in range(10):
            if "$ref" not in selected:
                break
            selected = self.registry.resolver().lookup(selected["$ref"]).contents
        else:
            _reject("Cyclic output schema definition.")
        fields = selected.get("properties", {})
        for kind in manifest["target_policy"]["accepted_kinds"]:
            field = manifest["target_policy"]["output_binding"]["upn_field" if kind == "upn" else "object_id_field"]
            if field not in fields:
                _reject("Target output binding is absent from the selected schema.")
        names = [p["name"].casefold() for p in manifest["parameters"]]
        if len(names) != len(set(names)) or set(names) & RESERVED:
            _reject("Duplicate or reserved parameter names.")
        for spec in manifest["parameters"]:
            for low, high in (("minimum", "maximum"), ("min_length", "max_length"),
                              ("min_items", "max_items"), ("item_min_length", "item_max_length")):
                if low in spec and high in spec and spec[low] > spec[high]:
                    _reject("Inverted parameter bounds.")
            if spec["type"] == "integer" and any(type(spec[k]) is not int for k in ("minimum", "maximum") if k in spec):
                _reject("Integer bounds must be integers.")
            values = spec.get("allowed_values", [])
            if len(values) != len({json.dumps(v, sort_keys=True) for v in values}):
                _reject("Duplicate allowed values.")
            for value in values + ([spec["default"]] if "default" in spec else []):
                if not self._parameter_value(spec, value):
                    _reject("Invalid parameter default or allowed value.")

    @staticmethod
    def _parameter_value(spec, value):
        kind = spec["type"]
        if kind == "integer":
            valid = type(value) is int and -(2**63) <= value < 2**63
        elif kind == "number":
            valid = type(value) in (int, float) and abs(value) <= 1.7976931348623157e308
        elif kind == "boolean":
            valid = type(value) is bool
        elif kind == "string":
            valid = isinstance(value, str) and spec.get("min_length", 0) <= len(value) <= spec.get("max_length", 4096)
        else:
            valid = (isinstance(value, list) and spec.get("min_items", 0) <= len(value) <= spec.get("max_items", 1000)
                     and all(isinstance(v, str) and spec.get("item_min_length", 0) <= len(v) <= spec.get("item_max_length", 4096) for v in value))
        if not valid:
            return False
        if kind in ("integer", "number") and not spec.get("minimum", -math.inf) <= value <= spec.get("maximum", math.inf):
            return False
        return "allowed_values" not in spec or value in spec["allowed_values"]


class M365CatalogService:
    """Immutable category and unavailable-operation snapshots for the GUI."""

    def __init__(self, metadata_root=None, library_root=None, contract_root=None, *, catalog_data=None):
        metadata_root = Path(metadata_root) if metadata_root is not None else ROOT / "assets/m365"
        library_root = Path(library_root) if library_root is not None else ROOT / "scripts/m365"
        contract_root = Path(contract_root) if contract_root is not None else CONTRACT_ROOT
        data, _ = _json(metadata_root / "categories.json")
        if set(data) != {"format_version", "categories"} or type(data["format_version"]) is not int or data["format_version"] != 1:
            _reject("Unsupported category registry.")
        self.categories = self._categories(data["categories"])
        self._by_category = {c.id: c for c in self.categories}
        if catalog_data is None:
            data, _ = _json(metadata_root / "catalog.json")
        else:
            data = catalog_data
        if (set(data) != {"format_version", "operations"} or type(data["format_version"]) is not int
                or data["format_version"] != 1 or not isinstance(data["operations"], list) or len(data["operations"]) > 1000):
            _reject("Unsupported operation registry.")
        pending, errors = [], []
        validator = None
        if data["operations"]:
            validator = ManifestValidator(contract_root, metadata_root / "contract-review-pins.json")
        for entry in data["operations"]:
            try:
                pending.append(self._operation(entry, library_root, validator))
            except (CatalogError, OSError):
                errors.append("Operation metadata rejected; review the catalog registration and manifest.")
        counts = Counter(op.id for op in pending)
        self._operations = {op.id: op for op in pending if counts[op.id] == 1}
        if any(n > 1 for n in counts.values()):
            errors.append("Duplicate operation IDs rejected, including every conflicting registration.")
        self.validation_errors = tuple(errors)

    @staticmethod
    def _categories(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            _reject("Invalid category list.")
        result = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "label", "description", "icon", "order", "kind"}:
                _reject("Invalid category fields.")
            if (not isinstance(item["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", item["id"])
                    or any(not isinstance(item[k], str) or not item[k].strip() or len(item[k]) > 1024 for k in ("label", "description", "icon"))
                    or type(item["order"]) is not int or item["order"] < 0 or item["kind"] not in ("view", "operations", "workflow")):
                _reject("Invalid category values.")
            result.append(Category(**item))
        for field in ("id", "order", "label"):
            if len({getattr(c, field) for c in result}) != len(result):
                _reject("Duplicate category metadata.")
        return tuple(sorted(result, key=lambda c: c.order))

    def _operation(self, entry, library_root, validator):
        if (not isinstance(entry, dict) or set(entry) != {"manifest_path", "manifest_sha256", "category_ids", "lifecycle"}
                or entry["lifecycle"] not in ("active", "deprecated", "archived")
                or not isinstance(entry["manifest_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["manifest_sha256"])):
            _reject()
        categories = entry["category_ids"]
        if (not isinstance(categories, list) or not categories or not all(isinstance(c, str) for c in categories)
                or len(categories) != len(set(categories))
                or any(c not in self._by_category or self._by_category[c].kind != "operations" for c in categories)):
            _reject("Unknown, duplicate or non-operation category reference.")
        path = _contained(library_root, entry["manifest_path"])
        manifest, digest = _json(path)
        if digest != entry["manifest_sha256"]:
            _reject("Manifest review identity mismatch.")
        validator.validate(manifest)
        if manifest["category"] != categories[0]:
            _reject("Primary category must match the manifest's stable category ID.")
        # No script read/import/hash approval here. That belongs to future independent trust validation.
        reasons = ("Contract approval pending.", "Executable trust and approval are not verified.",
                   "Target, service connections, permissions and RBAC are not verified.",
                   "Execution is disconnected in this catalog.")
        if entry["lifecycle"] != "active":
            reasons += (f"Operation is {entry['lifecycle']}.",)
        summary = {"operation_id": manifest["script_id"], "version": manifest["script_version"],
                   "contract_version": manifest["contract_version"], "risk": manifest["risk"],
                   "lifecycle": entry["lifecycle"], "manifest_sha256": digest,
                   **{k: manifest[k] for k in ("script_path", "script_sha256", "supported_powershell", "required_modules",
                       "target_policy", "connection_requirements", "graph_scopes", "required_roles", "parameters",
                       "expected_output_schema", "timeout_seconds", "cancellation_support", "data_sensitivity", "approval_requirements")}}
        search = " ".join([manifest["script_id"], manifest["title"], manifest["description"], manifest["risk"],
                           *manifest.get("tags", []), *categories, *manifest["connection_requirements"],
                           *(m["name"] for m in manifest["required_modules"])]).casefold()
        return Operation(manifest["script_id"], manifest["title"], manifest["description"], tuple(categories),
                         manifest["risk"], entry["lifecycle"], search, json.dumps(summary, ensure_ascii=False, indent=2), reasons)

    def category(self, category_id):
        try:
            return self._by_category[category_id]
        except KeyError as exc:
            raise CatalogError("Unknown category ID.") from exc

    def operations(self, category_id, query="", risk="all", lifecycle="current"):
        self.category(category_id)
        if risk not in ("all", "read_only", "write", "high_impact") or lifecycle not in ("current", "archived", "all"):
            _reject("Unknown catalog filter.")
        words = query.casefold().split()
        return tuple(sorted((op for op in self._operations.values()
                             if category_id in op.category_ids and all(word in op.search_text for word in words)
                             and (risk == "all" or op.risk == risk)
                             and (lifecycle == "all" or (op.lifecycle == "archived") == (lifecycle == "archived"))),
                            key=lambda op: (op.title.casefold(), op.id)))

    def operation(self, operation_id):
        try:
            return self._operations[operation_id]
        except KeyError as exc:
            raise CatalogError("Unknown or invalid operation ID.") from exc
