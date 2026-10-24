from io import StringIO

from django.core.management import call_command

from apps.recruitments.models import Tag
from apps.recruitments.seed import PRESET_TAGS
from tests.base import TxTestCase


class SeedTagsTest(TxTestCase):
    def test_creates_all_presets_in_order(self):
        call_command("seed_tags", stdout=StringIO())
        self.assertEqual(Tag.objects.count(), 19)
        self.assertEqual(
            list(Tag.objects.order_by("sort_order").values_list("name", flat=True)),
            PRESET_TAGS,
        )
        self.assertFalse(Tag.objects.filter(is_active=False).exists())

    def test_rerun_preserves_disabled_and_custom_tags(self):
        call_command("seed_tags", stdout=StringIO())
        original_ids = dict(Tag.objects.values_list("name", "pk"))
        Tag.objects.filter(name=PRESET_TAGS[0]).update(is_active=False, sort_order=999)
        custom = Tag.objects.create(name="自定义领域", sort_order=100, is_active=False)
        call_command("seed_tags", stdout=StringIO())
        self.assertEqual(Tag.objects.count(), 20)
        self.assertEqual(
            dict(Tag.objects.filter(name__in=PRESET_TAGS).values_list("name", "pk")),
            original_ids,
        )
        disabled = Tag.objects.get(name=PRESET_TAGS[0])
        self.assertFalse(disabled.is_active)
        self.assertEqual(disabled.sort_order, 0)
        custom.refresh_from_db()
        self.assertFalse(custom.is_active)
        self.assertEqual(custom.sort_order, 100)
