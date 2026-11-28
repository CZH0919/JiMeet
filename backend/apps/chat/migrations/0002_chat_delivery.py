from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatSendPause",
            fields=[
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT, primary_key=True, related_name="chat_send_pause",
                    serialize=False, to=settings.AUTH_USER_MODEL, verbose_name="发送者",
                )),
                ("blocked_until", models.DateTimeField("暂停截止时间")),
            ],
            options={"db_table": "chat_send_pause"},
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="expires_at",
            field=models.GeneratedField(
                db_index=True, db_persist=True,
                expression=models.Func(
                    models.F("created_at"),
                    template="(((%(expressions)s AT TIME ZONE 'Asia/Shanghai') + INTERVAL '6 months') AT TIME ZONE 'Asia/Shanghai')",
                    output_field=models.DateTimeField(),
                ),
                output_field=models.DateTimeField(), verbose_name="消息到期时间",
            ),
        ),
        # PostgreSQL 不从生成表达式推断列的非空约束。
        migrations.RunSQL(
            "ALTER TABLE chat_message ALTER COLUMN expires_at SET NOT NULL",
            "ALTER TABLE chat_message ALTER COLUMN expires_at DROP NOT NULL",
        ),
        migrations.AddIndex(
            model_name="chatmessage", index=models.Index(fields=["sender", "created_at"], name="chat_message_sender_time_idx"),
        ),
    ]
