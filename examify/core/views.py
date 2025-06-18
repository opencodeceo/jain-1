from rest_framework import generics, viewsets, permissions, parsers, status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import UserProfile, StudyMaterial, UserCourse, Course # Added UserCourse, Course
from .serializers import UserProfileSerializer, StudyMaterialSerializer
from .permissions import IsAdminUser, IsAdminOrOwner


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    Manages the profile (semester, region, department) for the currently authenticated user.
    Note: Djoser's /users/me/ endpoint is generally preferred for managing the current user's data,
    including their profile if the UserSerializer is set up for nested updates.
    This ViewSet might be more useful for admins to manage any profile or could be refactored.
    """
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated] # Should be more restrictive if it's for /users/me equivalent
    http_method_names = ['get', 'put', 'patch', 'head', 'options'] # Allow retrieve and update, disallow create and delete for existing profiles via this viewset

    def get_queryset(self):
        # Return only the profile of the requesting user
        return UserProfile.objects.filter(user=self.request.user)

    # For more fine-grained control if we only wanted retrieve/update,
    # we could inherit from generics.RetrieveUpdateAPIView and define get_object.
    # However, ModelViewSet with http_method_names and get_queryset filtering works.
    # get_object is implicitly handled by ModelViewSet for detail routes.
    # For a single object associated with the user (like a profile),
    # it's common to use a detail route or a custom action on the user viewset.
    # Here, we are treating it as a resource list of size 1 for the logged-in user.
    # If we wanted a singleton resource at /api/core/profile/, we might use RetrieveUpdateAPIView.
    # The current setup with router will give /api/core/profile/{user_pk_or_lookup_field}/
    # To make it behave more like a singleton for the current user, further customization
    # in urls.py and possibly the view would be needed, or use a simpler view like RetrieveUpdateAPIView
    # and a direct URL pattern instead of a router.

    # For simplicity and to align with the request for "retrieve and update actions",
    # limiting http_method_names is a straightforward approach with ModelViewSet.
    # The get_queryset ensures users can only see/edit their own profile.
    # Djoser's /users/me/ endpoint with the customized UserSerializer will also show profile data.
    # This UserProfileViewSet provides a dedicated endpoint for profile-specific updates if configured correctly.

    # No need to override perform_create as we don't allow 'post' (create for this view)
    # No need to override perform_update as default behavior is fine; serializer handles validation.
    # No need to override perform_destroy as we don't allow 'delete'.

class StudyMaterialViewSet(viewsets.ModelViewSet):
    """
    Handles CRUD operations for Study Materials.
    Uploaded materials are directly available based on visibility rules.
    File uploads should use multipart/form-data.
    """
    queryset = StudyMaterial.objects.all()
    serializer_class = StudyMaterialSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        - 'list', 'create': Authenticated users.
        - 'retrieve', 'update', 'partial_update', 'destroy': Admin or Owner.
        """
        if self.action in ['list', 'create']:
            self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminOrOwner]
        else:
            self.permission_classes = [permissions.IsAuthenticated] # Default for other actions
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        Allows authenticated users to upload new study materials.
        `uploaded_by` is set to the current user.
        """
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        """
        Allows the owner or an admin to update material details (e.g., title, description).
        """
        serializer.save()

    def get_queryset(self):
        """
        Lists study materials.
        - Admins see all materials.
        - Regular users see their own uploaded materials, materials for their enrolled courses,
          and materials from courses in their department.
        """
        user = self.request.user
        if user.is_staff: # Admins see all materials
            return StudyMaterial.objects.all().order_by('-upload_date')

        # For regular users:
        # 1. Their own uploaded materials
        own_materials = Q(uploaded_by=user)

        # Initialize Q objects for optional filters
        relevant_course_materials = Q()
        department_materials = Q()

        # 2. Materials relevant to their enrolled courses
        try:
            user_profile = user.userprofile
            user_courses_ids = list(UserCourse.objects.filter(user_profile=user_profile).values_list('course_id', flat=True))
            if user_courses_ids:
                relevant_course_materials = Q(course__id__in=user_courses_ids)
        except UserProfile.DoesNotExist:
            pass # No profile, so no course-based materials from enrollment

        # 3. Materials relevant to courses in their department
        try:
            # Ensure user_profile is available; it might have been fetched above or not.
            # This could be optimized by fetching user_profile once.
            user_profile = getattr(user, 'userprofile', None) or user.userprofile
            if user_profile and user_profile.department:
                department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
                if department_courses_ids:
                    department_materials = Q(course__id__in=department_courses_ids)
        except UserProfile.DoesNotExist:
            pass # No profile, so no department-based materials

        # Combine the conditions with OR
        combined_filters = own_materials | relevant_course_materials | department_materials

        # Ensure that if all Q objects are empty (e.g. new user with no profile data, no uploads)
        # it doesn't result in an empty filter call that might behave unexpectedly.
        # However, an empty Q object in a filter is typically a no-op, so it should be fine.
        # If combined_filters has no children, it means only own_materials could potentially be non-empty
        # or all are empty. If own_materials is also empty, filter will correctly return nothing.

        return StudyMaterial.objects.filter(combined_filters).distinct().order_by('-upload_date')

    @action(detail=True, methods=['post'], url_path='summarize', permission_classes=[permissions.IsAuthenticated])
    def summarize_material(self, request, pk=None):
        """
        Generates a summary for the text content of this study material using an AI model.

        This endpoint processes the entire material's text content. For very large materials,
        this operation can be resource-intensive and might take some time.
        Consider using this for materials of reasonable length or when asynchronous processing
        is implemented on the backend.

        **Response:**
        - `200 OK`: Summary successfully generated.
          ```json
          {
              "summary": "The AI-generated summary of the material."
          }
          ```
        - `400 Bad Request`: If the study material has no file or content cannot be extracted.
        - `404 Not Found`: If the study material does not exist.
        - `500 Internal Server Error`: If an AI service error or other unexpected error occurs.
        - `503 Service Unavailable`: If AI services are not configured by the administrator.
        """
        try:
            study_material = self.get_object() # This applies ViewSet's permission checks
            if not study_material.file or not hasattr(study_material.file, 'path'):
                logger.warning(f"Study material {pk} has no associated file or file path for summarization.")
                return Response({"error": "Study material has no associated file or file path cannot be determined."},
                                status=http_status.HTTP_400_BAD_REQUEST)

            file_path = study_material.file.path
            file_name = study_material.file.name
            file_type = file_name.split('.')[-1].lower() if '.' in file_name else ''

            logger.info(f"Attempting to summarize material ID {pk}, file: {file_name}")

            # Using functions from ai_processing module
            text_content = extract_text_from_file(file_path, file_type)

            if not text_content or not text_content.strip():
                logger.warning(f"Could not extract text content from material ID {pk} for summarization.")
                return Response({"error": "Could not extract text content from the material."},
                                status=http_status.HTTP_400_BAD_REQUEST)

            preferred_llm_provider = getattr(settings, 'PREFERRED_LLM_PROVIDER', 'google')
            if preferred_llm_provider == 'google' and \
               (settings.GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY" or not settings.GOOGLE_API_KEY):
                logger.error(f"Summarization failed for material ID {pk}: Google AI services are not configured.")
                return Response({"error": "Google AI services are not configured by the administrator."},
                                status=http_status.HTTP_503_SERVICE_UNAVAILABLE)
            elif preferred_llm_provider == 'openai' and \
                 (settings.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not settings.OPENAI_API_KEY):
                logger.error(f"Summarization failed for material ID {pk}: OpenAI services are not configured.")
                return Response({"error": "OpenAI services are not configured by the administrator."},
                                status=http_status.HTTP_503_SERVICE_UNAVAILABLE)

            logger.info(f"Calling summarize_text_with_llm for material ID {pk}, text length: {len(text_content)}")
            summary = summarize_text_with_llm(text_content, provider=preferred_llm_provider)

            if isinstance(summary, str) and summary.startswith("Error:"):
                logger.error(f"Summarization failed for material ID {pk}: {summary}")
                if "not configured" in summary or "API Key" in summary:
                    return Response({"error": f"AI service error: {summary}"}, status=http_status.HTTP_503_SERVICE_UNAVAILABLE)
                return Response({"error": f"AI processing error: {summary}"}, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

            logger.info(f"Successfully generated summary for material ID {pk}")
            return Response({"summary": summary, "study_material_id": pk}, status=http_status.HTTP_200_OK)

        except StudyMaterial.DoesNotExist:
            logger.warning(f"Attempt to summarize non-existent study material {pk}") # Should be caught by get_object
            return Response({"error": "Study material not found."}, status=http_status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error summarizing study material ID {pk}: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred during summarization."},
                            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


class RecommendedMaterialsView(generics.ListAPIView):
    """
    Provides a list of study materials recommended to the authenticated user.
    Recommendations are based on the user's enrolled courses and department, drawn from all available materials.
    """
    serializer_class = StudyMaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Returns a queryset of StudyMaterial objects recommended for the current user.
        Filters all available materials based on relevance to user's courses and department.
        """
        user = self.request.user
        try:
            user_profile = user.userprofile
        except UserProfile.DoesNotExist:
            return StudyMaterial.objects.none() # No profile, no recommendations

        # Fetch user's courses
        user_courses_ids = list(UserCourse.objects.filter(user_profile=user_profile).values_list('course_id', flat=True))

        # Base query: all materials (no longer filtering by status='approved')
        queryset = StudyMaterial.objects.all()

        # Filter conditions
        filters = Q() # Initialize with an empty Q object; will be an "AND" if not empty.
                      # Or, if we want to ensure at least one condition matches, might start differently.
                      # For "OR" logic as before for course/dept, this is fine.

        # 1. Materials for user's enrolled courses
        if user_courses_ids:
            filters |= Q(course__id__in=user_courses_ids)

        # 2. Materials matching user's department (if course match is not strong or for broader suggestions)
        if user_profile.department:
            department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
            if department_courses_ids:
                filters |= Q(course__id__in=department_courses_ids)

        # If no specific filters are matched from profile (e.g., no courses, no department, or courses/department have no materials)
        if not filters.children: # If no course or department filters could be formed
            # If user has no courses and no department, or those have no materials,
            # this would return ALL study materials. This might be too broad.
            # Let's return an empty set if no specific criteria are met.
            # Alternatively, a fallback to "latest N materials" regardless of relevance could be an option.
            # For now, require some relevance.
            if not user_courses_ids and not (user_profile and user_profile.department):
                 return StudyMaterial.objects.none()
            # If filters is still empty here, it implies user might have courses/dept, but they yielded no materials.
            # Returning queryset.filter(filters) would effectively return all if filters is truly empty.
            # So, if filters is empty (no criteria applied), return none.
            if not filters.children: # Check again, as department_courses_ids might not have added to filters
                return StudyMaterial.objects.none()


        return queryset.filter(filters).distinct().order_by('-upload_date')


from rest_framework.views import APIView
# from rest_framework.response import Response # Already imported
# from rest_framework import status # Already imported as http_status
# from rest_framework import permissions # Already imported
from .serializers import AIQuerySerializer # Ensure this is not duplicated if already imported
from .ai_processing import perform_rag_query, grade_answer_with_ai, summarize_text_with_llm, extract_text_from_file
from django.conf import settings
import logging
import uuid # Add this import

logger = logging.getLogger(__name__) # Define logger for this module


class AITutorQueryView(APIView):
    """
    Provides an interface to the AI Tutor powered by a Retrieval Augmented Generation (RAG) system.

    **POST:**
    Submit a query to receive an answer based on the processed study materials.

    **Request Body:**
    ```json
    {
        "query": "Your question about the study materials."
    }
    ```

    **Responses:**
    - `200 OK`: Successful query, answer provided.
      ```json
      {
          "answer": "The AI-generated answer."
      }
      ```
    - `400 Bad Request`: Invalid input (e.g., missing query).
      ```json
      {
          "query": ["This field is required."]
      }
      ```
    - `503 Service Unavailable`: AI services are not configured by the administrator or a temporary issue with an external AI service.
      ```json
      {
          "error": "AI services are not configured by the administrator."
          // or "AI service error: specific message from RAG pipeline"
      }
      ```
    - `500 Internal Server Error`: An unexpected error occurred, or an error within the AI processing pipeline.
      ```json
      {
          "error": "An unexpected error occurred while processing your query."
          // or "AI processing error: specific message from RAG pipeline"
      }
      ```
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AIQuerySerializer # Inform drf-yasg about the serializer for request body

    def post(self, request, *args, **kwargs):
        """
        Accepts a user's query and returns an AI-generated answer.
        The query is processed by a RAG pipeline leveraging uploaded study materials.
        """
        serializer = self.serializer_class(data=request.data) # Use self.serializer_class
        if serializer.is_valid():
            user_query = serializer.validated_data['query']

            # Check for placeholder API keys before calling RAG
            # This check can be more robust, e.g. on app startup or a dedicated health check endpoint

            google_embedding_used = getattr(settings, 'PREFERRED_EMBEDDING_PROVIDER', None) == 'google'
            google_llm_used = getattr(settings, 'PREFERRED_LLM_PROVIDER', None) == 'google'
            openai_embedding_used = getattr(settings, 'PREFERRED_EMBEDDING_PROVIDER', None) == 'openai'
            openai_llm_used = getattr(settings, 'PREFERRED_LLM_PROVIDER', None) == 'openai'

            if (google_embedding_used or google_llm_used) and \
               (settings.GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY" or not settings.GOOGLE_API_KEY):
                return Response(
                    {"error": "Google AI services are not configured by the administrator."},
                    status=http_status.HTTP_503_SERVICE_UNAVAILABLE
                )

            if (openai_embedding_used or openai_llm_used) and \
               (settings.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not settings.OPENAI_API_KEY):
                return Response(
                    {"error": "OpenAI services are not configured by the administrator."},
                    status=http_status.HTTP_503_SERVICE_UNAVAILABLE
                )

            try:
                rag_result = perform_rag_query(user_query) # Now returns a dictionary
                answer = rag_result.get("answer")
                context_vector_ids = rag_result.get("context_vector_ids", [])
                error_message = rag_result.get("error")

                if error_message:
                    logger.error(f"Error from perform_rag_query (Session ID: {session_id}): {error_message}")
                    # Distinguish between configuration errors and other processing errors based on message content
                    if "not configured" in error_message or "API Key" in error_message or "settings" in error_message.lower():
                        return Response({"error": "AI service error: " + error_message, "session_id": str(session_id)},
                                        status=http_status.HTTP_503_SERVICE_UNAVAILABLE)
                    return Response({"error": "AI processing error: " + error_message, "session_id": str(session_id)},
                                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

                # If there's an answer, even if context_vector_ids is empty (e.g., LLM answered without specific RAG context)
                if answer is not None:
                    return Response({
                        "answer": answer,
                        "session_id": str(session_id),
                        "context_vector_ids": context_vector_ids
                    }, status=http_status.HTTP_200_OK)
                else: # Should ideally be caught by error_message, but as a fallback
                    logger.error(f"perform_rag_query returned None for answer without an error message (Session ID: {session_id})")
                    return Response({"error": "AI processing error: Received no answer or error from RAG service.", "session_id": str(session_id)},
                                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.error(f"Unhandled exception in AITutorQueryView: {e}", exc_info=True)
                return Response(
                    {"error": "An unexpected error occurred while processing your query."},
                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)


# --- Mock Exam Views ---
from django.utils import timezone
from .models import MockExam, MockExamAttempt, MockExamQuestion, MockExamAnswer # Add new models
from .serializers import (MockExamListSerializer, MockExamDetailSerializer, # Add new serializers
                          MockExamAttemptSerializer, MockExamSubmissionSerializer)


class MockExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provides API endpoints for listing and retrieving Mock Exams.

    Mock exams are collections of questions designed to help users prepare.
    Users can view available exams and start new attempts.
    Creation of Mock Exams and their Questions is typically handled via the Django Admin interface.
    """
    queryset = MockExam.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """
        Returns the serializer class to be used for the current action.
        - `list`: Uses `MockExamListSerializer` for a summarized view.
        - `retrieve`: Uses `MockExamDetailSerializer` for a detailed view including questions.
        """
        if self.action == 'list':
            return MockExamListSerializer
        return MockExamDetailSerializer # For retrieve (detail view)

    @action(detail=True, methods=['post'], url_path='start-attempt', serializer_class=MockExamAttemptSerializer)
    def start_attempt(self, request, pk=None):
        """
        Starts a new mock exam attempt for the authenticated user for the specified mock exam.

        If an 'in_progress' attempt by the same user for the same exam already exists,
        details of that existing attempt are returned. Otherwise, a new attempt is created.

        **Response (New Attempt):**
        - `201 Created`: If a new attempt is successfully started.
          ```json
          {
              "id": 1,
              "user": "username",
              "mock_exam_title": "Test Exam 1",
              "mock_exam": 1, // ID of the mock exam
              "start_time": "YYYY-MM-DDTHH:MM:SS.ffffffZ",
              "end_time": null,
              "score": null,
              "status": "in_progress",
              "created_at": "YYYY-MM-DDTHH:MM:SS.ffffffZ"
          }
          ```
        **Response (Existing Attempt):**
        - `200 OK`: If an existing 'in_progress' attempt is found.
          ```json
          {
              "message": "You have an ongoing attempt for this exam.",
              "attempt_id": 1,
              "details": { /* Full MockExamAttemptSerializer data for the existing attempt */ }
          }
          ```
        - `404 Not Found`: If the specified mock exam does not exist.
        """
        mock_exam = self.get_object()
        user = request.user

        existing_attempt = MockExamAttempt.objects.filter(user=user, mock_exam=mock_exam, status='in_progress').first()
        if existing_attempt:
            serializer = self.get_serializer(existing_attempt) # Use get_serializer for action context
            return Response({
                "message": "You have an ongoing attempt for this exam.",
                "attempt_id": existing_attempt.id,
                "details": serializer.data
            }, status=http_status.HTTP_200_OK)

        attempt = MockExamAttempt.objects.create(user=user, mock_exam=mock_exam, status='in_progress')
        serializer = self.get_serializer(attempt) # Use get_serializer for action context
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class MockExamAttemptViewSet(viewsets.GenericViewSet,
                             viewsets.mixins.RetrieveModelMixin):
    """
    Provides API endpoints for managing and submitting Mock Exam Attempts.
    Users can retrieve their attempts and submit answers.
    """
    queryset = MockExamAttempt.objects.all()
    serializer_class = MockExamAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users can only access their own mock exam attempts.
        """
        return MockExamAttempt.objects.filter(user=self.request.user).order_by('-start_time')

    # RetrieveModelMixin provides the 'retrieve' action:
    # GET /api/core/mockexam-attempts/{id}/
    # It will use the self.serializer_class (MockExamAttemptSerializer) by default.
    # The get_queryset method ensures users can only retrieve their own attempts.

    @action(detail=True, methods=['post'], url_path='submit', serializer_class=MockExamSubmissionSerializer)
    def submit_answers(self, request, pk=None):
        """
        Submits answers for a given mock exam attempt.
        The attempt must be 'in_progress' and belong to the authenticated user.

        The system performs auto-grading for multiple-choice questions and uses AI for feedback
        and grading of short answer/essay questions.

        **Request Body:**
        ```json
        {
            "answers": [
                {
                    "question_id": 1,
                    "selected_choice_key": "B"
                },
                {
                    "question_id": 2,
                    "answer_text": "This is my detailed answer for the short question."
                }
            ]
        }
        ```

        **Response:**
        - `200 OK`: Answers successfully submitted and processed.
          ```json
          {
              "message": "Answers submitted and processed.",
              "attempt": { /* Updated MockExamAttempt data with score and status='completed' */ }
          }
          ```
        - `400 Bad Request`: Invalid input, attempt not in progress, or other submission errors.
        - `403 Forbidden`: If the user does not own the attempt.
        - `404 Not Found`: If the attempt does not exist.
        - `503 Service Unavailable`: If AI grading services are unavailable or misconfigured.
        """
        attempt = self.get_object()

        if attempt.user != request.user:
            # This check is technically redundant if get_queryset is correctly filtering,
            # but kept for explicitness, especially if an admin user could somehow hit this.
            logger.warning(f"User {request.user.id} tried to submit to attempt {attempt.id} owned by {attempt.user.id}")
            return Response({"error": "You do not have permission to submit to this attempt."}, status=http_status.HTTP_403_FORBIDDEN)

        if attempt.status != 'in_progress':
            logger.warning(f"Attempt to submit answers for already processed attempt {attempt.id} (status: {attempt.status}) by user {request.user.id}")
            return Response({"error": f"This attempt is not in progress (current status: {attempt.status}) and cannot be submitted to."}, status=http_status.HTTP_400_BAD_REQUEST)

        submission_serializer = self.get_serializer(data=request.data) # Uses action's serializer_class
        if not submission_serializer.is_valid():
            return Response(submission_serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        answers_data = submission_serializer.validated_data['answers']

        # --- Start of complex logic from previous step (AI-Graded Feedback) ---
        answers_to_create_later = []

        for answer_data_item in answers_data: # Renamed answer_data to answer_data_item for clarity
            try:
                question = MockExamQuestion.objects.get(id=answer_data_item['question_id'], mock_exam=attempt.mock_exam)
            except MockExamQuestion.DoesNotExist:
                logger.warning(f"Question ID {answer_data_item['question_id']} not found for exam {attempt.mock_exam.id} by user {request.user.id}.")
                continue

            current_points_for_answer = 0.0
            is_answer_correct = None
            feedback_text = ""

            user_text_answer = answer_data_item.get('answer_text', '')
            user_mcq_key = answer_data_item.get('selected_choice_key')

            content_for_ai_grading = user_text_answer

            if question.question_type == 'multiple_choice':
                if question.options and 'correct' in question.options:
                    correct_key = question.options.get('correct')
                    if user_mcq_key == correct_key:
                        is_answer_correct = True
                        current_points_for_answer = float(question.points)
                    else:
                        is_answer_correct = False
                        current_points_for_answer = 0.0
                else:
                    logger.warning(f"MCQ Question ID {question.id} has no 'correct' key in options. Auto-grading for points might be inaccurate.")
                    current_points_for_answer = 0.0

                if user_mcq_key and question.options and user_mcq_key in question.options:
                    option_value = question.options.get(user_mcq_key)
                    if isinstance(option_value, str):
                        content_for_ai_grading = option_value
                    else:
                        content_for_ai_grading = user_mcq_key
                        logger.info(f"MCQ option text for key '{user_mcq_key}' not found or not string for QID {question.id}. Sending key to AI.")
                elif user_mcq_key:
                     content_for_ai_grading = user_mcq_key
                else:
                    content_for_ai_grading = ""

            context_text_for_ai = None
            if question.original_material_chunk:
                try:
                    if question.original_material_chunk.chunk_text:
                         context_text_for_ai = question.original_material_chunk.chunk_text
                except Exception as e:
                    logger.error(f"Error fetching context from original_material_chunk for AI grading (QID {question.id}): {e}", exc_info=True)

            if content_for_ai_grading.strip() or question.question_type in ['short_answer', 'essay']:
                 ai_grading_result = grade_answer_with_ai(
                    question_text=question.question_text,
                    question_type=question.question_type,
                    user_answer_text=content_for_ai_grading,
                    question_points=float(question.points),
                    options=question.options if question.question_type == 'multiple_choice' else None,
                    context_text=context_text_for_ai
                )
                 feedback_text = ai_grading_result.get('feedback', "AI feedback processing error.")
                 ai_awarded_points = ai_grading_result.get('points_awarded')

                 if question.question_type in ['short_answer', 'essay'] and ai_awarded_points is not None:
                    current_points_for_answer = float(ai_awarded_points)
                    is_answer_correct = True if current_points_for_answer >= (float(question.points) / 2.0) else False
            elif question.question_type in ['short_answer', 'essay'] and not content_for_ai_grading.strip():
                feedback_text = "No answer was provided by the user for this question."
                current_points_for_answer = 0.0
                is_answer_correct = False

            answers_to_create_later.append(
                MockExamAnswer(
                    attempt=attempt,
                    question=question,
                    answer_text=user_text_answer,
                    selected_choice_key=user_mcq_key,
                    is_correct=is_answer_correct,
                    points_awarded=current_points_for_answer,
                    feedback=feedback_text
                )
            )

        if answers_to_create_later:
            MockExamAnswer.objects.bulk_create(answers_to_create_later)
            logger.info(f"Bulk created {len(answers_to_create_later)} answers for attempt {attempt.id}")

        final_total_score = 0.0
        all_attempt_answers = MockExamAnswer.objects.filter(attempt=attempt)
        for ans in all_attempt_answers:
            if ans.points_awarded is not None:
                final_total_score += ans.points_awarded

        attempt.score = final_total_score
        attempt.end_time = timezone.now()
        attempt.status = 'completed'
        attempt.save()
        # --- End of complex logic from previous step ---

        result_serializer = MockExamAttemptSerializer(attempt) # Use the ViewSet's default serializer for the attempt
        return Response({"message": "Answers submitted and processed.", "attempt": result_serializer.data}, status=http_status.HTTP_200_OK)


# --- AI Feedback View ---
from .serializers import AIFeedbackSerializer # Import new serializer
from .models import AIFeedback # Import AIFeedback model

class AIFeedbackSubmitView(generics.CreateAPIView):
    """
    Allows authenticated users to submit feedback on AI interactions.

    Feedback can include a rating, textual comments, and references to the specific
    AI interaction session and context materials used. This data is crucial for
    improving the AI's performance and content quality.

    **Request Body:**
    ```json
    {
        "session_id": "uuid-of-the-ai-interaction",
        "query_text": "(Optional) The user's query that led to the AI response.",
        "ai_response_text": "(Optional) The AI's response being reviewed.",
        "rating": 4, // Integer, e.g., 1-5
        "feedback_comment": "(Optional) Detailed textual feedback.",
        "interaction_type": "(Optional) e.g., 'rag_query', 'ai_exam_grading'",
        "context_vector_ids": ["vector_id1", "vector_id2"], // Optional list of vector_ids for context chunks
        "ai_low_confidence": false // Optional boolean
    }
    ```

    **Response:**
    - `201 Created`: Feedback successfully submitted. Returns the created feedback object.
    - `400 Bad Request`: Invalid input data (e.g., rating out of range, missing required fields if any beyond default).
    - `401 Unauthorized`: If the user is not authenticated.
    """
    queryset = AIFeedback.objects.all()
    serializer_class = AIFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]


# --- OCR View ---
from .models import ImageQuery # Already imported with AIFeedback, but good to note dependency
from .serializers import ImageQuerySerializer, ImageQueryUploadSerializer
from .ai_processing import extract_text_from_image_gcp

class OCRQueryView(generics.CreateAPIView):
    """
    Allows authenticated users to upload an image file to perform Optical Character Recognition (OCR)
    and extract text content from it.

    The extracted text can subsequently be used for other AI processing tasks, such as
    feeding it into the RAG (Retrieval Augmented Generation) system for queries.

    **Request (multipart/form-data):**
    - `image`: The image file to be processed.

    **Response (`201 Created` on successful upload and processing attempt):**
    Returns the `ImageQuery` object, which includes the processing status and extracted text (if any).
    ```json
    {
        "id": "uuid-of-the-image-query",
        "user": "username",
        "image": "/media/image_queries/YYYY/MM/DD/filename.jpg", // URL to the uploaded image
        "extracted_text": "The text extracted from the image by OCR...",
        "status": "completed", // or "pending", "processing", "failed"
        "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffffZ",
        "updated_at": "YYYY-MM-DDTHH:MM:SS.ffffffZ"
    }
    ```
    - `400 Bad Request`: If no image file is provided or the file is invalid.
    - `401 Unauthorized`: If the user is not authenticated.
    - `503 Service Unavailable`: If OCR services (e.g., Google Cloud Vision API) are not configured.
    """
    queryset = ImageQuery.objects.all()
    # get_serializer_class will determine which serializer to use
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ImageQueryUploadSerializer # Use this for creating/uploading
        return ImageQuerySerializer # Default for other methods if any (though CreateAPIView is POST only)

    def perform_create(self, serializer):
        image_query_instance = serializer.save(user=self.request.user, status='pending')
        logger.info(f"ImageQuery {image_query_instance.id} created by user {self.request.user.username}, status pending.")

        try:
            image_query_instance.status = 'processing'
            image_query_instance.save(update_fields=['status', 'updated_at'])

            image_file = image_query_instance.image
            # Ensure file pointer is at the beginning if it has been read before (though not in this flow for new upload)
            image_file.seek(0)
            image_content_bytes = image_file.read()

            extracted_text = extract_text_from_image_gcp(image_content_bytes)

            if extracted_text is not None: # Check for None which indicates an error during extraction
                image_query_instance.extracted_text = extracted_text
                image_query_instance.status = 'completed' if extracted_text else 'completed' # Still completed if no text found by OCR
                logger.info(f"ImageQuery {image_query_instance.id} OCR successful. Text found length: {len(extracted_text)}")
            else: # OCR process itself failed
                image_query_instance.status = 'failed'
                image_query_instance.extracted_text = "OCR process resulted in an error." # Generic error for user
                logger.error(f"ImageQuery {image_query_instance.id} OCR failed (extractor returned None).")

            image_query_instance.save(update_fields=['extracted_text', 'status', 'updated_at'])
            logger.info(f"ImageQuery {image_query_instance.id} processing finished with status: {image_query_instance.status}")

        except Exception as e:
            logger.error(f"Error during OCR processing for ImageQuery {image_query_instance.id}: {e}", exc_info=True)
            # Ensure instance is saved if not already, or update if it is
            if image_query_instance and image_query_instance.pk: # Check if instance was created
                image_query_instance.status = 'failed'
                image_query_instance.extracted_text = f"OCR processing error: {str(e)[:100]}" # Store a snippet of error
                image_query_instance.save(update_fields=['extracted_text', 'status', 'updated_at'])
            # This exception itself isn't directly returned to the client by perform_create.
            # The create method below handles the response.

    def create(self, request, *args, **kwargs):
        """
        Handles image upload, OCR processing, and returns the ImageQuery instance.
        """
        serializer = self.get_serializer(data=request.data) # Uses ImageQueryUploadSerializer
        serializer.is_valid(raise_exception=True)
        # perform_create will be called by super().create() or by us directly if we override.
        # To return the full ImageQuerySerializer output, we need to manage instance handling.

        # Manually call perform_create to get the instance
        # This is because perform_create does the actual work and saves the instance.
        # We need the instance *after* perform_create has updated it with OCR results.
        self.perform_create(serializer)
        instance_with_ocr_result = serializer.instance # This is the saved & processed instance

        # Now serialize this instance with the display serializer
        response_serializer = ImageQuerySerializer(instance_with_ocr_result)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=http_status.HTTP_201_CREATED, headers=headers)
