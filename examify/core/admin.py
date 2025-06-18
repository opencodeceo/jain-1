from django.contrib import admin
from .models import UserProfile, Course, StudyMaterial, UserCourse

@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_by', 'course', 'upload_date')
    list_filter = ('course', 'uploaded_by')
    search_fields = ('title', 'description')
    readonly_fields = ('upload_date',)

# Basic registration for other models, can be customized further if needed
admin.site.register(UserProfile)
admin.site.register(Course)
admin.site.register(UserCourse)
