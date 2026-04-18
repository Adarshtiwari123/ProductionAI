from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import JWTError

import models, schemas, auth
from database import engine, get_db
from resume_parser import parse_resume, detect_dynamic_sections, STANDARD_ATTRIBUTES
from seed import seed_attributes, get_or_create_attribute

# ── Create all tables ────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="InterviewAI API", version="2.0")

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
token_blacklist = set()


# ── Seed attributes on startup ───────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    db = next(get_db())
    try:
        seed_attributes(db)
    finally:
        db.close()


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
    if user.is_approved == 0:
        raise HTTPException(status_code=403, detail="Your account is not approved yet")
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
        is_approved=1
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
    if user.is_approved == 0:
        raise HTTPException(status_code=403, detail="Your account is not approved yet")

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

@app.post("/upload-resume", response_model=schemas.UserProfileResponse,
          summary="Upload PDF resume — auto extracts and stores all sections")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 5MB")

    try:
        parsed = parse_resume(file_bytes)
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")

    personal = parsed["personal"]
    sections = parsed["sections"]
    raw_text = parsed["raw_text"]

    # Update user personal info from resume
    if personal.get("name"):
        current_user.name = personal["name"][:30]
    if personal.get("email") and personal["email"] != current_user.email:
        current_user.email = personal["email"][:30]
    if personal.get("phone"):
        current_user.phone = personal["phone"][:20]
    db.commit()

    # Detect and create dynamic sections
    known_codes = [a["code"] for a in STANDARD_ATTRIBUTES]
    dynamic_attrs = detect_dynamic_sections(raw_text, known_codes)
    for dattr in dynamic_attrs:
        get_or_create_attribute(db, dattr["code"], dattr["name"], dattr["type"])

    # Store each section into user_profile
    for code, value in sections.items():
        if not value:
            continue
        attr = get_or_create_attribute(db, code)
        existing = db.query(models.UserProfile).filter(
            models.UserProfile.user_id == current_user.id,
            models.UserProfile.attribute_id == attr.id
        ).first()
        if existing:
            existing.attribute_value = value
        else:
            db.add(models.UserProfile(
                user_id=current_user.id,
                attribute_id=attr.id,
                attribute_value=value
            ))

    db.commit()
    return _build_profile_response(current_user, db)


# ════════════════════════════════════════════════════
# 6. GET PROFILE
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
# 7. UPDATE PROFILE FIELD
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
        existing.attribute_value = payload.attribute_value
    else:
        db.add(models.UserProfile(
            user_id=current_user.id,
            attribute_id=attr.id,
            attribute_value=payload.attribute_value
        ))

    db.commit()
    return _build_profile_response(current_user, db)


# ════════════════════════════════════════════════════
# 8. LIST ALL ATTRIBUTES
# ════════════════════════════════════════════════════

@app.get("/attributes", response_model=list[schemas.AttributeResponse],
         summary="List all available resume attributes/sections")
def list_attributes(db: Session = Depends(get_db)):
    return db.query(models.Attribute).all()


# ════════════════════════════════════════════════════
# 9. DELETE USER (cascades to profile)
# ════════════════════════════════════════════════════

@app.delete("/user", summary="Delete current user and all profile data")
def delete_user(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.delete(current_user)
    db.commit()
    return {"message": f"User '{current_user.username}' and all profile data deleted successfully"}


# ════════════════════════════════════════════════════
# HELPER
# ════════════════════════════════════════════════════

def _build_profile_response(user: models.User, db: Session) -> dict:
    entries = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == user.id
    ).all()

    profile_items = []
    for entry in entries:
        attr = db.query(models.Attribute).filter(
            models.Attribute.id == entry.attribute_id
        ).first()
        if attr:
            profile_items.append({
                "attribute_code": attr.code,
                "attribute_name": attr.name,
                "attribute_value": entry.attribute_value
            })

    return {
        "user_id": user.id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "profile": profile_items
    }
# from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
# from fastapi.security import OAuth2PasswordBearer
# from sqlalchemy.orm import Session
# from jose import JWTError

# import models, schemas, auth
# from database import engine, get_db
# from resume_parser import parse_resume, detect_dynamic_sections, STANDARD_ATTRIBUTES
# from seed import seed_attributes, get_or_create_attribute

# # ── Create all tables ────────────────────────────────────────────────────────
# models.Base.metadata.create_all(bind=engine)

# app = FastAPI(title="InterviewAI API", version="2.0")
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
# token_blacklist = set()


# # ── Seed attributes on startup ───────────────────────────────────────────────
# @app.on_event("startup")
# def on_startup():
#     db = next(get_db())
#     try:
#         seed_attributes(db)
#     finally:
#         db.close()


# # ════════════════════════════════════════════════════
# # AUTH DEPENDENCY
# # ════════════════════════════════════════════════════

# def get_current_user(
#     token: str = Depends(oauth2_scheme),
#     db: Session = Depends(get_db)
# ):
#     if token in token_blacklist:
#         raise HTTPException(status_code=401, detail="Token has been logged out. Please login again.")
#     try:
#         payload = auth.decode_token(token)
#         username = payload.get("sub")
#         if not username:
#             raise HTTPException(status_code=401, detail="Invalid token")
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Token invalid or expired")

#     user = db.query(models.User).filter(models.User.username == username).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     if user.is_approved == 0:
#         raise HTTPException(status_code=403, detail="Your account is not approved yet")
#     return user


# # ════════════════════════════════════════════════════
# # 1. REGISTER
# # ════════════════════════════════════════════════════

# @app.post("/register", response_model=schemas.UserResponse, status_code=201,
#           summary="Register a new user")
# def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
#     # Check duplicate username
#     if db.query(models.User).filter(models.User.username == payload.username).first():
#         raise HTTPException(status_code=400, detail="Username already taken")

#     # Check duplicate email
#     if db.query(models.User).filter(models.User.email == payload.email).first():
#         raise HTTPException(status_code=400, detail="Email already registered")

#     # Check passwords match
#     if payload.password != payload.confirm_password:
#         raise HTTPException(status_code=400, detail="Passwords do not match")

#     user = models.User(
#         username=payload.username,
#         name=payload.name,
#         email=str(payload.email),
#         phone=payload.phone,
#         password=auth.hash_password(payload.password),
#         is_approved=1  # auto-approved
#     )
#     db.add(user)
#     db.commit()
#     db.refresh(user)
#     return user


# # ════════════════════════════════════════════════════
# # 2. LOGIN
# # ════════════════════════════════════════════════════

# @app.post("/login", response_model=schemas.TokenResponse,
#           summary="Login with username and password")
# def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
#     user = db.query(models.User).filter(models.User.username == payload.username).first()
#     if not user or not auth.verify_password(payload.password, user.password):
#         raise HTTPException(status_code=401, detail="Invalid username or password")
#     if user.is_approved == 0:
#         raise HTTPException(status_code=403, detail="Your account is not approved yet")

#     token = auth.create_access_token({"sub": user.username})
#     return {"access_token": token, "token_type": "bearer"}


# # ════════════════════════════════════════════════════
# # 3. LOGOUT
# # ════════════════════════════════════════════════════

# @app.post("/logout", summary="Logout and invalidate token")
# def logout(token: str = Depends(oauth2_scheme)):
#     token_blacklist.add(token)
#     return {"message": "Successfully logged out"}


# # ════════════════════════════════════════════════════
# # 4. GET CURRENT USER
# # ════════════════════════════════════════════════════

# @app.get("/me", response_model=schemas.UserResponse,
#          summary="Get logged in user details")
# def get_me(current_user: models.User = Depends(get_current_user)):
#     return current_user


# # ════════════════════════════════════════════════════
# # 5. UPLOAD RESUME
# # ════════════════════════════════════════════════════

# @app.post("/upload-resume", response_model=schemas.UserProfileResponse,
#           summary="Upload PDF resume — auto extracts and stores all sections")
# async def upload_resume(
#     file: UploadFile = File(...),
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Validate PDF
#     if not file.filename.lower().endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="Only PDF files are allowed")

#     file_bytes = await file.read()
#     if len(file_bytes) > 5 * 1024 * 1024:
#         raise HTTPException(status_code=400, detail="File size must be less than 5MB")

#     try:
#         parsed = parse_resume(file_bytes)
#     except Exception as e:
#         print(f"PARSE ERROR: {e}")
#         raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")

#     personal = parsed["personal"]
#     sections = parsed["sections"]
#     raw_text = parsed["raw_text"]

#     # ── Update user's name/email/phone from resume if extracted ─────────────
#     if personal.get("name"):
#         current_user.name = personal["name"][:30]
#     if personal.get("email") and personal["email"] != current_user.email:
#         current_user.email = personal["email"][:30]
#     if personal.get("phone"):
#         current_user.phone = personal["phone"][:20]
#     db.commit()

#     # ── Detect dynamic sections not in standard list ─────────────────────────
#     known_codes = [a["code"] for a in STANDARD_ATTRIBUTES]
#     dynamic_attrs = detect_dynamic_sections(raw_text, known_codes)
#     for dattr in dynamic_attrs:
#         get_or_create_attribute(db, dattr["code"], dattr["name"], dattr["type"])

#     # ── Store each section into user_profile ─────────────────────────────────
#     for code, value in sections.items():
#         if not value:
#             continue

#         attr = get_or_create_attribute(db, code)

#         # Check if this user_profile entry already exists
#         existing = db.query(models.UserProfile).filter(
#             models.UserProfile.user_id == current_user.id,
#             models.UserProfile.attribute_id == attr.id
#         ).first()

#         if existing:
#             existing.attribute_value = value
#         else:
#             db.add(models.UserProfile(
#                 user_id=current_user.id,
#                 attribute_id=attr.id,
#                 attribute_value=value
#             ))

#     db.commit()

#     # ── Return full profile ──────────────────────────────────────────────────
#     return _build_profile_response(current_user, db)


# # ════════════════════════════════════════════════════
# # 6. GET PROFILE
# # ════════════════════════════════════════════════════

# @app.get("/profile", response_model=schemas.UserProfileResponse,
#          summary="Get full user profile with all resume sections")
# def get_profile(
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     profile_entries = db.query(models.UserProfile).filter(
#         models.UserProfile.user_id == current_user.id
#     ).all()

#     if not profile_entries:
#         raise HTTPException(
#             status_code=404,
#             detail="Profile not found. Please upload your resume first."
#         )

#     return _build_profile_response(current_user, db)


# # ════════════════════════════════════════════════════
# # 7. UPDATE PROFILE FIELD
# # ════════════════════════════════════════════════════

# @app.put("/profile", response_model=schemas.UserProfileResponse,
#          summary="Update a specific profile field by attribute code")
# def update_profile(
#     payload: schemas.UpdateProfileRequest,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     attr = db.query(models.Attribute).filter(
#         models.Attribute.code == payload.attribute_code
#     ).first()

#     if not attr:
#         raise HTTPException(status_code=404, detail=f"Attribute '{payload.attribute_code}' not found")

#     existing = db.query(models.UserProfile).filter(
#         models.UserProfile.user_id == current_user.id,
#         models.UserProfile.attribute_id == attr.id
#     ).first()

#     if existing:
#         existing.attribute_value = payload.attribute_value
#     else:
#         db.add(models.UserProfile(
#             user_id=current_user.id,
#             attribute_id=attr.id,
#             attribute_value=payload.attribute_value
#         ))

#     db.commit()
#     return _build_profile_response(current_user, db)


# # ════════════════════════════════════════════════════
# # 8. LIST ALL ATTRIBUTES
# # ════════════════════════════════════════════════════

# @app.get("/attributes", response_model=list[schemas.AttributeResponse],
#          summary="List all available resume attributes/sections")
# def list_attributes(db: Session = Depends(get_db)):
#     return db.query(models.Attribute).all()


# # ════════════════════════════════════════════════════
# # 9. DELETE USER (cascades to profile)
# # ════════════════════════════════════════════════════

# @app.delete("/user", summary="Delete current user and all profile data")
# def delete_user(
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     db.delete(current_user)
#     db.commit()
#     return {"message": f"User '{current_user.username}' and all profile data deleted successfully"}


# # ════════════════════════════════════════════════════
# # HELPER
# # ════════════════════════════════════════════════════

# def _build_profile_response(user: models.User, db: Session) -> dict:
#     """Build the full profile response with all attribute sections"""
#     entries = db.query(models.UserProfile).filter(
#         models.UserProfile.user_id == user.id
#     ).all()

#     profile_items = []
#     for entry in entries:
#         attr = db.query(models.Attribute).filter(
#             models.Attribute.id == entry.attribute_id
#         ).first()
#         if attr:
#             profile_items.append({
#                 "attribute_code": attr.code,
#                 "attribute_name": attr.name,
#                 "attribute_value": entry.attribute_value
#             })

#     return {
#         "user_id": user.id,
#         "username": user.username,
#         "name": user.name,
#         "email": user.email,
#         "profile": profile_items
#     }
# # from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
# # from fastapi.security import OAuth2PasswordBearer
# # from sqlalchemy.orm import Session
# # from jose import JWTError

# # import models, schemas, auth
# # from database import engine, get_db
# # from resume_parser import parse_resume, detect_dynamic_sections, STANDARD_ATTRIBUTES
# # from seed import seed_attributes, get_or_create_attribute

# # # ── Create all tables ────────────────────────────────────────────────────────
# # models.Base.metadata.create_all(bind=engine)

# # app = FastAPI(title="InterviewAI API", version="2.0")
# # oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
# # token_blacklist = set()


# # # ── Seed attributes on startup ───────────────────────────────────────────────
# # @app.on_event("startup")
# # def on_startup():
# #     db = next(get_db())
# #     try:
# #         seed_attributes(db)
# #     finally:
# #         db.close()


# # # ════════════════════════════════════════════════════
# # # AUTH DEPENDENCY
# # # ════════════════════════════════════════════════════

# # def get_current_user(
# #     token: str = Depends(oauth2_scheme),
# #     db: Session = Depends(get_db)
# # ):
# #     if token in token_blacklist:
# #         raise HTTPException(status_code=401, detail="Token has been logged out. Please login again.")
# #     try:
# #         payload = auth.decode_token(token)
# #         username = payload.get("sub")
# #         if not username:
# #             raise HTTPException(status_code=401, detail="Invalid token")
# #     except JWTError:
# #         raise HTTPException(status_code=401, detail="Token invalid or expired")

# #     user = db.query(models.User).filter(models.User.username == username).first()
# #     if not user:
# #         raise HTTPException(status_code=404, detail="User not found")
# #     if user.is_approved == '0':
# #         raise HTTPException(status_code=403, detail="Your account is not approved yet")
# #     return user


# # # ════════════════════════════════════════════════════
# # # 1. REGISTER
# # # ════════════════════════════════════════════════════

# # @app.post("/register", response_model=schemas.UserResponse, status_code=201,
# #           summary="Register a new user")
# # def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
# #     # Check duplicate username
# #     if db.query(models.User).filter(models.User.username == payload.username).first():
# #         raise HTTPException(status_code=400, detail="Username already taken")

# #     # Check duplicate email
# #     if db.query(models.User).filter(models.User.email == payload.email).first():
# #         raise HTTPException(status_code=400, detail="Email already registered")

# #     # Check passwords match
# #     if payload.password != payload.confirm_password:
# #         raise HTTPException(status_code=400, detail="Passwords do not match")

# #     user = models.User(
# #         username=payload.username,
# #         name=payload.name,
# #         email=str(payload.email),
# #         phone=payload.phone,
# #         password=auth.hash_password(payload.password),
# #         is_approved='1'  # auto-approved
# #     )
# #     db.add(user)
# #     db.commit()
# #     db.refresh(user)
# #     return user


# # # ════════════════════════════════════════════════════
# # # 2. LOGIN
# # # ════════════════════════════════════════════════════

# # @app.post("/login", response_model=schemas.TokenResponse,
# #           summary="Login with username and password")
# # def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
# #     user = db.query(models.User).filter(models.User.username == payload.username).first()
# #     if not user or not auth.verify_password(payload.password, user.password):
# #         raise HTTPException(status_code=401, detail="Invalid username or password")
# #     if user.is_approved == '0':
# #         raise HTTPException(status_code=403, detail="Your account is not approved yet")

# #     token = auth.create_access_token({"sub": user.username})
# #     return {"access_token": token, "token_type": "bearer"}


# # # ════════════════════════════════════════════════════
# # # 3. LOGOUT
# # # ════════════════════════════════════════════════════

# # @app.post("/logout", summary="Logout and invalidate token")
# # def logout(token: str = Depends(oauth2_scheme)):
# #     token_blacklist.add(token)
# #     return {"message": "Successfully logged out"}


# # # ════════════════════════════════════════════════════
# # # 4. GET CURRENT USER
# # # ════════════════════════════════════════════════════

# # @app.get("/me", response_model=schemas.UserResponse,
# #          summary="Get logged in user details")
# # def get_me(current_user: models.User = Depends(get_current_user)):
# #     return current_user


# # # ════════════════════════════════════════════════════
# # # 5. UPLOAD RESUME
# # # ════════════════════════════════════════════════════

# # @app.post("/upload-resume", response_model=schemas.UserProfileResponse,
# #           summary="Upload PDF resume — auto extracts and stores all sections")
# # async def upload_resume(
# #     file: UploadFile = File(...),
# #     current_user: models.User = Depends(get_current_user),
# #     db: Session = Depends(get_db)
# # ):
# #     # Validate PDF
# #     if not file.filename.lower().endswith(".pdf"):
# #         raise HTTPException(status_code=400, detail="Only PDF files are allowed")

# #     file_bytes = await file.read()
# #     if len(file_bytes) > 5 * 1024 * 1024:
# #         raise HTTPException(status_code=400, detail="File size must be less than 5MB")

# #     try:
# #         parsed = parse_resume(file_bytes)
# #     except Exception as e:
# #         print(f"PARSE ERROR: {e}")
# #         raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")

# #     personal = parsed["personal"]
# #     sections = parsed["sections"]
# #     raw_text = parsed["raw_text"]

# #     # ── Update user's name/email/phone from resume if extracted ─────────────
# #     if personal.get("name"):
# #         current_user.name = personal["name"][:30]
# #     if personal.get("email") and personal["email"] != current_user.email:
# #         current_user.email = personal["email"][:30]
# #     if personal.get("phone"):
# #         current_user.phone = personal["phone"][:20]
# #     db.commit()

# #     # ── Detect dynamic sections not in standard list ─────────────────────────
# #     known_codes = [a["code"] for a in STANDARD_ATTRIBUTES]
# #     dynamic_attrs = detect_dynamic_sections(raw_text, known_codes)
# #     for dattr in dynamic_attrs:
# #         get_or_create_attribute(db, dattr["code"], dattr["name"], dattr["type"])

# #     # ── Store each section into user_profile ─────────────────────────────────
# #     for code, value in sections.items():
# #         if not value:
# #             continue

# #         attr = get_or_create_attribute(db, code)

# #         # Check if this user_profile entry already exists
# #         existing = db.query(models.UserProfile).filter(
# #             models.UserProfile.user_id == current_user.id,
# #             models.UserProfile.attribute_id == attr.id
# #         ).first()

# #         if existing:
# #             existing.attribute_value = value
# #         else:
# #             db.add(models.UserProfile(
# #                 user_id=current_user.id,
# #                 attribute_id=attr.id,
# #                 attribute_value=value
# #             ))

# #     db.commit()

# #     # ── Return full profile ──────────────────────────────────────────────────
# #     return _build_profile_response(current_user, db)


# # # ════════════════════════════════════════════════════
# # # 6. GET PROFILE
# # # ════════════════════════════════════════════════════

# # @app.get("/profile", response_model=schemas.UserProfileResponse,
# #          summary="Get full user profile with all resume sections")
# # def get_profile(
# #     current_user: models.User = Depends(get_current_user),
# #     db: Session = Depends(get_db)
# # ):
# #     profile_entries = db.query(models.UserProfile).filter(
# #         models.UserProfile.user_id == current_user.id
# #     ).all()

# #     if not profile_entries:
# #         raise HTTPException(
# #             status_code=404,
# #             detail="Profile not found. Please upload your resume first."
# #         )

# #     return _build_profile_response(current_user, db)


# # # ════════════════════════════════════════════════════
# # # 7. UPDATE PROFILE FIELD
# # # ════════════════════════════════════════════════════

# # @app.put("/profile", response_model=schemas.UserProfileResponse,
# #          summary="Update a specific profile field by attribute code")
# # def update_profile(
# #     payload: schemas.UpdateProfileRequest,
# #     current_user: models.User = Depends(get_current_user),
# #     db: Session = Depends(get_db)
# # ):
# #     attr = db.query(models.Attribute).filter(
# #         models.Attribute.code == payload.attribute_code
# #     ).first()

# #     if not attr:
# #         raise HTTPException(status_code=404, detail=f"Attribute '{payload.attribute_code}' not found")

# #     existing = db.query(models.UserProfile).filter(
# #         models.UserProfile.user_id == current_user.id,
# #         models.UserProfile.attribute_id == attr.id
# #     ).first()

# #     if existing:
# #         existing.attribute_value = payload.attribute_value
# #     else:
# #         db.add(models.UserProfile(
# #             user_id=current_user.id,
# #             attribute_id=attr.id,
# #             attribute_value=payload.attribute_value
# #         ))

# #     db.commit()
# #     return _build_profile_response(current_user, db)


# # # ════════════════════════════════════════════════════
# # # 8. LIST ALL ATTRIBUTES
# # # ════════════════════════════════════════════════════

# # @app.get("/attributes", response_model=list[schemas.AttributeResponse],
# #          summary="List all available resume attributes/sections")
# # def list_attributes(db: Session = Depends(get_db)):
# #     return db.query(models.Attribute).all()


# # # ════════════════════════════════════════════════════
# # # 9. DELETE USER (cascades to profile)
# # # ════════════════════════════════════════════════════

# # @app.delete("/user", summary="Delete current user and all profile data")
# # def delete_user(
# #     current_user: models.User = Depends(get_current_user),
# #     db: Session = Depends(get_db)
# # ):
# #     db.delete(current_user)
# #     db.commit()
# #     return {"message": f"User '{current_user.username}' and all profile data deleted successfully"}


# # # ════════════════════════════════════════════════════
# # # HELPER
# # # ════════════════════════════════════════════════════

# # def _build_profile_response(user: models.User, db: Session) -> dict:
# #     """Build the full profile response with all attribute sections"""
# #     entries = db.query(models.UserProfile).filter(
# #         models.UserProfile.user_id == user.id
# #     ).all()

# #     profile_items = []
# #     for entry in entries:
# #         attr = db.query(models.Attribute).filter(
# #             models.Attribute.id == entry.attribute_id
# #         ).first()
# #         if attr:
# #             profile_items.append({
# #                 "attribute_code": attr.code,
# #                 "attribute_name": attr.name,
# #                 "attribute_value": entry.attribute_value
# #             })

# #     return {
# #         "user_id": user.id,
# #         "username": user.username,
# #         "name": user.name,
# #         "email": user.email,
# #         "profile": profile_items
# #     }
