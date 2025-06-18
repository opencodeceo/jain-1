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
    Uploaded materials are directly available based on visibility rules.
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
        """
        if self.action in ['list', 'create']:
            self.permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminOrOwner]
        else:
            self.permission_classes = [permissions.IsAuthenticated] # Default for other actions
        return super().get_permissions()

    def perform_create(self, serializer):
        """
        Allows authenticated users to upload new study materials.
        `uploaded_by` is set to the current user.
        """
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        """
        Allows the owner or an admin to update material details (e.g., title, description).
        """
        serializer.save()

    def get_queryset(self):
        """
        Lists study materials.
        - Admins see all materials.
        - Regular users see their own uploaded materials, materials for their enrolled courses,
          and materials from courses in their department.
        """
        user = self.request.user
        if user.is_staff: # Admins see all materials
            return StudyMaterial.objects.all().order_by('-upload_date')

        # For regular users:
        # 1. Their own uploaded materials
        own_materials = Q(uploaded_by=user)

        # Initialize Q objects for optional filters
        relevant_course_materials = Q()
        department_materials = Q()

        # 2. Materials relevant to their enrolled courses
        try:
            user_profile = user.userprofile
            user_courses_ids = list(UserCourse.objects.filter(user_profile=user_profile).values_list('course_id', flat=True))
            if user_courses_ids:
                relevant_course_materials = Q(course__id__in=user_courses_ids)
        except UserProfile.DoesNotExist:
            pass # No profile, so no course-based materials from enrollment

        # 3. Materials relevant to courses in their department
        try:
            # Ensure user_profile is available; it might have been fetched above or not.
            # This could be optimized by fetching user_profile once.
            user_profile = getattr(user, 'userprofile', None) or user.userprofile
            if user_profile and user_profile.department:
                department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
                if department_courses_ids:
                    department_materials = Q(course__id__in=department_courses_ids)
        except UserProfile.DoesNotExist:
            pass # No profile, so no department-based materials

        # Combine the conditions with OR
        combined_filters = own_materials | relevant_course_materials | department_materials

        # Ensure that if all Q objects are empty (e.g. new user with no profile data, no uploads)
        # it doesn't result in an empty filter call that might behave unexpectedly.
        # However, an empty Q object in a filter is typically a no-op, so it should be fine.
        # If combined_filters has no children, it means only own_materials could potentially be non-empty
        # or all are empty. If own_materials is also empty, filter will correctly return nothing.

        return StudyMaterial.objects.filter(combined_filters).distinct().order_by('-upload_date')

class RecommendedMaterialsView(generics.ListAPIView):
    """
    Provides a list of study materials recommended to the authenticated user.
    Recommendations are based on the user's enrolled courses and department, drawn from all available materials.
    """
    serializer_class = StudyMaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Returns a queryset of StudyMaterial objects recommended for the current user.
        Filters all available materials based on relevance to user's courses and department.
        """
        user = self.request.user
        try:
            user_profile = user.userprofile
        except UserProfile.DoesNotExist:
            return StudyMaterial.objects.none() # No profile, no recommendations

        # Fetch user's courses
        user_courses_ids = list(UserCourse.objects.filter(user_profile=user_profile).values_list('course_id', flat=True))

        # Base query: all materials (no longer filtering by status='approved')
        queryset = StudyMaterial.objects.all()

        # Filter conditions
        filters = Q() # Initialize with an empty Q object; will be an "AND" if not empty.
                      # Or, if we want to ensure at least one condition matches, might start differently.
                      # For "OR" logic as before for course/dept, this is fine.

        # 1. Materials for user's enrolled courses
        if user_courses_ids:
            filters |= Q(course__id__in=user_courses_ids)

        # 2. Materials matching user's department (if course match is not strong or for broader suggestions)
        if user_profile.department:
            department_courses_ids = list(Course.objects.filter(department=user_profile.department).values_list('id', flat=True))
            if department_courses_ids:
                filters |= Q(course__id__in=department_courses_ids)

        # If no specific filters are matched from profile (e.g., no courses, no department, or courses/department have no materials)
        if not filters.children: # If no course or department filters could be formed
            # If user has no courses and no department, or those have no materials,
            # this would return ALL study materials. This might be too broad.
            # Let's return an empty set if no specific criteria are met.
            # Alternatively, a fallback to "latest N materials" regardless of relevance could be an option.
            # For now, require some relevance.
            if not user_courses_ids and not (user_profile and user_profile.department):
                 return StudyMaterial.objects.none()
            # If filters is still empty here, it implies user might have courses/dept, but they yielded no materials.
            # Returning queryset.filter(filters) would effectively return all if filters is truly empty.
            # So, if filters is empty (no criteria applied), return none.
            if not filters.children: # Check again, as department_courses_ids might not have added to filters
                return StudyMaterial.objects.none()


        return queryset.filter(filters).distinct().order_by('-upload_date')
