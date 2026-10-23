import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

from apps.core.choices import Role


def _new_uid() -> str:
    return uuid.uuid4().hex


class UserManager(BaseUserManager):
    """
    用户管理器，用于创建和管理用户对象

    ### Methods
    - `_create_user`: 创建用户的内部方法
    - `create_user`: 创建普通用户
    - `create_superuser`: 创建超级用户

    """
    use_in_migrations = True

    def _create_user(self, real_id, name, email, password=None, **extra_fields):
        """
        创建用户的内部方法

        Params:
            real_id: 用户的学号或工号，不能为空
            name: 用户的真实姓名，不能为空
            email: 用户的邮箱地址
            password: 用户的密码，可选
            extra_fields: 其他额外的字段

        Returns:
            创建的用户对象
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
        # 这里开始，因为一直未能明确到底用统一认证还是邮箱和密码，所以这样写。
        # 用统一认证，就是 sso_subject 不为空，password 为空。
        # 用邮箱和密码，就是 sso_subject 为空，password 不为空。
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, real_id, name, email, password=None, **extra_fields):
        """
        按照输入的信息创建一个普通用户

        Params:
            real_id: 用户的学号或工号，不能为空
            name: 用户的真实姓名，不能为空
            email: 用户的邮箱地址
            password: 用户的密码，可选，默认 None
            extra_fields: 其他额外的字段

        Returns:
            创建的用户对象
        """
        extra_fields.setdefault("role", Role.STUDENT)
        extra_fields.setdefault("nickname", name)
        return self._create_user(real_id, name, email, password, **extra_fields)

    def create_superuser(self, real_id, name, email, password, **extra_fields):
        """
        按照输入的信息创建一个超级用户

        Params:
            real_id: 用户的学号或工号，不能为空
            name: 用户的真实姓名，不能为空
            email: 用户的邮箱地址
            password: 用户的密码，不能为空
            extra_fields: 其他额外的字段

        Returns:
            创建的超级用户对象
        """
        extra_fields.setdefault("role", Role.TEACHER)
        extra_fields.setdefault("nickname", name)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(real_id, name, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    用户模型

    这里和backend/file/design_manuscript/database.md是完全一致的
    自增id不需要写，Django会自动创建一个自增id作为主键。
    
    包含的字段和解释如下：
    | 字段名称 | 数据类型 | 约束 | 说明 |
    |---------|---------|------|-----|
    | id | BIGINT | PRIMARY KEY, 自增 | 数据库内的自增标识，不会对外公开 |
    | uid | VARCHAR(32) | NOT NULL, UNIQUE | 对外使用的的uid，随机生成（`uuid4().hex`，恰好 32 位），防止被遍历爬取|
    | real_id | VARCHAR(32) | NOT NULL, UNIQUE | 真实的学号/工号，内部使用，不对外公开|
    | nickname | VARCHAR(32)  | NOT NULL | 可以自主定义的用户名 |
    | name | VARCHAR(32)  | NOT NULL | 真实的姓名 |
    | email | VARCHAR(254) | NOT NULL（必须是同济邮箱格式） | 邮箱号，用于登录预留与邮件通知 |
    | role | VARCHAR(32)  | NOT NULL，CHECK (role IN ('student','teacher')) | 用户角色，只能是`student` 或 `teacher`，登录时依据学号/工号判定 |
    | is_admin | BOOLEAN | NOT NULL，默认 FALSE | 是否拥有管理员权限 |
    | is_active | BOOLEAN | NOT NULL，默认 TRUE | 是否启用 |
    | password | VARCHAR(128) | NOT NULL DEFAULT '' | Django 哈希格式密码。“邮箱登录”预留；若只走统一身份认证则保持空串 |
    | sso_subject | VARCHAR(191) | UNIQUE，可空 | 统一身份认证返回的稳定用户标识；与密码登录可并存 |
    | email_notify_enabled | BOOLEAN | NOT NULL，默认 TRUE | 是否接收邮件通知（站内通知始终生成） |
    | privacy_consented_at | TIMESTAMPTZ | 可空 | 确认个人信息处理告知的时间；为空时不允许提交申请（首次填写简历前须确认） |
    | last_login | TIMESTAMPTZ | 可空 | Django 内置字段，由 `AbstractBaseUser` 提供 |
    | created_at | TIMESTAMPTZ | NOT NULL | 注册时间、管理员/个人主页排序 |
    | updated_at | TIMESTAMPTZ | NOT NULL | 个人资料最近修改时间 |

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

    # 接受上述参数后，UserManager 会返回一个 User 对象，User 对象会调用 save 方法保存到数据库中。
    objects = UserManager()

    USERNAME_FIELD = "real_id"
    REQUIRED_FIELDS = ["name", "email"]

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
        return f"User({self.pk})"
