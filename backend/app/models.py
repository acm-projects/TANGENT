import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, ForeignKey, UniqueConstraint,
    TIMESTAMP, text,
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
    "standard", "temporary",
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

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    revoked_at = Column(TIMESTAMP(timezone=True), nullable=True)

    project = relationship("Project", back_populates="shares", foreign_keys=[project_id])
    shared_by = relationship("User", back_populates="shares_created", foreign_keys=[shared_by_id])
    shared_with = relationship("User", back_populates="shares_received", foreign_keys=[shared_with_id])