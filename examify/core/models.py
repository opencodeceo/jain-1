from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    semester = models.IntegerField(null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)

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
