import os
import uuid
import contextlib
import sys
import smtplib
from email.mime.text import MIMEText
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
import json
import openai
from groq import Groq

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path, override=True)

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)

# Add current directory to sys.path to support both direct run and module run
sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import JWTError
from typing import Optional, List
from sqlalchemy import text
import models, schemas, auth
from database import engine, get_db
from resume_parser import parse_resume, detect_dynamic_sections, STANDARD_ATTRIBUTES, extract_image_from_pdf
from seed import seed_attributes, get_or_create_attribute, seed_packages
from migration import migrate_schema

# ── Ensure upload directory exists ───────────────────────────────────────────
BASE_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "resumes")
os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)



# ── Lifespan event handler (Startup/Shutdown) ─────────────────────────────────
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Database Initialization ──────────────────────────────────────────────
    try:
        print("[START] Starting database initialization...")
        
        # 1. Run manual migrations (renaming columns, etc.)
        migrate_schema(engine)
        
        # 2. Create missing tables (Packages, Subscriptions, Payments, etc.)
        print("[BUILD] Syncing tables with models...")
        models.Base.metadata.create_all(bind=engine)
        
        # 3. Seed initial data
        db = next(get_db())
        try:
            print("[SEED] Seeding initial data...")
            seed_attributes(db)
            seed_packages(db)
            print("[SUCCESS] Database setup completed successfully!")
        finally:
            db.close()
            
    except Exception as e:
        print(f"[ERROR] Error during database initialization: {e}")
        import traceback
        traceback.print_exc()
    yield

app = FastAPI(title="InterviewAI API", version="2.0", lifespan=lifespan)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
        "https://testmock.lovable.app",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
token_blacklist: set = set()


# ════════════════════════════════════════════════════
# AUTH DEPENDENCY
# ════════════════════════════════════════════════════

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    if token in token_blacklist:
        raise HTTPException(status_code=401, detail="Token has been logged out. Please login again.")
    try:
        payload = auth.decode_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_valid == 0:
        raise HTTPException(status_code=403, detail="Your account is not valid yet")
    return user


# ════════════════════════════════════════════════════
# 1. REGISTER
# ════════════════════════════════════════════════════

@app.post("/register", response_model=schemas.UserResponse, status_code=201,
          summary="Register a new user")
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    user = models.User(
        username=payload.username,
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        password=auth.hash_password(payload.password),
        is_valid=1
    )
    db.add(user)
    db.flush() # Get user.id

    # Initialize UsageTracker with 1 free credit
    from datetime import date, timedelta
    today = date.today()
    usage = models.UsageTracker(
        user_id=user.id,
        subscription_id=None,
        sessions_used=0,
        credits_used=0,
        credits_remaining=1,
        questions_used=0,
        voice_minutes_used=0,
        period_start=today,
        period_end=today + timedelta(days=30)
    )
    db.add(usage)
    db.commit()
    db.refresh(user)
    return user


# ════════════════════════════════════════════════════
# 2. LOGIN
# ════════════════════════════════════════════════════

@app.post("/login", response_model=schemas.TokenResponse,
          summary="Login with username and password")
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.is_valid == 0:
        raise HTTPException(status_code=403, detail="Your account is not valid yet")

    token = auth.create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


# ════════════════════════════════════════════════════
# 3. LOGOUT
# ════════════════════════════════════════════════════

@app.post("/logout", summary="Logout and invalidate token")
def logout(token: str = Depends(oauth2_scheme)):
    token_blacklist.add(token)
    return {"message": "Successfully logged out"}


# ════════════════════════════════════════════════════
# 4. GET CURRENT USER
# ════════════════════════════════════════════════════

@app.get("/me", response_model=schemas.UserResponse,
         summary="Get logged in user details")
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ════════════════════════════════════════════════════
# 5. UPLOAD RESUME
# ════════════════════════════════════════════════════

@app.post("/upload-resume",
          summary="Upload PDF resume — parses, stores file, extracts skills & photo")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_bytes = await file.read()
    file_size  = len(file_bytes)

    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 5MB")

    # ── Parse resume ──────────────────────────────────────────────────────────
    try:
        parsed = parse_resume(file_bytes)
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")

    sections = parsed["sections"]
    raw_text = parsed["raw_text"]

    # NOTE: We never touch the USERS table here.
    # name / email / phone are set only at registration
    # and will only be editable via a dedicated update_user API in future.

    # Detect and create dynamic sections
    known_codes = [a["code"] for a in STANDARD_ATTRIBUTES]

    # NOTE: users table (name, phone, email) is set ONLY at registration.
    # Resume parsing never overwrites user account data.

    # ── Detect & store dynamic sections ───────────────────────────────────────
    known_codes  = [a["code"] for a in STANDARD_ATTRIBUTES]
    dynamic_attrs = detect_dynamic_sections(raw_text, known_codes)
    for dattr in dynamic_attrs:
        get_or_create_attribute(db, dattr["code"], dattr["name"], dattr["type"])


    # Store each section into user_profile
    # ── Save PDF file to disk ─────────────────────────────────────────────────
    # Use uuid prefix to guarantee uniqueness even if same filename is re-uploaded.
    user_dir  = os.path.join(BASE_UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(user_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # ── Extract and store profile photo ───────────────────────────────────────
    user_image_b64 = extract_image_from_pdf(file_bytes)
    if user_image_b64:
        current_user.pic = user_image_b64
    else:
        # User requested: "else make it null" if not found in resume
        current_user.pic = None

    # ── Clear old profile entries so we only keep data from the new resume ──────
    db.query(models.UserProfile).filter(
        models.UserProfile.user_id == current_user.id
    ).delete(synchronize_session=False)

    db.commit() # Commit image change and profile deletion


    #return _build_profile_response(current_user, db)# return _build_profile_response(current_user, db)  # ✅ commented

    # ── Delete any existing resume for this user (one resume per user policy) ──
    old_records = db.query(models.Resume).filter(
        models.Resume.user_id == current_user.id
    ).all()
    for old in old_records:
        # Remove old file from disk if it exists
        if old.path and os.path.exists(old.path):
            try:
                os.remove(old.path)
            except Exception:
                pass  # If file deletion fails, still proceed
        db.delete(old)
    db.commit()

    # ── Create Resume record in resumes table ─────────────────────────────────
    skills_str = sections.get("technical_skills", "") or ""
    resume_record = models.Resume(
        user_id     = current_user.id,
        resume_name = file.filename,
        path        = file_path,
        size        = file_size,
        mime_type   = "application/pdf",
        skills      = skills_str or None,
        domain      = parsed.get("domain")
    )
    db.add(resume_record)
    db.flush() # Get resume_id

    # ── Store each parsed section into user_profile ───────────────────────────
    for code, value in sections.items():
        if not value:
            continue
        attr = get_or_create_attribute(db, code)
        db.add(models.UserProfile(
            user_id      = current_user.id,
            resume_id    = resume_record.id,
            attribute_id = attr.id,
            value        = value
        ))

    if not sections:
        placeholder_attr = get_or_create_attribute(db, "resume_uploaded", "Resume Uploaded", "text")
        db.add(models.UserProfile(
            user_id      = current_user.id,
            resume_id    = resume_record.id,
            attribute_id = placeholder_attr.id,
            value        = "true"
        ))

    db.commit()
    db.refresh(resume_record)

    return {
        "success": True,
        "message": "Resume uploaded and parsed successfully",
        "data": _build_resume_data(resume_record)
    }



# ════════════════════════════════════════════════════
# 6. LIST ALL RESUMES for current user
# ════════════════════════════════════════════════════

@app.get("/resumes", summary="List all uploaded resumes for current user")
def list_resumes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Strictly filter by the authenticated user's ID — no other user's data is returned
    records = db.query(models.Resume).filter(
        models.Resume.user_id == current_user.id
    ).order_by(models.Resume.updated_at.desc()).all()

    return {
        "success":      True,
        "logged_in_as": current_user.username,   # confirms which user's data this is
        "user_id":      current_user.id,
        "message":      f"{len(records)} resume(s) found",
        "data":         [_build_resume_data(r) for r in records]
    }


# ════════════════════════════════════════════════════
# 7. VIEW RESUME (inline in browser)
# ════════════════════════════════════════════════════

@app.get("/resume/{resume_id}/view", summary="View resume PDF inline in browser")
def view_resume(
    resume_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = _get_resume_or_404(resume_id, current_user.id, db)
    if not os.path.exists(record.path):
        raise HTTPException(status_code=404, detail="Resume file not found on server")
    return FileResponse(
        path       = record.path,
        media_type = "application/pdf",
        filename   = record.resume_name,
        headers    = {"Content-Disposition": f"inline; filename=\"{record.resume_name}\""}
    )


# ════════════════════════════════════════════════════
# 8. DOWNLOAD RESUME (as attachment)
# ════════════════════════════════════════════════════

@app.get("/resume/{resume_id}/download", summary="Download resume PDF as file")
def download_resume(
    resume_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = _get_resume_or_404(resume_id, current_user.id, db)
    if not os.path.exists(record.path):
        raise HTTPException(status_code=404, detail="Resume file not found on server")
    return FileResponse(
        path       = record.path,
        media_type = "application/pdf",
        filename   = record.resume_name,
        headers    = {"Content-Disposition": f"attachment; filename=\"{record.resume_name}\""}
    )


# ════════════════════════════════════════════════════
# 9. DELETE RESUME
# ════════════════════════════════════════════════════

@app.delete("/resume/{resume_id}", summary="Delete a specific resume")
def delete_resume(
    resume_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = _get_resume_or_404(resume_id, current_user.id, db)

    # Remove file from disk
    if os.path.exists(record.path):
        os.remove(record.path)

    db.delete(record)
    db.commit()
    return {
        "success": True,
        "message": f"Resume '{record.resume_name}' deleted successfully"
    }


# ════════════════════════════════════════════════════
# 10. GET PROFILE
# ════════════════════════════════════════════════════

@app.get("/profile", response_model=schemas.UserProfileResponse,
         summary="Get full user profile with all resume sections")
def get_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile_entries = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == current_user.id
    ).all()

    if not profile_entries:
        raise HTTPException(
            status_code=404,
            detail="Profile not found. Please upload your resume first."
        )

    return _build_profile_response(current_user, db)


# ════════════════════════════════════════════════════
# 10b. UPDATE USER PROFILE — text fields via JSON body
#      PUT /update-profile
#      Body: { "first_name", "last_name", "email", "phone" }  (all optional)
# ════════════════════════════════════════════════════

class _UpdateProfilePayload(schemas.BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    email:      Optional[str] = None
    phone:      Optional[str] = None

@app.put("/update-profile",
         summary="Update user profile text fields (first_name, last_name, email, phone) — send as JSON")
def update_user_profile(
    payload:      _UpdateProfilePayload,
    current_user: models.User = Depends(get_current_user),
    db:           Session     = Depends(get_db)
):
    """
    Updates the authenticated user's record in the **users** table.

    Send as **raw JSON** (Content-Type: application/json):
    ```json
    {
        "first_name": "Adarsh",
        "last_name":  "Tiwari",
        "email":      "newemail@gmail.com",
        "phone":      "7505965253"
    }
    ```
    All fields are optional — only fields you include are updated.
    """

    # ── Build new full name ────────────────────────────────────────────────────
    existing_parts = (current_user.name or "").split(" ", 1)
    existing_first = existing_parts[0] if len(existing_parts) > 0 else ""
    existing_last  = existing_parts[1] if len(existing_parts) > 1 else ""

    new_first = payload.first_name.strip() if payload.first_name is not None else existing_first
    new_last  = payload.last_name.strip()  if payload.last_name  is not None else existing_last
    new_name  = f"{new_first} {new_last}".strip()

    if new_name and len(new_name) > 30:
        raise HTTPException(status_code=400, detail="Full name must be max 30 characters")

    # ── Email uniqueness check ─────────────────────────────────────────────────
    if payload.email is not None:
        new_email = payload.email.strip()
        conflict = db.query(models.User).filter(
            models.User.email == new_email,
            models.User.id    != current_user.id
        ).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Email is already used by another account")
    else:
        new_email = current_user.email   # keep existing

    # ── Write to users table & commit ─────────────────────────────────────────
    if new_name:
        current_user.name  = new_name
    current_user.email = new_email
    if payload.phone is not None:
        current_user.phone = payload.phone.strip()

    db.commit()
    db.refresh(current_user)

    image_path = current_user.pic

    # ── Build response ────────────────────────────────────────────────────────
    stored_parts = (current_user.name or "").split(" ", 1)
    resp_first   = stored_parts[0] if len(stored_parts) > 0 else ""
    resp_last    = stored_parts[1] if len(stored_parts) > 1 else ""

    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": {
            "user_id":    current_user.id,
            "username":   current_user.username,
            "first_name": resp_first,
            "last_name":  resp_last,
            "email":      current_user.email,
            "phone":      current_user.phone,
            "user_image": current_user.pic,
        }
    }


# ════════════════════════════════════════════════════
# 10c. UPLOAD PROFILE IMAGE
#      PUT /update-profile/image
#      Body: multipart/form-data  →  profile_image (file)
# ════════════════════════════════════════════════════

@app.put("/update-profile/image",
         summary="Upload / change profile avatar image — send as multipart/form-data")
async def update_profile_image(
    profile_image:  UploadFile  = File(..., description="Profile image — JPEG, PNG, GIF, or WebP"),
    current_user:  models.User = Depends(get_current_user),
    db:            Session     = Depends(get_db)
):
    """
    Upload a new profile avatar.

    - Saves the file under **uploads/profile_images/{user_id}/**.
    - Stores the local file **path** in `users.pic`.
    """

    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    content_type  = (profile_image.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Profile image must be JPEG, PNG, GIF, or WebP")

    img_bytes = await profile_image.read()
    if len(img_bytes) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Profile image must be less than 2 MB")

    # ── Upload to Cloudinary ──────────────────────────────────────────────────
    result = cloudinary.uploader.upload(
        img_bytes,
        folder=f"profile_images/{current_user.id}"
    )

    image_url = result["secure_url"]

    # ── Store URL in users.pic ────────────────────────────────────────────────
    current_user.pic = image_url
    db.commit()

    return {
        "success":    True,
        "message":    "Profile image uploaded successfully",
        "user_image": image_url,
    }





# ════════════════════════════════════════════════════
# 11. UPDATE PROFILE FIELD
# ════════════════════════════════════════════════════

@app.put("/profile", response_model=schemas.UserProfileResponse,
         summary="Update a specific profile field by attribute code")
def update_profile(
    payload: schemas.UpdateProfileRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    attr = db.query(models.Attribute).filter(
        models.Attribute.code == payload.attribute_code
    ).first()

    if not attr:
        raise HTTPException(
            status_code=404,
            detail=f"Attribute '{payload.attribute_code}' not found"
        )

    existing = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == current_user.id,
        models.UserProfile.attribute_id == attr.id
    ).first()

    if existing:
        existing.value = payload.value
    else:
        db.add(models.UserProfile(
            user_id      = current_user.id,
            attribute_id = attr.id,
            value        = payload.value
        ))

    db.commit()
    return _build_profile_response(current_user, db)


# ════════════════════════════════════════════════════
# 12. LIST ALL ATTRIBUTES
# ════════════════════════════════════════════════════

@app.get("/attributes", response_model=list[schemas.AttributeResponse],
         summary="List all available resume attributes/sections")
def list_attributes(db: Session = Depends(get_db)):
    return db.query(models.Attribute).all()


# ════════════════════════════════════════════════════
# 13. DELETE USER (cascades to profile & resumes)
# ════════════════════════════════════════════════════

@app.delete("/user", summary="Delete current user and all profile data")
def delete_user(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.delete(current_user)
    db.commit()
    return {"success": True, "message": "User account and all data deleted successfully"}


# ════════════════════════════════════════════════════
# 14. SUBSCRIPTIONS & PAYMENTS
# ════════════════════════════════════════════════════

@app.get("/packages", response_model=List[schemas.PackageResponse],
         summary="List all available subscription packages")
def list_packages(db: Session = Depends(get_db)):
    return db.query(models.Package).all()


@app.get("/subscriptions", response_model=List[schemas.SubscriptionResponse],
         summary="Get all subscriptions for current user")
def get_subscriptions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).order_by(models.Subscription.id.desc()).all()


@app.get("/subscription", response_model=schemas.SubscriptionResponse,
         summary="Get current user latest subscription")
def get_subscription(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    sub = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id
    ).order_by(models.Subscription.id.desc()).first()

    if sub:
        return sub

    # Fallback to Free/Basic Plan if no active subscription
    free_package = db.query(models.Package).filter(models.Package.name == "Basic Plan").first()
    
    from datetime import datetime
    now = datetime.utcnow()
    
    if free_package:
        return schemas.SubscriptionResponse(
            id=0,
            package_id=free_package.id,
            package_name=free_package.name,
            interview_limit=free_package.interview_limit,
            pricing=free_package.price,
            start_date=now,
            end_date=now,
            status=1
        )
    else:
        # Fallback if package is not seeded
        return schemas.SubscriptionResponse(
            id=0,
            package_id=0,
            package_name="Free",
            interview_limit=1,
            pricing=0.0,
            start_date=now,
            end_date=now,
            status=1
        )


@app.post("/subscription", response_model=schemas.SubscriptionResponse,
          summary="Select a package and request subscription")
def create_subscription(
    payload: schemas.SubscriptionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    package = db.query(models.Package).filter(models.Package.id == payload.package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    sub = models.Subscription(
        user_id=current_user.id,
        package_id=package.id,
        start_date=now,
        end_date=now + timedelta(days=30),
        status=0  # Pending
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return sub

@app.post("/request_payment_review", summary="Request payment review and send email")
def request_payment_review(
    payload: schemas.PaymentReviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Find the specific subscription for the user
    sub = db.query(models.Subscription).filter(
        models.Subscription.id == payload.subscription_id,
        models.Subscription.user_id == current_user.id
    ).first()

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    if sub.status != 0:
        raise HTTPException(status_code=400, detail="Subscription is not pending")

    package = db.query(models.Package).filter(models.Package.id == sub.package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Associated package not found")
        
    # Check if transaction ID already exists to avoid UniqueViolation
    existing_payment = db.query(models.Payment).filter(models.Payment.transaction_id == payload.transaction_id).first()
    if existing_payment:
        raise HTTPException(status_code=400, detail="Transaction ID already exists")

    # Create payment record
    new_payment = models.Payment(
        user_id=current_user.id,
        subscription_id=sub.id,
        amount=payload.amount_paid,
        payment_method=payload.payment_method,
        status="pending",
        transaction_id=payload.transaction_id
    )
    db.add(new_payment)
    
    # Update subscription status to requested
    sub.status = 1
    
    db.commit()
    db.refresh(new_payment)
    
    try:
        response_data = send_subscription_request_email(current_user, package, payload)
    except Exception as e:
        print(f"Error in request_payment_review: {e}")
        response_data = {
            "success": True,
            "message": "Payment review request submitted successfully."
        }

    return response_data


@app.get("/payments", response_model=List[schemas.PaymentResponse],
         summary="Get current user payment history")
def get_payments(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Payment).filter(
        models.Payment.user_id == current_user.id
    ).all()


# ════════════════════════════════════════════════════
# 15. INTERVIEW ACCESS VALIDATION
# ════════════════════════════════════════════════════

@app.post("/validate-access", response_model=schemas.ValidateAccessResponse,
          summary="Check if user can start a new interview session based on subscription limits")
def validate_access(
    payload: schemas.ValidateAccessRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Validates if a user can start an interview with the selected duration.
    Rules:
    1. If remaining interviews <= 0 -> Block completely.
    2. If remaining interviews == 1 and duration > 10 min -> Block (only 10 min allowed).
    3. Otherwise -> Allow.
    """
    from datetime import datetime

    # Security check: Ensure user is validating their own access
    # (Redundant with Depends(get_current_user) but kept as logic boundary if needed)

    today = datetime.utcnow().date()

    # STEP 1 - Get active subscription
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id,
        models.Subscription.status == 2,
        models.Subscription.end_date >= today
    ).order_by(models.Subscription.id.desc()).first()

    if not subscription:
        return {
            "allowed": False,
            "reason": "No active plan found. Please purchase a plan.",
            "credits_remaining": 0,
            "upgrade_required": True,
            "redirect_to": "/plans"
        }

    # STEP 2 - Get credit costs from Packages
    package = subscription.package
    if not package:
        raise HTTPException(status_code=500, detail="Package configuration missing for your subscription.")

    # STEP 3 - Get credits_remaining from Usage_Tracker
    usage = db.query(models.UsageTracker).filter(
        models.UsageTracker.user_id == current_user.id,
        models.UsageTracker.period_end >= today
    ).order_by(models.UsageTracker.id.desc()).first()

    credits_remaining = usage.credits_remaining if usage else 0

    # STEP 4 - Calculate cost for requested duration
    if payload.duration_minutes == 5:
        # Fallback to 10min cost since Package model doesn't explicitly store 5min cost
        cost = package.credit_cost_10min
    elif payload.duration_minutes == 10:
        cost = package.credit_cost_10min
    elif payload.duration_minutes == 20:
        cost = package.credit_cost_20min
    elif payload.duration_minutes == 40:
        cost = package.credit_cost_40min
    else:
        raise HTTPException(status_code=400, detail="Invalid duration. Must be 5, 10, 20, or 40.")

    # STEP 5 - Check if user can afford it
    if credits_remaining <= 0:
        return {
            "allowed": False,
            "credits_remaining": 0,
            "cost_required": cost,
            "reason": "You have no credits left. Please purchase a plan to continue.",
            "upgrade_required": True,
            "redirect_to": "/plans"
        }

    if credits_remaining < cost:
        return {
            "allowed": False,
            "credits_remaining": credits_remaining,
            "cost_required": cost,
            "reason": f"Not enough credits. This interview costs {cost} credits but you have {credits_remaining} remaining. Upgrade your plan.",
            "upgrade_required": True,
            "redirect_to": "/plans"
        }

    # credits_remaining >= cost
    warning = None
    if credits_remaining - cost <= 1:
        warning = f"After this interview you will have {credits_remaining - cost} credit(s) left. Consider upgrading your plan."

    return {
        "allowed": True,
        "credits_remaining": credits_remaining,
        "cost_required": cost,
        "credits_after": credits_remaining - cost,
        "warning": warning,
        "max_duration_allowed": 40 if credits_remaining >= 4 else (20 if credits_remaining >= 2 else 10)
    }


@app.get("/interview/allowed-durations", response_model=schemas.AllowedDurationsResponse,
         summary="Get available interview durations based on user credits")
def get_allowed_durations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Returns available durations and credit costs based on live balance.
    """
    from datetime import datetime
    today = datetime.utcnow().date()

    # STEP 1 - Get credits_remaining from Usage_Tracker
    usage = db.query(models.UsageTracker).filter(
        models.UsageTracker.user_id == current_user.id,
        models.UsageTracker.period_end >= today
    ).order_by(models.UsageTracker.id.desc()).first()
    
    credits_remaining = usage.credits_remaining if usage else 0

    # STEP 2 - Get credit costs from Packages via Subscription
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id,
        models.Subscription.status == 2, # Active
        models.Subscription.end_date >= today
    ).order_by(models.Subscription.id.desc()).first()

    cost_5 = 1
    cost_10 = 1
    cost_20 = 2
    cost_40 = 4
    package_name = "Free"

    if subscription and subscription.package:
        p = subscription.package
        cost_10 = p.credit_cost_10min
        cost_20 = p.credit_cost_20min
        cost_40 = p.credit_cost_40min
        package_name = p.name
        cost_5 = cost_10 # Fallback to cost_10 if not defined

    # STEP 3 - Calculate availability
    durations = []
    
    # 5 min
    is_5_avail = credits_remaining >= cost_5
    durations.append({
        "duration": 5,
        "is_available": is_5_avail,
        "cost": cost_5,
        "unavailable_reason": None if is_5_avail else f"Not enough credits. Required: {cost_5}, Remaining: {credits_remaining}"
    })

    # 10 min
    is_10_avail = credits_remaining >= cost_10
    durations.append({
        "duration": 10,
        "is_available": is_10_avail,
        "cost": cost_10,
        "unavailable_reason": None if is_10_avail else f"Not enough credits. Required: {cost_10}, Remaining: {credits_remaining}"
    })

    # 20 min
    is_20_avail = credits_remaining >= cost_20
    durations.append({
        "duration": 20,
        "is_available": is_20_avail,
        "cost": cost_20,
        "unavailable_reason": None if is_20_avail else f"Not enough credits. Required: {cost_20}, Remaining: {credits_remaining}"
    })

    # 40 min
    is_40_avail = credits_remaining >= cost_40
    durations.append({
        "duration": 40,
        "is_available": is_40_avail,
        "cost": cost_40,
        "unavailable_reason": None if is_40_avail else f"Not enough credits. Required: {cost_40}, Remaining: {credits_remaining}"
    })

    # If free tier, only allow 5 minutes
    if current_user.tier == "free":
        durations = [d for d in durations if d["duration"] == 5]

    # STEP 4 - Calculate Upgrade Banner
    show_banner = False
    banner_msg = ""
    target_plan = ""

    if package_name == "Free" and credits_remaining < cost_20:
        show_banner = True
        banner_msg = "Only 10 min interviews available. Upgrade to Basic plan for longer sessions!"
        target_plan = "Basic"
    elif credits_remaining < cost_10:
        show_banner = True
        banner_msg = "You have run out of credits. Upgrade your plan to continue!"
        target_plan = "Basic"

    return {
        "userid": current_user.id,
        "credits_remaining": credits_remaining,
        "allowed_durations": durations,
        "upgrade_banner": {
            "show": show_banner,
            "message": banner_msg,
            "target_plan": target_plan
        }
    }


@app.post("/interview/validate-and-setup", summary="Validate access and setup new interview session")
def validate_and_setup_interview(
    payload: schemas.InterviewSetupRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Sets up a new interview session.
    1. Re-validates access.
    2. Calculates question count.
    3. Links to latest resume.
    4. Creates session row.
    5. Increments usage tracking.
    """
    from datetime import datetime

    # Security Check
    # (Redundant with Depends(get_current_user) but kept as logic boundary if needed)

    # Validation: Enum checks
    if payload.difficulty not in ['easy', 'medium', 'hard']:
        raise HTTPException(status_code=400, detail="Invalid difficulty level")
    if payload.duration_minutes not in [5, 10, 20, 40]:
        raise HTTPException(status_code=400, detail="Invalid duration. Allowed: 5, 10, 20, 40")
        
    if current_user.tier == "free" and payload.duration_minutes > 5:
        raise HTTPException(status_code=403, detail="Free plan allows maximum 5 minute interviews only")

    try:
        # STEP 1 - Re-run access check
        today = datetime.utcnow().date()
        
        # Query Usage_Tracker for the current period
        usage = db.query(models.UsageTracker).filter(
            models.UsageTracker.user_id == current_user.id,
            models.UsageTracker.period_end >= today
        ).order_by(models.UsageTracker.id.desc()).first()

        if not usage:
             raise HTTPException(status_code=403, detail="No usage record found. Please ensure you have an active plan.")

        credits_remaining = usage.credits_remaining
        
        # Calculate cost
        if payload.duration_minutes == 5:
            cost = 1
        elif payload.duration_minutes == 10:
            cost = 1
        elif payload.duration_minutes == 20:
            cost = 2
        elif payload.duration_minutes == 40:
            cost = 4
        else:
            raise HTTPException(status_code=400, detail="Invalid duration. Allowed: 5, 10, 20, 40")

        if credits_remaining < cost:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Not enough credits for this duration.",
                    "credits_remaining": credits_remaining,
                    "cost_required": cost
                }
            )

        # STEP 2 - Calculate total_questions
        duration_map = {5: 5, 10: 5, 20: 10, 40: 20}
        total_questions = duration_map.get(payload.duration_minutes, 10)

        # STEP 3 - Check if user has uploaded resume
        resume = db.query(models.Resume).filter(
            models.Resume.user_id == current_user.id
        ).order_by(models.Resume.created_at.desc()).first()
        
        resume_id = resume.id if resume else None
        has_resume = True if resume else False

        # STEP 4 - Insert into Interview_Session
        new_session = models.InterviewSession(
            user_id=current_user.id,
            resume_id=resume_id,
            role=payload.role,
            topic=payload.topic,
            difficulty=payload.difficulty,
            duration_minutes=payload.duration_minutes,
            total_questions=total_questions,
            status='active'
        )
        db.add(new_session)
        db.flush() # To get the session ID

        # STEP 5 - Update Usage_Tracker (Deduct Credits)
        # We use current values for response calculation before committing
        old_credits_used = usage.credits_used
        old_credits_remaining = usage.credits_remaining

        usage.credits_used = old_credits_used + cost
        usage.credits_remaining = max(old_credits_remaining - cost, 0)
        usage.sessions_used = usage.sessions_used + 1
        usage.last_deducted_at = datetime.utcnow()
        usage.updated_at = datetime.utcnow()

        db.commit()

        return {
            "success": True,
            "session_id": new_session.id,
            "user_id": current_user.id
        }

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/interview/change-setup", response_model=schemas.InterviewChangeSetupResponse, summary="Cancel an interview setup and refund credits")
def change_interview_setup(
    payload: schemas.InterviewChangeSetupRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Handles cancelling an interview session setup and refunding the credits.
    1. Fetches the session to determine duration.
    2. Calculates the refund amount.
    3. Updates the Usage_Tracker to restore credits and decrement session count.
    4. Marks the session as abandoned.
    """
    from datetime import datetime

    try:
        # STEP 1 - Get the session to find duration
        session = db.query(models.InterviewSession).filter(
            models.InterviewSession.id == payload.session_id,
            models.InterviewSession.user_id == current_user.id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != 'active':
            raise HTTPException(status_code=400, detail="Session cannot be cancelled in its current state")

        if session.started_at is not None:
            raise HTTPException(status_code=400, detail="Cannot cancel a session that has already started")

        # STEP 2 - Calculate cost to refund
        duration = session.duration_minutes
        if duration == 10:
            refund = 1
        elif duration == 20:
            refund = 2
        elif duration == 40:
            refund = 4
        else:
            refund = 0

        # STEP 3 - Roll back credits in Usage_Tracker
        today = datetime.utcnow().date()
        usage = db.query(models.UsageTracker).filter(
            models.UsageTracker.user_id == current_user.id,
            models.UsageTracker.period_end >= today
        ).order_by(models.UsageTracker.id.desc()).first()

        if not usage:
            raise HTTPException(status_code=403, detail="No active usage record found for refund.")

        usage.credits_used = max(usage.credits_used - refund, 0)
        usage.credits_remaining = usage.credits_remaining + refund
        usage.sessions_used = max(usage.sessions_used - 1, 0)
        usage.updated_at = datetime.utcnow()

        # Update session status to prevent further refunds or starting the session
        session.status = 'abandoned'

        db.commit()

        return {
            "success": True,
            "message": "Session setup cancelled and credits refunded.",
            "session_id": session.id,
            "credits_refunded": refund,
            "credits_remaining": usage.credits_remaining
        }

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/interview/session-summary", response_model=schemas.InterviewSessionSummaryResponse, summary="Get session details for confirmation screen")
def get_session_summary(
    session_id: int,
    userid: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Powers the 'Ready to begin?' confirmation screen.
    Checks session ownership, status, and calculates remaining interviews.
    """
    from datetime import datetime
    
    # Security check: Ensure token matches query userid
    if userid != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized: User ID mismatch")

    try:
        # STEP 1 - Fetch session
        session = db.query(models.InterviewSession).filter(
            models.InterviewSession.id == session_id,
            models.InterviewSession.user_id == userid
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session.status != 'active':
            raise HTTPException(status_code=400, detail="Session is not active")
        
        if session.started_at is not None:
            raise HTTPException(status_code=400, detail="Session already started")

        # STEP 2 - Get credits_remaining from Usage_Tracker
        today = datetime.utcnow().date()
        
        usage = db.query(models.UsageTracker).filter(
            models.UsageTracker.user_id == userid,
            models.UsageTracker.period_end >= today
        ).order_by(models.UsageTracker.id.desc()).first()

        credits_remaining = usage.credits_remaining if usage else 0

        return {
            "success": True,
            "session_id": session.id,
            "userid": userid,
            "role": session.role,
            "topic": session.topic,
            "difficulty": session.difficulty,
            "duration_minutes": session.duration_minutes,
            "total_questions": session.total_questions,
            "has_resume": True if session.resume_id else False,
            "credits_remaining": credits_remaining,
            "status": session.status,
            "info_message": "The AI interviewer will greet you and begin asking questions. Use the mic button to answer with voice or type your responses. You can skip questions anytime."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/confirm-start", response_model=schemas.ConfirmStartResponse, summary="Confirm start of interview and fetch questions")
def confirm_start(
    payload: schemas.ConfirmStartRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from datetime import datetime
    import random

    if payload.userid != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")


    actual_session_id = payload.session_id
    if isinstance(actual_session_id, str):
        try:
            token_data = auth.decode_token(actual_session_id)
            actual_session_id = token_data.get("session_id")
        except Exception:
            pass
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == actual_session_id,
        models.InterviewSession.user_id == payload.userid
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.started_at is None:
        session.started_at = datetime.utcnow()
        db.commit()
    
    # STEP 2 - Fetch resume context from user_profile
    resume_context = ""
    if session.resume_id:
        profiles = db.query(models.UserProfile).join(models.Attribute).filter(
            models.UserProfile.user_id == session.user_id,
            models.UserProfile.resume_id == session.resume_id,
            models.Attribute.code.in_([
                'technical_skills', 'skills', 'projects', 
                'experience', 'education', 'project_details',
                'professional_experience', 'achievements', 'key_results'
            ])
        ).all()
        
        context_parts = []
        resume_skills = []
        resume_projects = []
        resume_experience = []
        resume_education = []
        for p in profiles:
            if p.value and p.value.strip():
                context_parts.append(f"{p.attribute.name}: {p.value}")
                if p.attribute.code in ['technical_skills', 'skills']:
                    resume_skills.append(p.value)
                elif p.attribute.code in ['projects', 'project_details', 'achievements', 'key_results']:
                    resume_projects.append(p.value)
                elif p.attribute.code in ['experience', 'professional_experience']:
                    resume_experience.append(p.value)
                elif p.attribute.code in ['education']:
                    resume_education.append(p.value)
        resume_context = "\n".join(context_parts)

    class ResumeContext:
        def __init__(self, s, p, e, ed):
            self.skills = "\n".join(s) if s else "Not provided"
            self.projects = "\n".join(p) if p else "Not provided"
            self.experience = "\n".join(e) if e else "Not provided"
            self.education = "\n".join(ed) if ed else "Not provided"
            self.is_empty = not (s or p or e or ed)

    resume_ctx = ResumeContext(resume_skills, resume_projects, resume_experience, resume_education)

    # FIX 1 — Role matching for ALL roles
    role_mapping = {
        "frontend": "Frontend Developer",
        "frontend developer": "Frontend Developer",
        "backend": "Backend Developer",
        "backend developer": "Backend Developer",
        "full stack": "Full Stack Developer",
        "fullstack": "Full Stack Developer",
        "full stack developer": "Full Stack Developer",
        "data analyst": "Data Analyst",
        "analyst": "Data Analyst",
        "hr": "HR Manager",
        "hr manager": "HR Manager",
        "human resources": "HR Manager",
        "marketing": "Marketing Analyst",
        "marketing analyst": "Marketing Analyst",
        "software engineer": "Software Engineer",
        "engineer": "Software Engineer"
    }
    normalized_role = role_mapping.get(session.role.lower(), session.role)

    # FIX 2 — No-repeat across all sessions
    used_question_ids = []
    
    previously_used = db.query(models.SessionQuestion.question_id).join(
        models.InterviewSession, 
        models.SessionQuestion.session_id == models.InterviewSession.id
    ).filter(
        models.InterviewSession.user_id == current_user.id
    ).all()
    
    for q_id in previously_used:
        used_question_ids.append(q_id[0])

    def fetch_question(difficulty, q_type=None, role=normalized_role):
        def _try_fetch(exclude_ids):
            base_query = db.query(models.Question)
            if exclude_ids:
                base_query = base_query.filter(models.Question.id.notin_(exclude_ids))
            
            # 1. Exact match (difficulty, role, type)
            query = base_query.filter(
                models.Question.difficulty == difficulty,
                models.func.lower(models.Question.role) == models.func.lower(role)
            )
            if q_type:
                query = query.filter(models.Question.type == q_type)
            q_obj = query.order_by(models.func.random()).first()
            
            # 2. Fallback: ignore type
            if not q_obj:
                q_obj = base_query.filter(
                    models.Question.difficulty == difficulty,
                    models.func.lower(models.Question.role) == models.func.lower(role)
                ).order_by(models.func.random()).first()
                
            # 3. Fallback: ignore difficulty
            if not q_obj:
                q_obj = base_query.filter(
                    models.func.lower(models.Question.role) == models.func.lower(role)
                ).order_by(models.func.random()).first()
                
            # 4. Fallback: Search for the topic inside the question text or domain
            if not q_obj:
                from sqlalchemy import or_
                q_obj = base_query.filter(
                    or_(
                        models.func.lower(models.Question.domain) == models.func.lower(session.topic),
                        models.Question.text.ilike(f"%{session.topic}%")
                    )
                ).order_by(models.func.random()).first()
                
            return q_obj
        
        # ALWAYS use the exclude list to prevent duplicates
        q_obj = _try_fetch(used_question_ids)
        if q_obj:
            used_question_ids.append(q_obj.id)
            return q_obj
            
        # If no relevant question exists in the DB, auto-generate one using the LLM and save it!
        import os
        import json
        from groq import Groq
        try:
            groq_api_key = os.getenv("GROQ_API_KEY")
            client = Groq(api_key=groq_api_key)
            prompt = f"""You are an expert technical interviewer.
Generate EXACTLY ONE very brief interview question for a {difficulty} level {role} interview.
The topic/domain is: {session.topic}.
Type requested: {q_type}

Rules:
1. The question MUST perfectly match the '{difficulty}' difficulty. An 'easy' question must be simple and fundamental.
2. The question MUST be short and conversational (maximum 15 words). DO NOT write complex scenarios.
3. If type is 'resume', ask a simple experience-based question. If 'design', a simple architecture question. If 'behavioural', a simple behavioral question.
4. NEVER ask the candidate to write code, scripts, or queries. All questions must focus entirely on theory, concepts, or past experience.

Return ONLY valid JSON with a single key "text" containing the question string."""

            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            gen_data = json.loads(resp.choices[0].message.content)
            new_text = gen_data.get("text", f"Can you explain your experience with {session.topic}?")
            
            # Map type safely
            safe_type = q_type if q_type in ['topic', 'resume', 'behavioural', 'design'] else 'topic'
            
            new_q = models.Question(
                text=new_text,
                type=safe_type,
                difficulty=difficulty,
                role=role,
                domain=session.topic,
                is_company_question=False,
                frequency_score=1
            )
            db.add(new_q)
            db.commit()
            db.refresh(new_q)
            
            used_question_ids.append(new_q.id)
            return new_q
        except Exception as e:
            print("Auto-generate question failed:", e)
            return None

    q1 = fetch_question('easy', 'resume')
    q2 = fetch_question('easy', 'topic')
    q3 = fetch_question('medium', 'resume')
    q4 = fetch_question('medium', 'topic')
    q5 = fetch_question('hard', None)

    fetched_qs = [q1, q2, q3, q4, q5]
    if any(q is None for q in fetched_qs):
        return {"success": False, "error": "No questions available for this role yet"}

    # FIX 3 — Project name extraction
    def extract_project_names(projects_text):
        lines = projects_text.split('\n')
        p_names = []
        for line in lines:
            line = line.strip()
            if '|' in line:
                name = line.split('|')[0].strip()
                if len(name) > 3:
                    p_names.append(name)
            elif ' - ' in line and len(line) < 60:
                name = line.split(' - ')[0].strip()
                if len(name) > 3:
                    p_names.append(name)
        return p_names[:3]

    project_names = extract_project_names(resume_ctx.projects)

    # FIX 4 — Experience field
    if resume_ctx.experience.strip() and resume_ctx.experience != "Not provided":
        experience_context = resume_ctx.experience
    elif resume_ctx.education.strip() and resume_ctx.education != "Not provided":
        experience_context = resume_ctx.education
    else:
        experience_context = "Fresher / Entry Level"

    # FIX 5, 8 & 1 — Combined single AI call for personalization and tips
    personalized_q1 = q1.text
    personalized_q3 = q3.text
    tips = ["Provide a clear explanation.", "Focus on key concepts.", "Relate this to your experience.", "Use structured reasoning.", "Explain your logic step-by-step."]

    if not resume_ctx.is_empty:
        try:
            groq_api_key = os.getenv("GROQ_API_KEY")
            client = Groq(api_key=groq_api_key)
            
            prompt_sys = "You are an expert interview question personalizer and coach. Return ONLY valid JSON. No markdown formatting, no backticks, no explanation."
            prompt_user = f"""Candidate profile:
- Role applying for: {normalized_role}
- Skills: {resume_ctx.skills}
- Projects/Achievements: {', '.join(project_names) if project_names else 'None'}

Questions:
Q1: {q1.text}
Q2: {q2.text}
Q3: {q3.text}
Q4: {q4.text}
Q5: {q5.text}

Rules:
1. Rewrite Q3 to mention ONE specific project/achievement name
2. If no projects exist (e.g. HR/Marketing role), rewrite Q3 to mention a specific skill or domain instead
3. Keep same difficulty and intent
4. Maximum 1 sentence for the rewritten question
5. Provide a 1-line answering tip for EACH of the 5 questions.
6. Return ONLY this JSON:
{{
  "personalized": {{"q3": "rewritten question here"}},
  "tips": ["tip1", "tip2", "tip3", "tip4", "tip5"]
}}"""
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": prompt_sys},
                    {"role": "user", "content": prompt_user}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            resp_text = response.choices[0].message.content.strip()
            
            ai_data = json.loads(resp_text)
            if "personalized" in ai_data:
                personalized_q3 = ai_data["personalized"].get("q3", q3.text)
            if "tips" in ai_data and len(ai_data["tips"]) == 5:
                tips = ai_data["tips"]
        except Exception as e:
            print("AI personalization failed:", e)

    final_questions_text = [personalized_q1, q2.text, personalized_q3, q4.text, q5.text]

    # Save to Session_Questions table
    db.query(models.SessionQuestion).filter(models.SessionQuestion.session_id == session.id).delete()
    for idx, (q_obj, q_txt) in enumerate(zip(fetched_qs, final_questions_text)):
        if q_obj:
            sq = models.SessionQuestion(
                session_id=session.id,
                question_id=q_obj.id,
                question_order=idx + 1,
                answer_text=None,
                score=None,
                ai_feedback=None,
                is_skipped=False
            )
            db.add(sq)
    db.commit()

    # FIX 6 — Enhanced ai_greeting
    has_projects = len(project_names) > 0
    first_name = current_user.name.split(' ')[0]

    if has_projects:
        project_mention = f"I can see you have worked on {' and '.join(project_names[:2])}"
    else:
        skill_list = resume_ctx.skills.split(',')
        first_skill = skill_list[0].strip() if skill_list and skill_list[0] != "Not provided" else session.topic
        project_mention = f"I can see your background in {first_skill}"

    ai_greeting = f"Hello {first_name}! Welcome to your {normalized_role} interview. {project_mention} — let us see how deep your knowledge goes today. We will focus on {session.topic}. I will ask you 5 questions and give you feedback after each answer. Let us begin. {personalized_q1}"

    # FIX 7 — Enhanced system prompt
    system_prompt = f"""You are a strict MNC technical interviewer at a top company conducting a real {normalized_role} interview.

Candidate Profile:
- Name: {current_user.name}
- Skills: {resume_ctx.skills}
- Projects/Work: {', '.join(project_names) if project_names else 'None provided'}
- Background: {experience_context}

Your Behavior Rules:
- Ask exactly ONE question at a time
- After candidate answers, give 1-2 line feedback
- Use words like 'Good point' or 'That needs more depth'
- Never reveal the score
- If answer is too short, say 'Can you elaborate further?'
- If answer is wrong, say 'Not quite — think about it from a {session.topic} perspective'
- Stay in interviewer character throughout
- Topic focus: {session.topic}
- Difficulty: {session.difficulty}
- Total questions: 5"""

    conversation_history = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": ai_greeting}
    ]

    # FIX 8 — Enhanced questions_list format
    questions_list = [
        {
            "order": 1,
            "question": personalized_q1,
            "difficulty": "easy",
            "resume_based": True,
            "tip": tips[0]
        },
        {
            "order": 2,
            "question": q2.text,
            "difficulty": "easy", 
            "resume_based": False,
            "tip": tips[1]
        },
        {
            "order": 3,
            "question": personalized_q3,
            "difficulty": "medium",
            "resume_based": True,
            "tip": tips[2]
        },
        {
            "order": 4,
            "question": q4.text,
            "difficulty": "medium",
            "resume_based": False,
            "tip": tips[3]
        },
        {
            "order": 5,
            "question": q5.text,
            "difficulty": "hard",
            "resume_based": False,
            "tip": tips[4]
        }
    ]

    return {
        "success": True,
        "enhanced": True,
        "questions_list": questions_list,
        "ai_greeting": ai_greeting,
        "conversation_history": conversation_history
    }


from fastapi import Request
import urllib.parse

@app.post("/interview/launch-and-confirm", summary="Confirm start and get Pyspace URL with questions")
def launch_and_confirm_interview(
    payload: schemas.ConfirmStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    userid = payload.userid
    session_id = payload.session_id
    
    # 1. Check current_user["id"] == userid, else 403 Unauthorized
    if current_user.id != userid:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    # 2. Fetch session from Interview_Session table
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == session_id,
        models.InterviewSession.user_id == userid
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.status in ["ended", "abandoned"]:
        raise HTTPException(status_code=400, detail="This interview session has already been used")
        
    # 3. Fetch user from users table WHERE id = userid
    user = db.query(models.User).filter(models.User.id == userid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.tier == "free":
        if session.duration_minutes > 5:
            raise HTTPException(status_code=403, detail="Free plan allows maximum 5 minute interviews only")
        if session.total_questions > 5:
            raise HTTPException(status_code=403, detail="Free plan allows maximum 5 questions only")
            
    # 4. Call the existing confirm-start logic internally
    try:
        result = confirm_start(payload=payload, db=db, current_user=current_user)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "No questions available"))
        ai_greeting = result["ai_greeting"]
        questions_list = result["questions_list"]
        conversation_history = result["conversation_history"]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate interview questions")
        
    # 5. Build Streamlit redirect URL
    #base = "https://pyspaceai-elnvkx9xny6rituuasqp8x.streamlit.app/"
    base = "https://interviewai-nfpypdpihrbukcmlrhwolb.streamlit.app"
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = auth_header.replace("Bearer ", "")
    
    params = {
        "token": token,
        "session_id": auth.create_access_token({"session_id": session_id}),
        "userid": str(userid),
        "duration": str(session.duration_minutes),
        "total_questions": str(session.total_questions),
        "ai_greeting": ai_greeting,
        "history": json.dumps(conversation_history),
        "questions": json.dumps(questions_list)
    }
    
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    full_streamlit_url = f"{base}?{query_string}"
    
    return {
        "success": True,
        "Pyspace_interview_url": full_streamlit_url,
        "questions": questions_list
    }


@app.get("/interview/verify-session", summary="Verify session validity for Streamlit")
def verify_session(
    session_id: str,
    userid: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Decode session_id (which is now a code)
    try:
        payload = auth.decode_token(session_id)
        actual_session_id = payload.get("session_id")
        if not actual_session_id:
            raise HTTPException(status_code=400, detail="Invalid session code")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired session code")

    # 1. Check current_user["id"] == userid, else 403 Unauthorized
    if current_user.id != userid:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    # 2. Fetch session from Interview_Session table
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == actual_session_id,
        models.InterviewSession.user_id == userid
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Invalid session")
        
    # 3. Return
    return {
        "success": True,
        "session_id": actual_session_id,
        "status": session.status,
        "duration_minutes": session.duration_minutes,
        "total_questions": session.total_questions
    }


@app.post("/api/interview/answer", response_model=schemas.AnswerResponse, summary="Submit an answer and get next question")
def submit_answer(
    payload: schemas.AnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if payload.userid != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")


    actual_session_id = payload.session_id
    if isinstance(actual_session_id, str):
        try:
            token_data = auth.decode_token(actual_session_id)
            actual_session_id = token_data.get("session_id")
        except Exception:
            pass
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == actual_session_id,
        models.InterviewSession.user_id == payload.userid
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history = payload.conversation_history
    
    if payload.is_skipped:
        user_msg = "(The user skipped this question)"
    else:
        user_msg = payload.answer
    history.append({"role": "user", "content": user_msg})
    next_q_num = payload.question_number + 1
    interview_complete = next_q_num > session.total_questions
    # Fetch the exact next question from Session_Questions (if interview is not complete)
    next_question_text = ""
    if not interview_complete:
        next_sq = db.query(models.SessionQuestion).filter(
            models.SessionQuestion.session_id == session.id,
            models.SessionQuestion.question_order == next_q_num
        ).first()
        next_question_text = next_sq.question.text if next_sq and next_sq.question else "Can you elaborate further?"
    # Evaluate using Groq LLM
    try:
        import json
        groq_api_key = os.getenv("GROQ_API_KEY")
        client = Groq(api_key=groq_api_key)
        
        system_instruction = f"""Evaluate the user's answer.
Respond in valid JSON format ONLY, with the following keys:
- "feedback_to_user": A 1-2 sentence brief feedback acknowledging their answer. Do NOT provide the correct solution. NEVER ask follow-up questions, and NEVER ask the user to write code or queries.
- "ai_feedback": A private detailed technical evaluation of their answer (what was missing, what was good).
- "score": An integer score from 0 to 10 based on accuracy and depth.
User answered: {user_msg}"""
        llm_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_instruction}],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        resp_text = llm_response.choices[0].message.content
        ai_data = json.loads(resp_text)
        
        feedback_to_user = ai_data.get("feedback_to_user", "Got it.")
        ai_feedback = ai_data.get("ai_feedback", "No detailed feedback generated.")
        score = ai_data.get("score", 0)
        
    except Exception as e:
        feedback_to_user = f"Got it. (Evaluation error: {str(e)})"
        ai_feedback = f"Error evaluating: {str(e)}"
        score = 0
    # Save user answer, score, and feedback to the database
    current_sq = db.query(models.SessionQuestion).filter(
        models.SessionQuestion.session_id == session.id,
        models.SessionQuestion.question_order == payload.question_number
    ).first()
    
    if current_sq:
        current_sq.answer_text = user_msg
        current_sq.is_skipped = payload.is_skipped
        current_sq.score = score
        current_sq.ai_feedback = ai_feedback
        from datetime import datetime
        current_sq.answered_at = datetime.utcnow()
        db.commit()
    if interview_complete:
        next_ai_message = f"{feedback_to_user} Thank you! That concludes our interview. I have gathered enough information to generate your report. You can now end the session."
    else:
        # Ask the exact next question from the database
        next_ai_message = f"{feedback_to_user}\n\n{next_question_text}"
    history.append({"role": "assistant", "content": next_ai_message})
    return {
        "next_ai_message": next_ai_message,
        "conversation_history": history,
        "question_number": next_q_num,
        "interview_complete": interview_complete
    }


@app.post("/api/interview/end", response_model=schemas.EndInterviewResponse, summary="Finalize the interview session")
def end_interview(
    payload: schemas.EndInterviewRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    from datetime import datetime

    if payload.userid != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")


    actual_session_id = payload.session_id
    if isinstance(actual_session_id, str):
        try:
            token_data = auth.decode_token(actual_session_id)
            actual_session_id = token_data.get("session_id")
        except Exception:
            pass
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == actual_session_id,
        models.InterviewSession.user_id == payload.userid
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended_at = datetime.utcnow()
    session.status = 'ended'
    db.commit()

    # Generate Report Logic
    existing_report = db.query(models.InterviewReport).filter(models.InterviewReport.session_id == session.id).first()
    if not existing_report:
        session_questions = db.query(models.SessionQuestion).filter(
            models.SessionQuestion.session_id == session.id
        ).order_by(models.SessionQuestion.question_order).all()

        qa_context = ""
        for sq in session_questions:
            q_text = sq.question.text if sq.question else "Unknown question"
            ans_text = sq.answer_text if sq.answer_text else "(No answer provided)"
            qa_context += f"Q: {q_text}\nA: {ans_text}\n\n"

        import json
        from groq import Groq
        import os
        try:
            groq_api_key = os.getenv("GROQ_API_KEY")
            client = Groq(api_key=groq_api_key)
            system_prompt = """You are an expert technical recruiter evaluating an interview.
Analyze the provided Questions and Answers and respond in valid JSON format ONLY with the following keys:
- "overall_score": Integer (0-100)
- "technical_score": Integer (0-25)
- "communication_score": Integer (0-25)
- "problem_solving_score": Integer (0-25)
- "project_score": Integer (0-25)
- "strengths": Array of 3-5 strings detailing candidate strengths
- "improvements": Array of 3-5 strings detailing areas of improvement
- "suggestions": A brief paragraph giving overall suggestions."""

            user_prompt = f"Here is the interview transcript:\n\n{qa_context}"

            llm_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            resp_text = llm_response.choices[0].message.content
            ai_data = json.loads(resp_text)

            new_report = models.InterviewReport(
                session_id=session.id,
                user_id=session.user_id,
                overall_score=ai_data.get("overall_score", 0),
                technical_score=ai_data.get("technical_score", 0),
                communication_score=ai_data.get("communication_score", 0),
                problem_solving_score=ai_data.get("problem_solving_score", 0),
                project_score=ai_data.get("project_score", 0),
                strengths=ai_data.get("strengths", []),
                improvements=ai_data.get("improvements", []),
                suggestions=ai_data.get("suggestions", "No suggestions provided."),
                generated_at=datetime.utcnow()
            )
            db.add(new_report)
            db.commit()
        except Exception as e:
            print("Failed to generate report:", e)
            db.rollback()

    return {
        "success": True,
        "message": "Interview completed successfully."
    }



# ════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════

def send_subscription_request_email(user: models.User, package: models.Package, payment_details: schemas.PaymentReviewRequest):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    
    receivers = ["professional.adarsh.00@gmail.com"]
    
    if not sender_email or not sender_password:
        print("SMTP_EMAIL or SMTP_PASSWORD not set. Skipping email.")
        return {
            "success": True,
            "email_from": user.email,
            "email_to": receivers[0],
            "message": "Payment review request submitted successfully."
        }

    subject = f"New Package Request & Payment Details from {user.name}"
    
    note_text = payment_details.note if payment_details.note else "None provided"
    
    body = f"""
Hello Admin,

User {user.name} ({user.email}, Phone: {user.phone}) has requested the '{package.name}' package.

They have submitted the following payment details:
- Payment Method: {payment_details.payment_method}
- Transaction ID: {payment_details.transaction_id}
- Amount Paid: ${payment_details.amount_paid}
- Note/Sender Name: {note_text}

Please review the request and validate the payment. Once validated, update their subscription status to Active (2) and update their interview limit.

Thank you,
System
"""
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = user.email  # Set to the authenticated user's email
    msg['Reply-To'] = user.email
    msg['To'] = ", ".join(receivers)
    
    # Commenting out SMTP email logic as Render (Free Tier) does not support outbound SMTP
    # server = smtplib.SMTP('smtp.gmail.com', 587)
    # server.starttls()
    # server.login(sender_email, sender_password)
    # server.sendmail(sender_email, receivers, msg.as_string())
    # server.quit()

    return {
        "success": True,
        "email_from": user.email,
        "email_to": receivers[0],
        "message": "Payment review request submitted successfully."
    }


def _format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    else:
        return f"{round(size_bytes / (1024 * 1024), 2)} MB"


def _build_resume_data(record: models.Resume) -> dict:
    """Build the dict that maps to ResumeData schema."""
    skills_list = []
    if record.skills:
        raw_skills = [s.strip() for s in record.skills.split(",") if s.strip()]
        skills_list = [
            s for s in raw_skills
            if not (s.isupper() and len(s.split()) <= 3)  # drop section headers
            and "(cid:" not in s
        ]

    formatted_date = record.updated_at.strftime("%B %d, %Y")

    return {
        "resume_id":       record.id,
        "resume_name":     record.resume_name,
        "size":            _format_size(record.size),
        "updated_at":      formatted_date,
        "skills":          skills_list,
        "domain":          record.domain,
        "view_resume":     f"/resume/{record.id}/view",
        "download_resume": f"/resume/{record.id}/download",
        "delete_resume":   f"/resume/{record.id}",
    }


def _get_resume_or_404(resume_id: int, user_id: int, db: Session) -> models.Resume:
    """Fetch a resume, ensuring it belongs to the current user."""
    record = db.query(models.Resume).filter(
        models.Resume.id == resume_id,
        models.Resume.user_id == user_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    return record


def _build_profile_response(user: models.User, db: Session) -> dict:
    """Build the full profile response with all attribute sections."""
    entries = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == user.id
    ).all()

    profile_items = []
    seen_codes = set()

    for entry in entries:
        attr = db.query(models.Attribute).filter(
            models.Attribute.id == entry.attribute_id
        ).first()
        if attr and attr.code not in seen_codes:
            seen_codes.add(attr.code)
            profile_items.append({
                "attribute_code":  attr.code,
                "attribute_name":  attr.name,
                "value":           entry.value
            })

    last_resume = db.query(models.Resume).filter(
        models.Resume.user_id == user.id
    ).order_by(models.Resume.updated_at.desc()).first()

    return {
        "user_id":     user.id,
        "username":    user.username,
        "name":        user.name,
        "email":       user.email,
        "resume_path": last_resume.path if last_resume else None,
        "user_image":  user.pic,
        "profile":     profile_items
    }


# ════════════════════════════════════════════════════
# 15. CHANGE PASSWORD
# ════════════════════════════════════════════════════

@app.post("/change-password", summary="Change user password")
def change_password(
    payload: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not auth.verify_password(payload.old_password, current_user.password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")

    if auth.verify_password(payload.new_password, current_user.password):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from your current password"
        )

    current_user.password = auth.hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully", "success": True}


# ════════════════════════════════════════════════════
# SEED QUESTIONS ENDPOINT
# ════════════════════════════════════════════════════

@app.post("/admin/questions/seed", summary="Generate and seed interview questions using GPT-4o")
def seed_questions(db: Session = Depends(get_db)):
    try:
        # OLD - OpenAI (cost reason)
        # openai_api_key = os.getenv("OPENAI_API_KEY")
        # if not openai_api_key:
        #     raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
        # client = openai.OpenAI(api_key=openai_api_key)
        
        # NEW - Groq Llama 3.3 70B (free tier)
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")
        client = Groq(api_key=groq_api_key)

        prompt = """Generate 60 interview questions for the following roles:
Frontend Developer, Backend Developer, Data Analyst,
Full Stack Developer, HR Manager, Marketing Analyst.

For each role generate exactly 10 questions.
Mix these types: topic, resume, behavioural, design.
Mix difficulties: easy, medium, hard.
Include domain tags like: SQL, Python, React, Power BI,
CSS, JavaScript, Node.js, System Design, HR Policies,
Marketing Strategy.

Return ONLY a valid JSON array, no extra text, no markdown.
Each object must have exactly these fields:
{
  "text": "full question text here",
  "type": "topic",
  "difficulty": "medium",
  "role": "Frontend Developer",
  "domain": "React",
  "is_company_question": false,
  "frequency_score": 7
}

frequency_score is 1-10 based on how commonly this question
is asked in real company interviews in India."""

        # OLD - OpenAI (cost reason)
        # response = client.chat.completions.create(
        #     model="gpt-4o",
        #     messages=[
        #         {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON arrays."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.7,
        # )
        
        # NEW - Groq Llama 3.3 70B (free tier)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        content = response.choices[0].message.content.strip()

        # Clean markdown if GPT still returns it
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()

        try:
            questions_data = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="GPT returned invalid JSON, try again")
        
        if not isinstance(questions_data, list):
            raise HTTPException(status_code=500, detail="GPT returned invalid JSON, try again")

        inserted_count = 0
        for q_data in questions_data:
            # Map string to enums if necessary, though SQLAlchemy might handle it depending on driver
            # The model fields: type, difficulty, role, domain, is_company_question, frequency_score
            new_q = models.Question(
                text=q_data.get("text"),
                type=q_data.get("type"),
                difficulty=q_data.get("difficulty"),
                role=q_data.get("role"),
                domain=q_data.get("domain"),
                is_company_question=q_data.get("is_company_question", False),
                frequency_score=q_data.get("frequency_score", 0)
            )
            db.add(new_q)
            inserted_count += 1
        
        db.commit()

        return {
            "success": True,
            "total_inserted": inserted_count,
            "message": "Questions seeded successfully"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════
# GET INTERVIEW ROLES ENDPOINT
# ════════════════════════════════════════════════════

@app.get("/interview/roles", summary="Get all distinct roles available in the Questions table")
def get_interview_roles(db: Session = Depends(get_db)):
    try:
        results = db.query(models.Question.role).distinct().order_by(models.Question.role.asc()).all()
        
        if not results:
            return {
                "success": True,
                "roles": [],
                "message": "No roles found. Please seed the questions first."
            }

        roles = [r[0] for r in results if r[0]]
        roles.append("Other")

        return {
            "success": True,
            "roles": roles
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════
# END INTERVIEW ENDPOINT
# ════════════════════════════════════════════════════

@app.post("/api/interview/end", response_model=schemas.EndInterviewResponse, summary="Evaluate and save completed interview session")
def end_interview(
    payload: schemas.EndInterviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if payload.userid != current_user.id:
        raise HTTPException(status_code=403, detail="User ID mismatch")

    # Verify session belongs to user

    actual_session_id = payload.session_id
    if isinstance(actual_session_id, str):
        try:
            token_data = auth.decode_token(actual_session_id)
            actual_session_id = token_data.get("session_id")
        except Exception:
            pass
    session = db.query(models.InterviewSession).filter(
        models.InterviewSession.id == actual_session_id,
        models.InterviewSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or access denied")
    
    try:
        # OLD - OpenAI (cost reason)
        # openai_api_key = os.getenv("OPENAI_API_KEY")
        # if not openai_api_key:
        #     raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
        # client = openai.OpenAI(api_key=openai_api_key)
        
        # NEW - Groq Llama 3.3 70B (free tier)
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")
        client = Groq(api_key=groq_api_key)

        prompt = f"""You are an expert technical interviewer evaluator.
Review the following interview transcript and generate an evaluation report in STRICT JSON format.

The JSON MUST exactly match this structure:
{{
  "questions": [
    {{
      "answer_text": "extracted text of the candidate's answer (or empty if skipped)",
      "score": 0,
      "ai_feedback": "detailed feedback for this answer",
      "is_skipped": false
    }}
  ],
  "report": {{
    "overall_score": 85,
    "technical_score": 80,
    "communication_score": 90,
    "problem_solving_score": 85,
    "project_score": 80,
    "strengths": ["strength1", "strength2"],
    "improvements": ["improvement1", "improvement2"],
    "suggestions": "overall suggestions for the candidate"
  }}
}}

Ensure all scores are integers between 0 and 100.
The number of objects in the "questions" array MUST match the number of questions asked by the interviewer in the transcript. If the candidate didn't answer or asked to skip, set is_skipped to true.

Transcript:
{json.dumps(payload.conversation_history)}
"""

        # OLD - OpenAI (cost reason)
        # response = client.chat.completions.create(
        #     model="gpt-4o",
        #     response_format={"type": "json_object"},
        #     messages=[
        #         {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON objects."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.7,
        # )
        
        # NEW - Groq Llama 3.3 70B (free tier)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON objects."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        content = response.choices[0].message.content.strip()
        eval_data = json.loads(content)
        
        questions_data = eval_data.get("questions", [])
        report_data = eval_data.get("report", {})
        
        # INSERT into Session_Questions
        for i, q_data in enumerate(questions_data, start=1):
            sq = models.SessionQuestion(
                session_id=payload.session_id,
                question_id=1,  # Placeholder as requested
                question_order=i,
                answer_text=q_data.get("answer_text", ""),
                score=q_data.get("score", 0),
                ai_feedback=q_data.get("ai_feedback", ""),
                is_skipped=q_data.get("is_skipped", False)
            )
            db.add(sq)
        
        # INSERT into Interview_Report
        # Note: as requested, json.dumps() is used for strengths and improvements
        report = models.InterviewReport(
            session_id=payload.session_id,
            user_id=current_user.id,
            overall_score=report_data.get("overall_score", 0),
            technical_score=report_data.get("technical_score", 0),
            communication_score=report_data.get("communication_score", 0),
            problem_solving_score=report_data.get("problem_solving_score", 0),
            project_score=report_data.get("project_score", 0),
            strengths=json.dumps(report_data.get("strengths", [])),
            improvements=json.dumps(report_data.get("improvements", [])),
            suggestions=report_data.get("suggestions", "")
        )
        db.add(report)
        
        # Update session status
        from datetime import datetime
        session.status = 'ended'
        session.ended_at = datetime.utcnow()
        
        db.commit()
        
        return {{"success": True, "message": "Interview evaluated and saved successfully"}}
        
    except json.JSONDecodeError:
        db.rollback()
        raise HTTPException(status_code=500, detail="GPT returned invalid JSON")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
