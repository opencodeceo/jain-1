from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileViewSet, StudyMaterialViewSet, RecommendedMaterialsView # Add RecommendedMaterialsView

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='userprofile')
router.register(r'studymaterials', StudyMaterialViewSet, basename='studymaterial')

from .views import (UserProfileViewSet, StudyMaterialViewSet, RecommendedMaterialsView, AITutorQueryView,
                    MockExamViewSet, MockExamAttemptViewSet) # Add new ViewSets

router.register(r'mockexams', MockExamViewSet, basename='mockexam') # New
router.register(r'mockexam-attempts', MockExamAttemptViewSet, basename='mockexamattempt') # New

urlpatterns = [
    path('', include(router.urls)),
    path('recommendations/', RecommendedMaterialsView.as_view(), name='recommended-materials'),
    path('ai/query/', AITutorQueryView.as_view(), name='ai-tutor-query'),
]
