from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recruitments", "0003_stage4_rules")]

    operations = [
        migrations.AddField(
            model_name="recruitment",
            name="note",
            field=models.TextField("补充说明", null=True, blank=True),
        ),
    ]
