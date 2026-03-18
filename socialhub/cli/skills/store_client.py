"""Skills Store API client."""

import hashlib
from typing import Any, Optional

import httpx

from .models import SkillDetail, SkillSearchResult


class StoreError(Exception):
    """Store API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SkillsStoreClient:
    """Client for SocialHub.AI Skills Store API."""

    # Official store URL
    OFFICIAL_STORE_URL = "https://skills.socialhub.ai/api/v1"

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        # Only allow official store URL
        self.base_url = self.OFFICIAL_STORE_URL
        self.timeout = timeout

        # If a custom URL is provided, reject it (security)
        if base_url and base_url != self.OFFICIAL_STORE_URL:
            raise StoreError(
                "Security Error: Only official SocialHub.AI Skills Store is allowed. "
                "External skill sources are not permitted."
            )

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": "SocialHub-CLI/0.1.0",
                "Accept": "application/json",
            },
        )

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response."""
        if response.status_code == 404:
            raise StoreError("Skill not found", 404)
        elif response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("error", error_data.get("message", "Unknown error"))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise StoreError(message, response.status_code)

        try:
            return response.json()
        except Exception:
            return {"data": response.text}

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[SkillSearchResult]:
        """Search skills in the store."""
        params: dict[str, Any] = {"page": page, "limit": limit}
        if query:
            params["search"] = query
        if category:
            params["category"] = category

        response = self._client.get("/skills", params=params)
        data = self._handle_response(response)

        items = data.get("data", {}).get("items", data.get("data", []))
        return [SkillSearchResult(**item) for item in items]

    def get_skill(self, name: str) -> SkillDetail:
        """Get skill details."""
        response = self._client.get(f"/skills/{name}")
        data = self._handle_response(response)
        return SkillDetail(**data.get("data", data))

    def get_versions(self, name: str) -> list[str]:
        """Get available versions of a skill."""
        response = self._client.get(f"/skills/{name}/versions")
        data = self._handle_response(response)
        return data.get("data", {}).get("versions", [])

    def download(self, name: str, version: Optional[str] = None) -> bytes:
        """Download skill package."""
        params = {}
        if version:
            params["version"] = version

        response = self._client.get(f"/skills/{name}/download", params=params)

        if response.status_code >= 400:
            raise StoreError(f"Failed to download skill: {response.status_code}")

        return response.content

    def get_download_info(self, name: str, version: Optional[str] = None) -> dict[str, Any]:
        """Get download info including hash and signature."""
        params = {}
        if version:
            params["version"] = version

        response = self._client.get(f"/skills/{name}/download-info", params=params)
        return self._handle_response(response).get("data", {})

    def verify_signature(
        self,
        name: str,
        signature: str,
        package_hash: str,
    ) -> bool:
        """Verify skill package signature with the store."""
        response = self._client.post(
            "/skills/verify",
            json={
                "skill_name": name,
                "signature": signature,
                "hash": package_hash,
            },
        )
        data = self._handle_response(response)
        return data.get("data", {}).get("valid", False)

    def check_updates(
        self,
        installed: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Check for updates to installed skills."""
        response = self._client.post(
            "/skills/check-updates",
            json={"installed": installed},
        )
        data = self._handle_response(response)
        return data.get("data", {}).get("updates", [])

    def get_categories(self) -> list[dict[str, Any]]:
        """Get available skill categories."""
        response = self._client.get("/categories")
        data = self._handle_response(response)
        return data.get("data", [])

    def get_featured(self) -> list[SkillSearchResult]:
        """Get featured skills."""
        response = self._client.get("/skills/featured")
        data = self._handle_response(response)
        items = data.get("data", [])
        return [SkillSearchResult(**item) for item in items]

    def close(self) -> None:
        """Close the client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def compute_package_hash(content: bytes) -> str:
    """Compute SHA-256 hash of package content."""
    return hashlib.sha256(content).hexdigest()
