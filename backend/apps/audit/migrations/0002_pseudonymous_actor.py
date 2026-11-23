from django.db import migrations, models
from django.db.models import Q


def redact_command_addresses(apps, schema_editor):
    """历史管理命令的原因保留操作说明，移除自动附加的目标邮箱。"""
    logs = apps.get_model("audit", "AuditLog").objects.using(schema_editor.connection.alias)
    for action, reason in (("admin_grant", "管理命令授予管理员权限"),
                           ("admin_revoke", "管理命令撤销管理员权限"),
                           ("password_init", "管理命令初始化账号密码")):
        logs.filter(action=action, target_type="user", reason__startswith=reason + "（目标 ",
                    reason__endswith="）").update(reason=reason)


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [
        migrations.AddField(model_name="auditlog", name="actor_ref",
                            field=models.UUIDField("去标识审计编号", null=True, editable=False)),
        migrations.RunPython(redact_command_addresses, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="auditlog", name="audit_actor_triple_chk"),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                condition=(
                    Q(actor__isnull=True, actor_ref__isnull=True, actor_role__isnull=True, actor_is_admin__isnull=True)
                    | Q(actor__isnull=False, actor_ref__isnull=True, actor_role__isnull=False, actor_is_admin__isnull=False)
                    | Q(actor__isnull=True, actor_ref__isnull=False, actor_role__isnull=False, actor_is_admin__isnull=False)
                ),
                name="audit_actor_triple_chk",
            ),
        ),
    ]
