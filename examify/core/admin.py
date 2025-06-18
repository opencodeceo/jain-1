from django.contrib import admin
from .models import (UserProfile, Course, StudyMaterial, UserCourse, DocumentChunk,
                     MockExam, MockExamQuestion, MockExamAttempt, MockExamAnswer, ActivityLog,
                     StudyGroup, StudyGroupMembership, AIFeedback, ImageQuery) # Add ImageQuery

# Register DocumentChunk if not already (assuming it might have been missed)
# A simple registration for now, can be customized later if needed.
if not admin.site.is_registered(DocumentChunk):
    @admin.register(DocumentChunk)
    class DocumentChunkAdmin(admin.ModelAdmin):
        list_display = ('study_material_title', 'vector_id', 'chunk_sequence_number', 'review_flags_count', 'created_at', 'embedding_provider')
        search_fields = ('study_material__title', 'chunk_text', 'vector_id')
        list_filter = ('embedding_provider', 'study_material__course', 'review_flags_count')
        raw_id_fields = ('study_material',)
        readonly_fields = ('vector_id', 'created_at', 'updated_at')


        def study_material_title(self, obj):
            return obj.study_material.title
        study_material_title.short_description = 'Study Material'
        study_material_title.admin_order_field = 'study_material__title'


@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_by', 'course', 'upload_date')
    list_filter = ('course', 'uploaded_by')
    search_fields = ('title', 'description')
    readonly_fields = ('upload_date',)

# Basic registration for other models, can be customized further if needed
if not admin.site.is_registered(UserProfile): admin.site.register(UserProfile)
if not admin.site.is_registered(Course): admin.site.register(Course)
if not admin.site.is_registered(UserCourse): admin.site.register(UserCourse)


class MockExamQuestionInline(admin.TabularInline): # Or StackedInline for more space
    model = MockExamQuestion
    extra = 1 # Number of empty forms to display
    fields = ('question_text', 'question_type', 'options', 'order', 'points')
    # Add ordering if needed, e.g., ordering = ('order',)

@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'creator', 'duration_minutes', 'created_at')
    list_filter = ('course', 'creator', 'created_at')
    search_fields = ('title', 'description')
    inlines = [MockExamQuestionInline] # Allows adding questions directly when creating/editing an exam

@admin.register(MockExamQuestion)
class MockExamQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'mock_exam', 'question_type', 'order', 'points')
    list_filter = ('mock_exam', 'question_type')
    search_fields = ('question_text',)
    raw_id_fields = ('mock_exam',)

@admin.register(MockExamAttempt)
class MockExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'mock_exam', 'status', 'score', 'start_time', 'end_time')
    list_filter = ('mock_exam', 'user', 'status')
    search_fields = ('user__username', 'mock_exam__title') # Search by related fields
    readonly_fields = ('start_time', 'created_at', 'updated_at', 'score') # Score is calculated

@admin.register(MockExamAnswer)
class MockExamAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt_info', 'question_short_text', 'is_correct', 'points_awarded')
    list_filter = ('attempt__mock_exam', 'is_correct', 'question__question_type') # Filter by exam via attempt
    search_fields = ('question__question_text', 'attempt__user__username')
    readonly_fields = ('answered_at',)
    raw_id_fields = ('attempt', 'question')


    def question_short_text(self, obj):
        return obj.question.question_text[:75] + '...' if len(obj.question.question_text) > 75 else obj.question.question_text
    question_short_text.short_description = 'Question (Shortened)'

    def attempt_info(self, obj):
        return f"{obj.attempt.user.username} - {obj.attempt.mock_exam.title}"
    attempt_info.short_description = 'Attempt'
    attempt_info.admin_order_field = 'attempt__user__username' # Allow sorting by username

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'points_awarded', 'timestamp', 'details')
    list_filter = ('action_type', 'user', 'timestamp')
    search_fields = ('user__username', 'details')
    readonly_fields = ('timestamp',)


class StudyGroupMembershipInline(admin.TabularInline):
    model = StudyGroupMembership
    extra = 1
    autocomplete_fields = ['user'] # If you have many users

@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'creator', 'created_at')
    list_filter = ('course', 'creator')
    search_fields = ('name', 'description')
    inlines = [StudyGroupMembershipInline]

@admin.register(StudyGroupMembership)
class StudyGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'role', 'date_joined')
    list_filter = ('group', 'role', 'user')
    search_fields = ('user__username', 'group__name')
    autocomplete_fields = ['user', 'group']

@admin.register(AIFeedback)
class AIFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user_display', 'session_id', 'interaction_type', 'rating', 'ai_low_confidence', 'timestamp', 'short_feedback_comment')
    list_filter = ('interaction_type', 'rating', 'timestamp', 'user', 'ai_low_confidence')
    search_fields = ('user__username', 'session_id', 'query_text', 'ai_response_text', 'feedback_comment')
    readonly_fields = ('timestamp', 'user', 'session_id', 'query_text', 'ai_response_text', 'context_chunks_display')
    fieldsets = (
        (None, {'fields': ('user', 'session_id', 'interaction_type', 'timestamp')}),
        ('Feedback Details', {'fields': ('rating', 'feedback_comment', 'query_text', 'ai_response_text', 'ai_low_confidence')}),
        ('Related Context', {'fields': ('context_chunks_display', 'context_chunks')}), # Display and editable widget
    )
    filter_horizontal = ('context_chunks',) # Better widget for ManyToMany

    def user_display(self, obj):
        return obj.user.username if obj.user else "Anonymous"
    user_display.short_description = "User"
    user_display.admin_order_field = 'user__username'

    def short_feedback_comment(self, obj):
        return (obj.feedback_comment[:75] + '...') if obj.feedback_comment and len(obj.feedback_comment) > 75 else obj.feedback_comment
    short_feedback_comment.short_description = 'Comment'

    def context_chunks_display(self, obj):
        # Display first 5 linked chunks. Make sure this is robust if no chunks.
        chunks = obj.context_chunks.all()
        if not chunks:
            return "None"
        return ", ".join([f"Chunk {c.id} (VecID: {c.vector_id})" for c in chunks[:5]])
    context_chunks_display.short_description = "Context Chunks (Sample)"


@admin.register(ImageQuery)
class ImageQueryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'timestamp', 'short_extracted_text')
    list_filter = ('status', 'user', 'timestamp')
    search_fields = ('user__username', 'id__iexact', 'extracted_text') # Use iexact for UUID search if needed
    readonly_fields = ('timestamp', 'updated_at', 'id', 'user', 'extracted_text', 'image_display')
    fields = ('user', 'image', 'image_display', 'status', 'extracted_text', 'timestamp', 'updated_at')

    def image_display(self, obj):
        from django.utils.html import format_html
        if obj.image and hasattr(obj.image, 'url'):
            return format_html('<img src="{}" width="150" height="auto" />', obj.image.url)
        return "No image"
    image_display.short_description = "Uploaded Image"

    def short_extracted_text(self, obj):
        if obj.extracted_text:
            return (obj.extracted_text[:100] + '...') if len(obj.extracted_text) > 100 else obj.extracted_text
        return None
    short_extracted_text.short_description = 'Extracted Text (Start)'
