"""认证身份与提供方接口；开发身份可用，正式 CAS 提供方为预留实现。"""
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
    """认证提供方抽象接口，约定授权地址生成与回调身份交换。"""

    @abstractmethod
    def authorize_url(self, state: str) -> str:
        """授权地址生成抽象入口，由具体提供方实现。

        Args:
            state: 调用方生成的认证状态标识。

        Raises:
            NotImplementedError: 直接执行基类方法。
        """
        raise NotImplementedError

    @abstractmethod
    def exchange(self, callback_params: dict) -> SSOIdentity:
        """回调身份交换抽象入口，由具体提供方实现。

        Args:
            callback_params: 回调或开发登录参数映射。

        Raises:
            NotImplementedError: 直接执行基类方法。
        """
        raise NotImplementedError


class DevSSOProvider(SSOProvider):
    """
    开发身份生成器，只能由受配置开关保护的开发登录入口使用。
    """

    def authorize_url(self, state: str) -> str:
        """返回开发登录入口，不执行外部认证跳转。

        Args:
            state: 为保持提供方接口一致而接收，开发实现不使用。

        Returns:
            str: 相对路径 /api/v1/auth/dev-login。
        """
        return "/api/v1/auth/dev-login"

    def exchange(self, callback_params: dict) -> SSOIdentity:
        """从开发登录参数构造稳定的身份对象。

        Args:
            callback_params: 经输入校验的 real_id 及可选 name、email；未提供姓名和邮箱时按编号生成。

        Returns:
            SSOIdentity: subject 为 dev: 加编号；具体身份有效性由账号服务继续校验。
        """
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
        """正式 CAS 的授权地址生成预留入口。

        Args:
            state: 调用方生成的认证状态标识。

        Raises:
            NotImplementedError: 学校 SSO 尚未接入；当前调用始终抛出 reserved。
        """
        raise NotImplementedError("reserved")

    def exchange(self, callback_params: dict) -> SSOIdentity:
        """正式 CAS 的回调身份交换预留入口。

        Args:
            callback_params: 回调或开发登录参数映射。

        Raises:
            NotImplementedError: 学校 SSO 尚未接入；当前调用始终抛出 reserved。
        """
        raise NotImplementedError("reserved")
