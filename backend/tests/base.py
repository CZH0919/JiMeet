from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.core.clock import freeze


class TxTestCase(TransactionTestCase):
    """不被外层事务包住，可验证真实提交与行锁行为。"""

    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def login(self, user):
        self.client.force_login(user)
        return user

    def freeze_at(self, moment):
        return freeze(moment)
