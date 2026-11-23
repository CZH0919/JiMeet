from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("applications", "0003_resume_removal")]
    operations = [
        migrations.AlterField(
            model_name="applicationstatushistory", name="reason",
            field=models.CharField("变更原因", max_length=32, choices=[
                ("accept", "接受"), ("reject_manual", "主动拒绝"), ("withdraw", "撤回"),
                ("auto_full", "满员自动拒绝"), ("auto_window", "处理期限届满"),
                ("publisher_cancelled", "发布者注销"), ("delete_invalid", "招聘删除失效"),
            ]),
        ),
        migrations.RemoveConstraint(model_name="applicationstatushistory", name="app_history_transition_chk"),
        migrations.RemoveConstraint(model_name="applicationstatushistory", name="app_history_actor_chk"),
        migrations.AddConstraint(
            model_name="applicationstatushistory",
            constraint=models.CheckConstraint(
                condition=(
                    Q(from_status="processing", to_status="accepted", reason="accept")
                    | Q(from_status="processing", to_status="rejected", reason__in=["reject_manual", "auto_full", "auto_window", "publisher_cancelled"])
                    | Q(from_status="processing", to_status="withdrawn", reason="withdraw")
                    | Q(from_status__in=["processing", "accepted"], to_status="invalid", reason="delete_invalid")
                ),
                name="app_history_transition_chk",
            ),
        ),
        migrations.AddConstraint(
            model_name="applicationstatushistory",
            constraint=models.CheckConstraint(
                condition=(
                    Q(reason__in=["auto_full", "auto_window", "publisher_cancelled"], actor__isnull=True)
                    | (Q(reason__in=["accept", "reject_manual", "withdraw", "delete_invalid"]) & Q(actor__isnull=False))
                ),
                name="app_history_actor_chk",
            ),
        ),
    ]
