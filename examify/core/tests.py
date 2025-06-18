import io
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase, APIClient # APIClient not explicitly used if self.client is enough
from .models import UserProfile, Course, StudyMaterial, UserCourse

User = get_user_model()

class BaseAPITestCase(APITestCase):
    """
    Base class for API tests.
    Provides helper methods for creating common objects.
    """
    def setUp(self):
        super().setUp()
        # self.client is already available from APITestCase

    def create_user_and_profile(self, username='testuser', email='test@example.com', password='password123',
                                profile_data=None, is_staff=False):
        """
        Creates a user and their profile.
        Ensures UserProfile is created as User.objects.create_user doesn't trigger signals/Djoser serializers.
        """
        if is_staff:
            user = User.objects.create_superuser(username=username, email=email, password=password)
        else:
            user = User.objects.create_user(username=username, email=email, password=password)

        # Manually create UserProfile as User.objects.create_user doesn't auto-create it.
        # Djoser's UserCreateSerializer handles this during API registration.
        # This helper is for setting up users needed by other tests.
        current_profile_data = profile_data if profile_data else {}
        profile, created = UserProfile.objects.get_or_create(user=user, defaults=current_profile_data)
        if not created and profile_data: # If it existed but we have new data for it for this test context
            for key, value in profile_data.items():
                setattr(profile, key, value)
            profile.save()

        return user, profile

    def create_course(self, name, department, **kwargs):
        return Course.objects.create(name=name, department=department, **kwargs)

    def create_studymaterial(self, uploaded_by, course, title="Test Material",
                             file_content=b"test content", status="pending", description="A test material."):
        # Ensure the file name is unique enough if multiple materials are created in one test method
        # or use a more robust way to generate file names if needed.
        file_name = f"{title.replace(' ', '_').lower()}_{uploaded_by.username}.txt"
        dummy_file = SimpleUploadedFile(file_name, file_content, content_type="text/plain")

        material = StudyMaterial.objects.create(
            title=title,
            description=description,
            file=dummy_file,
            uploaded_by=uploaded_by,
            course=course,
            status=status
        )
        return material


class UserAuthTests(BaseAPITestCase):

    def test_user_registration_success(self):
        user_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'password123',
            'userprofile': { # This relies on UserCreateSerializer handling nested 'userprofile'
                'semester': 1,
                'department': 'CS',
                'region': 'North'
            }
        }
        url = reverse('user-list')
        response = self.client.post(url, user_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(UserProfile.objects.filter(user__username='newuser').exists())
        user_profile = UserProfile.objects.get(user__username='newuser')
        self.assertEqual(user_profile.semester, 1)
        self.assertEqual(user_profile.department, 'CS')
        self.assertEqual(user_profile.region, 'North')

    def test_user_registration_existing_username(self):
        self.create_user_and_profile(username='existinguser') # Setup existing user
        url = reverse('user-list')
        data = {'username': 'existinguser', 'email': 'newemail@example.com', 'password': 'password123'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_success(self):
        self.create_user_and_profile(username='loginuser', password='password123')
        url = reverse('login')
        data = {'username': 'loginuser', 'password': 'password123'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('auth_token', response.data)

    def test_user_login_failure(self):
        self.create_user_and_profile(username='loginuser2', password='password123')
        url = reverse('login')
        data = {'username': 'loginuser2', 'password': 'wrongpassword'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fetch_user_details_authenticated(self):
        user, profile = self.create_user_and_profile(username='me_user', profile_data={'department': "Science"})
        self.client.force_authenticate(user=user)
        url = reverse('user-me')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['username'], 'me_user')
        self.assertIn('userprofile', response.data)
        self.assertEqual(response.data['userprofile']['department'], 'Science')

    def test_fetch_user_details_unauthenticated(self):
        url = reverse('user-me')
        response = self.client.get(url) # No client.force_authenticate()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_user_and_profile_details(self):
        user, profile = self.create_user_and_profile(
            username='updateuser',
            profile_data={'semester': 1, 'department': "InitialDept", "region": "InitialRegion"}
        )
        self.client.force_authenticate(user=user)
        url = reverse('user-me')

        data_to_update = {
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'userprofile': {
                'semester': 2,
                'department': 'UpdatedDept',
                'region': 'South'
            }
        }
        response = self.client.patch(url, data_to_update, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        user.refresh_from_db()
        # profile is user.userprofile, so refreshing user should make profile accessible,
        # but to be safe, refresh profile directly if it's a separate variable.
        profile.refresh_from_db()

        self.assertEqual(user.first_name, 'UpdatedFirst')
        self.assertEqual(user.last_name, 'UpdatedLast')
        self.assertEqual(profile.semester, 2)
        self.assertEqual(profile.department, 'UpdatedDept')
        self.assertEqual(profile.region, 'South')


class CourseModelTests(APITestCase):
    def test_course_creation_and_str(self):
        course = self.create_course(name="Intro to Testing", department="QA")
        self.assertEqual(str(course), "Intro to Testing")
        self.assertEqual(course.department, "QA")


class StudyMaterialTests(BaseAPITestCase):
    def setUp(self):
        super().setUp() # Call parent setUp if it does anything
        self.user, self.user_profile = self.create_user_and_profile(
            username='material_user',
            profile_data={'department': 'Science', 'semester': 3}
        )
        self.admin_user, _ = self.create_user_and_profile(
            username='material_admin',
            is_staff=True,
            profile_data={'department': 'AdminDept'}
        )
        self.course1 = self.create_course(name="Advanced Testology", department="Science")
        self.course2 = self.create_course(name="Basic QA", department="QA")

        # Enroll user in course1
        UserCourse.objects.create(user_profile=self.user_profile, course=self.course1)

    def test_upload_studymaterial_success(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('studymaterial-list') # Corresponds to StudyMaterialViewSet list/create

        file_content = b"This is some advanced test file content."
        # Using SimpleUploadedFile to simulate a file upload
        dummy_file = SimpleUploadedFile("advanced_material.txt", file_content, content_type="text/plain")

        data = {
            'title': 'My Advanced Material',
            'description': 'A material for testing uploads in Advanced Testology.',
            'course': self.course1.id, # User is enrolled in course1
            'file': dummy_file,
        }
        response = self.client.post(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(StudyMaterial.objects.filter(title='My Advanced Material').exists())
        material = StudyMaterial.objects.get(title='My Advanced Material')
        self.assertEqual(material.uploaded_by, self.user)
        self.assertEqual(material.status, 'pending') # Default status
        self.assertEqual(material.course, self.course1)
        self.assertIn("advanced_material", material.file.name) # Check if file name is reasonable

        # Optional: Check file content (can be tricky with storage backends)
        # material.file.open(mode='rb')
        # content_read = material.file.read()
        # material.file.close()
        # self.assertEqual(content_read, file_content)

    def test_upload_studymaterial_unauthenticated(self):
        # self.client is not authenticated here by default if BaseAPITestCase.setUp doesn't auth
        # Or explicitly: self.client.force_authenticate(user=None)
        url = reverse('studymaterial-list')
        dummy_file = SimpleUploadedFile("unauth_material.txt", b"content", content_type="text/plain")
        data = {
            'title': 'Unauthenticated Material',
            'course': self.course1.id, # course ID is arbitrary here as it should fail before course check
            'file': dummy_file
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # More tests for StudyMaterial: listing, retrieval, update, delete, permissions


class StudyMaterialReviewTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.uploader, self.uploader_profile = self.create_user_and_profile(username='uploader')
        self.admin, _ = self.create_user_and_profile(username='reviewer_admin', is_staff=True)
        self.course = self.create_course(name="Reviewable Course", department="AnyDept")
        self.material = self.create_studymaterial(
            uploaded_by=self.uploader,
            course=self.course,
            title="Material for Review",
            status="pending" # Explicitly set for clarity
        )

    def test_admin_approve_material(self):
        self.client.force_authenticate(user=self.admin)
        # URL for custom action 'review' on 'studymaterial-detail' route
        url = reverse('studymaterial-review', kwargs={'pk': self.material.pk})
        data = {'status': 'approved'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, 'approved')

    def test_admin_reject_material(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('studymaterial-review', kwargs={'pk': self.material.pk})
        data = {'status': 'rejected'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, 'rejected')

    def test_non_admin_cannot_review_material(self):
        self.client.force_authenticate(user=self.uploader) # Authenticate as non-admin
        url = reverse('studymaterial-review', kwargs={'pk': self.material.pk})
        data = {'status': 'approved'}
        response = self.client.post(url, data, format='json')
        # IsAdminUser permission should deny this
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, 'pending') # Status should not change

    def test_review_invalid_status_value(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('studymaterial-review', kwargs={'pk': self.material.pk})
        data = {'status': 'random_status_value'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, 'pending')


class RecommendationTests(BaseAPITestCase):
    # Setup for recommendations can be more involved
    pass
```
The tests for `UserAuthTests` and `CourseModelTests` are now in place, along with a more robust `create_user_and_profile` helper. I've also added initial tests for `StudyMaterialTests` (upload success and unauthenticated upload) and a full suite for `StudyMaterialReviewTests` as this was a key feature from a previous subtask.

The `RecommendationTests` and further `StudyMaterialTests` (listing, permissions, update, delete) are still placeholders and would be the next priority for testing.

I'll submit this version of `tests.py`.
