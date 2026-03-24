"""Local skill registry management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .models import InstalledSkill, SkillManifest


class SkillRegistry:
    """Manages the local registry of installed skills."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.home() / ".socialhub"
        self.skills_dir = self.base_dir / "skills"
        self.installed_dir = self.skills_dir / "installed"
        self.cache_dir = self.skills_dir / "cache"
        self.registry_file = self.skills_dir / "registry.json"

        # Ensure directories exist
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.installed_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)

    def _load_registry(self) -> dict:
        """Load registry from file."""
        if not self.registry_file.exists():
            return {"skills": {}, "updated_at": None}

        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {"skills": {}, "updated_at": None}

    def _save_registry(self, data: dict) -> None:
        """Save registry to file."""
        data["updated_at"] = datetime.now().isoformat()
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def list_installed(self) -> list[InstalledSkill]:
        """List all installed skills."""
        registry = self._load_registry()
        skills = []

        for name, data in registry.get("skills", {}).items():
            try:
                skill = InstalledSkill(**data)
                skills.append(skill)
            except Exception:
                continue

        return skills

    def get_installed(self, name: str) -> Optional[InstalledSkill]:
        """Get an installed skill by name."""
        registry = self._load_registry()
        data = registry.get("skills", {}).get(name)

        if data:
            try:
                return InstalledSkill(**data)
            except Exception:
                return None
        return None

    def is_installed(self, name: str) -> bool:
        """Check if a skill is installed."""
        return self.get_installed(name) is not None

    def get_installed_version(self, name: str) -> Optional[str]:
        """Get the installed version of a skill."""
        skill = self.get_installed(name)
        return skill.version if skill else None

    def register_skill(self, skill: InstalledSkill) -> None:
        """Register an installed skill."""
        registry = self._load_registry()

        if "skills" not in registry:
            registry["skills"] = {}

        registry["skills"][skill.name] = skill.model_dump()
        self._save_registry(registry)

    def unregister_skill(self, name: str) -> bool:
        """Unregister a skill."""
        registry = self._load_registry()

        if name in registry.get("skills", {}):
            del registry["skills"][name]
            self._save_registry(registry)
            return True
        return False

    def update_skill(self, name: str, **updates) -> bool:
        """Update skill registration."""
        registry = self._load_registry()

        if name in registry.get("skills", {}):
            registry["skills"][name].update(updates)
            self._save_registry(registry)
            return True
        return False

    def enable_skill(self, name: str) -> bool:
        """Enable a skill."""
        return self.update_skill(name, enabled=True)

    def disable_skill(self, name: str) -> bool:
        """Disable a skill."""
        return self.update_skill(name, enabled=False)

    def get_skill_path(self, name: str) -> Path:
        """Get the installation path for a skill."""
        return self.installed_dir / name

    def get_cache_path(self, name: str, version: str) -> Path:
        """Get the cache path for a skill package."""
        return self.cache_dir / f"{name}-{version}.zip"

    def clear_cache(self) -> int:
        """Clear the download cache. Returns number of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.zip"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        return count

    def get_stats(self) -> dict:
        """Get registry statistics."""
        skills = self.list_installed()
        return {
            "total_installed": len(skills),
            "enabled": sum(1 for s in skills if s.enabled),
            "disabled": sum(1 for s in skills if not s.enabled),
            "by_category": self._count_by_category(skills),
        }

    def _count_by_category(self, skills: list[InstalledSkill]) -> dict[str, int]:
        """Count skills by category."""
        counts: dict[str, int] = {}
        for skill in skills:
            cat = skill.category.value if hasattr(skill.category, "value") else str(skill.category)
            counts[cat] = counts.get(cat, 0) + 1
        return counts
