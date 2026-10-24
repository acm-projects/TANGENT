import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, ForeignKey, Identity, Index, Integer, Numeric, SmallInteger,
    String, Text, Boolean, UniqueConstraint, TIMESTAMP, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PGEnum
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


# ============================================================================
# ENUMS
# create_type=False tells SQLAlchemy the type already exists in Postgres —
# ============================================================================
auth_provider_enum = PGEnum(
    "google", "github",
    name="auth_provider",
    create_type=False,
)

node_type_enum = PGEnum(
    "standard", "temporary", "debate",
    name="node_type",
    create_type=False,
)

invitation_status_enum = PGEnum(
    "PENDING", "ACCEPTED", "EXPIRED", "REVOKED",
    name="invitation_status",
    create_type=False,
)

share_permission_enum = PGEnum(
    "view",
    name="share_permission",
    create_type=False,
)

# Debate mode (see tangent-debate-mode-ddl.sql). The values must match the Postgres enums exactly.
debate_status_enum = PGEnum(
    "queued", "running", "awaiting_input", "finalizing", "completed", "failed", "cancelled",
    name="debate_status",
    create_type=False,
)

debate_winner_enum = PGEnum(
    "for", "against", "no_clear_winner",
    name="debate_winner",
    create_type=False,
)

debate_end_reason_enum = PGEnum(
    "rounds_exhausted", "budget_exhausted", "user_picked", "user_stopped",
    name="debate_end_reason",
    create_type=False,
)

debate_phase_enum = PGEnum(
    "intake", "frame", "research", "opening", "rebuttal", "closing", "judging",
    name="debate_phase",
    create_type=False,
)

debate_event_type_enum = PGEnum(
    "phase_changed", "question_requested", "answer_received", "turn_started", "turn_completed", "thinking",
    "control_applied", "tool_called", "verdict_ready", "completed", "failed", "cancelled",
    name="debate_event_type",
    create_type=False,
)


# ============================================================================
# 1. IDENTITY & ACCESS
# ============================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(Text, unique=True, nullable=False)
    name = Column("user_name", Text, nullable=False)
    auth_provider = Column(auth_provider_enum, nullable=False)
    provider_id = Column(Text, nullable=False)
    avatar_url = Column("profile_picture", Text, nullable=True)
    onboarding_completed = Column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_id", name="uq_users_provider"),
    )

    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")
    owned_workspaces = relationship("Workspace", back_populates="owner", cascade="all, delete-orphan")

    owned_projects = relationship("Project", back_populates="created_by", cascade="all, delete-orphan")

    invitations_sent = relationship("Invitation", back_populates="invited_by", cascade="all, delete-orphan")
    trees_created = relationship("Tree", back_populates="created_by", cascade="all, delete-orphan")
    nodes_created = relationship("Node", back_populates="created_by", cascade="all, delete-orphan")
    shares_created = relationship(
        "Share", back_populates="shared_by", foreign_keys="Share.shared_by_id", cascade="all, delete-orphan",
        passive_deletes=True
    )
    shares_received = relationship(
        "Share", back_populates="shared_with", foreign_keys="Share.shared_with_id", cascade="all, delete-orphan",
        passive_deletes=True
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_token_hash = Column(Text, unique=True, nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    is_revoked = Column(Boolean, nullable=False, server_default=text("FALSE"))
    consumed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    user = relationship("User", back_populates="sessions")


# ============================================================================
# 2. WORKSPACES & PROJECTS
# ============================================================================
class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    last_used_at = Column(TIMESTAMP(timezone=True), nullable=True)

    owner = relationship("User", back_populates="owned_workspaces")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    forked_from_project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    workspace = relationship("Workspace", back_populates="projects")
    created_by = relationship("User", back_populates="owned_projects")

    forked_from_project = relationship(
        "Project", remote_side=[id], foreign_keys=[forked_from_project_id]
    )

    invitations = relationship("Invitation", back_populates="project", cascade="all, delete-orphan")
    trees = relationship("Tree", back_populates="project", cascade="all, delete-orphan")
    nodes = relationship("Node", back_populates="project", cascade="all, delete-orphan")
    shares = relationship(
        "Share", back_populates="project", foreign_keys="Share.project_id", cascade="all, delete-orphan",
        passive_deletes=True
    )

class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    project_slug = Column(Text, nullable=False)
    project_name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    token_hash = Column(Text, unique=True, nullable=False)
    status = Column(invitation_status_enum, nullable=False, server_default=text("'PENDING'"))
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    inviter_name = Column(Text, nullable=False)
    invited_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Set: the invite is for this node's branch (the node and everything under it), not the whole tree.
    branch_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    project = relationship("Project", back_populates="invitations")
    invited_by = relationship("User", back_populates="invitations_sent")


# ============================================================================
# 3. TREES & NODES (the mind map)
# ============================================================================
class Tree(Base):
    __tablename__ = "trees"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    root_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    forked_from_tree_id = Column(UUID(as_uuid=True), ForeignKey("trees.id", ondelete="SET NULL"), nullable=True)
    forked_from_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    project = relationship("Project", back_populates="trees")
    created_by = relationship("User", back_populates="trees_created")

    nodes = relationship(
        "Node", back_populates="tree", cascade="all, delete-orphan",
        foreign_keys="Node.tree_id",
    )
    root_node = relationship("Node", foreign_keys=[root_node_id], post_update=True)
    forked_from_node = relationship("Node", foreign_keys=[forked_from_node_id], post_update=True)
    forked_from_tree = relationship("Tree", remote_side=[id])


class Node(Base):
    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tree_id = Column(UUID(as_uuid=True), ForeignKey("trees.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    fork_index = Column(Integer, nullable=False)
    node_type = Column(node_type_enum, nullable=False, server_default=text("'standard'"))
    status = Column(Text, nullable=False, server_default=text("'active'"))
    title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    chats = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    model = Column(Text, nullable=True)
    tokens = Column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("parent_id", "fork_index", name="uq_nodes_parent_fork_index"),
    )

    tree = relationship("Tree", back_populates="nodes", foreign_keys=[tree_id])
    project = relationship("Project", back_populates="nodes")
    created_by = relationship("User", back_populates="nodes_created")

    parent = relationship("Node", remote_side=[id], back_populates="children")
    children = relationship("Node", back_populates="parent", cascade="all, delete-orphan")

    merge_sources = relationship(
        "NodeMergeSource", back_populates="node",
        foreign_keys="NodeMergeSource.node_id", cascade="all, delete-orphan",
    )


class NodeMergeSource(Base):
    __tablename__ = "node_merge_sources"

    node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    source_leaf_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    node = relationship("Node", foreign_keys=[node_id], back_populates="merge_sources")
    source_leaf = relationship("Node", foreign_keys=[source_leaf_id])


# ============================================================================
# 4. SHARING
# ============================================================================
class Share(Base):
    __tablename__ = "shares"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    shared_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shared_with_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    share_token = Column(Text, unique=True, nullable=True)
    permission = Column(share_permission_enum, nullable=False, server_default=text("'view'"))
    branch_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    revoked_at = Column(TIMESTAMP(timezone=True), nullable=True)

    project = relationship("Project", back_populates="shares", foreign_keys=[project_id])
    shared_by = relationship("User", back_populates="shares_created", foreign_keys=[shared_by_id])
    shared_with = relationship("User", back_populates="shares_received", foreign_keys=[shared_with_id])


# ============================================================================
# 5. DEBATE MODE
# Mapped for completeness (metadata, warm_pool, future migrations). No relationship() links to User/Project/Node on
# purpose: deleting a user, project or node is handled by the ON DELETE rules in Postgres, and the debate package reads
# and writes these tables with its own SQL. Row-level security is defined in the DDL, not here.
# ============================================================================
class Debate(Base):
    __tablename__ = "debates"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    topic = Column(Text, nullable=False)
    for_model = Column(Text, nullable=False)
    against_model = Column(Text, nullable=False)
    judge_model = Column(Text, nullable=False)
    rounds = Column(SmallInteger, nullable=False, server_default=text("2"))
    status = Column(debate_status_enum, nullable=False, server_default=text("'queued'"))
    current_phase = Column(debate_phase_enum, nullable=True)
    current_round = Column(SmallInteger, nullable=False, server_default=text("0"))
    pending_questions = Column(JSONB, nullable=True)
    resume_payload = Column(JSONB, nullable=True)
    result_node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    retain_artifacts = Column(Boolean, nullable=False, server_default=text("FALSE"))
    end_reason = Column(debate_end_reason_enum, nullable=True)
    control = Column(JSONB, nullable=True)
    lease_until = Column(TIMESTAMP(timezone=True), nullable=True)
    error_code = Column(Text, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=False, server_default=text("0"))
    usage_summary = Column(JSONB, nullable=True)
    wall_ms = Column(Integer, nullable=True)
    active_ms = Column(Integer, nullable=False, server_default=text("0"))
    waited_ms = Column(Integer, nullable=True)
    segments = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    timings = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW() + INTERVAL '7 days'"))
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("rounds BETWEEN 1 AND 3"),
        CheckConstraint("status = 'awaiting_input' OR pending_questions IS NULL", name="ck_debates_pending_only_when_awaiting"),
        CheckConstraint("jsonb_typeof(timings) = 'array'", name="ck_debates_timings_is_array"),
        CheckConstraint("jsonb_typeof(segments) = 'array'", name="ck_debates_segments_is_array"),
        Index("ix_debates_project_id", "project_id"),
        Index("ix_debates_owner_id", "owner_id"),
        Index("ix_debates_parent_node_id", "parent_node_id", postgresql_where=text("parent_node_id IS NOT NULL")),
        Index("ix_debates_owner_active", "owner_id",
              postgresql_where=text("status IN ('queued', 'running', 'awaiting_input', 'finalizing')")),
        Index("ix_debates_expiry", "expires_at",
              postgresql_where=text("status IN ('queued', 'running', 'awaiting_input')")),
        Index("uq_debates_result_node", "result_node_id", unique=True, postgresql_where=text("result_node_id IS NOT NULL")),
    )


class DebateEvent(Base):
    __tablename__ = "debate_events"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    debate_id = Column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(debate_event_type_enum, nullable=False)
    event_key = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    __table_args__ = (
        Index("ix_debate_events_debate_id_id", "debate_id", "id"),
        Index("uq_debate_events_key", "debate_id", "event_key", unique=True, postgresql_where=text("event_key IS NOT NULL")),
    )


class DebateResult(Base):
    """One row per finished debate, keyed by the debate-type node that holds the result in the mind map."""

    __tablename__ = "debate_results"

    node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    debate_id = Column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="SET NULL"), unique=True, nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    proposition = Column(Text, nullable=False)
    winner = Column(debate_winner_enum, nullable=False)
    judge_would_have_chosen = Column(debate_winner_enum, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=False)
    summary = Column(Text, nullable=False)
    final_output = Column(Text, nullable=False)
    verdict_rationale = Column(Text, nullable=False)
    scores = Column(JSONB, nullable=False)
    strongest_counterpoints = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    verdict_flips_if = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    citations = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    clarifications = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    for_model = Column(Text, nullable=False)
    against_model = Column(Text, nullable=False)
    judge_model = Column(Text, nullable=False)
    rounds = Column(SmallInteger, nullable=False)
    end_reason = Column(debate_end_reason_enum, nullable=False, server_default=text("'rounds_exhausted'"))
    cost_usd = Column(Numeric(12, 6), nullable=False, server_default=text("0"))
    usage = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    usage_summary = Column(JSONB, nullable=True)
    timings = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    timing_summary = Column(JSONB, nullable=True)
    wall_ms = Column(Integer, nullable=True)
    active_ms = Column(Integer, nullable=True)
    waited_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1"),
        CheckConstraint("jsonb_typeof(usage) = 'array'", name="ck_debate_results_usage_is_array"),
        CheckConstraint("jsonb_typeof(timings) = 'array'", name="ck_debate_results_timings_is_array"),
        Index("ix_debate_results_project_id", "project_id"),
    )