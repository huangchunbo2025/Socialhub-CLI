import enum


class DeveloperRole(str, enum.Enum):
    DEVELOPER = "developer"
    STORE_ADMIN = "store_admin"


class DeveloperStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class SkillCategory(str, enum.Enum):
    DATA = "data"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    INTEGRATION = "integration"
    UTILITY = "utility"


class SkillStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class VersionStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
