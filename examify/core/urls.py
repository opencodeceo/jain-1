from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserProfileViewSet, StudyMaterialViewSet, RecommendedMaterialsView # Add RecommendedMaterialsView

router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='userprofile')
router.register(r'studymaterials', StudyMaterialViewSet, basename='studymaterial')

urlpatterns = [
    path('', include(router.urls)),
    path('recommendations/', RecommendedMaterialsView.as_view(), name='recommended-materials'),
]
