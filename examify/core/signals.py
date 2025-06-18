import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Avg, F # Import F for atomic updates
from .models import MockExamAttempt, StudyMaterial, UserProfile, ActivityLog, AIFeedback, DocumentChunk # Ensure AIFeedback and DocumentChunk are imported
import logging

logger = logging.getLogger(__name__)

# Define points for actions (could be moved to settings.py or a config model)
POINTS_FOR_UPLOAD_MATERIAL = 10
POINTS_FOR_COMPLETE_MOCK_EXAM = 25 # Example

@receiver(post_save, sender=MockExamAttempt)
def update_progress_on_mock_exam_completion(sender, instance, created, **kwargs):
    """
    Updates UserProfile progress when a MockExamAttempt is completed.
    - Increments mock_exams_completed count.
    - Recalculates average_mock_exam_score.
    """
    # We are interested in updates when an attempt is marked as 'completed' and has a score.
    # The `created` flag might be true if it's created and immediately completed,
    # or it could be an update to an existing 'in_progress' attempt.
    if instance.status == 'completed' and instance.score is not None:
        activity_key = f"mock_exam_attempt_completed_{instance.id}" # Unique key for this event

        # Check if points were already awarded for this specific attempt completion
        if not ActivityLog.objects.filter(user=instance.user, action_type='complete_mock_exam', details=activity_key).exists():
            try:
                user_profile, profile_created = UserProfile.objects.get_or_create(user=instance.user)

                if profile_created:
                    logger.info(f"UserProfile created for user {instance.user.username} during signal handling for mock exam completion.")

                # Award points and log activity
                ActivityLog.objects.create(
                    user=instance.user,
                    action_type='complete_mock_exam',
                    points_awarded=POINTS_FOR_COMPLETE_MOCK_EXAM,
                    details=activity_key
                )
                # Atomically update total_points
                # Note: update() does not call save() on the model instance, so signals on UserProfile won't be triggered by this.
                # It also means user_profile instance needs to be refreshed if total_points is used later in this signal.
                UserProfile.objects.filter(user=instance.user).update(total_points=F('total_points') + POINTS_FOR_COMPLETE_MOCK_EXAM)
                logger.info(f"Awarded {POINTS_FOR_COMPLETE_MOCK_EXAM} points to user {instance.user.username} for completing mock exam attempt {instance.id}.")

                user_profile.refresh_from_db() # Refresh to get updated total_points

                # Update mock_exams_completed count (counts distinct completed mock exams)
                completed_exam_ids = MockExamAttempt.objects.filter(
                    user=instance.user,
                    status='completed'
                ).values_list('mock_exam_id', flat=True).distinct()
                user_profile.mock_exams_completed = len(completed_exam_ids)

                # Update average_mock_exam_score (considers all completed attempts with scores)
                completed_attempts_with_scores = MockExamAttempt.objects.filter(
                    user=instance.user,
                    status='completed',
                    score__isnull=False
                )
                if completed_attempts_with_scores.exists():
                    average_score = completed_attempts_with_scores.aggregate(Avg('score'))['score__avg']
                    user_profile.average_mock_exam_score = round(average_score, 2) if average_score is not None else None
                else:
                    user_profile.average_mock_exam_score = None

                user_profile.save() # Save mock_exams_completed and average_mock_exam_score
                logger.info(f"Progress updated for user {instance.user.username} after mock exam attempt {instance.id}. "
                            f"Exams completed: {user_profile.mock_exams_completed}, Avg score: {user_profile.average_mock_exam_score}, "
                            f"Total points: {user_profile.total_points}")

            except UserProfile.DoesNotExist: # Should be handled by get_or_create
                logger.error(f"UserProfile not found for user {instance.user.username} during point awarding for mock exam.")
            except Exception as e:
                logger.error(f"Error awarding points or updating progress for user {instance.user.username} (mock exam): {e}", exc_info=True)
        else:
            logger.info(f"Points for completing mock exam attempt {instance.id} already awarded to user {instance.user.username}. Only updating stats if needed.")
            # Even if points are already awarded, we might still want to update avg score / completed count
            # if this save operation is what finalizes the score or status.
            # The current logic re-calculates and saves mock_exams_completed and average_mock_exam_score
            # if the initial if condition (status=='completed' and score is not None) is met,
            # but the point awarding is skipped. This seems reasonable.
            # To ensure it updates, we'd need to fetch user_profile outside the points awarding block.
            try: # Corrected syntax: replaced { with :
                user_profile, _ = UserProfile.objects.get_or_create(user=instance.user)
                # Recalculate other progress stats
                completed_exam_ids = MockExamAttempt.objects.filter(user=instance.user, status='completed').values_list('mock_exam_id', flat=True).distinct()
                user_profile.mock_exams_completed = len(completed_exam_ids)
                completed_attempts_with_scores = MockExamAttempt.objects.filter(user=instance.user, status='completed', score__isnull=False)
                if completed_attempts_with_scores.exists():
                    average_score = completed_attempts_with_scores.aggregate(Avg('score'))['score__avg']
                    user_profile.average_mock_exam_score = round(average_score, 2) if average_score is not None else None
                else:
                    user_profile.average_mock_exam_score = None
                user_profile.save()
                logger.info(f"Progress stats (completed exams, avg score) re-evaluated for user {instance.user.username} for attempt {instance.id} (points previously awarded).")
            except Exception as e: # Corrected syntax: replaced { with : and removed extra }
                 logger.error(f"Error re-evaluating progress stats for user {instance.user.username} (mock exam, points previously awarded): {e}", exc_info=True)


@receiver(post_save, sender=StudyMaterial)
def update_progress_on_material_upload(sender, instance, created, **kwargs):
    """
    Updates UserProfile progress when a new StudyMaterial is created.
    - Increments study_materials_uploaded_count.
    """
    if created: # Only on new material creation
        if instance.uploaded_by: # Ensure uploaded_by is not None
            try:
                user_profile, profile_created = UserProfile.objects.get_or_create(user=instance.uploaded_by)

                if profile_created:
                    logger.info(f"UserProfile created for user {instance.uploaded_by.username} during signal handling for material upload.")

                # Award points and log activity
                ActivityLog.objects.create(
                    user=instance.uploaded_by,
                    action_type='upload_material',
                    points_awarded=POINTS_FOR_UPLOAD_MATERIAL,
                    details=f"material_id_{instance.id}"
                )
                # Atomically update total_points
                UserProfile.objects.filter(user=instance.uploaded_by).update(total_points=F('total_points') + POINTS_FOR_UPLOAD_MATERIAL)
                logger.info(f"Awarded {POINTS_FOR_UPLOAD_MATERIAL} points to user {instance.uploaded_by.username} for uploading material {instance.id}.")

                user_profile.refresh_from_db() # Refresh to get updated total_points

                # Update study_materials_uploaded_count
                user_profile.study_materials_uploaded_count = StudyMaterial.objects.filter(uploaded_by=instance.uploaded_by).count()
                user_profile.save() # Save material_upload_count
                logger.info(f"Progress updated for user {instance.uploaded_by.username} after material upload {instance.id}. "
                            f"Total uploads: {user_profile.study_materials_uploaded_count}, Total points: {user_profile.total_points}")
            except UserProfile.DoesNotExist: # Should be handled by get_or_create
                logger.error(f"UserProfile not found for user {instance.uploaded_by.username} during point awarding for material upload.")
            except Exception as e:
                logger.error(f"Error awarding points or updating material count for user {instance.uploaded_by.username} (material upload): {e}", exc_info=True)
        else:
            logger.warning(f"StudyMaterial {instance.id} created with no 'uploaded_by' user. Cannot update progress or award points.")


@receiver(post_save, sender=AIFeedback)
def update_document_chunk_flags_on_feedback(sender, instance, created, **kwargs):
    """
    Updates DocumentChunk review_flags_count based on AIFeedback.
    If feedback has a low rating (<=2) or ai_low_confidence is True,
    increment review_flags_count for all associated context_chunks.
    """
    if created: # Only process on new feedback creation
        increment_flag = False
        log_message_parts = []

        if instance.rating is not None and instance.rating <= 2:
            increment_flag = True
            log_message_parts.append(f"low rating ({instance.rating})")

        if instance.ai_low_confidence:
            increment_flag = True
            log_message_parts.append("AI low confidence flag")

        if increment_flag and instance.context_chunks.exists():
            reason_for_flagging = " and ".join(log_message_parts)
            logger.info(f"Feedback ID {instance.id} (session: {instance.session_id}) triggered review flag due to {reason_for_flagging}. Updating context chunk flags.")

            # Iterate and update. Using .update() on queryset is more efficient for batch updates.
            chunk_ids_to_update = list(instance.context_chunks.values_list('id', flat=True))
            if chunk_ids_to_update:
                updated_count = DocumentChunk.objects.filter(id__in=chunk_ids_to_update).update(review_flags_count=F('review_flags_count') + 1)
                logger.info(f"Incremented review_flags_count for {updated_count} DocumentChunk(s) linked to Feedback ID {instance.id}.")
                # Log individual chunks if needed for very detailed tracing, but batch update is better.
                # for chunk_id in chunk_ids_to_update:
                #    logger.info(f"Incremented review_flags_count for DocumentChunk ID {chunk_id}.")
        elif increment_flag: # Low rating or AI low confidence, but no context chunks linked
             logger.info(f"Feedback ID {instance.id} (session: {instance.session_id}) had {reason_for_flagging}, but no context chunks were linked to update.")
