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
    print("✅ Attributes seeded successfully")


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
        print(f"✅ New attribute created dynamically: {code}")
    return attr
