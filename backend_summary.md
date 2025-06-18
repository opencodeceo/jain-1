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
    *   Test suites (`tests_phase3.py`) added for mock exam system, progress tracking, and gamification signals.
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
*   **Phase 4: AI Model Integration & Continuous Learning**
    *   **Task-Specific Routing for LLMs:**
        *   Refined `get_llm_response` in `core.ai_processing` to accept a `task_type` parameter.
        *   For OpenAI, this allows dynamic adjustment of the system message based on the task (e.g., 'summarize', 'explain_complex', 'generate_questions', 'rag_query', 'grade_answer').
        *   New AI service functions added:
            *   `summarize_text_with_llm`: Generates concise summaries of provided text. Exposed via API at `/api/core/studymaterials/{id}/summarize/`.
            *   `explain_complex_problem_with_llm`: Provides step-by-step explanations for user queries, optionally using context. (Internal logic, not yet a direct public API).
            *   `generate_questions_from_text_with_llm`: Generates exam-style questions (MCQ, short answer) from text content in a structured JSON format. (Internal logic, not yet a direct public API).
    *   **User Feedback Mechanism:**
        *   `AIFeedback` model implemented to store user feedback on AI interactions.
        *   Includes fields for `session_id` (linking to a specific RAG query), `query_text`, `ai_response_text`, `rating` (1-5), `feedback_comment`, `interaction_type`, and linked `context_chunks`.
        *   API endpoint `/api/core/ai/feedback/` (POST) allows authenticated users to submit feedback.
        *   `AITutorQueryView` response now includes a `session_id` to facilitate feedback submission.
    *   **Content Highlighting & Active Learning (Basic):**
        *   `DocumentChunk` model updated with `review_flags_count` (PositiveIntegerField).
        *   A Django signal on `AIFeedback` creation increments `review_flags_count` for associated `DocumentChunk`s if the feedback indicates a low rating (<=2) or if `AIFeedback.ai_low_confidence` is true. This helps identify chunks that might need review.
    *   **OCR for Image-Based Assistance:**
        *   `ImageQuery` model created to store uploaded images, their OCR processing status, and extracted text.
        *   Utilizes Google Cloud Vision API (via `extract_text_from_image_gcp` in `core.ai_processing`) for text extraction.
        *   API endpoint `/api/core/ai/ocr-query/` (POST) allows users to upload images and receive extracted text. OCR processing is currently synchronous.

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
*   **Task-Specific Prompt Engineering in `get_llm_response`:**
    *   The `get_llm_response` function in `core.ai_processing` now accepts a `task_type`.
    *   For OpenAI, this `task_type` dynamically adjusts the system message sent to the LLM (e.g., "You are an AI assistant skilled in summarizing texts concisely." for summarization). This allows for more tailored and effective LLM interactions for different AI-powered features.
*   **AI-Powered Question Generation Logic (`generate_questions_from_text_with_llm`):**
    *   Constructs a detailed prompt instructing the LLM to generate a specified number of questions of given types (MCQ, short answer) from a provided text.
    *   Requests output in a structured JSON format, including question text, type, options (with correct answer for MCQs), and optional difficulty.
    *   Includes logic to parse and validate the LLM's JSON response, cleaning common markdown artifacts and ensuring basic structure.
*   **OCR Text Extraction Process (`extract_text_from_image_gcp` and `OCRQueryView`):**
    *   User uploads an image via the `/api/core/ai/ocr-query/` endpoint.
    *   The `OCRQueryView` saves an `ImageQuery` instance.
    *   Image content is read as bytes and passed to `extract_text_from_image_gcp`.
    *   This function uses the `google-cloud-vision` client library to call the Vision API's document text detection feature.
    *   The extracted text (or error status) is saved back to the `ImageQuery` instance.
*   **Feedback-Driven Content Flagging (Signals):**
    *   A `post_save` signal on the `AIFeedback` model (`update_document_chunk_flags_on_feedback`).
    *   If new feedback has a low rating (e.g., <=2) or the `ai_low_confidence` flag is set by the user/system:
        *   The signal increments the `review_flags_count` on all `DocumentChunk` instances linked to that feedback via `AIFeedback.context_chunks`.
        *   This provides a basic mechanism for identifying potentially problematic or low-quality document chunks based on user feedback or AI self-assessment.

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
        E6 --> AI_Grade[AI Grading Service (core.ai_processing)];
        E6 --> ANS_DB[MockExamAnswer DB Update];
        ANS_DB --> C;
        E6 --> Prog_Sig[Signals for Progress/Points];
        Prog_Sig --> C;
    end

    subgraph "AI Tutor & Services"
        A -->|RAG Query| E_RAG[/api/core/ai/query/];
        E_RAG --> RAG_Proc[RAG Process (core.ai_processing)];
        RAG_Proc --> VDB[Vertex AI Vector Search];
        RAG_Proc --> LLM_Synth[LLM for Synthesis];
        RAG_Proc --> C; # Fetch Document Chunks
        A -->|Image OCR| E_OCR[/api/core/ai/ocr-query/];
        E_OCR --> OCR_Proc[Google Cloud Vision API];
        E_OCR --> C; # Save ImageQuery with text
        A -->|Submit Feedback| E_Feedback[/api/core/ai/feedback/];
        E_Feedback --> Feedback_DB[AIFeedback DB Update];
        Feedback_DB --> C;
        Feedback_DB --> Sig_Flag[Signal to flag DocumentChunks];
        Sig_Flag --> C;
        SM[StudyMaterial] -->|Summarize Action| E_Summarize[/api/core/studymaterials/{id}/summarize/];
        E_Summarize --> LLM_Summ[LLM for Summarization];
    end

    M[Swagger/ReDoc UI] <--> N[drf-yasg];
    E --> N;
    E4 --> N; E5 --> N; E6 --> N; E_RAG --> N; E_OCR --> N; E_Feedback --> N; E_Summarize --> N;
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
    *   `#issue-12`: Add comprehensive tests for Mock Exam APIs, including AI grading mocks (partially done in tests_phase3.py).
    *   `#issue-13`: Add tests for signal handlers related to progress and points (partially done in tests_phase3.py).
    *   `#issue-14`: Add tests for new Phase 4 AI services (Summarization, OCR, Feedback API, Task-Specific LLM routing - created as tests_phase4.py).
*   **Mock Exams (Further Enhancements):**
    *   `#issue-M01`: User ability to create/share mock exams (was #issue-P3-M01).
    *   `#issue-M02`: More question types (e.g., fill-in-the-blanks, matching) (was #issue-P3-M02).
    *   `#issue-M03`: Timed exam interface with countdown on frontend (was #issue-P3-M03).
    *   `#issue-M04`: Review mode for completed attempts (show questions, user answers, correct answers, feedback) (was #issue-P3-M04).
    *   `#issue-M05`: Question bank for reusing questions across exams (was #issue-P3-M05).
    *   `#issue-M06`: Difficulty levels for questions/exams (was #issue-P3-M06).
*   **Progress Tracking & Gamification (Further Enhancements):**
    *   `#issue-P01`: Detailed progress dashboards/visualizations for users (was #issue-P3-P01).
    *   `#issue-P02`: More granular progress tracking (e.g., by topic/skill based on question tags) (was #issue-P3-P02).
    *   `#issue-P03`: Badges and achievements based on points or specific accomplishments (was #issue-P3-P03).
    *   `#issue-P04`: Leaderboards API with different scopes (overall, weekly, by course) (was #issue-P3-P04).
*   **Study Groups (Further Enhancements):**
    *   `#issue-S01`: API endpoints for users to create, list, join, and leave study groups (was #issue-P3-S01).
    *   `#issue-S02`: Functionality for group discussions (e.g., message threads within groups) (was #issue-P3-S02).
    *   `#issue-S03`: Resource sharing within study groups (was #issue-P3-S03).
    *   `#issue-S04`: Group-specific mock exams or challenges (was #issue-P3-S04).
*   **AI Integration & Continuous Learning (Phase 4 Enhancements & Beyond):**
    *   `#issue-AI-01`: Integrate NLP for analyzing uploaded materials (as per project doc).
    *   `#issue-AI-02`: Further refine AI Tutor RAG capabilities (was partially #issue-AI-02).
    *   `#issue-AI-03`: Full operationalization of OCR for image-based assistance and integration into RAG.
    *   `#issue-AI-04`: API endpoints for AI-powered question generation from study materials (using `generate_questions_from_text_with_llm`).
    *   `#issue-AI-05`: API endpoint for complex problem explanation (using `explain_complex_problem_with_llm`).
    *   `#issue-AI-06`: Admin interface for reviewing `DocumentChunk`s flagged by `review_flags_count`.
    *   `#issue-AI-07`: Mechanism to incorporate `AIFeedback` into model fine-tuning or prompt refinement (closing the loop).
    *   `#issue-AI-08`: Explore using AI confidence scores (if available from models) to populate `AIFeedback.ai_low_confidence` automatically.
*   **Deployment & DevOps:**
    *   `#issue-DO-01`: Configure production settings (e.g., database, static files, media storage with cloud services).
    *   `#issue-DO-02`: Set up CI/CD pipeline.

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
