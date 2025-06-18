from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileViewSet, StudyMaterialViewSet, RecommendedMaterialsView # Add RecommendedMaterialsView

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='userprofile')
router.register(r'studymaterials', StudyMaterialViewSet, basename='studymaterial')

from .views import UserProfileViewSet, StudyMaterialViewSet, RecommendedMaterialsView, AITutorQueryView # Add AITutorQueryView

# ... (router registrations if any are moved here, but typically router is defined and registered above urlpatterns)

urlpatterns = [
    path('', include(router.urls)),
    path('recommendations/', RecommendedMaterialsView.as_view(), name='recommended-materials'),
    path('ai/query/', AITutorQueryView.as_view(), name='ai-tutor-query'), # New AI Tutor endpoint
]
