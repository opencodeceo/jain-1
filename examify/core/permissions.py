from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

class IsAdminOrOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admin users to edit/delete it.
    Assumes the object has an 'uploaded_by' attribute.
    """
    def has_object_permission(self, request, view, obj):
        # Admin users can access anything
        if request.user and request.user.is_staff:
            return True

        # Write permissions are only allowed to the owner of the snippet.
        # Assumes the model instance has an `uploaded_by` attribute.
        return obj.uploaded_by == request.user
