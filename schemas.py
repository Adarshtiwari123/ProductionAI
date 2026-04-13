from pydantic import BaseModel, EmailStr
from typing import Optional

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    confirm_password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str

    class Config:
        from_attributes = True

class UserProfileResponse(BaseModel):
    id: int
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    years_of_experience: Optional[str] = None  # always string
    bio: Optional[str] = None
    skills: Optional[str] = None
    projects: Optional[str] = None             # for IT students
    resume_filename: Optional[str] = None

    class Config:
        from_attributes = True
# from pydantic import BaseModel, EmailStr
# from typing import Optional

# class RegisterRequest(BaseModel):
#     full_name: str
#     email: EmailStr
#     password: str
#     confirm_password: str

# class LoginRequest(BaseModel):
#     email: EmailStr
#     password: str

# class TokenResponse(BaseModel):
#     access_token: str
#     token_type: str

# class UserResponse(BaseModel):
#     id: int
#     full_name: str
#     email: str

#     class Config:
#         from_attributes = True

# class UserProfileResponse(BaseModel):
#     id: int
#     user_id: int
#     first_name: Optional[str] = None
#     last_name: Optional[str] = None
#     email: Optional[str] = None
#     phone: Optional[str] = None
#     location: Optional[str] = None
#     linkedin_url: Optional[str] = None
#     current_title: Optional[str] = None
#     current_company: Optional[str] = None
#     years_of_experience: Optional[str] = None
#     bio: Optional[str] = None
#     skills: Optional[str] = None
#     resume_filename: Optional[str] = None

#     class Config:
#         from_attributes = True
# # from pydantic import BaseModel, EmailStr

# # class RegisterRequest(BaseModel):
# #     full_name: str
# #     email: EmailStr
# #     password: str
# #     confirm_password: str

# # class LoginRequest(BaseModel):
# #     email: EmailStr
# #     password: str

# # class TokenResponse(BaseModel):
# #     access_token: str
# #     token_type: str

# # class UserResponse(BaseModel):
# #     id: int
# #     full_name: str
# #     email: str

# #     class Config:
# #         from_attributes = True