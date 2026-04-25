from sqlalchemy import Column, Integer, SmallInteger, String, Text, ForeignKey, TIMESTAMP, Float, DateTime
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
    pic           = Column(Text, nullable=True)          # Base64 or URL profile image
    is_valid      = Column(SmallInteger, default=1, nullable=False)  # 0=no, 1=yes (renamed from is_approved)
    password      = Column(String(255), nullable=False)              # bcrypt hash
    created_at    = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    profiles      = relationship("UserProfile", back_populates="user", cascade="all, delete-orphan")
    resumes       = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments      = relationship("Payment", back_populates="user", cascade="all, delete-orphan")


class Attribute(Base):
    __tablename__ = "attribute"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code       = Column(String(100), unique=True, nullable=False)
    name       = Column(String(100), nullable=False)
    type       = Column(String(50), nullable=False, default="text")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    user_profiles = relationship("UserProfile", back_populates="attribute")


class UserProfile(Base):
    """
    Stores resume-parsed attribute values per user.
    Each row = one attribute (skill, education, etc.) for a user.
    """
    __tablename__ = "user_profile"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id    = Column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
    attribute_id = Column(Integer, ForeignKey("attribute.id", ondelete="CASCADE"), nullable=False)
    value        = Column(Text, nullable=True)
    created_at   = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at   = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    user      = relationship("User", back_populates="profiles")
    attribute = relationship("Attribute", back_populates="user_profiles")
    resume    = relationship("Resume", back_populates="profile_entries")


class Resume(Base):
    """
    Tracks every uploaded resume separately.
    """
    __tablename__ = "resumes"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_name = Column(String(255), nullable=False) # Renamed from file_name
    path        = Column(String(500), nullable=False) # Renamed from file_path
    skills      = Column(Text, nullable=True)
    size        = Column(Integer, nullable=False)     # Renamed from file_size
    domain      = Column(String(100), nullable=True)
    mime_type   = Column(String(50), default="application/pdf", nullable=False)
    created_at  = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at  = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False) # Renamed from uploaded_date

    user            = relationship("User", back_populates="resumes")
    profile_entries = relationship("UserProfile", back_populates="resume", cascade="all, delete-orphan")


class Package(Base):
    __tablename__ = "packages"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name            = Column(String(100), nullable=False)
    price           = Column(Float, nullable=False)
    interview_limit = Column(Integer, nullable=False)
    features        = Column(Text, nullable=True) # JSON or Comma-separated
    created_at      = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at      = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    subscriptions = relationship("Subscription", back_populates="package")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date   = Column(DateTime, nullable=False)
    status     = Column(String(50), default="active")
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    user    = relationship("User", back_populates="subscriptions")
    package = relationship("Package", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    amount          = Column(Float, nullable=False)
    payment_method  = Column(String(50), nullable=False)
    status          = Column(String(50), default="completed")
    transaction_id  = Column(String(100), unique=True, nullable=False)
    created_at      = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at      = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    user         = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")