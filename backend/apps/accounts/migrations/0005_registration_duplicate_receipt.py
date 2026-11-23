from django.db import migrations, models


def expire_unclassified_grants(apps, schema_editor):
    """清除无法区分新旧账号的短时建号资格，保留账号、投递记录和未验验证码。"""
    verification = apps.get_model("accounts", "RegistrationVerification")
    verification.objects.using(schema_editor.connection.alias).filter(
        purpose="registration", verified_at__isnull=False,
    ).update(verified_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_remove_registrationverification_reg_verify_email_session_uniq_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrationverification",
            name="duplicate_verified_at",
            field=models.DateTimeField("已有账号核验时间", null=True),
        ),
        migrations.RunPython(expire_unclassified_grants, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="registrationverification",
            constraint=models.CheckConstraint(
                condition=models.Q(duplicate_verified_at__isnull=True) | models.Q(
                    purpose="registration", verified_at__isnull=True, code_digest="", code_expires_at__isnull=True,
                ),
                name="reg_duplicate_receipt_chk",
            ),
        ),
    ]
