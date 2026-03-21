from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
import zipfile

import yaml
from fastapi import HTTPException, UploadFile, status

from ..config import settings
from ..services.scan import run_basic_scan

MAX_PACKAGE_SIZE = 20 * 1024 * 1024


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


def _find_manifest(archive: zipfile.ZipFile) -> tuple[str, dict]:
    manifest_names = ("skill.yaml", "skill.yml", "skill.json", "manifest.json")
    archive_names = {name: name.lower() for name in archive.namelist()}
    for original_name, lowered in archive_names.items():
        if lowered.endswith(manifest_names):
            raw = archive.read(original_name)
            if lowered.endswith((".yaml", ".yml")):
                return original_name, yaml.safe_load(raw.decode("utf-8"))
            return original_name, json.loads(raw.decode("utf-8"))
    raise _error("INVALID_PACKAGE", "Package manifest is missing", status.HTTP_422_UNPROCESSABLE_ENTITY)


def _validate_manifest(manifest: dict, skill_name: str, version: str) -> dict:
    if not isinstance(manifest, dict):
        raise _error("INVALID_PACKAGE", "Manifest format is invalid", status.HTTP_422_UNPROCESSABLE_ENTITY)

    manifest_name = str(manifest.get("name", "")).strip().lower()
    manifest_version = str(manifest.get("version", "")).strip()
    if manifest_name and manifest_name != skill_name:
        raise _error("INVALID_PACKAGE", "Manifest skill name does not match target skill", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if manifest_version and manifest_version != version:
        raise _error("INVALID_PACKAGE", "Manifest version does not match request version", status.HTTP_422_UNPROCESSABLE_ENTITY)
    manifest["name"] = skill_name
    manifest["version"] = version
    return manifest


async def validate_and_store_package(skill_name: str, version: str, package: UploadFile) -> dict:
    filename = package.filename or f"{skill_name}-{version}.zip"
    if not filename.lower().endswith(".zip"):
        raise _error("INVALID_PACKAGE", "Only zip packages are supported", status.HTTP_422_UNPROCESSABLE_ENTITY)

    content = await package.read()
    if not content:
        raise _error("INVALID_PACKAGE", "Package is empty", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if len(content) > MAX_PACKAGE_SIZE:
        raise _error("INVALID_PACKAGE", "Package exceeds the 20MB size limit", status.HTTP_422_UNPROCESSABLE_ENTITY)
    if not zipfile.is_zipfile(BytesIO(content)):
        raise _error("INVALID_PACKAGE", "Uploaded file is not a valid zip archive", status.HTTP_422_UNPROCESSABLE_ENTITY)

    with zipfile.ZipFile(BytesIO(content), "r") as archive:
        _, manifest = _find_manifest(archive)
        normalized_manifest = _validate_manifest(manifest, skill_name, version)
    scan_summary, scan_detail = run_basic_scan(content, normalized_manifest)

    digest = hashlib.sha256(content).hexdigest()
    storage_root: Path = settings.package_storage_root
    target_dir = storage_root / skill_name / version
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "bundle.zip"
    target_path.write_bytes(content)

    return {
        "package_filename": filename,
        "package_path": str(target_path),
        "package_size": len(content),
        "package_hash": f"sha256:{digest}",
        "manifest_json": normalized_manifest,
        "scan_summary": scan_summary,
        "scan_detail": scan_detail,
    }
