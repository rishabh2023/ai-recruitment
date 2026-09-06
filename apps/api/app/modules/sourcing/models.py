"""External sourcing (people-search provenance)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, created_at, uuid_pk


class ExternalSearch(Base):
    __tablename__ = "external_searches"

    id = uuid_pk()
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Text, nullable=False)  # apollo | pdl | proxycurl | coresignal
    query = Column(JSONB, nullable=False, server_default="{}")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = created_at()


class ExternalCandidate(Base):
    __tablename__ = "external_candidates"

    id = uuid_pk()
    external_search_id = Column(UUID(as_uuid=True), ForeignKey("external_searches.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Text, nullable=False)
    source_id = Column(Text)
    profile = Column(JSONB, nullable=False, server_default="{}")
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="SET NULL"))
    created_at = created_at()
