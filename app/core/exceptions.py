from fastapi import HTTPException, status


class NotFound(HTTPException):
    def __init__(self, entity: str, entity_id: object | None = None):
        detail = f"{entity} not found" if entity_id is None else f"{entity} {entity_id} not found"
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class Conflict(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_409_CONFLICT, detail)


class BadRequest(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


# Friendly messages for known database constraints.
CONSTRAINT_MESSAGES: dict[str, str] = {
    "uq_active_loan": (
        "This copy already has a loan with that status. The (copy_id, status) constraint "
        "blocks repeat returns of the same copy - apply migrations/001_fix_unique_constraints.sql."
    ),
    "uq_active_reservation": (
        "This member already has a reservation with that status for this book. "
        "Apply migrations/001_fix_unique_constraints.sql to allow repeat reservations."
    ),
    "uq_loans_active_copy": "This copy is already on an active loan.",
    "uq_reservations_pending": "This member already has a pending reservation for this book.",
    "users_email_key": "A user with this email already exists.",
    "members_email_key": "A member with this email already exists.",
    "members_enrollment_no_key": "A member with this enrollment number already exists.",
    "books_isbn_key": "A book with this ISBN already exists.",
    "book_copies_accession_no_key": "A copy with this accession number already exists.",
    "categories_category_name_key": "A category with this name already exists.",
    "publishers_publisher_name_key": "A publisher with this name already exists.",
    "departments_department_name_key": "A department with this name already exists.",
    "academic_courses_course_code_key": "A course with this code already exists.",
    "roles_role_name_key": "A role with this name already exists.",
}
