from sqlalchemy import Column, Integer, SmallInteger, String, Text, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(30), nullable=False)
    email = Column(String(30), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    is_approved = Column(SmallInteger, default=1, nullable=False)  # 0 = not approved, 1 = approved
    password = Column(String(255), nullable=False)  # MD5 hash stored here
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to user_profile
    profiles = relationship(
        "UserProfile",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Attribute(Base):
    __tablename__ = "attribute"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False)   # e.g. technical_skills
    name = Column(String(100), nullable=False)                # e.g. Technical Skills
    type = Column(String(50), nullable=False, default="text") # text, multi, date

    # Relationship
    user_profiles = relationship("UserProfile", back_populates="attribute")


class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    attribute_id = Column(
        Integer,
        ForeignKey("attribute.id", ondelete="CASCADE"),
        nullable=False
    )
    attribute_value = Column(Text, nullable=True)  # comma separated for multi values

    # Relationships
    user = relationship("User", back_populates="profiles")
    attribute = relationship("Attribute", back_populates="user_profiles")