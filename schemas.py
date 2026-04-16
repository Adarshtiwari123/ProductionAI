from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
import re


# ── User Schemas ─────────────────────────────────────────────────────────────

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
        # Remove spaces and dashes for validation
        cleaned = re.sub(r'[\s\-()]', '', v)
        # Accept formats: +91XXXXXXXXXX, +1XXXXXXXXXX, 10-digit numbers
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
    username: str   # login via username
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
    is_approved: int  # 0 = not approved, 1 = approved

    class Config:
        from_attributes = True


# ── Attribute Schemas ────────────────────────────────────────────────────────

class AttributeResponse(BaseModel):
    id: int
    code: str
    name: str
    type: str

    class Config:
        from_attributes = True


# ── User Profile Schemas ─────────────────────────────────────────────────────

class UserProfileItem(BaseModel):
    attribute_code: str
    attribute_name: str
    attribute_value: Optional[str] = None

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    name: str
    email: str
    profile: List[UserProfileItem] = []

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    attribute_code: str
    attribute_value: str
# from pydantic import BaseModel, EmailStr, field_validator
# from typing import Optional, List
# import re


# # ── User Schemas ─────────────────────────────────────────────────────────────

# class RegisterRequest(BaseModel):
#     username: str
#     name: str
#     email: EmailStr
#     phone: str
#     password: str
#     confirm_password: str

#     @field_validator("username")
#     @classmethod
#     def username_valid(cls, v):
#         if len(v) > 30:
#             raise ValueError("Username must be max 30 characters")
#         if not re.match(r'^[a-zA-Z0-9_]+$', v):
#             raise ValueError("Username can only contain letters, numbers, underscores")
#         return v

#     @field_validator("password")
#     @classmethod
#     def password_valid(cls, v):
#         if len(v) < 8:
#             raise ValueError("Password must be at least 8 characters")
#         if len(v) > 13:
#             raise ValueError("Password must be max 13 characters")
#         if not re.search(r'[A-Za-z]', v):
#             raise ValueError("Password must contain at least one letter")
#         if not re.search(r'\d', v):
#             raise ValueError("Password must contain at least one digit")
#         return v

#     @field_validator("phone")
#     @classmethod
#     def phone_valid(cls, v):
#         # Remove spaces and dashes for validation
#         cleaned = re.sub(r'[\s\-()]', '', v)
#         # Accept formats: +91XXXXXXXXXX, +1XXXXXXXXXX, 10-digit numbers
#         if not re.match(r'^\+?[\d]{7,15}$', cleaned):
#             raise ValueError("Enter a valid phone number (e.g. +91 7800046119)")
#         return v

#     @field_validator("name")
#     @classmethod
#     def name_valid(cls, v):
#         if len(v) > 30:
#             raise ValueError("Name must be max 30 characters")
#         return v


# class LoginRequest(BaseModel):
#     username: str   # login via username
#     password: str


# class TokenResponse(BaseModel):
#     access_token: str
#     token_type: str


# class UserResponse(BaseModel):
#     id: int
#     username: str
#     name: str
#     email: str
#     phone: str
#     is_approved: str

#     class Config:
#         from_attributes = True


# # ── Attribute Schemas ────────────────────────────────────────────────────────

# class AttributeResponse(BaseModel):
#     id: int
#     code: str
#     name: str
#     type: str

#     class Config:
#         from_attributes = True


# # ── User Profile Schemas ─────────────────────────────────────────────────────

# class UserProfileItem(BaseModel):
#     attribute_code: str
#     attribute_name: str
#     attribute_value: Optional[str] = None

#     class Config:
#         from_attributes = True


# class UserProfileResponse(BaseModel):
#     user_id: int
#     username: str
#     name: str
#     email: str
#     profile: List[UserProfileItem] = []

#     class Config:
#         from_attributes = True


# class UpdateProfileRequest(BaseModel):
#     attribute_code: str
#     attribute_value: str
