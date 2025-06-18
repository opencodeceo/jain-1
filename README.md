# Examify - AI-Powered Exam Preparation App

## 1. Overview

Examify is an AI-driven platform designed to assist students in their exam preparation. It leverages artificial intelligence, a growing library of past exam questions and study materials, and interactive features to offer a personalized and dynamic study experience. Key functionalities include user-contributed content, AI-powered tutoring, mock exams with AI-assisted grading, progress tracking, and gamification to enhance user engagement.

This backend is built using Django and Django REST Framework, providing a robust API for frontend applications.

## 2. Features Implemented (Phases 1-4)

### Phase 1: Foundational Backend & Content Management (RAG-focused)

*   **User Authentication & Profile Management:**
    *   Secure user registration (signup), login, and logout (token-based).
    *   User profiles storing academic details (semester, region, department) and progress metrics.
    *   Endpoint to fetch/update current user details: `/auth/users/me/`.
*   **Course Management:**
    *   `Course` model (name, department) to categorize materials and exams.
    *   `UserCourse` model to link users to their enrolled courses.
*   **Study Material Management (Direct to RAG):**
    *   Authenticated users can upload study materials (PDFs, DOCX files).
    *   Uploaded materials are processed directly for the RAG system (no admin review queue).
    *   Files stored in `/media/study_materials/`.
*   **Basic Recommendation System (Content Filtering):**
    *   API endpoint (`/api/core/recommendations/`) suggests study materials based on user's enrolled courses and department.

### Phase 2: Document Processing & RAG Implementation

*   **Document Processing Pipeline (`core.ai_processing`):**
    *   Text extraction from PDF (`PyMuPDF`) and DOCX (`python-docx`) files.
    *   Text chunking to prepare content for embedding.
    *   `DocumentChunk` Django model stores text chunks, their vector IDs from the vector DB, and links to original `StudyMaterial`.
*   **Switchable Embedding Models:**
    *   Supports generating vector embeddings using:
        *   Google Gemini API (e.g., `embedding-001`).
        *   OpenAI API (e.g., `text-embedding-ada-002`).
    *   The preferred provider is configurable via Django settings.
*   **Vector Database Integration:**
    *   Utilizes **Google Cloud Vertex AI Vector Search** to store and query document embeddings for efficient similarity search.
*   **RAG Query Service & AI Tutor API:**
    *   Core RAG logic in `perform_rag_query` function:
        1.  Generates query embedding.
        2.  Queries Vertex AI Vector Search for relevant document chunks.
        3.  Retrieves chunk text from `DocumentChunk` model.
        4.  Constructs a prompt with query and context.
        5.  Synthesizes an answer using a selected LLM.
    *   Switchable LLM Providers for Synthesis:
        *   Google Gemini Pro API.
        *   OpenAI GPT models (e.g., `gpt-3.5-turbo`).
    *   AI Tutor API endpoint: `/api/core/ai/query/` (POST) for users to ask questions and receive AI-generated answers based on processed materials.

### Phase 3: User Engagement Features

*   **Mock Exam System:**
    *   Models: `MockExam`, `MockExamQuestion`, `MockExamAttempt`, `MockExamAnswer`.
    *   `MockExamQuestion` can optionally link to a `DocumentChunk` for contextual AI grading.
    *   Admin interface for creating and managing mock exams and questions.
    *   APIs for users:
        *   List/retrieve mock exams: `/api/core/mockexams/`.
        *   Start an attempt: `/api/core/mockexams/{id}/start-attempt/`.
        *   Submit answers: `/api/core/mockexam-attempts/{attempt_id}/submit/`.
    *   **Grading:**
        *   Multiple-choice questions (MCQs) are auto-graded.
        *   Short answer/essay questions receive AI-generated feedback and scores via the `grade_answer_with_ai` function, which uses the configured LLM and can leverage context from linked `DocumentChunk`s.
*   **Progress Tracking:**
    *   `UserProfile` extended to track:
        *   `mock_exams_completed` (count).
        *   `average_mock_exam_score` (float).
        *   `study_materials_uploaded_count` (count).
    *   Statistics automatically updated via Django signals upon exam completion or material upload.
    *   Progress data included in the user's profile API response (`/auth/users/me/`).
*   **Gamification - Points System:**
    *   `ActivityLog` model records point-earning activities (e.g., uploading material, completing mock exam).
    *   `UserProfile.total_points` stores accumulated points.
    *   Points awarded automatically via Django signals, with logic to prevent duplicate awards.
    *   Total points included in the user's profile API response.
*   **Study Groups (Foundation):**
    *   Basic models (`StudyGroup`, `StudyGroupMembership`) implemented.
    *   Admin interface for managing groups and memberships. (User-facing APIs deferred).

### Phase 4: AI Model Integration & Continuous Learning

*   **Task-Specific Routing for LLMs:**
    *   The core LLM interaction function (`get_llm_response`) was enhanced to support `task_type` specific behaviors (e.g., different system messages for OpenAI).
    *   New AI service functions added for:
        *   **Summarization:** (`summarize_text_with_llm`) Exposed via `/api/core/studymaterials/{id}/summarize/`.
        *   **Complex Explanation:** (`explain_complex_problem_with_llm`) Provides detailed step-by-step explanations. (Internal logic).
        *   **Question Generation:** (`generate_questions_from_text_with_llm`) Creates exam-style questions from text in structured JSON. (Internal logic).
*   **User Feedback Mechanism:**
    *   `AIFeedback` model allows users to submit ratings, comments, and context (linked `DocumentChunk`s) for AI interactions via a `session_id`.
    *   The RAG API (`/api/core/ai/query/`) now returns a `session_id`.
    *   A new API endpoint (`/api/core/ai/feedback/`) allows users to submit their feedback.
*   **Content Highlighting & Active Learning (Basic):**
    *   `DocumentChunk` model now includes a `review_flags_count`.
    *   This count is automatically incremented by a Django signal if linked `AIFeedback` indicates a low rating or AI low confidence, helping identify content for review.
*   **OCR for Image-Based Assistance:**
    *   `ImageQuery` model stores uploaded images and their extracted text.
    *   Uses Google Cloud Vision API for text extraction from images.
    *   New API endpoint (`/api/core/ai/ocr-query/`) for users to upload images and receive OCR results.

## 3. Technology Stack

*   **Backend:** Django, Django REST Framework
*   **Database:** SQLite (default for development), PostgreSQL recommended for production.
*   **AI/ML:**
    *   **Document Parsing:** PyMuPDF, python-docx
    *   **Text Splitting:** Custom recursive character-based splitting (in `core.ai_processing`).
    *   **Embedding Models (Switchable):** Google Gemini API, OpenAI API.
    *   **Large Language Models (LLMs for RAG & Grading - Switchable):** Google Gemini Pro API, OpenAI GPT API.
    *   **OCR:** Google Cloud Vision API.
    *   **Vector Store:** Google Cloud Vertex AI Vector Search.
*   **API Documentation:** `drf-yasg` (generating Swagger UI at `/swagger/` and ReDoc UI at `/redoc/`).
*   **Task Queue (Recommended for Production):** Celery (for asynchronous document processing - not yet implemented).

## 4. Setup and Installation Instructions

1.  **Prerequisites:**
    *   Python (3.9+ recommended)
    *   Pip (Python package installer)
    *   Git
    *   (Optional, for production) PostgreSQL server.

2.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

3.  **Create and Activate Virtual Environment:**
    ```bash
    python -m venv venv
    # On Windows
    # venv\Scripts\activate
    # On macOS/Linux
    # source venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configuration (`examify/examify/settings.py`):**
    *   **Database:** Defaults to SQLite. For PostgreSQL, configure `DATABASES` settings.
    *   **AI Service API Keys & Settings:**
        *   `GOOGLE_API_KEY`: Your Google API key with Gemini API enabled.
        *   `GOOGLE_CLOUD_PROJECT`: Your Google Cloud Project ID.
        *   `GOOGLE_CLOUD_REGION`: Your Google Cloud region (e.g., `us-central1`).
        *   `VERTEX_AI_INDEX_ID`: Full resource name of your Vertex AI Vector Search Index.
        *   `VERTEX_AI_INDEX_ENDPOINT_ID`: Full resource name of your Vertex AI Index Endpoint.
        *   `OPENAI_API_KEY`: Your OpenAI API key.
        *   `PREFERRED_EMBEDDING_PROVIDER`: `'google'` or `'openai'`.
        *   `PREFERRED_LLM_PROVIDER`: `'google'` or `'openai'`.
    *   **Important for Production:** Do NOT hardcode sensitive keys in `settings.py`. Use environment variables (e.g., using `python-decouple` or `django-environ`).
    *   Ensure your Google Cloud project has Vertex AI and Gemini APIs enabled.
    *   Ensure your Vertex AI Vector Search Index is configured with the correct embedding dimension matching your chosen `PREFERRED_EMBEDDING_PROVIDER`. (Gemini `embedding-001` is 768, OpenAI `text-embedding-ada-002` is 1536. A single index cannot support both simultaneously unless a workaround is implemented).

6.  **Apply Database Migrations:**
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

7.  **Create a Superuser (for Admin Access):**
    ```bash
    python manage.py createsuperuser
    ```

8.  **Run the Development Server:**
    ```bash
    python manage.py runserver
    ```
    The application will typically be available at `http://127.0.0.1:8000/`.

## 5. API Endpoints Overview

The primary API endpoints are provided under the `/api/core/` namespace. Full interactive documentation is available via:

*   **Swagger UI:** `http://127.0.0.1:8000/swagger/`
*   **ReDoc UI:** `http://127.0.0.1:8000/redoc/`

Key functional endpoints include:

*   **Authentication (Djoser):** `/auth/users/`, `/auth/token/login/`, `/auth/token/logout/`, `/auth/users/me/`
*   **Study Materials:** `/api/core/studymaterials/` (List, Create, Retrieve, Update, Delete)
*   **Recommendations:** `/api/core/recommendations/` (GET study material recommendations)
*   **AI Tutor Query:** `/api/core/ai/query/` (POST user questions for RAG-based answers)
*   **Mock Exams:**
    *   `/api/core/mockexams/` (List/Retrieve exams)
    *   `/api/core/mockexams/{id}/start-attempt/` (POST to start an attempt)
*   **Mock Exam Attempts:**
    *   `/api/core/mockexam-attempts/{id}/` (Retrieve specific attempt - for owner)
    *   `/api/core/mockexam-attempts/{id}/submit/` (POST answers to an attempt)
*   **Content Summarization:** `/api/core/studymaterials/{pk}/summarize/` (POST)
*   **AI Feedback Submission:** `/api/core/ai/feedback/` (POST)
*   **Image OCR Query:** `/api/core/ai/ocr-query/` (POST)

## 6. Project Structure

*   `examify/` (Django Project Root)
    *   `examify/settings.py`: Main project settings.
    *   `examify/urls.py`: Root URL configurations.
*   `core/` (Main Django App)
    *   `models.py`: Database models.
    *   `views.py`: API view logic.
    *   `serializers.py`: Data serialization for API.
    *   `urls.py`: App-specific URL configurations.
    *   `admin.py`: Django Admin interface customization.
    *   `ai_processing.py`: Core logic for document processing, embedding, RAG, and AI grading.
    *   `signals.py`: Signal handlers for automated actions (e.g., progress updates, content flagging).
    *   `tests.py`, `tests_ai.py` (if exists), `tests_phase3.py`, `tests_phase4.py`: Unit and integration tests.
*   `media/`: (Created locally) Stores uploaded study materials and images for OCR.
*   `README.md`: This file.
*   `requirements.txt`: Project dependencies.
*   `manage.py`: Django's command-line utility.

## 7. How to Run Tests

To run all tests for the `core` app:
```bash
python manage.py test core
```
To run specific test files:
```bash
python manage.py test core.tests
python manage.py test core.tests_ai
python manage.py test core.tests_phase3
```

## 8. Future Work (Phase 4 & Beyond)

*   **Advanced AI Model Integration (Phase 4):**
    *   Deeper integration of specialized capabilities of Gemini, Grok (if API available), and advanced OpenAI models.
    *   Implementing "Hybrid AI Approach" as described in original project documentation.
    *   Full operationalization and refinement of continuous learning loops using `AIFeedback` and `DocumentChunk.review_flags_count`.
*   **Enhanced User Engagement:**
    *   Full implementation of Study Groups (user creation, joining, discussions, resource sharing).
    *   Advanced gamification (badges, leaderboards).
    *   Detailed progress dashboards.
    *   User interfaces for AI-generated questions and explanations.
*   **Operational Excellence:**
    *   Production deployment (Docker, cloud platforms like AWS/Google Cloud).
    *   CI/CD pipeline.
    *   Robust asynchronous task processing for all AI operations (OCR, summarization, RAG indexing, AI grading) using Celery.
    *   Scalability and performance optimizations for AI services and database interactions.
    *   Comprehensive monitoring, alerting, and cost management for AI services.
*   **Advanced OCR and Document Understanding:**
    *   Beyond basic text extraction, leverage more advanced OCR features (e.g., layout preservation, table extraction, diagram understanding) if supported by Vision API or other tools.
    *   Integrate OCR results more deeply into the RAG context.
*   **Multilingual Support.**
*   **Admin Tools:**
    *   Admin interface for reviewing flagged `DocumentChunk`s.
    *   Tools for triggering re-processing or re-indexing of specific materials.

---

This README provides a snapshot of the Examify backend project. For detailed API specifications, please refer to the Swagger/ReDoc documentation.
