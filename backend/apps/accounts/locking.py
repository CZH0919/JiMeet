"""账号生命周期写入锁，必须先于招聘及会话行锁取得。"""
from apps.accounts.models import User
from apps.core.errors import NotAuthenticated


def lock_active_user(user):
    """在调用方事务内重新读取账号。注销先提交时拒绝旧请求写入。"""
    try:
        return User.objects.select_for_update(no_key=True).get(pk=user.pk, is_active=True)
    except User.DoesNotExist:
        raise NotAuthenticated() from None
