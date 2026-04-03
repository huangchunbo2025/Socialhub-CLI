"""Skills Store API client."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .models import (
    SkillCategory,
    SkillCommand,
    SkillDependencies,
    SkillDetail,
    SkillSearchResult,
)

_TOKEN_FILE = Path.home() / ".socialhub" / "store_token.json"


class StoreError(Exception):
    """Store API error."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Demo data for testing when store is not available
DEMO_SKILLS = [
    {
        "name": "data-export-plus",
        "display_name": "高级数据导出",
        "description": "支持更多格式的数据导出，包括 Parquet、Feather、JSON Lines 等",
        "version": "1.2.0",
        "author": "SocialHub Official",
        "category": SkillCategory.DATA,
        "downloads": 15680,
        "rating": 4.8,
        "tags": ["export", "parquet", "data-format"],
        "certified": True,
    },
    {
        "name": "wechat-analytics",
        "display_name": "微信数据分析",
        "description": "深度分析微信渠道用户行为、互动数据和转化漏斗",
        "version": "2.1.0",
        "author": "SocialHub Official",
        "category": SkillCategory.ANALYTICS,
        "downloads": 28450,
        "rating": 4.9,
        "tags": ["wechat", "analytics", "funnel"],
        "certified": True,
    },
    {
        "name": "campaign-optimizer",
        "display_name": "营销活动优化器",
        "description": "AI 驱动的营销活动优化建议，提升 ROI 和转化率",
        "version": "1.5.0",
        "author": "SocialHub Official",
        "category": SkillCategory.MARKETING,
        "downloads": 12300,
        "rating": 4.7,
        "tags": ["campaign", "optimization", "ai"],
        "certified": True,
    },
    {
        "name": "customer-rfm",
        "display_name": "RFM 客户分析",
        "description": "基于 RFM 模型的客户价值分析和分群",
        "version": "1.0.0",
        "author": "SocialHub Official",
        "category": SkillCategory.ANALYTICS,
        "downloads": 9800,
        "rating": 4.6,
        "tags": ["rfm", "segmentation", "customer-value"],
        "certified": True,
    },
    {
        "name": "sms-batch-sender",
        "display_name": "短信批量发送",
        "description": "高效的短信批量发送工具，支持模板变量和发送调度",
        "version": "2.0.0",
        "author": "SocialHub Official",
        "category": SkillCategory.MARKETING,
        "downloads": 18900,
        "rating": 4.5,
        "tags": ["sms", "batch", "messaging"],
        "certified": True,
    },
    {
        "name": "data-sync-tool",
        "display_name": "数据同步工具",
        "description": "与主流 CRM、ERP 系统的数据双向同步",
        "version": "1.3.0",
        "author": "SocialHub Official",
        "category": SkillCategory.INTEGRATION,
        "downloads": 7500,
        "rating": 4.4,
        "tags": ["sync", "crm", "integration"],
        "certified": True,
    },
    {
        "name": "report-generator",
        "display_name": "报表生成器",
        "description": "自动化生成多维度业务报表，支持定时发送",
        "version": "1.1.0",
        "author": "SocialHub Official",
        "category": SkillCategory.UTILITY,
        "downloads": 21000,
        "rating": 4.8,
        "tags": ["report", "automation", "schedule"],
        "certified": True,
    },
    {
        "name": "loyalty-calculator",
        "display_name": "会员积分计算器",
        "description": "灵活的积分规则配置和批量积分计算工具",
        "version": "1.0.0",
        "author": "SocialHub Official",
        "category": SkillCategory.UTILITY,
        "downloads": 5600,
        "rating": 4.3,
        "tags": ["points", "loyalty", "calculator"],
        "certified": True,
    },
]


class SkillsStoreClient:
    """Client for SocialHub.AI Skills Store API."""

    # Official store URL — hardcoded, cannot be overridden at runtime (supply-chain protection)
    OFFICIAL_STORE_URL = "https://skills.socialhub.ai/api/v1"

    def __init__(self, base_url: str | None = None, timeout: int = 30, demo_mode: bool | None = None):
        self.base_url = self.OFFICIAL_STORE_URL
        self.timeout = timeout

        # Demo mode: use mock data when store is unavailable
        # Can be set via SOCIALHUB_DEMO_MODE env var
        if demo_mode is None:
            demo_mode = os.getenv("SOCIALHUB_DEMO_MODE", "").lower() in ("1", "true", "yes")
        self._demo_mode = demo_mode
        self._force_demo = False

        # Reject any non-official URL — prevents credential hijacking
        if base_url and base_url != self.OFFICIAL_STORE_URL:
            raise StoreError(
                "Security Error: Only official SocialHub.AI Skills Store is allowed. "
                "External skill sources are not permitted."
            )

        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            from ..config import load_config
            from ..network import build_httpx_kwargs
            _net_kwargs = build_httpx_kwargs(load_config().network)
            # Security: the Skills Store must always use TLS verification regardless
            # of the global NetworkConfig.ssl_verify setting. Disabling certificate
            # verification for store downloads would allow a MITM attacker to serve
            # malicious skill packages. Unconditionally override any ssl_verify=False
            # that build_httpx_kwargs may have injected.
            _net_kwargs["verify"] = True
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "SocialHub-CLI/0.1.0",
                    "Accept": "application/json",
                },
                **_net_kwargs,
            )
        return self._client

    def _is_demo_mode(self) -> bool:
        """Check if running in demo mode."""
        return self._demo_mode or self._force_demo

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response."""
        if response.status_code == 404:
            raise StoreError("Skill not found", 404)
        elif response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("error", error_data.get("detail", error_data.get("message", "Unknown error")))
                if isinstance(message, list):
                    message = message[0].get("msg", str(message)) if message else "Unknown error"
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise StoreError(message, response.status_code)

        try:
            return response.json()
        except Exception:
            return {"data": response.text}

    def _try_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Try to make a request, fall back to demo mode on connection error."""
        if self._is_demo_mode():
            raise StoreError("Demo mode", 0)  # Will be caught and handled

        try:
            client = self._get_client()
            if method == "GET":
                response = client.get(endpoint, **kwargs)
            elif method == "POST":
                response = client.post(endpoint, **kwargs)
            elif method == "DELETE":
                response = client.delete(endpoint, **kwargs)
            elif method == "PATCH":
                response = client.patch(endpoint, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            return self._handle_response(response)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout):
            # Connection failed, switch to demo mode
            self._force_demo = True
            raise StoreError("Store unavailable, using demo mode", 0)

    # ------------------------------------------------------------------ #
    # Auth — token stored at ~/.socialhub/store_token.json               #
    # ------------------------------------------------------------------ #

    def _load_token(self) -> str | None:
        """Load JWT token from disk. Returns None if missing or expired."""
        if not _TOKEN_FILE.exists():
            return None
        try:
            data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
            expires_at = data.get("expires_at")
            if expires_at:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= exp:
                    return None
            return data.get("token")
        except Exception:
            return None

    def _save_token(self, token: str, expires_in: int) -> None:
        """Save JWT token to disk with restricted permissions (owner read/write only)."""
        import stat
        from datetime import timedelta
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        _TOKEN_FILE.write_text(
            json.dumps({"token": token, "expires_at": expires_at.isoformat()}, ensure_ascii=False),
            encoding="utf-8",
        )
        # chmod 600 — owner read/write only, no access for group or others
        try:
            _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows doesn't support Unix permissions, best effort

    def _auth_headers(self) -> dict[str, str]:
        """Return Authorization header if authenticated."""
        token = self._load_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def is_authenticated(self) -> bool:
        """Check if a valid (non-expired) token is stored."""
        return self._load_token() is not None

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate as storefront user. Saves token to ~/.socialhub/store_token.json.

        Uses /api/v1/users/login — separate from developer login (/api/v1/auth/login).
        """
        try:
            client = self._get_client()
            response = client.post(
                "/users/login",
                json={"email": email, "password": password},
            )
            data = self._handle_response(response)
            payload = data.get("data", data)
            token = payload.get("access_token")
            expires_in = payload.get("expires_in", 86400)
            if not token:
                raise StoreError("Login failed: no token in response")
            self._save_token(token, expires_in)
            return payload
        except (httpx.ConnectError, httpx.TimeoutException):
            raise StoreError("Store unavailable", 503)

    def logout(self) -> None:
        """Remove stored token."""
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()

    # ------------------------------------------------------------------ #
    # User Skills Library — /api/v1/users/me/skills                      #
    # ------------------------------------------------------------------ #

    def get_my_skills(self) -> list[dict[str, Any]]:
        """GET /api/v1/users/me/skills — returns user's personal skill library."""
        headers = self._auth_headers()
        if not headers:
            raise StoreError("Not authenticated. Run 'skills login' first.", 401)
        try:
            client = self._get_client()
            response = client.get("/users/me/skills", headers=headers)
            data = self._handle_response(response)
            return data.get("data", {}).get("items", [])
        except (httpx.ConnectError, httpx.TimeoutException):
            raise StoreError("Store unavailable", 503)

    def add_my_skill(self, skill_name: str, version: str | None = None) -> dict[str, Any]:
        """POST /api/v1/users/me/skills/{skill_name} — add to user library."""
        headers = self._auth_headers()
        if not headers:
            return {}
        try:
            client = self._get_client()
            body = {"version": version} if version else {}
            response = client.post(f"/users/me/skills/{skill_name}", json=body, headers=headers)
            if response.status_code == 409:
                return {}  # Already in library — idempotent, not an error
            data = self._handle_response(response)
            return data.get("data", {})
        except (httpx.ConnectError, httpx.TimeoutException):
            return {}  # Fire-and-forget: local install already succeeded

    def remove_my_skill(self, skill_name: str) -> None:
        """DELETE /api/v1/users/me/skills/{skill_name} — remove from user library."""
        headers = self._auth_headers()
        if not headers:
            return
        try:
            client = self._get_client()
            response = client.delete(f"/users/me/skills/{skill_name}", headers=headers)
            if response.status_code not in (200, 204, 404):
                self._handle_response(response)
        except (httpx.ConnectError, httpx.TimeoutException):
            return  # Fire-and-forget

    def toggle_my_skill(self, skill_name: str, enabled: bool) -> None:
        """PATCH /api/v1/users/me/skills/{skill_name}/toggle — enable or disable."""
        headers = self._auth_headers()
        if not headers:
            return
        try:
            client = self._get_client()
            response = client.patch(
                f"/users/me/skills/{skill_name}/toggle",
                json={"enabled": enabled},
                headers=headers,
            )
            if response.status_code not in (200, 204, 404):
                self._handle_response(response)
        except (httpx.ConnectError, httpx.TimeoutException):
            return  # Fire-and-forget

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[SkillSearchResult]:
        """Search skills in the store."""
        try:
            params: dict[str, Any] = {"page": page, "limit": limit}
            if query:
                params["search"] = query
            if category:
                params["category"] = category

            data = self._try_request("GET", "/skills", params=params)
            items = data.get("data", {}).get("items", data.get("data", []))
            return [SkillSearchResult(**item) for item in items]

        except StoreError:
            # Return demo data
            results = DEMO_SKILLS.copy()

            # Filter by query
            if query:
                query_lower = query.lower()
                results = [
                    s for s in results
                    if query_lower in s["name"].lower()
                    or query_lower in s["display_name"].lower()
                    or query_lower in s["description"].lower()
                    or any(query_lower in tag for tag in s.get("tags", []))
                ]

            # Filter by category
            if category:
                results = [s for s in results if s["category"].value == category]

            # Paginate
            start = (page - 1) * limit
            end = start + limit
            results = results[start:end]

            return [SkillSearchResult(**item) for item in results]

    def get_skill(self, name: str) -> SkillDetail:
        """Get skill details."""
        try:
            data = self._try_request("GET", f"/skills/{name}")
            return SkillDetail(**data.get("data", data))

        except StoreError:
            # Return demo data
            for skill in DEMO_SKILLS:
                if skill["name"] == name:
                    return SkillDetail(
                        name=skill["name"],
                        display_name=skill["display_name"],
                        description=skill["description"],
                        version=skill["version"],
                        author=skill["author"],
                        license="MIT",
                        homepage=f"https://skills.socialhub.ai/{skill['name']}",
                        category=skill["category"],
                        tags=skill.get("tags", []),
                        downloads=skill["downloads"],
                        rating=skill["rating"],
                        permissions=[],
                        dependencies=SkillDependencies(),
                        commands=[
                            SkillCommand(
                                name="run",
                                description=f"Run {skill['display_name']}",
                                function="main",
                            )
                        ],
                        versions=[skill["version"], "1.0.0"],
                        certified=True,
                        readme=f"# {skill['display_name']}\n\n{skill['description']}",
                    )

            raise StoreError(f"Skill not found: {name}", 404)

    def get_versions(self, name: str) -> list[str]:
        """Get available versions of a skill."""
        try:
            data = self._try_request("GET", f"/skills/{name}/versions")
            return data.get("data", {}).get("versions", [])
        except StoreError:
            # Demo mode
            for skill in DEMO_SKILLS:
                if skill["name"] == name:
                    return [skill["version"], "1.0.0"]
            return []

    def download(self, name: str, version: str | None = None) -> bytes:
        """Download skill package."""
        if self._is_demo_mode():
            raise StoreError(
                "Demo mode: Cannot download skills. "
                "Set up the Skills Store backend or disable demo mode.",
                503
            )

        params = {}
        if version:
            params["version"] = version

        try:
            client = self._get_client()
            response = client.get(f"/skills/{name}/download", params=params)

            if response.status_code >= 400:
                raise StoreError(f"Failed to download skill: {response.status_code}")

            return response.content
        except (httpx.ConnectError, httpx.TimeoutException):
            self._force_demo = True
            raise StoreError("Store unavailable", 503)

    def get_download_info(self, name: str, version: str | None = None) -> dict[str, Any]:
        """Get download info including hash and signature."""
        try:
            params = {}
            if version:
                params["version"] = version

            data = self._try_request("GET", f"/skills/{name}/download-info", params=params)
            return data.get("data", {})
        except StoreError:
            return {"hash": "", "signature": ""}

    def verify_signature(
        self,
        name: str,
        signature: str,
        package_hash: str,
    ) -> bool:
        """Verify skill package signature with the store."""
        try:
            data = self._try_request(
                "POST",
                "/skills/verify",
                json={
                    "skill_name": name,
                    "signature": signature,
                    "hash": package_hash,
                },
            )
            return data.get("data", {}).get("valid", False)
        except StoreError:
            return False  # Network error during verification — fail closed

    def check_updates(
        self,
        installed: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Check for updates to installed skills."""
        try:
            data = self._try_request(
                "POST",
                "/skills/check-updates",
                json={"installed": installed},
            )
            return data.get("data", {}).get("updates", [])
        except StoreError:
            return []

    def get_categories(self) -> list[dict[str, Any]]:
        """Get available skill categories."""
        try:
            data = self._try_request("GET", "/categories")
            return data.get("data", [])
        except StoreError:
            return [
                {"id": "data", "name": "数据处理", "count": 2},
                {"id": "analytics", "name": "数据分析", "count": 2},
                {"id": "marketing", "name": "营销工具", "count": 2},
                {"id": "integration", "name": "系统集成", "count": 1},
                {"id": "utility", "name": "实用工具", "count": 2},
            ]

    def get_featured(self) -> list[SkillSearchResult]:
        """Get featured skills."""
        try:
            data = self._try_request("GET", "/skills/featured")
            items = data.get("data", [])
            return [SkillSearchResult(**item) for item in items]
        except StoreError:
            # Return top 3 demo skills
            return [SkillSearchResult(**item) for item in DEMO_SKILLS[:3]]

    def close(self) -> None:
        """Close the client."""
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def compute_package_hash(content: bytes) -> str:
    """Compute SHA-256 hash of package content."""
    return hashlib.sha256(content).hexdigest()
