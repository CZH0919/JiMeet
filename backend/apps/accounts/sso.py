"""SSO 身份与提供方抽象；正式 CAS 接入本周仅预留。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SSOIdentity:
    """认证提供方验证后的最小身份信息，不包含 ticket 或 token。"""

    real_id: str
    name: str
    email: str
    subject: str


class SSOProvider(ABC):
    """
    认证跳转与身份交换的统一接口。

    ### 这里由于未知学校的正式认证规范，暂时全部返回 NotImplementedError，开发期使用 DevSSOProvider。
    """

    @abstractmethod
    def authorize_url(self, state: str) -> str:
        """
        返回携带 state 的认证地址。
        """
        raise NotImplementedError

    @abstractmethod
    def exchange(self, callback_params: dict) -> SSOIdentity:
        """交换已验证的回调信息，不保存认证凭证。"""
        raise NotImplementedError


class DevSSOProvider(SSOProvider):
    """
    开发身份生成器，只能由受配置开关保护的开发登录入口使用。
    """

    def authorize_url(self, state: str) -> str:
        """开发期直接使用 dev-login，不提供模拟跳转。"""
        return "/api/v1/auth/dev-login"

    def exchange(self, callback_params: dict) -> SSOIdentity:
        """用编号生成稳定 subject，未提供姓名和邮箱时使用开发默认值。"""
        real_id = callback_params.get("real_id", "").strip()
        return SSOIdentity(
            real_id=real_id,
            name=callback_params.get("name", real_id),
            email=callback_params.get("email", f"{real_id}@tongji.edu.cn"),
            subject=f"dev:{real_id}",
        )


class CasSSOProvider(SSOProvider):
    """等待学校正式认证规范的 CAS 接入位置。"""

    def authorize_url(self, state: str) -> str:
        """预留正式认证跳转。"""
        raise NotImplementedError("reserved")

    def exchange(self, callback_params: dict) -> SSOIdentity:
        """预留正式身份交换。"""
        raise NotImplementedError("reserved")
