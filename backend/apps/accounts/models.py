import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

from apps.core.choices import Role


def _new_uid() -> str:
    """生成不含学工号信息的公开用户标识。

    Returns:
        str: UUID4 的 32 位十六进制字符串。
    """
    return uuid.uuid4().hex


class UserManager(BaseUserManager):
    """创建用户并设置密码存储、身份默认值及昵称。"""
    use_in_migrations = True

    def _create_user(self, real_id, name, email, password=None, **extra_fields):
        """保存规范化邮箱及密码存储状态的用户。

        Args:
            real_id: 非空的内部学号或工号。
            name: 非空姓名。
            email: 邮箱字符串，由 Django 规范化；域名准入由上层服务校验。
            password: 原始密码；省略或为空时设置不可用密码，不提供密码登录。
            extra_fields: 角色、昵称、SSO 标识等 User 模型字段。

        Returns:
            User: 已保存的用户对象。

        Raises:
            ValueError: real_id 或 name 为空。
            IntegrityError: 数据库唯一性或字段约束冲突。
        """
        if not real_id:
            raise ValueError("real_id 不能为空")
        if not name:
            raise ValueError("name 不能为空")
        user = self.model(
            real_id=real_id,
            name=name,
            email=self.normalize_email(email),
            **extra_fields,
        )
        # 无密码时使用 Django 的不可用密码标记，保留身份提供方登录路径。
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, real_id, name, email, password=None, **extra_fields):
        """创建用户，默认学生角色并生成与姓名分离的昵称。

        Args:
            real_id: 非空的内部学号或工号。
            name: 非空姓名。
            email: 邮箱字符串，由 Django 规范化；域名准入由上层服务校验。
            password: 原始密码；省略或为空时设置不可用密码，不提供密码登录。
            extra_fields: 角色、昵称、SSO 标识等 User 模型字段。

        Returns:
            User: 已保存的用户对象。

        Raises:
            ValueError: real_id 或 name 为空。
            IntegrityError: 数据库唯一性或字段约束冲突。
        """
        extra_fields.setdefault("role", Role.STUDENT)
        if "nickname" not in extra_fields:
            nickname = f"同学_{uuid.uuid4().hex[:12]}"
            # 即使真实姓名恰好与生成值相同，也保持默认昵称与姓名分离。
            extra_fields["nickname"] = nickname if nickname != name else f"用户_{uuid.uuid4().hex[:12]}"
        return self._create_user(real_id, name, email, password, **extra_fields)

    def create_superuser(self, real_id, name, email, password, **extra_fields):
        """创建默认带业务管理员及 Django 管理权限的用户。

        Args:
            real_id: 非空的内部学号或工号。
            name: 非空姓名。
            email: 邮箱字符串，由 Django 规范化；域名准入由上层服务校验。
            password: 调用时必须提供该参数；非空时进行哈希存储，空值仍会设置不可用密码。
            extra_fields: 可覆盖默认教师角色、昵称及管理员标记的模型字段。

        Returns:
            User: 已保存的用户对象。

        Raises:
            ValueError: real_id 或 name 为空。
            IntegrityError: 数据库唯一性或字段约束冲突。
        """
        extra_fields.setdefault("role", Role.TEACHER)
        extra_fields.setdefault("nickname", name)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(real_id, name, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    用户模型，对应 database.md 1.1 的 app_user 表。

    ### Attributes
    - `uid` / `real_id`: 对外随机标识（uuid4().hex，32 位）与内部学号/工号，
      均唯一，real_id 不对外公开
    - `nickname` / `name`: 可自定义的昵称与真实姓名
    - `email`: 同济邮箱，按小写唯一，用于邮箱密码登录；后缀校验不代表邮箱归属已核验
    - `role`: 用户角色，只能是 student 或 teacher
    - `is_admin` / `is_active`: 业务管理员标记与账号是否启用，业务权限只看 is_admin
    - `password` / `sso_subject`: Django 哈希密码与统一身份认证稳定标识，
      数据库要求 password 非空或 sso_subject 非空，不保证存在可用的密码认证方式
    - `email_notify_enabled`: 保留的邮件偏好兼容字段，当前不触发邮件发送
    - `privacy_consented_at`: 确认个人信息处理告知的时间，为空时不允许提交申请
    - `is_staff` / `is_superuser` / `groups` / `user_permissions`: 仅 Django Admin
      访问权限，不代表业务权限
    - `last_login` / `created_at` / `updated_at`: 登录时间、注册时间与资料最近修改时间

    id 为 Django 自主生成的自增主键，不对外公开；邮箱唯一与登录方式由数据库约束保证，
    访问权限由应用层校验。
    """
    uid = models.CharField(
        "对外标识", max_length=32, unique=True, default=_new_uid, editable=False
    )
    real_id = models.CharField("学号/工号", max_length=32, unique=True)
    nickname = models.CharField("昵称", max_length=32)
    name = models.CharField("姓名", max_length=32)
    email = models.EmailField("邮箱", max_length=254)
    role = models.CharField("角色", max_length=32, choices=Role.choices)
    is_admin = models.BooleanField("管理员", default=False, db_default=False)
    is_active = models.BooleanField("启用", default=True, db_default=True)
    password = models.CharField("密码", max_length=128, default="", db_default="")
    sso_subject = models.CharField(
        "统一身份认证标识", max_length=191, unique=True, null=True, blank=True
    )
    email_notify_enabled = models.BooleanField("邮件通知", default=True, db_default=True)
    privacy_consented_at = models.DateTimeField("隐私告知确认时间", null=True, blank=True)
    # 仅供 Django Admin 使用，业务权限一律看 is_admin。
    is_staff = models.BooleanField("可登录 Django Admin", default=False, db_default=False)
    created_at = models.DateTimeField("创建时间", db_default=Now())
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "real_id"
    REQUIRED_FIELDS = ["name", "email", "nickname"]

    class Meta:
        db_table = "app_user"
        verbose_name = "用户"
        verbose_name_plural = "用户"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_lower_uniq"),
            models.CheckConstraint(condition=Q(role__in=Role.values), name="user_role_chk"),
            models.CheckConstraint(
                condition=~Q(password="") | Q(sso_subject__isnull=False),
                name="user_login_method_chk",
            ),
        ]

    def __str__(self) -> str:
        """返回仅含内部主键的对象标识，避免输出身份资料。

        Returns:
            str: User(主键)。
        """
        return f"User({self.pk})"


class AuthFailure(models.Model):
    """
    注册/登录失败计数记录，对应 database.md 4.2 的 auth_failure 表。

    ### Attributes
    - `key_hash`: 限流键的 SHA-256 摘要（邮箱或来源 IP），不保存明文
    - `kind`: 失败发生的操作，login 或 register
    - `created_at`: 失败发生时间；窗口计数与惰性清理按该时间过滤

    采用插入即计数（INSERT-only），并发失败不会互相覆盖或丢失。
    """

    key_hash = models.CharField("键摘要", max_length=64)
    kind = models.CharField("操作类型", max_length=16)
    created_at = models.DateTimeField("失败时间", db_default=Now())

    class Meta:
        db_table = "auth_failure"
        indexes = [
            models.Index(fields=["key_hash", "created_at"], name="auth_failure_key_idx"),
        ]

    def __str__(self) -> str:
        """返回仅含数据库主键的标识，不输出键摘要。"""
        return f"AuthFailure({self.pk})"
