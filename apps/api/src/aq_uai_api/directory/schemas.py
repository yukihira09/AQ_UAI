"""Explicit inputs and public projections for directory and audit routes."""

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)

from aq_uai_api.auth.security import PASSWORD_MAX, PASSWORD_MIN, normalize_username
from aq_uai_api.authorization.policy import GrantScope, GrantSubject, PermissionCode

AccountState = Literal["PENDING", "ACTIVE", "DISABLED"]
CodeType = Literal["STAFF", "STUDENT"]
GroupKind = Literal["SYSTEM", "AUTHORIZATION", "AI_SPECIALIST"]
Outcome = Literal["SUCCESS", "FAILURE"]


def clean_text(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Control characters are not allowed.")
    value.encode("utf-8")
    return value


def canonical_username(value: str) -> str:
    name = normalize_username(value)
    if name is None:
        raise ValueError("Enter a valid username.")
    return name


Name = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(clean_text),
]
Code = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=64),
    AfterValidator(clean_text),
]
Username = Annotated[
    str, StringConstraints(strict=True, max_length=256), AfterValidator(canonical_username)
]
TemporaryPassword = Annotated[SecretStr, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateUser(Input):
    primary_unit_id: UUID
    username: Username
    display_name: Name
    code_type: CodeType
    institutional_code: Code
    temporary_password: TemporaryPassword | None = None


class ProfilePatch(Input):
    display_name: Name


class PartialPatch(Input):
    @model_validator(mode="after")
    def supplied_fields_are_non_null(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply at least one non-null field.")
        return self


class IdentityPatch(PartialPatch):
    username: Username | None = None
    code_type: CodeType | None = None
    institutional_code: Code | None = None


class Activation(Input):
    temporary_password: TemporaryPassword | None = None


class Transfer(Input):
    primary_unit_id: UUID


class CreateUnit(Input):
    code: Code
    name: Name


class UnitPatch(PartialPatch):
    code: Code | None = None
    name: Name | None = None


class CreateGroup(Input):
    code: Code
    name: Name
    kind: GroupKind


class GroupPatch(Input):
    name: Name


class CreateAssignment(Input):
    role_code: Code
    scope: GrantScope
    unit_id: UUID | None = None


class PageParams(Input):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)


class SearchParams(PageParams):
    q: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=128),
            AfterValidator(clean_text),
        ]
        | None
    ) = None


class UserFilters(SearchParams):
    primary_unit_id: UUID | None = None
    state: AccountState | None = None
    code_type: CodeType | None = None


class UnitFilters(SearchParams):
    active: bool | None = None


class GroupFilters(UnitFilters):
    kind: GroupKind | None = None


class MemberFilters(SearchParams):
    active: bool | None = True


class AssignmentFilters(PageParams):
    role_code: Code | None = None
    scope: GrantScope | None = None
    unit_id: UUID | None = None


class AuditFilters(PageParams):
    action: Code | None = None
    actor_id: UUID | None = None
    target_type: Code | None = None
    target_id: UUID | None = None
    outcome: Outcome | None = None
    from_time: AwareDatetime | None = None
    to_time: AwareDatetime | None = None

    @model_validator(mode="after")
    def time_range_is_ordered(self):
        if self.from_time and self.to_time and self.from_time >= self.to_time:
            raise ValueError("Use an increasing event time range.")
        return self


class PublicRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(PublicRecord):
    id: UUID
    institution_id: UUID
    primary_unit_id: UUID
    username: str
    display_name: str
    code_type: CodeType
    institutional_code: str
    state: AccountState
    created_at: datetime
    updated_at: datetime


class UnitOut(PublicRecord):
    id: UUID
    institution_id: UUID
    code: str
    name: str
    active: bool


class GroupOut(UnitOut):
    kind: GroupKind
    created_at: datetime
    updated_at: datetime


class MemberOut(PublicRecord):
    group_id: UUID
    user: UserOut
    active: bool
    created_at: datetime
    updated_at: datetime


class AssignmentOut(PublicRecord):
    id: UUID
    institution_id: UUID
    subject: GrantSubject
    subject_id: UUID
    role_code: str
    scope: GrantScope
    unit_id: UUID | None


class RoleOut(PublicRecord):
    code: str
    permissions: list[str]


class AuditOut(PublicRecord):
    id: UUID
    institution_id: UUID
    actor_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    outcome: Outcome
    occurred_at: datetime
    request_id: str
    changes: Mapping[str, object]


class CapabilityScope(PublicRecord):
    institution_wide: bool
    unit_ids: list[UUID]


class Capabilities(PublicRecord):
    institution_id: UUID
    permissions: dict[PermissionCode, CapabilityScope]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
