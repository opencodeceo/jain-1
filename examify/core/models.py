from django.db import models
from django.contrib.auth.models import User
from django.conf import settings # Import settings

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    semester = models.IntegerField(null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)

    # Progress tracking fields
    mock_exams_completed = models.PositiveIntegerField(default=0, help_text="Number of mock exams completed by the user.")
    average_mock_exam_score = models.FloatField(null=True, blank=True, help_text="Average score achieved in completed mock exams.")
    study_materials_uploaded_count = models.PositiveIntegerField(default=0, help_text="Number of study materials uploaded by the user.")
    total_points = models.PositiveIntegerField(default=0, help_text="Total points earned by the user for various activities.")

    def __str__(self):
        return self.user.username

class Course(models.Model):
    name = models.CharField(max_length=200)
    department = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class UserCourse(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user_profile', 'course')

    def __str__(self):
        return f"{self.user_profile.user.username}'s {self.course.name}"

class StudyMaterial(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to='study_materials/')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class DocumentChunk(models.Model):
    study_material = models.ForeignKey('StudyMaterial', on_delete=models.CASCADE, related_name='chunks')
    chunk_text = models.TextField()
    # ID from Vertex AI Vector Search. Max length might vary based on Vertex AI's ID format.
    # Using CharField, ensure it's indexed if queried frequently.
    vector_id = models.CharField(max_length=255, unique=True, db_index=True,
                                 help_text="ID of the chunk in the vector database")
    embedding_provider = models.CharField(max_length=50, blank=True, null=True,
                                       help_text="Embedding provider used for this chunk (e.g., 'google', 'openai')")
    chunk_sequence_number = models.PositiveIntegerField(default=0,
                                                    help_text="Order of the chunk within the document")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['study_material', 'chunk_sequence_number']
        unique_together = [['study_material', 'chunk_sequence_number']] # A chunk number should be unique per material

    def __str__(self):
        return f"Chunk {self.chunk_sequence_number} for {self.study_material.title[:30]}..."


class MockExam(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    course = models.ForeignKey('Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='mock_exams')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_mock_exams')
    duration_minutes = models.PositiveIntegerField(default=60, help_text="Duration of the exam in minutes")
    instructions = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class MockExamQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', 'Multiple Choice'),
        ('short_answer', 'Short Answer'),
        ('essay', 'Essay'),
    ]
    mock_exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple_choice')
    # For multiple choice, options could be stored as JSON or in a separate model if complex
    options = models.JSONField(blank=True, null=True, help_text="For multiple choice: e.g., {'A': 'Option 1', 'B': 'Option 2', 'correct': 'A'}")
    # For auto-gradable questions (like MCQs), correct answer might be stored here or within options.
    # For short_answer/essay, this might be a model answer or grading rubric (simplified for now).
    original_material_chunk = models.ForeignKey('core.DocumentChunk', on_delete=models.SET_NULL, null=True, blank=True, help_text="Link to specific document chunk if question is derived from it")
    order = models.PositiveIntegerField(default=0, help_text="Order of the question in the exam")
    points = models.PositiveIntegerField(default=1, help_text="Points for this question")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['mock_exam', 'order']

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}... (Exam: {self.mock_exam.title})"

class MockExamAttempt(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'), # Could be useful if attempts are pre-created
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mock_exam_attempts')
    mock_exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name='attempts')
    start_time = models.DateTimeField(auto_now_add=True) # Or set when user actually starts
    end_time = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Attempt by {self.user.username} for {self.mock_exam.title} (Status: {self.status})"

class MockExamAnswer(models.Model):
    attempt = models.ForeignKey(MockExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(MockExamQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField(blank=True, null=True, help_text="For short answer/essay or user's choice for MCQ if not using selected_choices directly")
    # For MCQ, selected_choices could store the key of the chosen option e.g., 'A' or a list of keys for multi-select
    selected_choice_key = models.CharField(max_length=50, blank=True, null=True, help_text="Key of the selected multiple choice option (e.g., 'A')")
    # For more complex MCQ (multi-select), a JSONField might be better:
    # selected_choices = models.JSONField(blank=True, null=True)
    is_correct = models.BooleanField(null=True, blank=True, help_text="For auto-gradable questions")
    # Score for this specific answer, especially if questions have different point values or partial credit
    points_awarded = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True, null=True, help_text="AI or manual feedback for this answer")
    answered_at = models.DateTimeField(auto_now_add=True) # Or auto_now=True if updated frequently

    def __str__(self):
        return f"Answer by {self.attempt.user.username} to Q: {self.question.question_text[:30]}... (Attempt ID: {self.attempt.id})"


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('upload_material', 'Uploaded Study Material'),
        ('complete_mock_exam', 'Completed Mock Exam'),
        # Add more actions as needed
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity_logs')
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    points_awarded = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True, help_text="Optional details about the activity, e.g., material ID, exam ID.")

    def __str__(self):
        return f"{self.user.username} - {self.get_action_type_display()} ({self.points_awarded} points) at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['-timestamp']


class StudyGroup(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    course = models.ForeignKey('Course', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='study_groups', help_text="Optional: Link group to a specific course.")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                related_name='created_study_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # members = models.ManyToManyField(settings.AUTH_USER_MODEL, through='StudyGroupMembership', related_name='study_groups_joined')

    def __str__(self):
        return self.name

class StudyGroupMembership(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='study_group_memberships')
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name='memberships')
    date_joined = models.DateTimeField(auto_now_add=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = [['user', 'group']] # User can only be in a group once
        ordering = ['group', 'date_joined']

    def __str__(self):
        return f"{self.user.username} in {self.group.name} as {self.get_role_display()}"
