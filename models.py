from sqlalchemy import Column, Integer, SmallInteger, String, Text, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username      = Column(String(30), unique=True, nullable=False, index=True)
    name          = Column(String(30), nullable=False)
    email         = Column(String(100), unique=True, nullable=False, index=True)
    phone         = Column(String(20), nullable=False)
    is_approved   = Column(SmallInteger, default=1, nullable=False)  # 0=no, 1=yes
    password      = Column(String(255), nullable=False)              # bcrypt hash
    created_at    = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    profiles = relationship(
        "UserProfile",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    resumes = relationship(
        "Resume",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Attribute(Base):
    __tablename__ = "attribute"

    id   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False, default="text")

    user_profiles = relationship("UserProfile", back_populates="attribute")


class UserProfile(Base):
    """
    Stores resume-parsed attribute values per user.
    Each row = one attribute (skill, education, etc.) for a user.

    Columns:
      - user_image  : Base64 profile photo extracted from resume, or NULL
      - resume_path : Local path of the uploaded resume file, or NULL
    """
    __tablename__ = "user_profile"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attribute_id    = Column(Integer, ForeignKey("attribute.id", ondelete="CASCADE"), nullable=False)
    attribute_value = Column(Text, nullable=True)
    user_image      = Column(Text, nullable=True)          # Base64 image from resume (nullable)
    resume_path     = Column(String(500), nullable=True)   # Local path to uploaded resume file

    user      = relationship("User", back_populates="profiles")
    attribute = relationship("Attribute", back_populates="user_profiles")


class Resume(Base):
    """
    Tracks every uploaded resume separately (one user can have multiple resumes).
    """
    __tablename__ = "resumes"

    id            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_name   = Column(String(255), nullable=False)          # Original file name
    file_path     = Column(String(500), nullable=False)          # Server disk path
    file_size     = Column(Integer, nullable=False)              # Size in bytes
    mime_type     = Column(String(50), default="application/pdf", nullable=False)
    skills        = Column(Text, nullable=True)                  # Comma-separated extracted skills
    uploaded_date = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="resumes")