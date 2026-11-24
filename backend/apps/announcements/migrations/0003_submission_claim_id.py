from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("announcements", "0002_announcement_submitted_by_announcementsubmission"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcementsubmission",
            name="claim_id",
            field=models.UUIDField("领取批次", null=True, editable=False),
        ),
        migrations.AddConstraint(
            model_name="announcementsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(claim_id__isnull=True) | models.Q(
                    status="pending", claimed_by__isnull=False, claimed_until__isnull=False,
                ),
                name="ann_submission_claim_batch_chk",
            ),
        ),
    ]
