from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_user_cancelled_at")]

    operations = [
        migrations.AddField(
            model_name="registrationmailrequest",
            name="delivered",
            field=models.BooleanField(null=True),
        ),
    ]
