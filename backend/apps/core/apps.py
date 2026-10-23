from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    核心管理app配置类，用于配置核心管理app的相关设置

    ### Attributes
    - `name`: 应用的完整Python路径
    - `label`: 应用的简短标签，用于在Django中引用应用
    - `default_auto_field`: 默认的自动字段类型，用于模型的主键字段
    
    它继承自 `AppConfig`，并定义了上面提到的三个属性。  
    """
    name = "apps.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"
