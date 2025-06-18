# Examify Django Backend - Phase 1 Summary

This document summarizes the features implemented in Phase 1 of the Examify Django backend.

## 1. Overview of Implemented Features

*   **User Authentication & Profile Management:**
    *   User registration (signup) with email, username, password.
    *   Creation of an associated UserProfile (semester, region, department).
    *   User login and logout (token-based authentication using Django REST Framework's Authtoken).
    *   Endpoint to fetch and update current user's details and profile (`/auth/users/me/`).
*   **Course Management:**
    *   Basic `Course` model (name, department).
    *   `UserCourse` model to link users to courses they are enrolled in (though API for managing this link directly by users is not yet implemented in Phase 1, can be managed via Django Admin).
*   **Study Material Management:**
    *   Authenticated users can upload study materials (files like PDFs, images, etc.) with title, description, and associated course.
    *   Uploaded files are stored in the `/media/study_materials/` directory.
    *   `uploaded_by` field is automatically set to the logged-in user.
    *   `status` of new materials defaults to 'pending'.
*   **Content Review System:**
    *   Admin users can review uploaded study materials.
    *   Dedicated API endpoint (`/api/core/studymaterials/{id}/review/`) for admins to 'approve' or 'reject' materials.
    *   Django Admin interface also allows for management and review of materials.
    *   Users can only view their own pending/rejected materials or globally approved materials. Admins can view all.
*   **Basic Recommendation System:**
    *   API endpoint (`/api/core/recommendations/`) that suggests 'approved' study materials to authenticated users.
    *   Recommendations are based on the user's enrolled courses and their department.
*   **API Documentation:**
    *   Swagger UI available at `/swagger/`.
    *   ReDoc UI available at `/redoc/`.
    *   Generated using `drf-yasg` with detailed docstrings in views and serializers.
*   **Unit Tests:**
    *   A foundational suite of unit and integration tests covering user authentication, profile updates, material uploads, and the review process.

## 2. Key Algorithms and Logic

*   **User Profile Handling (Djoser & Custom Serializers):**
    *   `UserCreateSerializer` extends Djoser's default to create a `UserProfile` instance alongside the `User` instance during registration.
    *   `UserSerializer` extends Djoser's default to include `UserProfile` data when fetching user details and allows updating profile fields via the `/auth/users/me/` endpoint.
*   **Study Material Access Control (`StudyMaterialViewSet`):**
    *   `get_queryset()`: Filters materials based on user role (admin vs. regular user) and material status. Regular users see their own non-approved items + all approved items. Admins see everything.
    *   `perform_create()`: Automatically assigns `request.user` to `uploaded_by`.
    *   `review` action: Custom action restricted to admins for changing material status.
    *   Permissions (`IsAdminOrOwner`): Ensures users can only modify/delete their own materials, while admins have full control (status changes are restricted to the `review` action).
*   **Recommendation Logic (`RecommendedMaterialsView`):**
    *   Retrieves the user's `UserProfile` and enrolled `UserCourse`s.
    *   Constructs a `Q` object to filter approved `StudyMaterial`s:
        1.  Primary filter: Materials linked to the user's enrolled courses.
        2.  Secondary filter: Materials linked to any course within the user's department.
    *   If no specific profile criteria lead to recommendations, a fallback (e.g., materials from user's department, or latest approved) is attempted.
    *   Results are distinct and ordered by upload date.

## 3. High-Level System Flowchart

```mermaid
graph TD
    A[User Client] -->|Signup / Login| B(Djoser Auth Endpoints);
    B --> C{User DB};
    B --> D[Auth Token];
    A -->|Authenticated Requests w/ Token| E{API Endpoints};

    subgraph "User Profile"
        E1[/auth/users/me/] --> F[User & UserProfile Data];
    end

    subgraph "Study Materials"
        E2[/api/core/studymaterials/];
        E2 -- Upload (POST) --> G[Pending Material];
        G --> C;
        E2 -- List (GET) --> H[Filtered Materials List];
        H --> C;
    end

    subgraph "Admin Review"
        I[Admin Client] --> J{Django Admin / Review API};
        J -- Approve/Reject --> K[Material Status Update];
        K --> C;
    end

    subgraph "Recommendations"
        E3[/api/core/recommendations/] --> L[Filtered Approved Materials];
        L --> C;
    end

    M[Swagger/ReDoc UI] <--> N[drf-yasg];
    E --> N;
```
*(Note: This is a simplified text-based flowchart. A proper diagramming tool would be better for visual representation.)*

## 4. Potential GitHub Issues for Future Work (Phase 1 Scope)

*   **User Profile & Course Enrollment:**
    *   `#issue-1`: Implement API endpoints for users to list and manage their course enrollments (`UserCourse`).
    *   `#issue-2`: Allow users to select their department/courses from predefined lists during signup/profile update.
*   **Study Materials & Search:**
    *   `#issue-3`: Add semester/region fields to `Course` or `StudyMaterial` for more granular recommendations and filtering.
    *   `#issue-4`: Implement full-text search functionality for study materials.
    *   `#issue-5`: Add support for tagging study materials with keywords.
*   **Recommendations:**
    *   `#issue-6`: Enhance recommendation engine (e.g., collaborative filtering, content-based similarity beyond current filters).
    *   `#issue-7`: Allow users to rate study materials and factor ratings into recommendations.
*   **Content Management:**
    *   `#issue-8`: Implement versioning for study materials.
    *   `#issue-9`: Add notifications to users when their uploaded material is reviewed (approved/rejected).
*   **Testing:**
    *   `#issue-10`: Complete unit tests for the recommendation system.
    *   `#issue-11`: Add tests for more edge cases in `StudyMaterialViewSet` access permissions.
*   **AI Integration (Beyond Phase 1):**
    *   `#issue-12`: Integrate NLP for analyzing uploaded materials (as per project doc).
    *   `#issue-13`: Develop AI Tutor endpoint using a chosen AI model (Gemini, Grok, OpenAI).
    *   `#issue-14`: Implement OCR for image-based assistance.
*   **Deployment & DevOps:**
    *   `#issue-15`: Configure production settings (e.g., database, static files, media storage with cloud services).
    *   `#issue-16`: Set up CI/CD pipeline.

## 5. Instructions to Run

1.  Ensure Python and Pip are installed.
2.  Clone the repository.
3.  Create a virtual environment: `python -m venv venv` and activate it.
4.  Install dependencies: `pip install -r requirements.txt` (A `requirements.txt` file should be generated based on installed packages like Django, DRF, Djoser, drf-yasg, psycopg2-binary if using PostgreSQL, etc.).
5.  Run database migrations: `python manage.py makemigrations` and `python manage.py migrate`.
6.  Create a superuser (for admin access): `python manage.py createsuperuser`.
7.  Run the development server: `python manage.py runserver`.
8.  Access the API at `http://127.0.0.1:8000/`.
    *   Swagger docs: `http://127.0.0.1:8000/swagger/`
    *   ReDoc docs: `http://127.0.0.1:8000/redoc/`
    *   Admin panel: `http://127.0.0.1:8000/admin/`

*(A `requirements.txt` file would need to be generated separately by running `pip freeze > requirements.txt` in the virtual environment after all packages are installed.)*
