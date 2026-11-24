from app.models import AcademicCourse, Author, Category, Department, Publisher
from app.routers.crud import build_crud_router
from app.schemas.catalog import (
    AuthorCreate,
    AuthorRead,
    AuthorUpdate,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PublisherCreate,
    PublisherRead,
    PublisherUpdate,
)
from app.schemas.people import (
    CourseCreate,
    CourseRead,
    CourseUpdate,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
)

categories = build_crud_router(
    model=Category,
    name="category",
    tag="Categories",
    prefix="/categories",
    read_schema=CategoryRead,
    create_schema=CategoryCreate,
    update_schema=CategoryUpdate,
    search_fields=[Category.category_name, Category.description],
    order_by=Category.category_name,
)

publishers = build_crud_router(
    model=Publisher,
    name="publisher",
    tag="Publishers",
    prefix="/publishers",
    read_schema=PublisherRead,
    create_schema=PublisherCreate,
    update_schema=PublisherUpdate,
    search_fields=[Publisher.publisher_name, Publisher.city],
    order_by=Publisher.publisher_name,
)

authors = build_crud_router(
    model=Author,
    name="author",
    tag="Authors",
    prefix="/authors",
    read_schema=AuthorRead,
    create_schema=AuthorCreate,
    update_schema=AuthorUpdate,
    search_fields=[Author.full_name, Author.nationality],
    order_by=Author.full_name,
)

departments = build_crud_router(
    model=Department,
    name="department",
    tag="Departments",
    prefix="/departments",
    read_schema=DepartmentRead,
    create_schema=DepartmentCreate,
    update_schema=DepartmentUpdate,
    search_fields=[Department.department_name, Department.hod_name],
    order_by=Department.department_name,
)

courses = build_crud_router(
    model=AcademicCourse,
    name="course",
    tag="Courses",
    prefix="/courses",
    read_schema=CourseRead,
    create_schema=CourseCreate,
    update_schema=CourseUpdate,
    search_fields=[AcademicCourse.course_name, AcademicCourse.course_code],
    order_by=AcademicCourse.course_name,
    filters={"department_id": AcademicCourse.department_id},
)

routers = [categories, publishers, authors, departments, courses]
