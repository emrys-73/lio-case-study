import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MemberRole = Literal["admin", "buyer", "requester"]

# Request fields an organization may optionally mark as required. (The other
# request fields are always required by the app.)
ConfigurableRequiredField = Literal["vat_id", "department"]


class _RuleFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] = Field(min_length=1)
    commodity_group_id: int
    reason: str = ""
    max_amount: float | None = Field(default=None, gt=0)

    @field_validator("keywords")
    @classmethod
    def _keywords_not_blank(cls, keywords: list[str]) -> list[str]:
        cleaned = [keyword.strip() for keyword in keywords]
        if any(not keyword for keyword in cleaned):
            raise ValueError("keywords can't be blank")
        return cleaned


class CommodityRuleIn(_RuleFields):
    id: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class CommodityRule(_RuleFields):
    id: str
    updated_by: str | None = None
    updated_at: datetime | None = None


class OrganizationSettings(BaseModel):
    """Per-organization configuration. Stored as JSONB, validated here.

    This is the reference pattern for tenant config: keep the storage flexible,
    but validate the shape at the edge so it can't drift into a free-for-all.
    """

    model_config = ConfigDict(extra="forbid")

    required_fields: list[ConfigurableRequiredField] = Field(default_factory=list)
    commodity_rules: list[CommodityRule] = Field(default_factory=list)


class OrganizationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_fields: list[ConfigurableRequiredField] | None = None
    commodity_rules: list[CommodityRuleIn] | None = None


class OrganizationCreate(BaseModel):
    name: str
    slug: str


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class MyOrganizationOut(OrganizationOut):
    role: MemberRole


class MemberProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MemberRole
    created_at: datetime
    # Named to match the Supabase join key the frontend already renders.
    profiles: MemberProfileOut | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: str
    invited_by: uuid.UUID
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class MembersResponse(BaseModel):
    members: list[MemberOut]
    invites: list[InviteOut]


class InviteCreate(BaseModel):
    email: EmailStr
    role: MemberRole = "requester"


class InviteAccept(BaseModel):
    token: str
