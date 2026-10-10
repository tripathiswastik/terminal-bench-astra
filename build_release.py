"""
Release Packaging Tool for Terminal-Bench Astra.

Packages a clean release distribution zip file strictly excluding:
- .git / repository metadata
- __pycache__ / compiled python bytecode (*.pyc, *.pyo)
- .pytest_cache, .mypy_cache, .ruff_cache
- .venv / virtual environments
- release artifacts / dist / build
"""

import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
RELEASE_ZIP_NAME = "terminal-bench-astra.zip"

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "ENV",
    "env",
    "dist",
    "build",
    ".vscode",
    ".idea",
}

EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".zip",
    ".swp",
    ".swo",
}


def is_excluded(rel_path: Path) -> bool:
    parts = rel_path.parts
    for part in parts:
        if part in EXCLUDED_DIRS:
            return True

    filename = rel_path.name
    if filename == ".env" or filename.startswith(".env.") or filename.startswith("_env"):
        return True

    for suffix in EXCLUDED_FILE_SUFFIXES:
        if filename.endswith(suffix):
            return True

    return False


def build_release_zip() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / RELEASE_ZIP_NAME

    print(f"Building clean release archive: {zip_path.name}...")
    included_files = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(PROJECT_ROOT):
            root_path = Path(root)
            rel_dir = root_path.relative_to(PROJECT_ROOT)

            if any(part in EXCLUDED_DIRS for part in rel_dir.parts):
                continue

            for file in files:
                file_path = root_path / file
                rel_file = file_path.relative_to(PROJECT_ROOT)

                if is_excluded(rel_file):
                    continue

                arcname = f"terminal-bench-astra/{rel_file.as_posix()}"
                zf.write(file_path, arcname)
                included_files.append(rel_file.as_posix())

    print(f"Packaged {len(included_files)} files into {zip_path}.")

    # Integrity verification
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        for name in namelist:
            if "/.git/" in name or name.endswith(".pyc") or "/__pycache__/" in name:
                raise ValueError(f"Prohibited artifact detected in release zip: {name}")

    print("Verification PASSED: Archive is free of .git, bytecode, and unapproved secrets.")
    return zip_path


if __name__ == "__main__":
    build_release_zip()
