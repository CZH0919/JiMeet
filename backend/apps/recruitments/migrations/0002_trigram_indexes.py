from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """先启用 pg_trgm，再创建招聘标题和描述的 GIN 搜索索引。"""

    dependencies = [("recruitments", "0001_initial")]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="recruitment",
            index=GinIndex(fields=["title"], opclasses=["gin_trgm_ops"], name="recruitment_title_trgm"),
        ),
        migrations.AddIndex(
            model_name="recruitment",
            index=GinIndex(fields=["description"], opclasses=["gin_trgm_ops"], name="recruitment_description_trgm"),
        ),
    ]
