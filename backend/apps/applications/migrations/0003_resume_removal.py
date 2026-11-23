from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("applications", "0002_stage4_rules")]
    operations = [
        migrations.CreateModel(
            name="ResumeRemoval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=255, unique=True)),
            ],
            options={"db_table": "resume_removal"},
        ),
    ]
