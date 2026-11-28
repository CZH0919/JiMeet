from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recruitments", "0004_recruitment_note")]
    operations = [
        migrations.AddField(model_name="recruitment", name="anonymous_counts",
                            field=models.JSONField("注销申请的匿名计数", blank=True, default=dict)),
    ]
