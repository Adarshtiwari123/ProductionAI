from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
import re


# ── User Schemas ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    name: str
    email: EmailStr
    phone: str
    password: str
    confirm_password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        if len(v) > 30:
            raise ValueError("Username must be max 30 characters")
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError("Username can only contain letters, numbers, underscores")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 13:
            raise ValueError("Password must be max 13 characters")
        if not re.search(r'[A-Za-z]', v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        cleaned = re.sub(r'[\s\-()]', '', v)
        if not re.match(r'^\+?[\d]{7,15}$', cleaned):
            raise ValueError("Enter a valid phone number (e.g. +91 7800046119)")
        return v

    @field_validator("name")
    @classmethod
    def name_valid(cls, v):
        if len(v) > 30:
            raise ValueError("Name must be max 30 characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    email: str
    phone: str
    pic: Optional[str] = None
    is_valid: int

    class Config:
        from_attributes = True


# ── Update User Profile Schemas ───────────────────────────────────────────────

class UpdateUserProfileResponse(BaseModel):
    """Returned after a successful profile update."""
    success: bool = True
    message: str
    data: dict  # contains user_id, username, first_name, last_name, email, phone, user_image

    class Config:
        from_attributes = True


# ── Attribute Schemas ─────────────────────────────────────────────────────────

class AttributeResponse(BaseModel):
    id: int
    code: str
    name: str
    type: str

    class Config:
        from_attributes = True


# ── User Profile Schemas ──────────────────────────────────────────────────────

class UserProfileItem(BaseModel):
    attribute_code: str
    attribute_name: str
    values: Optional[str] = None

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    name: str
    email: str
    resume_path: Optional[str] = None   # path of the last uploaded resume on disk
    user_image: Optional[str] = None    # path or base64 of the profile image
    profile: List[UserProfileItem] = []

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    attribute_code: str
    values: str


# ── Change Password ───────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_valid(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 13:
            raise ValueError("Password must be max 13 characters")
        if not re.search(r'[A-Za-z]', v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── Resume Schemas ────────────────────────────────────────────────────────────

class ResumeData(BaseModel):
    """Detailed data returned after upload or in list."""
    resume_id:       int
    resume_name:     str
    size:            str                    # Human-readable, e.g. "256 KB"
    updated_at:      str                    # Formatted as "April 22, 2026"
    skills:          List[str] = []         # List of individual skills
    domain:          Optional[str] = None
    view_resume:     str                    # URL path to view inline
    download_resume: str                    # URL path to download
    delete_resume:   str                    # URL path to delete

    class Config:
        from_attributes = True


class ResumeUploadResponse(BaseModel):
    """Returned by POST /upload-resume"""
    success: bool = True
    message: str
    data:    ResumeData


class ResumeListResponse(BaseModel):
    """Returned by GET /resumes"""
    success: bool = True
    message: str
    data:    List[ResumeData] = []


# ── Packages & Payments (New) ────────────────────────────────────────────────

class PackageResponse(BaseModel):
    id: int
    name: str
    price: float
    interview_limit: int
    features: Optional[str] = None

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    id: int
    package_id: int
    start_date: datetime
    end_date: datetime
    status: str

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: int
    subscription_id: int
    amount: float
    payment_method: str
    status: str
    transaction_id: str
    created_at: datetime

    class Config:
        from_attributes = True
