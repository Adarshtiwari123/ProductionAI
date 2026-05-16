from resume_parser import STANDARD_ATTRIBUTES


def seed_attributes(db):
    """
    Pre-seed the attribute table with standard resume sections.
    Runs on every startup — skips if already exists (upsert by code).
    """
    from models import Attribute

    for attr in STANDARD_ATTRIBUTES:
        existing = db.query(Attribute).filter(Attribute.code == attr["code"]).first()
        if not existing:
            db.add(Attribute(
                code=attr["code"],
                name=attr["name"],
                type=attr["type"]
            ))
    db.commit()
    print("[OK] Attributes seeded successfully")


def get_or_create_attribute(db, code: str, name: str = None, type: str = "text"):
    """
    Get an attribute by code, or create it if it doesn't exist.
    Used for dynamic attribute creation from resume parsing.
    """
    from models import Attribute

    attr = db.query(Attribute).filter(Attribute.code == code).first()
    if not attr:
        attr = Attribute(
            code=code,
            name=name or code.replace('_', ' ').title(),
            type=type
        )
        db.add(attr)
        db.commit()
        db.refresh(attr)
        print(f"[OK] New attribute created dynamically: {code}")
    return attr


def seed_packages(db):
    """
    Pre-seed the packages table with standard plans.
    Updates existing plans with new credit values.
    """
    from models import Package
    from sqlalchemy import func

    standard_packages = [
        {
            "name": "Free",
            "price": 0.0,
            "total_credits": 1,
            "interview_limit": 1,
            "credit_cost_10min": 1,
            "credit_cost_20min": 2,
            "credit_cost_40min": 4,
            "features": "Basic access"
        },
        {
            "name": "Basic Plan",
            "price": 10.0,
            "total_credits": 10,
            "interview_limit": 10,
            "credit_cost_10min": 1,
            "credit_cost_20min": 2,
            "credit_cost_40min": 4,
            "features": "10 AI Interviews, Resume Analysis, Basic Feedback"
        },
        {
            "name": "Pro Plan",
            "price": 29.99,
            "total_credits": 25,
            "interview_limit": 25,
            "credit_cost_10min": 1,
            "credit_cost_20min": 2,
            "credit_cost_40min": 4,
            "features": "25 AI Interviews, Advanced Analysis, Detailed Feedback, Mock Technical Rounds"
        }
    ]

    for pkg_data in standard_packages:
        existing = db.query(Package).filter(Package.name == pkg_data["name"]).first()
        if not existing:
            # If "Basic Plan" or "Pro Plan" exist with different names but similar purpose, 
            # we might need to handle them. But user said "Free plan row", "Basic plan row", etc.
            db.add(Package(**pkg_data))
            print(f"[OK] Package '{pkg_data['name']}' created")
        else:
            # Update existing row
            existing.total_credits = pkg_data["total_credits"]
            existing.credit_cost_10min = pkg_data["credit_cost_10min"]
            existing.credit_cost_20min = pkg_data["credit_cost_20min"]
            existing.credit_cost_40min = pkg_data["credit_cost_40min"]
            # Also update interview_limit if specified
            if "interview_limit" in pkg_data:
                existing.interview_limit = pkg_data["interview_limit"]
            print(f"[OK] Package '{pkg_data['name']}' updated")
    
    db.commit()
    print("[OK] Packages seeded successfully")
