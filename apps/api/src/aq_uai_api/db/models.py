"""Phase-1 diagnostic table only. Not a replacement for phase-2/3 domain schemas."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from aq_uai_api.db.base import Base


class AppMetadata(Base):
    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
