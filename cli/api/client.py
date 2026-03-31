"""API client for SocialHub platform."""

import json
import stat
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from rich.console import Console

from ..config import CONFIG_DIR, load_config

console = Console()

# Token cache file (parallel to store_token.json)
_TOKEN_FILE = CONFIG_DIR / "api_token.json"


class APIError(Exception):
    """API error exception."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SocialHubClient:
    """HTTP client for SocialHub API.

    Authentication flow:
    1. Load cached token from ~/.socialhub/api_token.json
    2. If missing or expired, fetch new token via appId + appSecret
    3. Use accessToken as Bearer token for all subsequent requests
    4. On 401, refresh token and retry once
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        config = load_config()
        self.base_url = (base_url or config.api.url).rstrip("/")
        self.timeout = timeout or config.api.timeout
        self._app_id = config.api.app_id
        self._app_secret = config.api.app_secret
        self._access_token: Optional[str] = None

        # Ensure we have a valid token before building the client
        self._ensure_token()

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._build_headers(),
        )

    # ── Token cache management ──────────────────────────────────────

    @staticmethod
    def _load_token() -> Optional[dict[str, str]]:
        """Load cached token from disk. Returns None if missing or expired."""
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
            return data
        except Exception:
            return None

    @staticmethod
    def _save_token(access_token: str, refresh_token: str, expires_at: datetime) -> None:
        """Save token to disk with restricted permissions (0600)."""
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at.isoformat(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows best-effort

    def _fetch_token(self) -> str:
        """Fetch a new token from the auth endpoint using appId + appSecret."""
        if not self._app_id or not self._app_secret:
            raise APIError(
                "API credentials not configured. "
                "Run 'sh config set api.app_id YOUR_APP_ID' and "
                "'sh config set api.app_secret YOUR_APP_SECRET'."
            )

        url = f"{self.base_url}/v1/auth/token"
        response = httpx.post(
            url,
            json={"appId": self._app_id, "appSecret": self._app_secret},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise APIError(
                f"Token request failed: HTTP {response.status_code} — {response.text}",
                response.status_code,
            )

        body = response.json()
        if str(body.get("code")) != "200":
            raise APIError(f"Token request failed: {body.get('msg', 'unknown error')}")

        data = body.get("data", {})
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken", "")
        expires_time = data.get("expiresTime")

        if not access_token or expires_time is None:
            raise APIError("Token response missing accessToken or expiresTime")

        # expiresTime is an absolute Unix timestamp (seconds)
        expires_at = datetime.fromtimestamp(int(expires_time), tz=timezone.utc)
        self._save_token(access_token, refresh_token, expires_at)
        return access_token

    def _ensure_token(self) -> None:
        """Ensure a valid access token is available (cache-first)."""
        cached = self._load_token()
        if cached and cached.get("access_token"):
            self._access_token = cached["access_token"]
        else:
            self._access_token = self._fetch_token()

    def _refresh_and_rebuild(self) -> None:
        """Force-refresh token and rebuild the httpx client headers."""
        self._access_token = self._fetch_token()
        self._client.headers.update({"Authorization": f"Bearer {self._access_token}"})

    # ── HTTP helpers ────────────────────────────────────────────────

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SocialHub-CLI/0.1.0",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response."""
        if response.status_code >= 400:
            try:
                error_data = response.json()
                message = error_data.get("error", error_data.get("message", "Unknown error"))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise APIError(message, response.status_code)

        try:
            return response.json()
        except Exception:
            return {"data": response.text}

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Execute request; on 401 refresh token and retry once."""
        try:
            response = self._client.request(method, endpoint, params=params, json=data)
            if response.status_code == 401:
                raise APIError("Unauthorized", 401)
            return self._handle_response(response)
        except APIError as e:
            if e.status_code == 401:
                self._refresh_and_rebuild()
                response = self._client.request(method, endpoint, params=params, json=data)
                return self._handle_response(response)
            raise

    def get(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Make GET request."""
        return self._request_with_retry("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Optional[dict] = None) -> dict[str, Any]:
        """Make POST request."""
        return self._request_with_retry("POST", endpoint, data=data)

    def put(self, endpoint: str, data: Optional[dict] = None) -> dict[str, Any]:
        """Make PUT request."""
        return self._request_with_retry("PUT", endpoint, data=data)

    def delete(self, endpoint: str) -> dict[str, Any]:
        """Make DELETE request."""
        return self._request_with_retry("DELETE", endpoint)

    def close(self) -> None:
        """Close the client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # Analytics endpoints

    def get_analytics_overview(
        self,
        period: str = "7d",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        customer_type: str = "all",
    ) -> dict[str, Any]:
        """Get analytics overview."""
        params = {"period": period, "type": customer_type}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.get("/api/v1/analytics/overview", params)

    def get_customer_analytics(
        self,
        period: str = "30d",
        channel: str = "all",
    ) -> dict[str, Any]:
        """Get customer analytics."""
        return self.get(
            "/api/v1/analytics/customers",
            params={"period": period, "channel": channel},
        )

    def get_retention_analytics(self, days: list[int]) -> dict[str, Any]:
        """Get customer retention analytics."""
        return self.get(
            "/api/v1/analytics/customers/retention",
            params={"days": ",".join(map(str, days))},
        )

    def get_order_analytics(
        self,
        period: str = "30d",
        metric: str = "sales",
    ) -> dict[str, Any]:
        """Get order analytics."""
        return self.get(
            "/api/v1/analytics/orders",
            params={"period": period, "metric": metric},
        )

    def get_campaign_analytics(
        self,
        campaign_id: Optional[str] = None,
        name: Optional[str] = None,
        period: str = "30d",
    ) -> dict[str, Any]:
        """Get campaign analytics."""
        params: dict[str, Any] = {"period": period}
        if campaign_id:
            params["id"] = campaign_id
        if name:
            params["name"] = name
        return self.get("/api/v1/analytics/campaigns", params)

    # Customer endpoints

    def search_customers(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search customers."""
        params = {}
        if phone:
            params["phone"] = phone
        if email:
            params["email"] = email
        if name:
            params["name"] = name
        return self.get("/api/v1/customers/search", params)

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        """Get customer by ID."""
        return self.get(f"/api/v1/customers/{customer_id}")

    def get_customer_portrait(self, customer_id: str) -> dict[str, Any]:
        """Get customer portrait/360 view."""
        return self.get(f"/api/v1/customers/{customer_id}/portrait")

    def list_customers(
        self,
        customer_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List customers."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if customer_type:
            params["type"] = customer_type
        return self.get("/api/v1/customers", params)

    # Segment endpoints

    def list_segments(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List segments."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        return self.get("/api/v1/segments", params)

    def get_segment(self, segment_id: str) -> dict[str, Any]:
        """Get segment by ID."""
        return self.get(f"/api/v1/segments/{segment_id}")

    def preview_segment(self, segment_id: str) -> dict[str, Any]:
        """Preview segment customers."""
        return self.get(f"/api/v1/segments/{segment_id}/preview")

    def create_segment(self, name: str, rules: dict, description: Optional[str] = None) -> dict[str, Any]:
        """Create a new segment."""
        data = {"name": name, "rules": rules}
        if description:
            data["description"] = description
        return self.post("/api/v1/segments", data)

    def enable_segment(self, segment_id: str) -> dict[str, Any]:
        """Enable a segment."""
        return self.put(f"/api/v1/segments/{segment_id}/enable")

    def disable_segment(self, segment_id: str) -> dict[str, Any]:
        """Disable a segment."""
        return self.put(f"/api/v1/segments/{segment_id}/disable")

    def export_segment(self, segment_id: str) -> dict[str, Any]:
        """Export segment customers."""
        return self.get(f"/api/v1/segments/{segment_id}/export")

    # Tag endpoints

    def list_tags(
        self,
        group: Optional[str] = None,
        tag_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List tags."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if group:
            params["group"] = group
        if tag_type:
            params["type"] = tag_type
        return self.get("/api/v1/tags", params)

    def get_tag(self, tag_id: str) -> dict[str, Any]:
        """Get tag by ID."""
        return self.get(f"/api/v1/tags/{tag_id}")

    def get_tag_analysis(self, tag_id: str) -> dict[str, Any]:
        """Get tag analysis."""
        return self.get(f"/api/v1/tags/{tag_id}/analysis")

    def create_tag(
        self,
        name: str,
        tag_type: str,
        values: list[str],
        group: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new tag."""
        data = {"name": name, "type": tag_type, "values": values}
        if group:
            data["group"] = group
        return self.post("/api/v1/tags", data)

    def enable_tag(self, tag_id: str) -> dict[str, Any]:
        """Enable a tag."""
        return self.put(f"/api/v1/tags/{tag_id}/enable")

    def disable_tag(self, tag_id: str) -> dict[str, Any]:
        """Disable a tag."""
        return self.put(f"/api/v1/tags/{tag_id}/disable")

    # Campaign endpoints

    def list_campaigns(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List campaigns."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        return self.get("/api/v1/campaigns", params)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Get campaign by ID."""
        return self.get(f"/api/v1/campaigns/{campaign_id}")

    def get_campaign_analysis(self, campaign_id: str) -> dict[str, Any]:
        """Get campaign analysis."""
        return self.get(f"/api/v1/campaigns/{campaign_id}/analysis")

    def create_campaign(
        self,
        name: str,
        campaign_type: str = "single",
        config: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Create a new campaign."""
        data = {"name": name, "type": campaign_type}
        if config:
            data.update(config)
        return self.post("/api/v1/campaigns", data)

    def start_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Start a campaign."""
        return self.put(f"/api/v1/campaigns/{campaign_id}/start")

    def end_campaign(self, campaign_id: str) -> dict[str, Any]:
        """End a campaign."""
        return self.put(f"/api/v1/campaigns/{campaign_id}/end")

    def approve_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Approve a campaign."""
        return self.put(f"/api/v1/campaigns/{campaign_id}/approve")

    def get_campaign_calendar(self, month: str) -> dict[str, Any]:
        """Get campaign calendar for a month."""
        return self.get("/api/v1/campaigns/calendar", params={"month": month})

    # Coupon endpoints

    def list_coupon_rules(
        self,
        coupon_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List coupon rules."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if coupon_type:
            params["type"] = coupon_type
        return self.get("/api/v1/coupons/rules", params)

    def get_coupon_rule(self, rule_id: str) -> dict[str, Any]:
        """Get coupon rule by ID."""
        return self.get(f"/api/v1/coupons/rules/{rule_id}")

    def create_coupon_rule(self, config: dict) -> dict[str, Any]:
        """Create a new coupon rule."""
        return self.post("/api/v1/coupons/rules", config)

    def list_coupons(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List coupons."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        return self.get("/api/v1/coupons", params)

    def get_coupon(self, coupon_id: str) -> dict[str, Any]:
        """Get coupon by ID."""
        return self.get(f"/api/v1/coupons/{coupon_id}")

    def get_coupon_analysis(self, rule_id: str) -> dict[str, Any]:
        """Get coupon rule analysis."""
        return self.get(f"/api/v1/coupons/rules/{rule_id}/analysis")

    # Points endpoints

    def list_points_rules(
        self,
        rule_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List points rules."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if rule_type:
            params["type"] = rule_type
        return self.get("/api/v1/points/rules", params)

    def get_points_rule(self, rule_id: str) -> dict[str, Any]:
        """Get points rule by ID."""
        return self.get(f"/api/v1/points/rules/{rule_id}")

    def get_points_balance(self, member_id: str) -> dict[str, Any]:
        """Get member points balance."""
        return self.get(f"/api/v1/points/balance/{member_id}")

    def get_points_history(
        self,
        member_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Get member points history."""
        return self.get(
            f"/api/v1/points/history/{member_id}",
            params={"page": page, "page_size": page_size},
        )

    # Message endpoints

    def list_message_templates(
        self,
        channel: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List message templates."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if channel:
            params["channel"] = channel
        return self.get("/api/v1/messages/templates", params)

    def get_message_template(self, template_id: str) -> dict[str, Any]:
        """Get message template by ID."""
        return self.get(f"/api/v1/messages/templates/{template_id}")

    def list_message_records(
        self,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List message records."""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if channel:
            params["channel"] = channel
        if status:
            params["status"] = status
        return self.get("/api/v1/messages/records", params)

    def get_message_stats(self, period: str = "7d") -> dict[str, Any]:
        """Get message statistics."""
        return self.get("/api/v1/messages/stats", params={"period": period})
