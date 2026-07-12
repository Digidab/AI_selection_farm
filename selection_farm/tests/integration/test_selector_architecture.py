import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "services" / "selector" / "app"
BRANCHES = frozenset({"core", "llm", "ml"})
FORBIDDEN_IMPORTS = {
    "core": frozenset({"llm", "ml"}),
    "llm": frozenset({"ml"}),
    "ml": frozenset({"llm"}),
}
LEGACY_FLAT_MODULES = frozenset(
    {
        "config.py",
        "dataset_writer.py",
        "db.py",
        "embedding_client.py",
        "logging_config.py",
        "main.py",
        "ollama_client.py",
        "schemas.py",
        "validators.py",
    }
)
PACKAGE_READMES = (
    "core/README.md",
    "llm/README.md",
    "llm/pipelines/README.md",
    "llm/runtimes/README.md",
    "llm/modalities/README.md",
    "llm/output_contracts/README.md",
    "llm/evaluators/README.md",
    "ml/README.md",
    "ml/pipelines/README.md",
)


def _target_branch(parts: tuple[str, ...]) -> str | None:
    if parts and parts[0] in BRANCHES:
        return parts[0]

    for index, part in enumerate(parts[:-1]):
        if part == "app" and parts[index + 1] in BRANCHES:
            return parts[index + 1]
    return None


def _import_candidates(
    node: ast.Import | ast.ImportFrom,
    source: Path,
    app_root: Path,
) -> tuple[tuple[str, ...], ...]:
    if isinstance(node, ast.Import):
        return tuple(tuple(alias.name.split(".")) for alias in node.names)

    module_parts = tuple(node.module.split(".")) if node.module else ()
    if node.level:
        package_parts = source.relative_to(app_root).with_suffix("").parts[:-1]
        parent_count = max(0, len(package_parts) - (node.level - 1))
        base_parts = package_parts[:parent_count] + module_parts
    else:
        base_parts = module_parts

    aliases = tuple(base_parts + tuple(alias.name.split(".")) for alias in node.names)
    return (base_parts, *aliases)


def find_forbidden_imports(app_root: Path) -> list[str]:
    violations: list[str] = []
    for source in sorted(app_root.rglob("*.py")):
        relative = source.relative_to(app_root)
        source_branch = relative.parts[0]
        if source_branch not in BRANCHES:
            continue

        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            targets = {
                target
                for parts in _import_candidates(node, source, app_root)
                if (target := _target_branch(parts)) is not None
            }
            for target in sorted(targets & FORBIDDEN_IMPORTS[source_branch]):
                violations.append(f"{relative}:{node.lineno}: {source_branch} -> {target}")
    return violations


def test_selector_packages_import() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import services.selector.app.core, services.selector.app.llm, services.selector.app.ml",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_scaffold_has_readmes_and_no_legacy_flat_modules() -> None:
    missing_readmes = [path for path in PACKAGE_READMES if not (APP_ROOT / path).is_file()]
    remaining_legacy = sorted(
        path.name for path in APP_ROOT.iterdir() if path.name in LEGACY_FLAT_MODULES
    )

    assert not missing_readmes
    assert not remaining_legacy


def test_selector_import_graph_is_isolated() -> None:
    assert find_forbidden_imports(APP_ROOT) == []


def test_import_guard_rejects_seeded_violations(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    for branch in BRANCHES:
        (app_root / branch).mkdir(parents=True)

    (app_root / "core" / "bad.py").write_text("from ..llm import main\n", encoding="utf-8")
    (app_root / "llm" / "bad.py").write_text("import services.selector.app.ml\n", encoding="utf-8")
    (app_root / "ml" / "bad.py").write_text(
        "from services.selector.app import llm\n", encoding="utf-8"
    )

    violations = find_forbidden_imports(app_root)

    assert len(violations) == 3
    assert any("core -> llm" in violation for violation in violations)
    assert any("llm -> ml" in violation for violation in violations)
    assert any("ml -> llm" in violation for violation in violations)
