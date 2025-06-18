# examify/core/tests_phase4.py
import logging
import uuid
from unittest.mock import patch, MagicMock, call
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase # Using APITestCase for API tests
from django.test import TestCase # Using TestCase for signal/model tests
from io import BytesIO # For creating dummy image file

from .models import (
    Course, MockExam, MockExamQuestion, MockExamAttempt, MockExamAnswer,
    UserProfile, StudyMaterial, ActivityLog, DocumentChunk, ImageQuery
)
from .ai_processing import get_llm_response # To inspect its behavior or patch its direct callers

User = get_user_model()
# Disable most logging during tests to keep output clean unless specifically testing logging.
# This can be done globally or per-test class if needed.
# logging.disable(logging.CRITICAL)


class BasePhase4APITestCase(APITestCase):
    def setUp(self):
        super().setUp()
        self.user1_django_user = User.objects.create_user(username='p4user1', password='password123', email='p4user1@example.com')
        self.user2_django_user = User.objects.create_user(username='p4user2', password='password123', email='p4user2@example.com')
        self.admin_user_django_user = User.objects.create_superuser(username='p4admin', password='password123', email='p4admin@example.com')

        self.user1, _ = UserProfile.objects.get_or_create(user=self.user1_django_user)
        self.user2, _ = UserProfile.objects.get_or_create(user=self.user2_django_user)
        self.admin_user_profile, _ = UserProfile.objects.get_or_create(user=self.admin_user_django_user)

        self.course = Course.objects.create(name="Phase 4 Course", department="P4")

        self.dummy_file_content = b"This is test file content for summarization and other tests."
        self.dummy_file = SimpleUploadedFile("test_material_p4.txt", self.dummy_file_content, content_type="text/plain")

        self.study_material = StudyMaterial.objects.create(
            title="Phase 4 Material",
            uploaded_by=self.admin_user_django_user, # Ensure this is a User instance
            course=self.course,
            file=self.dummy_file
        )
        self.chunk1 = DocumentChunk.objects.create(
            study_material=self.study_material,
            chunk_text="First chunk of text.",
            vector_id=str(uuid.uuid4()),
            embedding_provider="test_provider"
        )
        self.chunk2 = DocumentChunk.objects.create(
            study_material=self.study_material,
            chunk_text="Second chunk for context.",
            vector_id=str(uuid.uuid4()),
            embedding_provider="test_provider"
        )

        self.mock_exam = MockExam.objects.create(
            title="Test Exam 1 Phase 4",
            course=self.course,
            creator=self.admin_user_django_user,
            duration_minutes=60,
            instructions="Read carefully."
        )
        self.question_mcq = MockExamQuestion.objects.create(
            mock_exam=self.mock_exam,
            question_text="What is 2+2 in P4?",
            question_type='multiple_choice',
            options={'A': '3', 'B': '4', 'C': '5', 'correct': 'B'},
            order=1,
            points=10
        )
        self.question_short = MockExamQuestion.objects.create(
            mock_exam=self.mock_exam,
            question_text="Explain Django models in P4.",
            question_type='short_answer',
            order=2,
            points=20,
            original_material_chunk=self.chunk1 # Link to one of the chunks
        )


class TaskSpecificLLMRoutingTests(BasePhase4APITestCase):
    @patch('core.ai_processing.OpenAIClient')
    @patch('core.ai_processing.genai.GenerativeModel')
    def test_get_llm_response_task_specific_system_messages_openai(self, mock_gemini_model_class, mock_openai_client_class):
        with self.settings(PREFERRED_LLM_PROVIDER='openai', OPENAI_API_KEY='fake_openai_key_p4'):
            mock_openai_instance = MagicMock()
            mock_chat_completion = MagicMock()
            mock_chat_completion.choices = [MagicMock(message=MagicMock(content="OpenAI Test Response"))]
            mock_openai_instance.chat.completions.create.return_value = mock_chat_completion
            mock_openai_client_class.return_value = mock_openai_instance

            tasks_and_expected_system_messages = {
                'summarize': "You are an AI assistant skilled in summarizing texts concisely.",
                'explain_complex': "You are an AI assistant skilled in explaining complex topics clearly and step-by-step.",
                'generate_questions': "You are an AI assistant skilled in generating relevant exam questions from a given text.",
                'rag_query': "You are an AI assistant answering questions based on provided context.",
                'grade_answer': "You are an AI assistant evaluating an answer to a question.", # Updated from prompt
                'general_query': "You are an AI assistant performing a general_query task."
            }

            for task, expected_msg in tasks_and_expected_system_messages.items():
                get_llm_response("dummy prompt", task_type=task) # provider will be openai due to settings
                self.assertTrue(mock_openai_instance.chat.completions.create.called, f"OpenAI client not called for task {task}")
                actual_kwargs = mock_openai_instance.chat.completions.create.call_args.kwargs
                self.assertEqual(actual_kwargs['messages'][0]['role'], 'system', f"System role not set for task {task}")
                self.assertEqual(actual_kwargs['messages'][0]['content'], expected_msg, f"Incorrect system message for task {task}")
                mock_openai_instance.chat.completions.create.reset_mock()


class SummarizationAPITests(BasePhase4APITestCase):
    @patch('core.views.summarize_text_with_llm') # Patch where it's called in the view
    @patch('core.views.extract_text_from_file') # Patch extract_text_from_file in view
    def test_summarize_material_success(self, mock_extract_text, mock_summarize_llm):
        mock_extract_text.return_value = self.dummy_file_content.decode('utf-8')
        mock_summarize_llm.return_value = "This is a test summary."

        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('studymaterial-summarize-material', kwargs={'pk': self.study_material.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['summary'], "This is a test summary.")
        mock_extract_text.assert_called_once()
        mock_summarize_llm.assert_called_once_with(self.dummy_file_content.decode('utf-8'), provider=settings.PREFERRED_LLM_PROVIDER)


    @patch('core.views.summarize_text_with_llm')
    @patch('core.views.extract_text_from_file')
    def test_summarize_material_ai_error(self, mock_extract_text, mock_summarize_llm):
        mock_extract_text.return_value = self.dummy_file_content.decode('utf-8')
        mock_summarize_llm.return_value = "Error: AI service unavailable."

        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('studymaterial-summarize-material', kwargs={'pk': self.study_material.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("AI processing error: Error: AI service unavailable.", response.data['error'])

    def test_summarize_material_not_found(self):
        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('studymaterial-summarize-material', kwargs={'pk': 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AIFeedbackAPITests(BasePhase4APITestCase):
    def test_submit_ai_feedback_success(self):
        self.client.force_authenticate(user=self.user1_django_user)
        session_id = uuid.uuid4()
        context_vector_ids = [self.chunk1.vector_id, self.chunk2.vector_id]

        feedback_data = {
            "session_id": str(session_id),
            "query_text": "What is Django?",
            "ai_response_text": "Django is a web framework.",
            "rating": 4,
            "feedback_comment": "Helpful response!",
            "interaction_type": "rag_query",
            "context_vector_ids": context_vector_ids,
            "ai_low_confidence": False
        }
        url = reverse('ai-feedback-submit')
        response = self.client.post(url, feedback_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(AIFeedback.objects.count(), 1)
        feedback_obj = AIFeedback.objects.first()
        self.assertEqual(feedback_obj.user, self.user1_django_user)
        self.assertEqual(str(feedback_obj.session_id), str(session_id))
        self.assertEqual(feedback_obj.rating, 4)
        self.assertEqual(feedback_obj.context_chunks.count(), 2)
        self.assertIn(self.chunk1, feedback_obj.context_chunks.all())
        self.assertIn(self.chunk2, feedback_obj.context_chunks.all())

    def test_submit_ai_feedback_invalid_rating(self):
        self.client.force_authenticate(user=self.user1_django_user)
        feedback_data = {"session_id": str(uuid.uuid4()), "rating": 0}
        url = reverse('ai-feedback-submit')
        response = self.client.post(url, feedback_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Rating must be an integer between 1 and 5.", str(response.data['rating']))


class ContentHighlightingSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='feedbackuser_p4', password='password')
        UserProfile.objects.get_or_create(user=self.user)
        self.course = Course.objects.create(name="Content Highlight Course P4")
        self.material = StudyMaterial.objects.create(title="CH Material P4", uploaded_by=self.user, course=self.course)
        self.chunk1 = DocumentChunk.objects.create(study_material=self.material, chunk_text="Chunk 1 text P4", vector_id="ch_vec1_p4", review_flags_count=0)
        self.chunk2 = DocumentChunk.objects.create(study_material=self.material, chunk_text="Chunk 2 text P4", vector_id="ch_vec2_p4", review_flags_count=0)

    def test_chunk_flag_increment_on_low_rating_feedback(self):
        feedback = AIFeedback.objects.create(
            user=self.user, session_id=uuid.uuid4(), rating=1, feedback_comment="Low rating test."
        )
        feedback.context_chunks.set([self.chunk1, self.chunk2])
        # Signal is post_save, .set() happens after create usually, so this test structure is fine.
        # The signal handler uses instance.context_chunks.all(), which queries the DB state after .set()

        self.chunk1.refresh_from_db()
        self.chunk2.refresh_from_db()
        self.assertEqual(self.chunk1.review_flags_count, 1)
        self.assertEqual(self.chunk2.review_flags_count, 1)

    def test_chunk_flag_increment_on_ai_low_confidence(self):
        feedback = AIFeedback.objects.create(
            user=self.user, session_id=uuid.uuid4(), ai_low_confidence=True
        )
        feedback.context_chunks.set([self.chunk1])

        self.chunk1.refresh_from_db()
        self.assertEqual(self.chunk1.review_flags_count, 1)


class OCRAPITests(BasePhase4APITestCase):
    @patch('core.views.extract_text_from_image_gcp') # Patch where it's used in views
    def test_ocr_query_success(self, mock_extract_text_gcp):
        mock_extract_text_gcp.return_value = "Extracted OCR text."

        try:
            from PIL import Image as PILImage
            img_io = BytesIO()
            image = PILImage.new('RGB', (60, 30), color = 'red')
            image.save(img_io, 'jpeg')
            img_io.seek(0)
            dummy_image_file = SimpleUploadedFile("test_ocr.jpg", img_io.read(), content_type="image/jpeg")
        except ImportError:
            self.skipTest("Pillow is not installed, skipping image creation part of OCR test.")
            # Fallback: Create a very simple text file if Pillow is not there,
            # though this doesn't truly test image handling.
            # For this test, if Pillow isn't there, it means the ImageField itself would fail earlier.
            # So, assuming Pillow IS installed as per previous subtask.

        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('ai-ocr-query')
        response = self.client.post(url, {'image': dummy_image_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(ImageQuery.objects.count(), 1)
        image_query_obj = ImageQuery.objects.first()
        self.assertEqual(image_query_obj.user, self.user1_django_user)
        self.assertEqual(image_query_obj.status, 'completed')
        self.assertEqual(image_query_obj.extracted_text, "Extracted OCR text.")
        self.assertIn("Extracted OCR text.", response.data['extracted_text'])
        # Check that the mock was called with the bytes content of the dummy_image_file
        mock_extract_text_gcp.assert_called_once_with(dummy_image_file.getvalue())


    @patch('core.views.extract_text_from_image_gcp')
    def test_ocr_query_gcp_error(self, mock_extract_text_gcp):
        mock_extract_text_gcp.return_value = None

        try:
            from PIL import Image as PILImage
            img_io = BytesIO()
            image = PILImage.new('RGB', (60, 30), color = 'blue')
            image.save(img_io, 'jpeg')
            img_io.seek(0)
            dummy_image_file = SimpleUploadedFile("test_error_ocr.jpg", img_io.read(), content_type="image/jpeg")
        except ImportError:
            self.skipTest("Pillow is not installed for OCR error test image.")

        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('ai-ocr-query')
        response = self.client.post(url, {'image': dummy_image_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        image_query_obj = ImageQuery.objects.first()
        self.assertEqual(image_query_obj.status, 'failed')
        self.assertEqual(image_query_obj.extracted_text, "OCR process resulted in an error.")

    def test_ocr_query_no_image(self):
        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('ai-ocr-query')
        response = self.client.post(url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

```
