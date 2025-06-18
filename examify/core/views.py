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
    Users can upload materials, which are then reviewed by admins.
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
        - 'review': Admin only.
        """
        if self.action in ['list', 'create']:
            self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminOrOwner]
        elif self.action == 'review':
            self.permission_classes = [IsAdminUser]
        else:
            self.permission_classes = [permissions.IsAuthenticated] # Default
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        Allows authenticated users to upload new study materials.
        `uploaded_by` is set to the current user.
        Status defaults to 'pending' as per model definition.
        """
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        """
        Allows the owner or an admin to update material details (e.g., title, description).
        Status cannot be changed here by non-admins due to serializer field being read-only.
        Admins use the 'review' action to change status.
        """
        serializer.save()

    def get_queryset(self):
        """
        Lists study materials.
        - Regular users see their own pending/rejected materials and all approved materials.
        - Admins see all materials.
        """
        user = self.request.user
        if user.is_staff:
            return StudyMaterial.objects.all().order_by('-upload_date')
        return StudyMaterial.objects.filter(
            Q(uploaded_by=user) | Q(status='approved')
        ).distinct().order_by('-upload_date')

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def review(self, request, pk=None):
        """
        Allows admin users to approve or reject a study material.
        Expects `{"status": "approved"}` or `{"status": "rejected"}` in the request body.
        """
        material = self.get_object()
        new_status = request.data.get('status')

        if new_status not in ['approved', 'rejected']: # Simpler check
            return Response(
                {'error': 'Invalid status value. Must be "approved" or "rejected".'},
                status=http_status.HTTP_400_BAD_REQUEST
            )

        material.status = new_status
        material.save()
        return Response(StudyMaterialSerializer(material).data)

class RecommendedMaterialsView(generics.ListAPIView):
    """
    Provides a list of approved study materials recommended to the authenticated user.
    Recommendations are based on the user's enrolled courses and their department.
    """
    serializer_class = StudyMaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Returns a queryset of StudyMaterial objects recommended for the current user.
        Filters by approved materials relevant to user's courses and department.
        """
        user = self.request.user
        try:
            # Ensure related_name is 'userprofile' or adjust if it's different.
            # Default is <classname>_set, but for OneToOneField, it's often just the classname.
            # If User.userprofile doesn't work, it might be User.profile or whatever was defined/defaulted.
            # Let's assume it's user.userprofile as per common practice when related_name isn't explicitly set
            # on the OneToOneField in UserProfile to User.
            user_profile = user.userprofile
        except UserProfile.DoesNotExist:
            return StudyMaterial.objects.none() # No profile, no recommendations

        # Fetch user's courses
        user_courses_ids = list(UserCourse.objects.filter(user_profile=user_profile).values_list('course_id', flat=True))

        # Base query: only approved materials
        queryset = StudyMaterial.objects.filter(status='approved')

        # Filter conditions
        filters = Q()

        # 1. Materials for user's enrolled courses
        if user_courses_ids:
            filters |= Q(course__id__in=user_courses_ids)

        # 2. Materials matching user's department (if course match is not strong or for broader suggestions)
        if user_profile.department:
            department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
            if department_courses_ids:
                filters |= Q(course__id__in=department_courses_ids)

        # If no specific filters are matched from profile (e.g., no courses, no department, or courses/department have no materials)
        if not filters.children: # Check if any conditions were added to Q object
            # Fallback: Show approved materials from their department if they have one
            if user_profile.department:
                 department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
                 if department_courses_ids:
                    return queryset.filter(course__id__in=department_courses_ids).distinct().order_by('-upload_date')
                 else: # Department exists but has no courses, or courses have no materials
                    return StudyMaterial.objects.none()
            else:
                # If no department, maybe return latest approved materials, or none if too broad
                # Returning none for now to be more specific. Could return all approved as a last resort.
                return StudyMaterial.objects.none()
                # return queryset.order_by('-upload_date')[:20] # Example: limit to latest 20 general approved

        return queryset.filter(filters).distinct().order_by('-upload_date')
