# examify/core/tests_phase3.py
import logging
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase # Using APITestCase for API tests
from django.test import TestCase # Using TestCase for signal/model tests
from .models import (Course, MockExam, MockExamQuestion, MockExamAttempt, MockExamAnswer,
                     UserProfile, StudyMaterial, ActivityLog, DocumentChunk)
from .serializers import MockExamAttemptSerializer # For assertions

User = get_user_model()

# Disable most logging during tests to keep output clean, unless specifically testing logging.
# logging.disable(logging.CRITICAL) # This might be too broad, could be enabled with a flag or env var for debugging tests.
# For now, let's allow logs to show if any errors are explicitly logged by the app during tests.


class BasePhase3APITestCase(APITestCase):
    def setUp(self):
        super().setUp()
        self.user1, _ = UserProfile.objects.get_or_create(
            user=User.objects.create_user(username='user1', password='password123', email='user1@example.com')
        )
        self.user2, _ = UserProfile.objects.get_or_create(
            user=User.objects.create_user(username='user2', password='password123', email='user2@example.com')
        )
        self.admin_user, _ = UserProfile.objects.get_or_create(
             user=User.objects.create_superuser(username='adminuser', password='password123', email='admin@example.com')
        )
        # Make users accessible directly for clarity in tests
        self.user1_django_user = self.user1.user
        self.user2_django_user = self.user2.user
        self.admin_user_django_user = self.admin_user.user


        self.course = Course.objects.create(name="Test Course", department="Testing")
        self.mock_exam = MockExam.objects.create(
            title="Test Exam 1",
            course=self.course,
            creator=self.admin_user_django_user,
            duration_minutes=60,
            instructions="Read carefully."
        )

        # Create a dummy StudyMaterial for DocumentChunk foreign key
        self.study_material_for_chunk = StudyMaterial.objects.create(
            title="Django Basics Material",
            uploaded_by=self.admin_user_django_user,
            course=self.course
        )
        self.doc_chunk = DocumentChunk.objects.create(
            study_material=self.study_material_for_chunk,
            chunk_text="Django models are Python classes that represent database tables.",
            vector_id="test_vector_id_for_q_short", # Ensure this is unique if more chunks are made
            embedding_provider="test_provider"
        )

        self.question_mcq = MockExamQuestion.objects.create(
            mock_exam=self.mock_exam,
            question_text="What is 2+2?",
            question_type='multiple_choice',
            options={'A': '3', 'B': '4', 'C': '5', 'correct': 'B'},
            order=1,
            points=10
        )
        self.question_short = MockExamQuestion.objects.create(
            mock_exam=self.mock_exam,
            question_text="Explain Django models.",
            question_type='short_answer',
            order=2,
            points=20,
            original_material_chunk=self.doc_chunk # Link to the created chunk
        )


class MockExamAPITests(BasePhase3APITestCase):
    def test_list_mock_exams_authenticated(self):
        self.client.force_authenticate(user=self.user1_django_user)
        response = self.client.get(reverse('mockexam-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming pagination might be active, check response.data['results'] or adjust if not paginated
        # For now, assuming it returns a list directly or DRF's default pagination structure
        data_to_check = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(data_to_check), 1)
        self.assertEqual(data_to_check[0]['title'], "Test Exam 1")

    def test_list_mock_exams_unauthenticated(self):
        response = self.client.get(reverse('mockexam-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_mock_exam_detail(self):
        self.client.force_authenticate(user=self.user1_django_user)
        response = self.client.get(reverse('mockexam-detail', kwargs={'pk': self.mock_exam.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.mock_exam.title)
        self.assertEqual(len(response.data['questions']), 2)

    def test_start_mock_exam_attempt(self):
        self.client.force_authenticate(user=self.user1_django_user)
        url = reverse('mockexam-start-attempt', kwargs={'pk': self.mock_exam.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['mock_exam']['id'], self.mock_exam.pk) # Assuming nested serializer for mock_exam
        self.assertEqual(response.data['user'], self.user1_django_user.username)
        self.assertEqual(response.data['status'], 'in_progress')
        self.assertTrue(MockExamAttempt.objects.filter(user=self.user1_django_user, mock_exam=self.mock_exam).exists())

    def test_start_existing_inprogress_attempt_returns_existing(self):
        # This test assumes the view logic was updated to return existing in-progress attempts
        self.client.force_authenticate(user=self.user1_django_user)
        existing_attempt = MockExamAttempt.objects.create(user=self.user1_django_user, mock_exam=self.mock_exam, status='in_progress')
        url = reverse('mockexam-start-attempt', kwargs={'pk': self.mock_exam.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK) # Expect 200 OK if existing is returned
        self.assertEqual(response.data['attempt_id'], existing_attempt.id)
        self.assertEqual(MockExamAttempt.objects.filter(user=self.user1_django_user, mock_exam=self.mock_exam, status='in_progress').count(), 1)


    @patch('core.views.grade_answer_with_ai') # Patch where it's used (core.views)
    def test_submit_mock_exam_answers(self, mock_grade_ai):
        mock_grade_ai.side_effect = [
            {'feedback': "AI feedback for MCQ.", 'points_awarded': None},
            {'feedback': "Good explanation of Django models.", 'points_awarded': 18.0}
        ]

        self.client.force_authenticate(user=self.user1_django_user)
        attempt = MockExamAttempt.objects.create(user=self.user1_django_user, mock_exam=self.mock_exam, status='in_progress')

        submission_data = {
            "answers": [
                {"question_id": self.question_mcq.id, "selected_choice_key": "B"},
                {"question_id": self.question_short.id, "answer_text": "Django models are classes."}
            ]
        }
        url = reverse('mockexamattempt-submit-answers', kwargs={'pk': attempt.pk})
        response = self.client.post(url, submission_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'completed')
        self.assertEqual(attempt.score, 28.0) # MCQ (10) + Short Answer (18 from AI)

        mcq_answer = MockExamAnswer.objects.get(attempt=attempt, question=self.question_mcq)
        self.assertTrue(mcq_answer.is_correct)
        self.assertEqual(mcq_answer.points_awarded, 10.0)
        self.assertEqual(mcq_answer.feedback, "AI feedback for MCQ.")

        short_answer = MockExamAnswer.objects.get(attempt=attempt, question=self.question_short)
        self.assertEqual(short_answer.points_awarded, 18.0)
        self.assertEqual(short_answer.feedback, "Good explanation of Django models.")
        self.assertTrue(short_answer.is_correct) # 18 > 20/2

        self.assertEqual(mock_grade_ai.call_count, 2)
        args_mcq_call = mock_grade_ai.call_args_list[0][0] # Get positional args of first call
        self.assertEqual(args_mcq_call[2], self.question_mcq.options['B']) # user_answer_text for MCQ

        args_short_call = mock_grade_ai.call_args_list[1][0] # Positional args of second call
        self.assertEqual(args_short_call[5], self.doc_chunk.chunk_text) # context_text


    def test_submit_to_completed_attempt_fails(self):
        self.client.force_authenticate(user=self.user1_django_user)
        attempt = MockExamAttempt.objects.create(user=self.user1_django_user, mock_exam=self.mock_exam, status='completed')
        url = reverse('mockexamattempt-submit-answers', kwargs={'pk': attempt.pk})
        response = self.client.post(url, {"answers": []}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_to_others_attempt_fails(self):
        self.client.force_authenticate(user=self.user2_django_user)
        attempt = MockExamAttempt.objects.create(user=self.user1_django_user, mock_exam=self.mock_exam, status='in_progress')
        url = reverse('mockexamattempt-submit-answers', kwargs={'pk': attempt.pk})
        response = self.client.post(url, {"answers": []}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProgressGamificationSignalTests(TestCase):
    def setUp(self):
        self.user_django = User.objects.create_user(username='testsignaluser', password='password')
        self.user_profile, _ = UserProfile.objects.get_or_create(user=self.user_django)
        self.course = Course.objects.create(name="Signal Test Course", department="Signals")
        self.mock_exam = MockExam.objects.create(title="Signal Exam", course=self.course, duration_minutes=30, creator=self.user_django)
        self.question = MockExamQuestion.objects.create(mock_exam=self.mock_exam, question_text="Q1", points=10)

    def test_progress_update_on_exam_completion(self):
        attempt = MockExamAttempt.objects.create(user=self.user_django, mock_exam=self.mock_exam, status='in_progress')
        attempt.status = 'completed'
        attempt.score = 8.0
        attempt.save()

        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.mock_exams_completed, 1)
        self.assertEqual(self.user_profile.average_mock_exam_score, 8.0)
        self.assertEqual(self.user_profile.total_points, 25) # POINTS_FOR_COMPLETE_MOCK_EXAM
        self.assertTrue(ActivityLog.objects.filter(user=self.user_django, action_type='complete_mock_exam').exists())

        attempt.score = 9.0 # Resave, e.g. regrade
        attempt.save() # Should trigger signal again
        self.user_profile.refresh_from_db()
        # Points should NOT be awarded again for the same attempt ID
        self.assertEqual(self.user_profile.total_points, 25)
        self.assertEqual(ActivityLog.objects.filter(user=self.user_django, action_type='complete_mock_exam').count(), 1)
        # But average score and completed count should re-evaluate (completed count should be stable here)
        self.assertEqual(self.user_profile.average_mock_exam_score, 9.0)
        self.assertEqual(self.user_profile.mock_exams_completed, 1)


    def test_progress_update_on_material_upload(self):
        StudyMaterial.objects.create(title="Test Material S", uploaded_by=self.user_django, course=self.course)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.study_materials_uploaded_count, 1)
        self.assertEqual(self.user_profile.total_points, 10) # POINTS_FOR_UPLOAD_MATERIAL
        self.assertTrue(ActivityLog.objects.filter(user=self.user_django, action_type='upload_material').exists())

        StudyMaterial.objects.create(title="Test Material S2", uploaded_by=self.user_django, course=self.course)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.study_materials_uploaded_count, 2)
        self.assertEqual(self.user_profile.total_points, 20)


class MockExamModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='modeltestuser', password='password')
        self.course = Course.objects.create(name="Model Course", department="Models")
        self.mock_exam = MockExam.objects.create(title="Model Exam", course=self.course, creator=self.user)
        self.question = MockExamQuestion.objects.create(mock_exam=self.mock_exam, question_text="Model Q1", order=0)
        self.attempt = MockExamAttempt.objects.create(user=self.user, mock_exam=self.mock_exam)

    def test_mock_exam_str(self):
        self.assertEqual(str(self.mock_exam), "Model Exam")

    def test_mock_exam_question_str(self):
        expected_str = f"Q0: {self.question.question_text[:50]}... (Exam: {self.mock_exam.title})"
        self.assertEqual(str(self.question), expected_str)

    def test_mock_exam_attempt_str(self):
        expected_str = f"Attempt by {self.user.username} for {self.mock_exam.title} (Status: in_progress)"
        self.assertEqual(str(self.attempt), expected_str)

    def test_mock_exam_answer_str(self):
        answer = MockExamAnswer.objects.create(attempt=self.attempt, question=self.question, answer_text="Test Answer")
        expected_str = f"Answer by {self.user.username} to Q: {self.question.question_text[:30]}... (Attempt ID: {self.attempt.id})"
        self.assertEqual(str(answer), expected_str)
