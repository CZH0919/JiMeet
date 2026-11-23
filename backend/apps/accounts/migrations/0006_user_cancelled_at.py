from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_registration_duplicate_receipt")]
    operations = [
        migrations.AddField(model_name="user", name="cancelled_at",
                            field=models.DateTimeField("注销时间", editable=False, null=True)),
        migrations.AddConstraint(model_name="user", constraint=models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | Q(is_active=False, is_admin=False, is_staff=False, is_superuser=False),
                name="cancelled_user_inactive_chk",
            )),
    ]
