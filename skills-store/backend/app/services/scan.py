from __future__ import annotations

from io import BytesIO
import re
import zipfile


BLOCKED_CODE_PATTERNS: dict[str, re.Pattern[str]] = {
    "python_eval": re.compile(r"(?<!\w)eval\s*\(", re.IGNORECASE),
    "python_exec": re.compile(r"(?<!\w)exec\s*\(", re.IGNORECASE),
    "pickle_loads": re.compile(r"pickle\s*\.\s*loads\s*\(", re.IGNORECASE),
    "os_system": re.compile(r"os\s*\.\s*system\s*\(", re.IGNORECASE),
    "subprocess_shell": re.compile(r"subprocess\s*\.\s*(run|Popen|call)\s*\([^)]*shell\s*=\s*True", re.IGNORECASE | re.DOTALL),
}

TEXT_SCAN_SUFFIXES = (
    ".py",
    ".pyw",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
    ".md",
    ".sh",
)


def run_basic_scan(package_bytes: bytes, manifest: dict) -> tuple[dict, dict]:
    issues: list[dict[str, str]] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    required_fields = ("name", "version")
    missing_fields = [field for field in required_fields if not manifest.get(field)]
    if missing_fields:
        issues.append(
            {
                "name": "manifest_required_fields",
                "message": f"Missing required manifest fields: {', '.join(missing_fields)}",
            }
        )
        checks.append({"name": "manifest_required_fields", "result": "failed"})
    else:
        checks.append({"name": "manifest_required_fields", "result": "passed"})

    with zipfile.ZipFile(BytesIO(package_bytes), "r") as archive:
        names = archive.namelist()
        checks.append(
            {
                "name": "archive_not_empty",
                "result": "passed" if names else "failed",
            }
        )
        if not names:
            issues.append({"name": "archive_not_empty", "message": "Archive contains no files"})

        forbidden_suffixes = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh")
        risky_files = [name for name in names if name.lower().endswith(forbidden_suffixes)]
        if risky_files:
            warnings.extend([f"Potentially risky file detected: {name}" for name in risky_files[:10]])
            checks.append({"name": "forbidden_suffix_scan", "result": "warning"})
        else:
            checks.append({"name": "forbidden_suffix_scan", "result": "passed"})

        compressed_size = sum(item.file_size for item in archive.infolist())
        if compressed_size > 20 * 1024 * 1024:
            issues.append({"name": "archive_size", "message": "Expanded archive size exceeds the allowed limit"})
            checks.append({"name": "archive_size", "result": "failed"})
        else:
            checks.append({"name": "archive_size", "result": "passed"})

        dangerous_hits: list[str] = []
        for name in names:
            lowered = name.lower()
            if not lowered.endswith(TEXT_SCAN_SUFFIXES):
                continue
            try:
                content = archive.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for rule_name, pattern in BLOCKED_CODE_PATTERNS.items():
                if pattern.search(content):
                    dangerous_hits.append(f"{name}: {rule_name}")

        if dangerous_hits:
            issues.append(
                {
                    "name": "dangerous_code_patterns",
                    "message": "Dangerous code patterns detected",
                }
            )
            warnings.extend([f"Blocked pattern detected: {item}" for item in dangerous_hits[:20]])
            checks.append({"name": "dangerous_code_scan", "result": "failed"})
        else:
            checks.append({"name": "dangerous_code_scan", "result": "passed"})

    scan_status = "passed" if not issues else "failed"
    risk_level = "low"
    if issues:
        risk_level = "medium"
    elif warnings:
        risk_level = "low"

    summary = {
        "status": scan_status,
        "risk_level": risk_level,
        "issues": issues,
        "warnings": warnings,
        "scanner_version": "0.1.0",
    }
    detail = {
        "checks": checks,
        "warnings": warnings,
        "errors": issues,
    }
    return summary, detail
