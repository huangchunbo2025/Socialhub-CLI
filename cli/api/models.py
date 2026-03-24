"""Data models for SocialHub API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CustomerType(str, Enum):
    """Customer type enumeration."""

    MEMBER = "member"
    REGISTERED = "registered"
    VISITOR = "visitor"


class CampaignStatus(str, Enum):
    """Campaign status enumeration."""

    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class SegmentStatus(str, Enum):
    """Segment status enumeration."""

    DRAFT = "draft"
    ENABLED = "enabled"
    DISABLED = "disabled"


class CouponStatus(str, Enum):
    """Coupon status enumeration."""

    UNUSED = "unused"
    USED = "used"
    EXPIRED = "expired"


class CouponType(str, Enum):
    """Coupon type enumeration."""

    DISCOUNT = "discount"
    PERCENT = "percent"
    EXCHANGE = "exchange"


class TagType(str, Enum):
    """Tag type enumeration."""

    RFM = "rfm"
    AIPL = "aipl"
    STATIC = "static"
    COMPUTED = "computed"


class MessageChannel(str, Enum):
    """Message channel enumeration."""

    SMS = "sms"
    EMAIL = "email"
    WECHAT = "wechat"
    APP_PUSH = "app_push"


# Response Models


class Customer(BaseModel):
    """Customer data model."""

    id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_type: CustomerType = CustomerType.VISITOR
    created_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    total_orders: int = 0
    total_spent: float = 0.0
    points_balance: int = 0
    tags: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    """Customer segment data model."""

    id: str
    name: str
    description: Optional[str] = None
    status: SegmentStatus = SegmentStatus.DRAFT
    rules: dict[str, Any] = Field(default_factory=dict)
    customer_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Tag(BaseModel):
    """Tag data model."""

    id: str
    name: str
    group: Optional[str] = None
    tag_type: TagType = TagType.STATIC
    values: list[str] = Field(default_factory=list)
    customer_count: int = 0
    enabled: bool = True


class Campaign(BaseModel):
    """Marketing campaign data model."""

    id: str
    name: str
    campaign_type: str = "single"
    status: CampaignStatus = CampaignStatus.DRAFT
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    target_segment_id: Optional[str] = None
    target_count: int = 0
    reached_count: int = 0
    converted_count: int = 0
    created_at: Optional[datetime] = None


class CouponRule(BaseModel):
    """Coupon rule data model."""

    id: str
    name: str
    coupon_type: CouponType = CouponType.DISCOUNT
    discount_value: float = 0.0
    min_purchase: float = 0.0
    total_count: int = 0
    used_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    enabled: bool = True


class Coupon(BaseModel):
    """Coupon instance data model."""

    id: str
    rule_id: str
    code: str
    status: CouponStatus = CouponStatus.UNUSED
    customer_id: Optional[str] = None
    used_at: Optional[datetime] = None
    order_id: Optional[str] = None


class PointsRule(BaseModel):
    """Points rule data model."""

    id: str
    name: str
    rule_type: str = "basic"
    points_per_yuan: float = 1.0
    multiplier: float = 1.0
    enabled: bool = True


class MessageTemplate(BaseModel):
    """Message template data model."""

    id: str
    name: str
    channel: MessageChannel = MessageChannel.SMS
    content: str = ""
    variables: list[str] = Field(default_factory=list)
    enabled: bool = True


# Analytics Models


class AnalyticsOverview(BaseModel):
    """Analytics overview data."""

    period: str
    total_customers: int = 0
    new_customers: int = 0
    active_customers: int = 0
    total_orders: int = 0
    total_revenue: float = 0.0
    average_order_value: float = 0.0
    conversion_rate: float = 0.0


class CustomerRetention(BaseModel):
    """Customer retention data."""

    period_days: int
    cohort_size: int = 0
    retained_count: int = 0
    retention_rate: float = 0.0


class CampaignAnalytics(BaseModel):
    """Campaign analytics data."""

    campaign_id: str
    campaign_name: str
    target_count: int = 0
    reached_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    converted_count: int = 0
    reach_rate: float = 0.0
    open_rate: float = 0.0
    click_rate: float = 0.0
    conversion_rate: float = 0.0
    revenue: float = 0.0
    roi: float = 0.0


# API Response Wrappers


class PaginatedResponse(BaseModel):
    """Paginated API response."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool = False


class APIResponse(BaseModel):
    """Standard API response wrapper."""

    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
