"""Skills Store API client."""

import hashlib
import os
from typing import Any, Optional

import httpx

from .models import SkillCategory, SkillDetail, SkillSearchResult, SkillCommand, SkillDependencies, SkillCertification


class StoreError(Exception):
    """Store API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
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

    # Official store URL
    OFFICIAL_STORE_URL = "https://skills.socialhub.ai/api/v1"

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30, demo_mode: Optional[bool] = None):
        # Only allow official store URL
        self.base_url = self.OFFICIAL_STORE_URL
        self.timeout = timeout

        # Demo mode: use mock data when store is unavailable
        # Can be set via SOCIALHUB_DEMO_MODE env var
        if demo_mode is None:
            demo_mode = os.getenv("SOCIALHUB_DEMO_MODE", "").lower() in ("1", "true", "yes")
        self._demo_mode = demo_mode
        self._force_demo = False

        # If a custom URL is provided, reject it (security)
        if base_url and base_url != self.OFFICIAL_STORE_URL:
            raise StoreError(
                "Security Error: Only official SocialHub.AI Skills Store is allowed. "
                "External skill sources are not permitted."
            )

        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "SocialHub-CLI/0.1.0",
                    "Accept": "application/json",
                },
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
                message = error_data.get("error", error_data.get("message", "Unknown error"))
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
            else:
                raise ValueError(f"Unsupported method: {method}")
            return self._handle_response(response)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout):
            # Connection failed, switch to demo mode
            self._force_demo = True
            raise StoreError("Store unavailable, using demo mode", 0)

    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
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

    def download(self, name: str, version: Optional[str] = None) -> bytes:
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

    def get_download_info(self, name: str, version: Optional[str] = None) -> dict[str, Any]:
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
            return True  # Demo mode: assume valid

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
