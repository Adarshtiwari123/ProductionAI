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
    """
    from models import Package

    standard_packages = [
        {
            "name": "Basic Plan",
            "price": 0.0,
            "interview_limit": 5,
            "features": "5 AI Interviews, Resume Analysis, Basic Feedback"
        },
        {
            "name": "Pro Plan",
            "price": 29.99,
            "interview_limit": 25,
            "features": "25 AI Interviews, Advanced Analysis, Detailed Feedback, Mock Technical Rounds"
        },
        {
            "name": "Premium Plan",
            "price": 99.99,
            "interview_limit": 999,
            "features": "Unlimited AI Interviews, Priority Support, 1-on-1 Mentorship Session, Unlimited Resume Variations"
        }
    ]

    for pkg_data in standard_packages:
        existing = db.query(Package).filter(Package.name == pkg_data["name"]).first()
        if not existing:
            db.add(Package(**pkg_data))
    
    db.commit()
    print("[OK] Packages seeded successfully")
