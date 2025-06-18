from django.contrib import admin
from .models import UserProfile, Course, StudyMaterial, UserCourse

@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded_by', 'course', 'status', 'upload_date')
    list_filter = ('status', 'course', 'uploaded_by')
    search_fields = ('title', 'description')
    actions = ['approve_materials', 'reject_materials']
    readonly_fields = ('upload_date',) # Keep upload_date read-only in admin as it's auto_now_add

    def approve_materials(self, request, queryset):
        queryset.update(status='approved')
    approve_materials.short_description = "Mark selected materials as Approved"

    def reject_materials(self, request, queryset):
        queryset.update(status='rejected')
    reject_materials.short_description = "Mark selected materials as Rejected"

# Basic registration for other models, can be customized further if needed
admin.site.register(UserProfile)
admin.site.register(Course)
admin.site.register(UserCourse)
