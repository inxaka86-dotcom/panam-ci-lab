#!/usr/bin/env python3
"""Public-only static qualification for exact-pinned CLI-Anything LibreOffice files.

This script never imports or executes upstream code. It inspects selected public
source files and emits evidence for a later isolated pilot decision.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

UPSTREAM_COMMIT = "810c18b0d1ab9b234bc996c9fd999318523a3ef0"


def read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def subprocess_run_shell_true(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        is_run = (
            isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "subprocess"
            and fn.attr == "run"
        )
        if not is_run:
            continue
        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                return True
    return False


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing expected upstream property: {label}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    security = read(root, "SECURITY.md")
    harness = read(root, "HARNESS.md")
    skill = read(root, "SKILL.md")
    backend = read(root, "lo_backend.py")
    export = read(root, "export.py")
    importer = read(root, "importer.py")

    require(security, "NOT part of the CLI generation methodology", "security guidance is outside generation SOP")
    require(security, "Never use `shell=True`", "upstream no-shell security guidance")
    require(security, "Validate all subprocess arguments", "subprocess allowlist guidance")
    require(harness, "Phase 7: PyPI Publishing and Installation", "publishing/install methodology")
    require(harness, "subprocess.run()", "real backend subprocess methodology")
    require(skill, "Interactive REPL Session", "persistent interactive surface")
    require(skill, "pip install cli-anything-libreoffice", "package installation surface")
    require(skill, "Use absolute paths for all file operations", "agent-controlled absolute path guidance")

    require(backend, "_HEADLESS_FLAGS", "bounded headless flag set")
    require(backend, "TemporaryDirectory(prefix=\"lo-profile-\")", "isolated LibreOffice profile")
    require(backend, "subprocess.run(", "LibreOffice subprocess integration")
    require(export, "EXPORT_PRESETS", "export preset map")
    require(export, '"pdf":', "PDF preset")
    require(export, '"docx":', "DOCX preset")
    require(export, "overwrite", "overwrite capability")
    require(importer, "defusedxml", "defused XML parser")
    require(importer, "OFFICE_EXTENSION_CONVERSIONS", "import extension allowlist")
    require(importer, 'project["metadata"]["source_path"] = os.path.abspath(path)', "absolute source path persistence")

    if subprocess_run_shell_true(backend):
        raise AssertionError("pinned LibreOffice backend contains subprocess.run(..., shell=True)")
    for forbidden in ("os.system(", "eval(", "exec("):
        if forbidden in backend:
            raise AssertionError(f"unexpected backend primitive: {forbidden}")

    selected_path_sources = "\n".join((backend, export, importer))
    sandbox_containment_detected = any(
        marker in selected_path_sources
        for marker in ("relative_to(", "os.path.commonpath(", "Path.is_relative_to(")
    )

    report = {
        "schema": "panam-public.cli-anything-libreoffice-static-qualification.v1",
        "upstream_commit": UPSTREAM_COMMIT,
        "public_source_only": True,
        "upstream_code_executed": False,
        "static_qualification_passed": True,
        "positive_controls": {
            "upstream_security_threat_model": True,
            "no_shell_true_in_selected_libreoffice_backend": True,
            "temporary_libreoffice_profile": True,
            "export_preset_map": True,
            "defusedxml_import_parser": True,
            "import_extension_allowlist": True,
        },
        "panam_gaps": {
            "security_guidance_outside_agent_generation_sop": True,
            "repl_and_persistent_state_surface_present": True,
            "package_install_and_publish_surface_present": True,
            "existing_document_import_surface_present": True,
            "overwrite_surface_present": True,
            "absolute_path_guidance_present": True,
            "sandbox_containment_detected_in_selected_files": sandbox_containment_detected,
        },
        "automatic_adoption": False,
        "production_authority": False,
        "owner_review_required": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    print("PANAM_PUBLIC_CLI_ANYTHING_LIBREOFFICE_STATIC_QUALIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
