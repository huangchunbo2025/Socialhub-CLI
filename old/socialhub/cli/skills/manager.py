"""Skill manager for installation, updates, and removal."""

import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import InstalledSkill, SkillManifest
from .registry import SkillRegistry
from .security import (
    HashVerifier,
    PermissionChecker,
    PermissionPrompter,
    PermissionStore,
    RevocationListManager,
    SecurityAuditLogger,
    SecurityError,
    SignatureVerifier,
    validate_skill_source,
)
from .store_client import SkillsStoreClient, StoreError, compute_package_hash

console = Console()


class SkillManagerError(Exception):
    """Skill manager error."""

    pass


class SkillManager:
    """Manages skill installation, updates, and removal."""

    def __init__(self):
        self.registry = SkillRegistry()
        self.verifier = SignatureVerifier()
        self.hash_verifier = HashVerifier()
        self.permission_checker = PermissionChecker()
        self.permission_store = PermissionStore()
        self.permission_prompter = PermissionPrompter(console)
        self.revocation_manager = RevocationListManager()
        self.audit_logger = SecurityAuditLogger()
        self._store_client: Optional[SkillsStoreClient] = None

    @property
    def store(self) -> SkillsStoreClient:
        """Get store client (lazy initialization)."""
        if self._store_client is None:
            self._store_client = SkillsStoreClient()
        return self._store_client

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list:
        """Search skills in the store."""
        return self.store.search(query=query, category=category)

    def get_skill_info(self, name: str):
        """Get skill details from store."""
        return self.store.get_skill(name)

    def install(
        self,
        name: str,
        version: Optional[str] = None,
        force: bool = False,
    ) -> InstalledSkill:
        """Install a skill from the official store.

        Args:
            name: Skill name
            version: Specific version (optional, defaults to latest)
            force: Force reinstall if already installed

        Returns:
            InstalledSkill record
        """
        # Check if already installed
        installed = self.registry.get_installed(name)
        if installed and not force:
            if version and installed.version == version:
                raise SkillManagerError(
                    f"Skill '{name}' version {version} is already installed. "
                    "Use --force to reinstall."
                )
            elif not version:
                raise SkillManagerError(
                    f"Skill '{name}' is already installed (v{installed.version}). "
                    "Use 'skills update' to update or --force to reinstall."
                )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Step 1: Get skill info
            task = progress.add_task("Fetching skill info...", total=None)
            try:
                skill_info = self.store.get_skill(name)
            except StoreError as e:
                raise SkillManagerError(f"Failed to fetch skill info: {e.message}")

            # Use latest version if not specified
            if not version:
                version = skill_info.version

            # Step 2: Get download info (hash, signature)
            progress.update(task, description="Verifying skill...")
            try:
                download_info = self.store.get_download_info(name, version)
                expected_hash = download_info.get("hash", "")
                signature = download_info.get("signature", "")
            except StoreError:
                expected_hash = ""
                signature = ""

            # Step 3: Download package
            progress.update(task, description=f"Downloading {name}@{version}...")
            try:
                package_content = self.store.download(name, version)
            except StoreError as e:
                raise SkillManagerError(f"Failed to download skill: {e.message}")

            # Step 4: Verify hash (MANDATORY - cannot be skipped)
            progress.update(task, description="Verifying package integrity...")
            if expected_hash:
                actual_hash = compute_package_hash(package_content)
                if not self.hash_verifier.verify_hash(
                    package_content, expected_hash, "sha256"
                ):
                    self.audit_logger.log_install_blocked(
                        name, f"Hash mismatch: expected {expected_hash[:16]}..."
                    )
                    raise SecurityError(
                        "Package integrity check failed. "
                        "The downloaded package may be corrupted or tampered with."
                    )
            else:
                # In strict mode, require hash for all packages
                console.print(
                    "[yellow]Warning: No hash provided for package verification[/yellow]"
                )

            # Step 5: Save to cache
            cache_path = self.registry.get_cache_path(name, version)
            with open(cache_path, "wb") as f:
                f.write(package_content)

            # Step 6: Extract package
            progress.update(task, description="Installing skill...")
            install_path = self.registry.get_skill_path(name)

            # Remove old installation if exists
            if install_path.exists():
                shutil.rmtree(install_path)

            install_path.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(cache_path, "r") as zf:
                    zf.extractall(install_path)
            except zipfile.BadZipFile:
                raise SkillManagerError("Invalid skill package (not a valid zip file)")

            # Step 7: Load and verify manifest
            progress.update(task, description="Verifying certification...")
            manifest_path = install_path / "skill.yaml"
            if not manifest_path.exists():
                shutil.rmtree(install_path)
                raise SkillManagerError("Invalid skill package (missing skill.yaml)")

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f)
                manifest = SkillManifest(**manifest_data)
            except Exception as e:
                shutil.rmtree(install_path)
                raise SkillManagerError(f"Invalid skill manifest: {e}")

            # Step 8: Verify signature
            try:
                self.verifier.verify_manifest_signature(manifest)
                self.audit_logger.log_signature_verified(manifest.name, manifest.version)
            except SecurityError as e:
                self.audit_logger.log_signature_failed(manifest.name, manifest.version, str(e))
                shutil.rmtree(install_path)
                raise SkillManagerError(f"Security verification failed: {e}")

            # Step 8.5: Check revocation list
            progress.update(task, description="Checking revocation status...")
            cert_id = (
                manifest.certification.certificate_id
                if manifest.certification
                else None
            )
            if self.revocation_manager.is_revoked(name, cert_id):
                self.audit_logger.log_install_blocked(name, "Skill is revoked")
                shutil.rmtree(install_path)
                raise SecurityError(
                    f"Skill '{name}' has been revoked for security reasons. "
                    "Installation is blocked. Please contact the skill author."
                )

        # Step 8.6: Request permission approval (outside progress context for user interaction)
        requested_permissions = [p.value for p in manifest.permissions]
        if requested_permissions:
            console.print()  # Add spacing
            all_approved, approved_perms = self.permission_prompter.request_permissions(
                skill_name=manifest.name,
                permissions=requested_permissions,
                skill_version=manifest.version,
            )

            if not all_approved:
                # Check if any sensitive permissions were denied
                sensitive_denied = [
                    p for p in requested_permissions
                    if p not in approved_perms
                    and p not in self.permission_checker.SAFE_PERMISSIONS
                ]
                if sensitive_denied:
                    # Ask if user wants to continue anyway
                    from rich.prompt import Confirm
                    if not Confirm.ask(
                        "\n[yellow]Some permissions were denied. Continue installation anyway?[/yellow]",
                        default=False,
                    ):
                        shutil.rmtree(install_path)
                        raise SkillManagerError("Installation cancelled by user")

            # Store approved permissions
            if approved_perms:
                self.permission_store.grant_permissions(
                    manifest.name,
                    approved_perms,
                    manifest.version,
                )
                # Also update in-memory permission checker
                for perm in approved_perms:
                    self.permission_checker.grant_permission(manifest.name, perm)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Continuing installation...", total=None)

            # Step 9: Install Python dependencies
            if manifest.dependencies.python:
                progress.update(task, description="Installing dependencies...")
                self._install_dependencies(manifest.dependencies.python)

            # Step 10: Register skill
            progress.update(task, description="Registering skill...")
            skill_record = InstalledSkill(
                name=manifest.name,
                version=manifest.version,
                display_name=manifest.display_name or manifest.name,
                description=manifest.description,
                category=manifest.category,
                installed_at=datetime.now(),
                path=str(install_path),
                enabled=True,
                manifest=manifest,
            )
            self.registry.register_skill(skill_record)

            progress.update(task, description="[green]Installation complete!")

        # Sync to backend (fire-and-forget — local install already done)
        self.store.add_my_skill(manifest.name, manifest.version)

        return skill_record

    def _install_dependencies(self, dependencies: list[str]) -> None:
        """Install Python dependencies for a skill."""
        if not dependencies:
            return

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q"] + dependencies,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise SkillManagerError(
                f"Failed to install dependencies: {e.stderr.decode() if e.stderr else str(e)}"
            )

    def uninstall(self, name: str) -> bool:
        """Uninstall a skill.

        Args:
            name: Skill name

        Returns:
            True if uninstalled successfully
        """
        installed = self.registry.get_installed(name)
        if not installed:
            raise SkillManagerError(f"Skill '{name}' is not installed")

        # Remove skill directory
        install_path = self.registry.get_skill_path(name)
        if install_path.exists():
            shutil.rmtree(install_path)

        # Remove from registry
        self.registry.unregister_skill(name)

        # Revoke permissions
        self.permission_checker.revoke_all_permissions(name)

        # Sync to backend (fire-and-forget)
        self.store.remove_my_skill(name)

        return True

    def update(
        self,
        name: Optional[str] = None,
        all_skills: bool = False,
    ) -> list[InstalledSkill]:
        """Update installed skill(s).

        Args:
            name: Skill name to update (optional if all_skills=True)
            all_skills: Update all installed skills

        Returns:
            List of updated skills
        """
        updated = []

        if all_skills:
            # Check updates for all installed skills
            installed = self.registry.list_installed()
            if not installed:
                return []

            installed_info = [
                {"name": s.name, "version": s.version}
                for s in installed
            ]

            try:
                updates = self.store.check_updates(installed_info)
            except StoreError as e:
                raise SkillManagerError(f"Failed to check updates: {e.message}")

            for update in updates:
                skill_name = update.get("name")
                new_version = update.get("latest_version")
                if skill_name and new_version:
                    try:
                        skill = self.install(skill_name, new_version, force=True)
                        updated.append(skill)
                    except SkillManagerError as e:
                        console.print(f"[yellow]Failed to update {skill_name}: {e}[/yellow]")

        elif name:
            # Update specific skill
            installed = self.registry.get_installed(name)
            if not installed:
                raise SkillManagerError(f"Skill '{name}' is not installed")

            try:
                skill_info = self.store.get_skill(name)
            except StoreError as e:
                raise SkillManagerError(f"Failed to fetch skill info: {e.message}")

            if skill_info.version != installed.version:
                skill = self.install(name, skill_info.version, force=True)
                updated.append(skill)
            else:
                console.print(f"[dim]Skill '{name}' is already up to date (v{installed.version})[/dim]")

        return updated

    def list_installed(self) -> list[InstalledSkill]:
        """List all installed skills."""
        return self.registry.list_installed()

    def enable(self, name: str) -> bool:
        """Enable a skill."""
        if not self.registry.is_installed(name):
            raise SkillManagerError(f"Skill '{name}' is not installed")
        result = self.registry.enable_skill(name)
        self.store.toggle_my_skill(name, True)  # fire-and-forget
        return result

    def disable(self, name: str) -> bool:
        """Disable a skill."""
        if not self.registry.is_installed(name):
            raise SkillManagerError(f"Skill '{name}' is not installed")
        result = self.registry.disable_skill(name)
        self.store.toggle_my_skill(name, False)  # fire-and-forget
        return result

    def close(self) -> None:
        """Close manager resources."""
        if self._store_client:
            self._store_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
