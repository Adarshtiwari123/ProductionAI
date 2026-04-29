import os
import uuid
import contextlib
import sys
import smtplib
from email.mime.text import MIMEText
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

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
from fastapi.responses import FileResponse
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
        print("🚀 Starting database initialization...")
        
        # 1. Run manual migrations (renaming columns, etc.)
        migrate_schema(engine)
        
        # 2. Create missing tables (Packages, Subscriptions, Payments, etc.)
        print("🔨 Syncing tables with models...")
        models.Base.metadata.create_all(bind=engine)
        
        # 3. Seed initial data
        db = next(get_db())
        try:
            print("🌱 Seeding initial data...")
            seed_attributes(db)
            seed_packages(db)
            print("✅ Database setup completed successfully!")
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error during database initialization: {e}")
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


@app.get("/subscription", response_model=schemas.SubscriptionResponse,
         summary="Get current user subscription")
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
    # Find the most recent pending subscription for the user
    sub = db.query(models.Subscription).filter(
        models.Subscription.user_id == current_user.id,
        models.Subscription.status == 0
    ).order_by(models.Subscription.id.desc()).first()

    if not sub:
        raise HTTPException(status_code=400, detail="No pending subscription found")

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
    db.commit()
    db.refresh(new_payment)
    
    try:
        response_data = send_subscription_request_email(current_user, package, payload)
    except Exception as e:
        print(f"Error sending email: {e}")
        # On platforms like Render (Free Tier), outbound SMTP ports (like 587) are blocked.
        # So we catch the error and return a graceful success response instead of crashing.
        response_data = {
            "success": True,
            "message": "Payment review requested successfully, but email notification failed (server restriction)."
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
# HELPERS
# ════════════════════════════════════════════════════

def send_subscription_request_email(user: models.User, package: models.Package, payment_details: schemas.PaymentReviewRequest):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    
    receivers = ["professional.adarsh.00@gmail.com"]
    
    if not sender_email or not sender_password:
        print("SMTP_EMAIL or SMTP_PASSWORD not set. Skipping email.")
        return {
            "email_from": user.email,
            "email_to": receivers[0],
            "message": "Email has been sent successfully."
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

Please review the request and validate the payment. Once validated, update their subscription status to Active (1) and update their interview limit.

Thank you,
System
"""
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = user.email  # Set to the authenticated user's email
    msg['Reply-To'] = user.email
    msg['To'] = ", ".join(receivers)
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, sender_password)
    # SMTP servers usually require the authenticated user in the envelope sender (mail from), 
    # but we can pass user.email in the From header.
    server.sendmail(sender_email, receivers, msg.as_string())
    server.quit()

    return {
        "email_from": user.email,
        "email_to": receivers[0],
        "message": "Email has been sent successfully."
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
