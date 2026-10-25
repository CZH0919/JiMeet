from django.apps import apps
from django.db import connection
from django.db.models import ForeignKey, NOT_PROVIDED, PROTECT

from tests.base import TxTestCase


BUSINESS_MODELS = [
    ("accounts", "User"),
    ("recruitments", "Recruitment"),
    ("recruitments", "Tag"),
    ("recruitments", "RecruitmentTag"),
    ("applications", "Application"),
    ("notifications", "Notification"),
    ("notifications", "EmailLog"),
    ("audit", "AuditLog"),
    ("chat", "ChatConversation"),
    ("chat", "ChatMessage"),
]


class SchemaTest(TxTestCase):
    def test_all_business_tables_columns_constraints_and_indexes(self):
        with connection.cursor() as cursor:
            for app_label, name in BUSINESS_MODELS:
                model = apps.get_model(app_label, name)
                table = model._meta.db_table
                with self.subTest(table=table):
                    cursor.execute(
                        "SELECT column_name, is_nullable, column_default "
                        "FROM information_schema.columns "
                        "WHERE table_schema = current_schema() AND table_name = %s",
                        [table],
                    )
                    columns = {name: (nullable, default) for name, nullable, default in cursor.fetchall()}
                    fields = model._meta.local_concrete_fields
                    self.assertEqual(set(columns), {field.column for field in fields})
                    for field in fields:
                        with self.subTest(table=table, column=field.column):
                            nullable, default = columns[field.column]
                            self.assertEqual(nullable == "YES", field.null)
                            if field.db_default is not NOT_PROVIDED:
                                self.assertIsNotNone(default)
                            if isinstance(field, ForeignKey):
                                self.assertIs(field.remote_field.on_delete, PROTECT)
                                self.assertIsNotNone(field.remote_field.related_name)
                    constraints = connection.introspection.get_constraints(
                        cursor,
                        table,
                    )
                    for constraint in model._meta.constraints:
                        self.assertIn(constraint.name, constraints)
                        if hasattr(constraint, "fields"):
                            self.assertTrue(constraints[constraint.name]["unique"])
                        else:
                            self.assertTrue(constraints[constraint.name]["check"])
                    for index in model._meta.indexes:
                        self.assertIn(index.name, constraints)
                        self.assertTrue(constraints[index.name]["index"])

    def test_search_extension_and_gin_indexes(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')",
            )
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() AND tablename = 'recruitment'",
            )
            indexes = dict(cursor.fetchall())
        for name in ("recruitment_title_trgm", "recruitment_description_trgm"):
            with self.subTest(index=name):
                self.assertIn("USING gin", indexes[name])
                self.assertIn("gin_trgm_ops", indexes[name])
