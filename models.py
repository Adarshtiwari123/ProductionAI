from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"  # cascade delete
    )

class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Personal Information
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)

    # Professional Summary
    current_title = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    years_of_experience = Column(String, nullable=True)
    bio = Column(Text, nullable=True)

    # Skills
    skills = Column(Text, nullable=True)

    # Projects (for IT students)
    projects = Column(Text, nullable=True)

    # Resume
    resume_filename = Column(String, nullable=True)
    resume_text = Column(Text, nullable=True)

    user = relationship("User", back_populates="profile")
# from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
# from sqlalchemy.orm import relationship
# from database import Base

# class User(Base):
#     __tablename__ = "users"

#     id = Column(Integer, primary_key=True, index=True)
#     full_name = Column(String, nullable=False)
#     email = Column(String, unique=True, index=True, nullable=False)
#     hashed_password = Column(String, nullable=False)
#     profile = relationship("UserProfile", back_populates="user", uselist=False)

# class UserProfile(Base):
#     __tablename__ = "user_profile"

#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

#     # Personal Information
#     first_name = Column(String, nullable=True)
#     last_name = Column(String, nullable=True)
#     email = Column(String, nullable=True)
#     phone = Column(String, nullable=True)
#     location = Column(String, nullable=True)
#     linkedin_url = Column(String, nullable=True)

#     # Professional Summary
#     current_title = Column(String, nullable=True)
#     current_company = Column(String, nullable=True)
#     years_of_experience = Column(String, nullable=True)
#     bio = Column(Text, nullable=True)

#     # Skills
#     skills = Column(Text, nullable=True)  # stored as comma separated

#     # Resume
#     resume_filename = Column(String, nullable=True)
#     resume_text = Column(Text, nullable=True)

#     user = relationship("User", back_populates="profile")
# # from sqlalchemy import Column, Integer, String
# # from database import Base

# # class User(Base):
# #     __tablename__ = "users"

# #     id = Column(Integer, primary_key=True, index=True)
# #     full_name = Column(String, nullable=False)
# #     email = Column(String, unique=True, index=True, nullable=False)
# #     hashed_password = Column(String, nullable=False)