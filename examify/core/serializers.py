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
        fields = ('semester', 'region', 'department',
                  'mock_exams_completed', 'average_mock_exam_score', 'study_materials_uploaded_count',
                  'total_points') # Added total_points
        read_only_fields = ('mock_exams_completed', 'average_mock_exam_score',
                            'study_materials_uploaded_count', 'total_points') # Added total_points

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

class AIQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000, help_text="The user's query for the AI tutor.")


# --- AI Feedback Serializer ---
from .models import AIFeedback # Import AIFeedback

class AIFeedbackSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    # Ensure user is read-only if set by default, or not included in 'fields' if purely backend set.
    # CurrentUserDefault handles setting it, so it doesn't need to be in request payload.
    context_vector_ids = serializers.ListField(
       child=serializers.CharField(max_length=255),
       required=False,
       write_only=True, # Processed in create, not stored directly on AIFeedback model as a field
       help_text="List of vector_ids for DocumentChunks that were used as context."
    )
    ai_low_confidence = serializers.BooleanField(required=False, default=False,
                                               help_text="Indicates if the AI response was flagged for low confidence (can be set by user or system).")

    class Meta:
        model = AIFeedback
        fields = ['id', 'user', 'session_id', 'query_text', 'ai_response_text',
                  'rating', 'feedback_comment', 'interaction_type',
                  'context_vector_ids', 'ai_low_confidence', 'context_chunks', 'timestamp']
        read_only_fields = ['user', 'timestamp', 'id', 'context_chunks']
        # context_chunks is populated from context_vector_ids in create method

    def validate_rating(self, value):
        if value is not None and not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be an integer between 1 and 5.")
        return value

    def create(self, validated_data):
        context_vector_ids = validated_data.pop('context_vector_ids', [])
        # User is already handled by CurrentUserDefault via HiddenField
        # ai_low_confidence is directly passed to model if present in validated_data

        feedback_instance = AIFeedback.objects.create(**validated_data)

        if context_vector_ids:
            # Ensure DocumentChunk is imported at the top of serializers.py if not already
            # from .models import DocumentChunk (already there for other serializers)
            chunks = DocumentChunk.objects.filter(vector_id__in=context_vector_ids)
            if chunks.exists():
                feedback_instance.context_chunks.set(chunks)
            else:
                logger.warning(f"AIFeedback create: No DocumentChunks found for vector_ids: {context_vector_ids} for feedback {feedback_instance.id}")

        return feedback_instance


# --- Mock Exam Serializers ---

class MockExamQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = 'core.MockExamQuestion' # Use string import
        fields = ['id', 'question_text', 'question_type', 'options', 'order', 'points']
        # `options` might need custom handling if validation beyond JSON is needed for specific question_type.

class MockExamListSerializer(serializers.ModelSerializer):
    # For listing exams - less detail
    creator_username = serializers.StringRelatedField(source='creator.username', read_only=True)
    course_name = serializers.StringRelatedField(source='course.name', read_only=True)

    class Meta:
        model = 'core.MockExam' # Use string import
        fields = ['id', 'title', 'description', 'course', 'course_name', 'duration_minutes', 'creator', 'creator_username']
        # `creator` will show user ID, `creator_username` shows username.
        # `course` will show course ID, `course_name` shows course name.

class MockExamDetailSerializer(serializers.ModelSerializer):
    # For retrieving a single exam with questions
    questions = MockExamQuestionSerializer(many=True, read_only=True)
    creator_username = serializers.StringRelatedField(source='creator.username', read_only=True)
    course_name = serializers.StringRelatedField(source='course.name', read_only=True)

    class Meta:
        model = 'core.MockExam' # Use string import
        fields = ['id', 'title', 'description', 'course', 'course_name', 'duration_minutes',
                  'instructions', 'questions', 'creator', 'creator_username', 'created_at', 'updated_at']

class MockExamAttemptSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    # To show exam title instead of just ID for mock_exam field in attempt list/detail
    mock_exam_title = serializers.StringRelatedField(source='mock_exam.title', read_only=True)

    class Meta:
        model = 'core.MockExamAttempt' # Use string import
        fields = ['id', 'user', 'mock_exam', 'mock_exam_title', 'start_time', 'end_time', 'score', 'status', 'created_at']
        read_only_fields = ['start_time', 'end_time', 'score', 'user', 'mock_exam', 'mock_exam_title', 'created_at']
        # Status can be updated by the system (e.g., from 'in_progress' to 'completed').


# --- Image Query OCR Serializers ---
from .models import ImageQuery # Import ImageQuery

class ImageQuerySerializer(serializers.ModelSerializer): # For displaying results
    user = serializers.StringRelatedField(read_only=True)
    # image_url = serializers.ImageField(source='image', read_only=True) # Alternative if just URL needed
    image = serializers.ImageField(read_only=True) # Provides full URL for image

    class Meta:
        model = ImageQuery
        fields = ['id', 'user', 'image', 'extracted_text', 'status', 'timestamp', 'updated_at']
        read_only_fields = ['id', 'user', 'extracted_text', 'status', 'timestamp', 'updated_at', 'image']

class ImageQueryUploadSerializer(serializers.ModelSerializer): # For uploading image
    class Meta:
        model = ImageQuery
        fields = ['image'] # Only allow image upload for creation

class AnswerSubmissionSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer_text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    selected_choice_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=50)

    def validate(self, data):
        """
        Check that either answer_text or selected_choice_key is provided, but not necessarily both,
        depending on the question type (though that validation might be better done in the view
        where question_type is known).
        For now, just ensures at least one is present if the other is not.
        """
        if not data.get('answer_text') and not data.get('selected_choice_key'):
            # This validation might be too strict if a question type allows empty submission for an answer
            # For example, if a user skips a question.
            # Consider if this validation is truly needed here or if logic in view is better.
            # For now, allowing fully empty submission.
            pass
        return data

class MockExamSubmissionSerializer(serializers.Serializer):
    answers = AnswerSubmissionSerializer(many=True, allow_empty=False) # Must submit at least one answer.
