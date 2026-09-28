from sqlalchemy import text
from sqlalchemy.orm import Session


def next_number(db: Session, code: str) -> str:
    """Allocate the next number atomically (row lock held until commit; gaps possible on rollback)."""
    row = db.execute(
        text(
            "UPDATE number_sequence SET next_value = next_value + 1 WHERE code = :c "
            "RETURNING prefix, width, next_value - 1"
        ),
        {"c": code},
    ).one()
    prefix, width, value = row
    return f"{prefix}{value:0{width}d}"
