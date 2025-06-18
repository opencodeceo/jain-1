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
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to='study_materials/')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
