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
    *   Uploaded materials are directly available based on user roles and relevance (own, course, department).
*   **Basic Recommendation System:**
    *   API endpoint (`/api/core/recommendations/`) that suggests study materials to authenticated users.
    *   Recommendations are based on the user's enrolled courses and their department, drawn from all available materials.
*   **API Documentation:**
    *   Swagger UI available at `/swagger/`.
    *   ReDoc UI available at `/redoc/`.
    *   Generated using `drf-yasg` with detailed docstrings in views and serializers.
*   **Unit Tests:**
    *   A foundational suite of unit and integration tests covering user authentication, profile updates, material uploads, and the review process.
    *   **Mock Exam System:**
        *   Users can list available mock exams.
        *   Users can retrieve detailed information for a specific mock exam, including its questions.
        *   Users can start a timed mock exam attempt.
        *   Users can submit answers to an attempt.
        *   Multiple-choice questions (MCQs) are auto-graded upon submission.
        *   Short answer and essay questions receive AI-generated feedback and scores (using the RAG pipeline for context if questions are linked to `DocumentChunk`).
        *   Mock exams and questions are managed by administrators via the Django Admin interface.
    *   **Progress Tracking:**
        *   User profiles now track:
            *   Number of mock exams completed.
            *   Average score across completed mock exams.
            *   Number of study materials uploaded.
        *   These statistics are automatically updated via signals when relevant actions occur (e.g., exam completion, material upload).
        *   Progress data is available as part of the user's profile information via the `/auth/users/me/` API endpoint.
    *   **Gamification - Points System:**
        *   Users earn points for contributions:
            *   Uploading study materials.
            *   Successfully completing mock exams.
        *   An `ActivityLog` records these point-earning activities.
        *   `UserProfile` stores the user's `total_points`.
        *   Points and activity logs are managed by the system and viewable in the Django Admin. Total points are part of the user's profile API response.
    *   **Study Groups (Foundation):**
        *   Basic models (`StudyGroup`, `StudyGroupMembership`) have been implemented to support future study group functionality.
        *   Groups and memberships can be managed by administrators via the Django Admin. User-facing APIs for group interaction are deferred.

## 2. Key Algorithms and Logic

*   **User Profile Handling (Djoser & Custom Serializers):**
    *   `UserCreateSerializer` extends Djoser's default to create a `UserProfile` instance alongside the `User` instance during registration.
    *   `UserSerializer` extends Djoser's default to include `UserProfile` data when fetching user details and allows updating profile fields via the `/auth/users/me/` endpoint.
*   **Study Material Access Control (`StudyMaterialViewSet`):**
    *   `get_queryset()`: Filters materials based on user role. Admins see all materials. Regular users see their own uploaded materials, materials relevant to their enrolled courses, and materials relevant to courses in their department.
    *   `perform_create()`: Automatically assigns `request.user` to `uploaded_by`.
    *   Permissions (`IsAdminOrOwner`): Ensures users can only modify/delete their own materials, while admins have full control.
*   **Recommendation Logic (`RecommendedMaterialsView`):**
    *   Retrieves the user's `UserProfile` and enrolled `UserCourse`s.
    *   Constructs a `Q` object to filter all available `StudyMaterial`s:
        1.  Primary filter: Materials linked to the user's enrolled courses.
        2.  Secondary filter: Materials linked to any course within the user's department.
    *   If no specific profile criteria lead to recommendations, a fallback (e.g., materials from user's department) is attempted, or an empty list is returned.
    *   Results are distinct and ordered by upload date.
*   **Mock Exam Submission & Grading (`MockExamAttemptViewSet::submit_answers`):**
    *   Handles submission of answers for various question types.
    *   Auto-grades MCQs based on predefined correct answers in `MockExamQuestion.options`.
    *   Integrates with `ai_processing.grade_answer_with_ai` for short answer/essay questions:
        *   Sends question, user's answer, question points, and optional context (from linked `DocumentChunk`) to the AI.
        *   Parses AI response for feedback and awarded points.
    *   Stores all answers, feedback, and points in `MockExamAnswer` instances (using `bulk_create`).
    *   Calculates and updates the total score for the `MockExamAttempt`.
*   **Automated Progress Updates (Signals in `core/signals.py`):**
    *   `post_save` signal on `MockExamAttempt`: When an attempt status is 'completed' with a score, updates `UserProfile.mock_exams_completed` and recalculates `UserProfile.average_mock_exam_score`. Also triggers point awarding.
    *   `post_save` signal on `StudyMaterial`: When a new material is `created`, updates `UserProfile.study_materials_uploaded_count`. Also triggers point awarding.
*   **Points Awarding and Activity Logging (Signals):**
    *   Integrated into the above signals (`MockExamAttempt`, `StudyMaterial`).
    *   Creates `ActivityLog` entries detailing the action and points awarded.
    *   Atomically updates `UserProfile.total_points` using `F()` expressions.
    *   Includes logic to prevent awarding points multiple times for the same event (e.g., for a single mock exam completion).

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
        E2 -- Upload (POST) --> G[Uploaded Material];
        G --> C;
        E2 -- List (GET) --> H[Filtered Materials List];
        H --> C;
    end

    subgraph "Recommendations"
        E3[/api/core/recommendations/] --> L[Filtered Materials];
        L --> C;
    end

    subgraph "Mock Exams"
        A -->|List/Retrieve Exams| E4[/api/core/mockexams/];
        A -->|Start Attempt| E5[/api/core/mockexams/{id}/start-attempt/];
        E5 --> MEA[MockExamAttempt DB Update];
        MEA --> C;
        A -->|Submit Answers| E6[/api/core/mockexam-attempts/{id}/submit/];
        E6 --> AI_Grade[AI Grading Service];
        E6 --> ANS_DB[MockExamAnswer DB Update];
        ANS_DB --> C;
        E6 --> Prog_Sig[Signals for Progress/Points];
        Prog_Sig --> C; # Updates UserProfile
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
    *   `#issue-7`: Allow users to rate study materials and factor ratings into recommendations (consider how 'quality' is determined without admin approval).
*   **Content Management & Quality:**
    *   `#issue-8`: Implement versioning for study materials.
    *   `#issue-9`: Develop a system for community feedback or flagging of materials to help identify quality content (replaces admin review).
*   **Testing:**
    *   `#issue-10`: Complete unit tests for the recommendation system (ensure it handles the new "all materials" scope correctly).
    *   `#issue-11`: Add tests for more edge cases in `StudyMaterialViewSet` access permissions.
    *   `#issue-12`: Add comprehensive tests for Mock Exam APIs, including AI grading mocks.
    *   `#issue-13`: Add tests for signal handlers related to progress and points.
*   **Mock Exams (Phase 3 Enhancements):**
    *   `#issue-P3-M01`: User ability to create/share mock exams.
    *   `#issue-P3-M02`: More question types (e.g., fill-in-the-blanks, matching).
    *   `#issue-P3-M03`: Timed exam interface with countdown on frontend.
    *   `#issue-P3-M04`: Review mode for completed attempts (show questions, user answers, correct answers, feedback).
    *   `#issue-P3-M05`: Question bank for reusing questions across exams.
    *   `#issue-P3-M06`: Difficulty levels for questions/exams.
*   **Progress Tracking & Gamification (Phase 3 Enhancements):**
    *   `#issue-P3-P01`: Detailed progress dashboards/visualizations for users.
    *   `#issue-P3-P02`: More granular progress tracking (e.g., by topic/skill based on question tags).
    *   `#issue-P3-P03`: Badges and achievements based on points or specific accomplishments.
    *   `#issue-P3-P04`: Leaderboards API with different scopes (overall, weekly, by course).
*   **Study Groups (Phase 3 Enhancements):**
    *   `#issue-P3-S01`: API endpoints for users to create, list, join, and leave study groups.
    *   `#issue-P3-S02`: Functionality for group discussions (e.g., message threads within groups).
    *   `#issue-P3-S03`: Resource sharing within study groups.
    *   `#issue-P3-S04`: Group-specific mock exams or challenges.
*   **AI Integration (Beyond Phase 1/2):**
    *   `#issue-AI-01`: Integrate NLP for analyzing uploaded materials (as per project doc - was #issue-12).
    *   `#issue-AI-02`: Develop AI Tutor endpoint using a chosen AI model (Gemini, Grok, OpenAI - was #issue-13, now partially done with RAG).
    *   `#issue-AI-03`: Implement OCR for image-based assistance (was #issue-14).
    *   `#issue-AI-04`: AI-powered question generation from study materials.
*   **Deployment & DevOps:**
    *   `#issue-DO-01`: Configure production settings (e.g., database, static files, media storage with cloud services - was #issue-15).
    *   `#issue-DO-02`: Set up CI/CD pipeline (was #issue-16).

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
