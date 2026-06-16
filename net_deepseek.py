"""
net_deepseek.py — DeepSeek API 余额查询引擎

- 通过 urllib 调用 GET https://api.deepseek.com/user/balance
- 每 300 秒最多查询一次，避免触发限流
- 存储余额快照和错误状态供 UI 读取
"""

import json
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BalanceInfo:
    """DeepSeek 账户余额快照（不可变）。"""
    currency: str
    total_balance: str      # 总余额（字符串，保持精度）
    granted_balance: str    # 赠送余额
    topped_up_balance: str  # 充值余额
    is_available: bool      # 是否可用（余额 > 0）


# ------------------------------------------------------------------
# 异常类型
# ------------------------------------------------------------------


class DeepSeekError(Exception):
    """DeepSeek API 异常基类。"""


class DeepSeekAuthError(DeepSeekError):
    """API Key 无效 (HTTP 401)。"""


class DeepSeekRateLimitError(DeepSeekError):
    """请求频率过高 (HTTP 429)。"""


class DeepSeekNetworkError(DeepSeekError):
    """网络连接或超时错误。"""


# ------------------------------------------------------------------
# 余额查询引擎
# ------------------------------------------------------------------


class DeepSeekBalanceChecker:
    """DeepSeek 余额查询引擎。

    用法:
        checker = DeepSeekBalanceChecker(config)
        checker.try_refresh()          # 每 300s 允许一次实际请求
        balance = checker.balance      # BalanceInfo | None
        error = checker.last_error     # str | None
    """

    POLL_INTERVAL = 300   # 查询间隔（秒）
    TIMEOUT = 10           # HTTP 请求超时（秒）
    API_URL = "https://api.deepseek.com/user/balance"

    def __init__(self, config):
        """config: ConfigStore 实例，读取 deepseek_api_key。"""
        self._config = config
        self._last_balance: Optional[BalanceInfo] = None
        self._last_fetch_time: float = 0.0
        self._last_error: Optional[str] = None

        # 后台 fetch 状态（仅主线程访问）
        self._fetching = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._fetch_result_data: list = []
        self._fetch_error_data: list = []

    # ------------------------------------------------------------------
    # 公开属性
    # ------------------------------------------------------------------

    @property
    def balance(self) -> Optional[BalanceInfo]:
        """最近一次成功获取的余额信息，未获取过则为 None。"""
        return self._last_balance

    @property
    def last_error(self) -> Optional[str]:
        """最近一次错误描述字符串，无错误则为 None。"""
        return self._last_error

    def is_configured(self) -> bool:
        """是否已配置 API Key。"""
        key = self._config.deepseek_api_key
        return bool(key and key.strip())

    # ------------------------------------------------------------------
    # 查询逻辑
    # ------------------------------------------------------------------

    def try_refresh(self) -> bool:
        """如果到了轮询间隔，启动后台线程查询余额。

        不阻塞主线程。调用方需要随后调用 poll() 来收集结果。
        返回 True 表示已启动后台请求。
        """
        if not self.is_configured() or self._fetching:
            return False

        now = time.time()
        if now - self._last_fetch_time < self.POLL_INTERVAL:
            return False

        self._last_fetch_time = now
        self._fetching = True

        # 使用可变容器传递结果，避免跨线程属性写入的可见性问题
        result_holder: list = []
        error_holder: list = []

        def _run():
            try:
                result_holder.append(self._fetch())
            except Exception as e:
                error_holder.append(e)

        self._fetch_result_data = result_holder
        self._fetch_error_data = error_holder
        self._fetch_thread = threading.Thread(target=_run, daemon=True)
        self._fetch_thread.start()
        return True

    def poll(self) -> None:
        """主线程调用：检查后台 fetch 是否完成并处理结果。

        非阻塞（is_alive() 立即返回）。应在每次 _on_tick 中调用。
        结果通过 balance / last_error 属性获取。
        """
        if not self._fetching:
            return False
        if self._fetch_thread is None or self._fetch_thread.is_alive():
            return False

        # 线程已完成，收集结果
        self._fetching = False
        self._fetch_thread = None

        error = self._fetch_error_data[0] if self._fetch_error_data else None
        result = self._fetch_result_data[0] if self._fetch_result_data else None
        self._fetch_error_data = []
        self._fetch_result_data = []

        self._process_fetch_result(result, error)

    def _process_fetch_result(
        self, result: Optional[BalanceInfo], error: Optional[Exception]
    ) -> None:
        """在主线程处理 fetch 结果，更新 balance / last_error 属性。"""
        if error is not None:
            if isinstance(error, DeepSeekAuthError):
                self._last_error = "API Key 无效，请检查后重新设置"
            elif isinstance(error, DeepSeekRateLimitError):
                self._last_error = "请求过于频繁，稍后重试"
            elif isinstance(error, DeepSeekNetworkError):
                self._last_error = "网络连接失败，请检查网络"
            elif isinstance(error, DeepSeekError):
                self._last_error = "查询余额失败"
            else:
                self._last_error = "未知错误"
            return

        self._last_error = None
        self._last_balance = result

    def reset(self) -> None:
        """重置状态，使下次 try_refresh 立即查询。"""
        self._last_fetch_time = 0.0
        self._last_error = None
        self._fetching = False
        self._fetch_thread = None
        self._fetch_result_data = []
        self._fetch_error_data = []

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------

    def _fetch(self) -> BalanceInfo:
        """执行 HTTP GET 请求，返回 BalanceInfo。"""
        req = urllib.request.Request(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self._config.deepseek_api_key}",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise DeepSeekAuthError("API Key 无效") from e
            if e.code == 402:
                raise DeepSeekError("余额不足") from e
            if e.code == 429:
                raise DeepSeekRateLimitError("请求过于频繁") from e
            raise DeepSeekError(f"HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise DeepSeekNetworkError(str(e.reason)) from e
        except (OSError, TimeoutError) as e:
            raise DeepSeekNetworkError(str(e)) from e

        # 解析响应 JSON
        try:
            is_available = data.get("is_available", False)
            infos = data.get("balance_infos", [])
            if infos:
                bi = infos[0]
                return BalanceInfo(
                    currency=bi.get("currency", "CNY"),
                    total_balance=bi.get("total_balance", "0.00"),
                    granted_balance=bi.get("granted_balance", "0.00"),
                    topped_up_balance=bi.get("topped_up_balance", "0.00"),
                    is_available=is_available,
                )
            return BalanceInfo(
                currency="CNY",
                total_balance="0.00",
                granted_balance="0.00",
                topped_up_balance="0.00",
                is_available=False,
            )
        except (KeyError, TypeError, IndexError) as e:
            raise DeepSeekError("响应格式异常") from e
