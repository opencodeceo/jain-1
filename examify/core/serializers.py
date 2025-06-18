from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer, UserSerializer as BaseUserSerializer
from rest_framework import serializers
from .models import UserProfile, StudyMaterial, Course # Added Course for potential use if needed

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for UserProfile data.
    Handles fields: semester, region, department.
    Used nested within UserSerializer and UserCreateSerializer.
    """
    class Meta:
        model = UserProfile
        fields = ('semester', 'region', 'department')

class UserCreateSerializer(BaseUserCreateSerializer):
    """
    Extends Djoser's UserCreateSerializer to handle nested creation of UserProfile
    during user registration. The `userprofile` field accepts UserProfile data.
    """
    userprofile = UserProfileSerializer(required=False)

    class Meta(BaseUserCreateSerializer.Meta):
        fields = BaseUserCreateSerializer.Meta.fields + ('userprofile',)

    def create(self, validated_data):
        profile_data = validated_data.pop('userprofile', None)
        user = super().create(validated_data)
        UserProfile.objects.create(user=user, **(profile_data or {})) # Ensures profile is always created
        return user

class UserSerializer(BaseUserSerializer):
    """
    Extends Djoser's UserSerializer to include nested UserProfile data.
    The `userprofile` field can be used to view and update UserProfile information
    when interacting with Djoser's /users/me/ endpoint.
    """
    userprofile = UserProfileSerializer(required=False)

    class Meta(BaseUserSerializer.Meta):
        fields = BaseUserSerializer.Meta.fields + ('userprofile',)

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('userprofile', None)
        user = super().update(instance, validated_data)

        if profile_data is not None:
            profile_instance = getattr(user, 'userprofile', None)
            if profile_instance:
                for attr, value in profile_data.items():
                    setattr(profile_instance, attr, value)
                profile_instance.save()
            else: # Should not happen if UserCreateSerializer ensures creation
                UserProfile.objects.create(user=user, **profile_data)
        return user

class StudyMaterialSerializer(serializers.ModelSerializer):
    """
    Serializer for the StudyMaterial model.
    - `uploaded_by`: Read-only field, automatically set to the logged-in user upon creation (in the ViewSet).
    - `file`: Handled by DRF's FileField for uploads.
    """
    uploaded_by = serializers.ReadOnlyField(source='uploaded_by.username')
    # status field has been removed from the model

    class Meta:
        model = StudyMaterial
        fields = ('id', 'title', 'description', 'file', 'course', 'upload_date', 'uploaded_by')
        # `course` field will be a PrimaryKeyRelatedField by default.
        # `upload_date` is read-only by model definition (auto_now_add=True)

    def create(self, validated_data):
        # `uploaded_by` is set in the ViewSet's perform_create method.
        return super().create(validated_data)
