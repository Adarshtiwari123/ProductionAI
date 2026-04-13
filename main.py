from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError

import models, schemas, auth
from database import engine, get_db
from resume_parser import parse_resume

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth API")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
token_blacklist = set()

# ── Test ─────────────────────────────────────────────────
@app.get("/test")
def test():
    return {"status": "working"}

# ── Register ─────────────────────────────────────────────
@app.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    try:
        if payload.password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        if len(payload.password.encode('utf-8')) > 72:
            raise HTTPException(status_code=400, detail="Password too long, max 72 characters")
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = models.User(
            full_name=payload.full_name,
            email=payload.email,
            hashed_password=auth.hash_password(payload.password)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except HTTPException:
        raise
    except Exception as e:
        print(f"REGISTER ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Login ─────────────────────────────────────────────────
@app.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not auth.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

# ── Get current user dependency ───────────────────────────
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if token in token_blacklist:
        raise HTTPException(status_code=401, detail="Token has been logged out, please login again")
    try:
        payload = auth.decode_token(token)
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ── Me ────────────────────────────────────────────────────
@app.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# ── Logout ────────────────────────────────────────────────
@app.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    token_blacklist.add(token)
    return {"message": "Successfully logged out"}

# ── Resume Upload ─────────────────────────────────────────
@app.post("/upload-resume", response_model=schemas.UserProfileResponse)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 5MB")

    try:
        extracted = parse_resume(file_bytes, file.filename)
    except Exception as e:
        print(f"PARSE ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {str(e)}")

    # Convert years_of_experience to string if it's a number
    if extracted.get("years_of_experience") is not None:
        extracted["years_of_experience"] = str(extracted["years_of_experience"])

    print(f"EXTRACTED DATA: {extracted}")

    profile = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == current_user.id
    ).first()

    if profile:
        for key, value in extracted.items():
            if value is not None:
                setattr(profile, key, value)
    else:
        profile = models.UserProfile(
            user_id=current_user.id,
            **extracted
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return profile
# @app.post("/upload-resume", response_model=schemas.UserProfileResponse)
# async def upload_resume(
#     file: UploadFile = File(...),
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     # Validate file type
#     if not file.filename.endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="Only PDF files are allowed")

#     # Validate file size (max 5MB)
#     file_bytes = await file.read()
#     if len(file_bytes) > 5 * 1024 * 1024:
#         raise HTTPException(status_code=400, detail="File size must be less than 5MB")

#     # Parse resume and extract all info
#     extracted = parse_resume(file_bytes, file.filename)

#     # Check if profile already exists
#     profile = db.query(models.UserProfile).filter(
#         models.UserProfile.user_id == current_user.id
#     ).first()

#     if profile:
#         # Update existing profile
#         for key, value in extracted.items():
#             if value is not None:
#                 setattr(profile, key, value)
#     else:
#         # Create new profile
#         profile = models.UserProfile(
#             user_id=current_user.id,
#             **extracted
#         )
#         db.add(profile)

#     db.commit()
#     db.refresh(profile)
#     return profile

# ── Get Profile ───────────────────────────────────────────
@app.get("/profile", response_model=schemas.UserProfileResponse)
def get_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = db.query(models.UserProfile).filter(
        models.UserProfile.user_id == current_user.id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Please upload your resume first.")
    return profile
# from fastapi import FastAPI, Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordBearer
# from sqlalchemy.orm import Session
# from jose import JWTError

# import models, schemas, auth
# from database import engine, get_db

# models.Base.metadata.create_all(bind=engine)

# app = FastAPI(title="Auth API")

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# # ── Token blacklist (logged out tokens) ──────────────────
# token_blacklist = set()

# # ── Test route ───────────────────────────────────────────
# @app.get("/test")
# def test():
#     return {"status": "working"}

# # ── Register ─────────────────────────────────────────────
# @app.post("/register", response_model=schemas.UserResponse, status_code=201)
# def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
#     try:
#         if payload.password != payload.confirm_password:
#             raise HTTPException(status_code=400, detail="Passwords do not match")

#         if len(payload.password.encode('utf-8')) > 72:
#             raise HTTPException(status_code=400, detail="Password too long, max 72 characters")

#         existing = db.query(models.User).filter(models.User.email == payload.email).first()
#         if existing:
#             raise HTTPException(status_code=400, detail="Email already registered")

#         user = models.User(
#             full_name=payload.full_name,
#             email=payload.email,
#             hashed_password=auth.hash_password(payload.password)
#         )
#         db.add(user)
#         db.commit()
#         db.refresh(user)
#         return user

#     except HTTPException:
#         raise
#     except Exception as e:
#         print(f"REGISTER ERROR: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# # ── Login ─────────────────────────────────────────────────
# @app.post("/login", response_model=schemas.TokenResponse)
# def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
#     user = db.query(models.User).filter(models.User.email == payload.email).first()
#     if not user or not auth.verify_password(payload.password, user.hashed_password):
#         raise HTTPException(status_code=401, detail="Invalid email or password")

#     token = auth.create_access_token({"sub": user.email})
#     return {"access_token": token, "token_type": "bearer"}

# # ── Get current user (dependency) ─────────────────────────
# def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
#     if token in token_blacklist:
#         raise HTTPException(status_code=401, detail="Token has been logged out, please login again")
#     try:
#         payload = auth.decode_token(token)
#         email = payload.get("sub")
#         if not email:
#             raise HTTPException(status_code=401, detail="Invalid token")
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Token invalid or expired")

#     user = db.query(models.User).filter(models.User.email == email).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     return user

# # ── Protected route ───────────────────────────────────────
# @app.get("/me", response_model=schemas.UserResponse)
# def get_me(current_user: models.User = Depends(get_current_user)):
#     return current_user

# # ── Logout ────────────────────────────────────────────────
# @app.post("/logout")
# def logout(token: str = Depends(oauth2_scheme)):
#     token_blacklist.add(token)
#     return {"message": "Successfully logged out"}
# # from fastapi import FastAPI, Depends, HTTPException, status
# # from fastapi.security import OAuth2PasswordBearer
# # from sqlalchemy.orm import Session
# # from jose import JWTError

# # import models, schemas, auth
# # from database import engine, get_db

# # models.Base.metadata.create_all(bind=engine)

# # app = FastAPI(title="Auth API")

# # oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# # # ── Test route ───────────────────────────────────────────
# # @app.get("/test")
# # def test():
# #     return {"status": "working"}

# # # ── Register ─────────────────────────────────────────────
# # @app.post("/register", response_model=schemas.UserResponse, status_code=201)
# # def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
# #     try:
# #         if payload.password != payload.confirm_password:
# #             raise HTTPException(status_code=400, detail="Passwords do not match")

# #         if len(payload.password.encode('utf-8')) > 72:
# #             raise HTTPException(status_code=400, detail="Password too long, max 72 characters")

# #         existing = db.query(models.User).filter(models.User.email == payload.email).first()
# #         if existing:
# #             raise HTTPException(status_code=400, detail="Email already registered")

# #         user = models.User(
# #             full_name=payload.full_name,
# #             email=payload.email,
# #             hashed_password=auth.hash_password(payload.password)
# #         )
# #         db.add(user)
# #         db.commit()
# #         db.refresh(user)
# #         return user

# #     except HTTPException:
# #         raise
# #     except Exception as e:
# #         print(f"REGISTER ERROR: {e}")
# #         raise HTTPException(status_code=500, detail=str(e))

# # # ── Login ─────────────────────────────────────────────────
# # @app.post("/login", response_model=schemas.TokenResponse)
# # def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
# #     user = db.query(models.User).filter(models.User.email == payload.email).first()
# #     if not user or not auth.verify_password(payload.password, user.hashed_password):
# #         raise HTTPException(status_code=401, detail="Invalid email or password")

# #     token = auth.create_access_token({"sub": user.email})
# #     return {"access_token": token, "token_type": "bearer"}

# # # ── Get current user (dependency) ────────────────────────
# # def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
# #     try:
# #         payload = auth.decode_token(token)
# #         email = payload.get("sub")
# #         if not email:
# #             raise HTTPException(status_code=401, detail="Invalid token")
# #     except JWTError:
# #         raise HTTPException(status_code=401, detail="Token invalid or expired")

# #     user = db.query(models.User).filter(models.User.email == email).first()
# #     if not user:
# #         raise HTTPException(status_code=404, detail="User not found")
# #     return user

# # # ── Protected route ───────────────────────────────────────
# # @app.get("/me", response_model=schemas.UserResponse)
# # def get_me(current_user: models.User = Depends(get_current_user)):
# #     return current_user

