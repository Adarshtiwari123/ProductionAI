from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime, date
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
    interview_limit: int
    tier: str

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
    value: Optional[str] = None

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
    value: str


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

class SubscriptionRequest(BaseModel):
    package_id: int

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
    package_name: str
    interview_limit: int
    pricing: float
    start_date: datetime
    end_date: datetime
    status: int

    class Config:
        from_attributes = True


class PaymentReviewRequest(BaseModel):
    subscription_id: int
    payment_method: str
    transaction_id: str
    amount_paid: float
    note: Optional[str] = None


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


# ── Interview Session Schemas (New) ───────────────────────────────────────────

class InterviewSessionBase(BaseModel):
    role:             str
    topic:            str
    difficulty:       str = "medium"
    duration_minutes: int = 20
    total_questions:  int = 5
    resume_id:        Optional[int] = None

class InterviewSessionCreate(InterviewSessionBase):
    pass

class InterviewSessionResponse(InterviewSessionBase):
    id:         int
    user_id:    int
    status:     str
    started_at: Optional[datetime] = None
    ended_at:   Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Question Schemas (New) ────────────────────────────────────────────────────

class QuestionBase(BaseModel):
    text:               str
    type:               str
    difficulty:         str
    role:               str
    domain:             Optional[str] = None
    is_company_question: bool = False
    frequency_score:    int = 0

class QuestionResponse(QuestionBase):
    id:         int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Session Question Schemas (New) ───────────────────────────────────────────

class SessionQuestionBase(BaseModel):
    session_id:     int
    question_id:    int
    question_order: int
    answer_text:    Optional[str] = None
    score:          Optional[int] = None
    ai_feedback:    Optional[str] = None
    is_skipped:     bool = False
    answered_at:    Optional[datetime] = None

class SessionQuestionResponse(SessionQuestionBase):
    id:         int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Interview Report Schemas (New) ────────────────────────────────────────────

class InterviewReportBase(BaseModel):
    session_id:            int
    user_id:               int
    overall_score:         Optional[int] = None
    technical_score:       Optional[int] = None
    communication_score:   Optional[int] = None
    problem_solving_score: Optional[int] = None
    project_score:         Optional[int] = None
    strengths:             Optional[List[str]] = None
    improvements:          Optional[List[str]] = None
    suggestions:           Optional[str] = None
    pdf_path:              Optional[str] = None
    generated_at:          Optional[datetime] = None

class InterviewReportResponse(InterviewReportBase):
    id:         int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Company Question Schemas (New) ────────────────────────────────────────────

class CompanyQuestionBase(BaseModel):
    question_id:     int
    company_name:    str
    frequency_score: int = 5
    role:            Optional[str] = None
    year_seen:       Optional[int] = None
    source:          str = "gpt_generated"

class CompanyQuestionResponse(CompanyQuestionBase):
    id:         int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Usage Tracker Schemas (New) ──────────────────────────────────────────────

class UsageTrackerResponse(BaseModel):
    id:                 int
    user_id:            int
    subscription_id:    Optional[int] = None
    sessions_used:      int
    questions_used:     int
    voice_minutes_used: int
    period_start:       date
    period_end:         date
    reset_at:           Optional[datetime] = None
    created_at:         datetime
    updated_at:         datetime

    class Config:
        from_attributes = True


# ── Access Validation Schemas (New) ───────────────────────────────────────────

class ValidateAccessRequest(BaseModel):
    duration_minutes: int
    role:             str
    topic:            str
    difficulty:       str

class ValidateAccessResponse(BaseModel):
    allowed:               bool
    credits_remaining:     int
    cost_required:         Optional[int] = None
    credits_after:         Optional[int] = None
    warning:               Optional[str] = None
    reason:                Optional[str] = None
    redirect_to:           Optional[str] = None
    upgrade_required:      Optional[bool] = None
    # For backward compatibility
    max_duration_allowed:  Optional[int] = None


class InterviewSetupRequest(BaseModel):
    role:             str
    topic:            str
    difficulty:       str
    duration_minutes: int

class InterviewSetupResponse(BaseModel):
    success:              bool
    session_id:           int
    userid:               int
    name:                 str
    role:                 str
    topic:                str
    difficulty:           str
    duration_minutes:     int
    total_questions:      int
    resume_id:            Optional[int] = None
    has_resume:           bool
    status:               str
    started_at:           Optional[str] = None
    credits_remaining:    int
    credits_used:         int
    credits_deducted:     int


class InterviewChangeSetupRequest(BaseModel):
    session_id:           int


class InterviewChangeSetupResponse(BaseModel):
    success:              bool
    message:              str
    session_id:           int
    credits_refunded:     int
    credits_remaining:    int



class InterviewSessionSummaryResponse(BaseModel):
    success:              bool
    session_id:           int
    userid:               int
    role:                 str
    topic:                str
    difficulty:           str
    duration_minutes:     int
    total_questions:      int
    has_resume:           bool
    credits_remaining:    int
    status:               str
    info_message:         str

class DurationOption(BaseModel):
    duration: int
    is_available: bool
    cost: int
    unavailable_reason: Optional[str] = None

class UpgradeBanner(BaseModel):
    show: bool
    message: str
    target_plan: Optional[str] = None

class AllowedDurationsResponse(BaseModel):
    userid: int
    credits_remaining: int
    allowed_durations: List[DurationOption]
    upgrade_banner: UpgradeBanner


# ── Interview Execution Schemas (New) ────────────────────────────────────────

from typing import Union

class ConfirmStartRequest(BaseModel):
    session_id:           Union[int, str]
    userid:               int

class ConfirmStartResponse(BaseModel):
    success:              bool
    enhanced:             Optional[bool] = False
    error:                Optional[str] = None
    questions_list:       Optional[List[Union[dict, str]]] = None
    ai_greeting:          Optional[str] = None
    conversation_history: Optional[List[dict]] = None

class AnswerRequest(BaseModel):
    session_id:           Union[int, str]
    userid:               int
    answer:               str
    question_number:      int
    is_skipped:           bool
    conversation_history: List[dict]

class AnswerResponse(BaseModel):
    next_ai_message:      str
    conversation_history: List[dict]
    question_number:      int
    interview_complete:   bool

class EndInterviewRequest(BaseModel):
    session_id:           Union[int, str]
    userid:               int
    conversation_history: List[dict]

class EndInterviewResponse(BaseModel):
    success:              bool
    message:              str
