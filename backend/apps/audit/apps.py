from django.apps import AppConfig


class AuditConfig(AppConfig):
    """
    审计管理app配置类，用于配置审计管理app的相关设置

    ### Attributes
    - `name`: 应用的完整Python路径
    - `label`: 应用的简短标签，用于在Django中引用应用
    - `default_auto_field`: 默认的自动字段类型，用于模型的主键字段

    继承自 `AppConfig`，并定义了上面提到的三个属性。
    """
    name = "apps.audit"
    label = "audit"
    default_auto_field = "django.db.models.BigAutoField"
