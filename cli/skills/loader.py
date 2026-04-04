"""Skill loader and runtime execution."""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from .models import SkillCommand, SkillManifest
from .registry import SkillRegistry
from .sandbox import SandboxManager
from .security import (
    PermissionChecker,
    PermissionContext,
    PermissionStore,
    SecurityError,
)


class SkillLoadError(Exception):
    """Skill loading error."""

    pass


class SkillLoader:
    """Load and execute installed skills."""

    def __init__(self):
        self.registry = SkillRegistry()
        self.permission_checker = PermissionChecker()
        self.permission_store = PermissionStore()
        self._loaded_skills: dict[str, dict[str, Any]] = {}
        self._permission_contexts: dict[str, PermissionContext] = {}

    def load_skill(self, name: str) -> dict[str, Any]:
        """Load a skill module.

        Args:
            name: Skill name

        Returns:
            Dict containing skill module and metadata
        """
        # Check cache
        if name in self._loaded_skills:
            return self._loaded_skills[name]

        # Get installed skill
        installed = self.registry.get_installed(name)
        if not installed:
            raise SkillLoadError(f"Skill '{name}' is not installed")

        if not installed.enabled:
            raise SkillLoadError(f"Skill '{name}' is disabled")

        # Load manifest
        skill_path = Path(installed.path)
        manifest_path = skill_path / "skill.yaml"

        if not manifest_path.exists():
            # Fallback: bundled skills live in the source tree under cli/skills/store/<name>/
            # If the registry has a stale absolute path (e.g. after a directory move), try to
            # locate the skill relative to this loader module and auto-heal the registry.
            _source_fallback = Path(__file__).parent / "store" / name
            if (_source_fallback / "skill.yaml").exists():
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Skill '%s': registry path '%s' not found, "
                    "falling back to source tree '%s' and updating registry.",
                    name, skill_path, _source_fallback,
                )
                skill_path = _source_fallback
                manifest_path = skill_path / "skill.yaml"
                self.registry.update_skill(name, path=str(skill_path))
            else:
                raise SkillLoadError(f"Skill manifest not found: {manifest_path}")

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest_data = yaml.safe_load(f)
            manifest = SkillManifest(**manifest_data)
        except Exception as e:
            raise SkillLoadError(f"Failed to load skill manifest: {e}")

        # Check permissions - load from persistent store first
        stored_permissions = self.permission_store.get_permissions(name, version=manifest.version)
        for perm in stored_permissions:
            self.permission_checker.grant_permission(name, perm)

        if manifest.permissions:
            required_perms = [p.value for p in manifest.permissions]
            granted, missing = self.permission_checker.check_permissions(
                name, required_perms
            )
            if not granted:
                # Filter out safe permissions from missing list
                truly_missing = [
                    p for p in missing
                    if p not in self.permission_checker.SAFE_PERMISSIONS
                ]
                if truly_missing:
                    raise SecurityError(
                        f"Skill '{name}' requires permissions that have not been granted: "
                        f"{', '.join(truly_missing)}. "
                        "Please reinstall the skill to grant permissions."
                    )

        # Load Python module
        entrypoint_path = skill_path / manifest.entrypoint

        if not entrypoint_path.exists():
            raise SkillLoadError(f"Skill entrypoint not found: {entrypoint_path}")

        spec = importlib.util.spec_from_file_location(
            f"socialhub_skill_{name}",
            entrypoint_path,
        )
        if spec is None or spec.loader is None:
            raise SkillLoadError(f"Failed to load skill module: {entrypoint_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        # Load Python module under sandbox to prevent module-level code escaping
        _load_sandbox = SandboxManager(
            skill_name=name,
            permissions=[],  # No permissions during import — module-level code gets zero trust
        )
        try:
            with _load_sandbox:
                spec.loader.exec_module(module)
        except Exception as e:
            raise SkillLoadError(f"Failed to execute skill module: {e}")

        # Cache loaded skill
        skill_info = {
            "name": name,
            "module": module,
            "manifest": manifest,
            "path": skill_path,
            "commands": {cmd.name: cmd for cmd in manifest.commands},
        }
        self._loaded_skills[name] = skill_info

        return skill_info

    def get_command(self, skill_name: str, command_name: str) -> Callable | None:
        """Get a command function from a skill.

        Args:
            skill_name: Skill name
            command_name: Command name

        Returns:
            Command function or None
        """
        skill_info = self.load_skill(skill_name)
        module = skill_info["module"]
        commands = skill_info["commands"]

        if command_name not in commands:
            return None

        cmd: SkillCommand = commands[command_name]
        func = getattr(module, cmd.function, None)

        return func

    def execute_command(
        self,
        skill_name: str,
        command_name: str,
        *args,
        **kwargs,
    ) -> Any:
        """Execute a skill command.

        Args:
            skill_name: Skill name
            command_name: Command name
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Command result
        """
        func = self.get_command(skill_name, command_name)

        if func is None:
            raise SkillLoadError(
                f"Command '{command_name}' not found in skill '{skill_name}'"
            )

        # Get granted permissions — version-bound to prevent stale grants
        skill_info = self._loaded_skills.get(skill_name) or self.load_skill(skill_name)
        manifest_version = skill_info["manifest"].version
        granted_permissions = self.permission_store.get_permissions(
            skill_name, version=manifest_version,
        )

        # Create permission context for runtime enforcement
        perm_context = PermissionContext(
            skill_name=skill_name,
            granted_permissions=granted_permissions,
            permission_store=self.permission_store,
        )

        # Store context for potential runtime checks
        self._permission_contexts[skill_name] = perm_context

        # Create sandbox manager for isolation
        sandbox = SandboxManager(
            skill_name=skill_name,
            permissions=granted_permissions,
        )

        # Execute command within permission context and sandbox
        with perm_context:
            with sandbox:
                return func(*args, **kwargs)

    def get_permission_context(self, skill_name: str) -> PermissionContext | None:
        """Get the permission context for a skill.

        Args:
            skill_name: Skill name

        Returns:
            PermissionContext if skill is loaded, None otherwise
        """
        return self._permission_contexts.get(skill_name)

    def list_commands(self, skill_name: str) -> list[SkillCommand]:
        """List all commands provided by a skill.

        Args:
            skill_name: Skill name

        Returns:
            List of commands
        """
        skill_info = self.load_skill(skill_name)
        manifest: SkillManifest = skill_info["manifest"]
        return manifest.commands

    def list_all_commands(self) -> dict[str, list[SkillCommand]]:
        """List commands from all enabled skills.

        Returns:
            Dict mapping skill name to list of commands
        """
        all_commands = {}

        for installed in self.registry.list_installed():
            if not installed.enabled:
                continue

            try:
                commands = self.list_commands(installed.name)
                if commands:
                    all_commands[installed.name] = commands
            except SkillLoadError:
                continue

        return all_commands

    def unload_skill(self, name: str) -> None:
        """Unload a skill from memory.

        Args:
            name: Skill name
        """
        if name in self._loaded_skills:
            module_name = f"socialhub_skill_{name}"
            if module_name in sys.modules:
                del sys.modules[module_name]
            del self._loaded_skills[name]

    def reload_skill(self, name: str) -> dict[str, Any]:
        """Reload a skill.

        Args:
            name: Skill name

        Returns:
            Reloaded skill info
        """
        self.unload_skill(name)
        return self.load_skill(name)


def create_skill_typer_commands(loader: SkillLoader):
    """Create Typer commands for all loaded skills.

    This function dynamically creates CLI commands from skill definitions.
    """

    commands = {}

    for skill_name, skill_commands in loader.list_all_commands().items():
        for cmd in skill_commands:
            # Create a command function
            def make_command(sn: str, cn: str):
                def command(**kwargs):
                    result = loader.execute_command(sn, cn, **kwargs)
                    if result is not None:
                        print(result)
                return command

            command_func = make_command(skill_name, cmd.name)
            command_func.__doc__ = cmd.description

            # Add to commands dict
            full_name = f"{skill_name}:{cmd.name}" if ":" not in cmd.name else cmd.name
            commands[full_name] = command_func

    return commands
