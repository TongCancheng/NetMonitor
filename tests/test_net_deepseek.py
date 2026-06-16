"""
test_net_deepseek.py — 测试 net_deepseek 模块

覆盖: BalanceInfo, DeepSeekBalanceChecker (配置检测/节流/200/401/429/网络错误/reset)
"""

import io
import json
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from net_deepseek import (
    BalanceInfo,
    DeepSeekError,
    DeepSeekAuthError,
    DeepSeekRateLimitError,
    DeepSeekNetworkError,
    DeepSeekBalanceChecker,
)

# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------


def _make_config(api_key=None):
    """创建一个模拟的 ConfigStore。"""
    cfg = MagicMock()
    cfg.deepseek_api_key = api_key
    return cfg


def _mock_response(json_data):
    """用 BytesIO 模拟 HTTP 响应体（支持 with 和 read）。"""
    return io.BytesIO(json.dumps(json_data).encode("utf-8"))


# ----------------------------------------------------------------------
# BalanceInfo
# ----------------------------------------------------------------------


class TestBalanceInfo:
    def test_creation(self):
        bi = BalanceInfo(
            currency="CNY",
            total_balance="110.00",
            granted_balance="10.00",
            topped_up_balance="100.00",
            is_available=True,
        )
        assert bi.currency == "CNY"
        assert bi.total_balance == "110.00"
        assert bi.granted_balance == "10.00"
        assert bi.topped_up_balance == "100.00"
        assert bi.is_available is True

    def test_frozen_prevents_mutation(self):
        bi = BalanceInfo(
            currency="CNY",
            total_balance="0.00",
            granted_balance="0.00",
            topped_up_balance="0.00",
            is_available=False,
        )
        with pytest.raises(Exception):
            bi.total_balance = "999.00"  # type: ignore

    def test_equality(self):
        a = BalanceInfo("CNY", "110.00", "10.00", "100.00", True)
        b = BalanceInfo("CNY", "110.00", "10.00", "100.00", True)
        c = BalanceInfo("CNY", "0.00", "0.00", "0.00", False)
        assert a == b
        assert a != c


# ----------------------------------------------------------------------
# DeepSeekBalanceChecker
# ----------------------------------------------------------------------


class TestIsConfigured:
    def test_none_key(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key=None))
        assert checker.is_configured() is False

    def test_empty_string(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key=""))
        assert checker.is_configured() is False

    def test_whitespace_only(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="   "))
        assert checker.is_configured() is False

    def test_valid_key(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc123"))
        assert checker.is_configured() is True


class TestTryRefreshRateLimit:
    def test_skips_when_not_configured(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key=None))
        assert checker.try_refresh() is False
        assert checker.balance is None

    def test_throttles_within_interval(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        checker._last_fetch_time = time.time()  # 刚查过一次
        assert checker.try_refresh() is False  # 被节流


def _wait_poll(checker):
    """等待后台线程完成并调用 poll()，返回 poll() 的结果。"""
    if checker._fetch_thread is not None:
        checker._fetch_thread.join(timeout=1.0)
    return checker.poll()


class TestTryRefreshSuccess:
    def test_fetches_and_stores_balance(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        mock_data = {
            "is_available": True,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "110.00",
                "granted_balance": "10.00",
                "topped_up_balance": "100.00",
            }],
        }
        with patch.object(urllib.request, "urlopen",
                          return_value=_mock_response(mock_data)):
            assert checker.try_refresh() is True   # 启动后台线程
            changed = _wait_poll(checker)
            assert changed is True
            assert checker.balance is not None
            assert checker.balance.total_balance == "110.00"
            assert checker.balance.currency == "CNY"
            assert checker.balance.is_available is True

    def test_no_balance_infos_defaults(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        mock_data = {"is_available": False, "balance_infos": []}
        with patch.object(urllib.request, "urlopen",
                          return_value=_mock_response(mock_data)):
            assert checker.try_refresh() is True
            _wait_poll(checker)
            assert checker.balance.total_balance == "0.00"
            assert checker.balance.is_available is False

    def test_second_fetch_no_change(self):
        """第二次获取相同数据时 poll() 返回 False。"""
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        mock_data = {
            "is_available": True,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "50.00",
                "granted_balance": "0.00",
                "topped_up_balance": "50.00",
            }],
        }
        with patch.object(urllib.request, "urlopen",
                          return_value=_mock_response(mock_data)):
            assert checker.try_refresh() is True    # 启动线程
            assert _wait_poll(checker) is True      # 首次有变更
            checker._last_fetch_time = 0.0           # 重置节流
            assert checker.try_refresh() is True    # 再次启动线程
            assert _wait_poll(checker) is False     # 相同数据无变更


class TestTryRefreshErrors:
    def test_401_auth_error(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="bad-key"))
        with patch.object(urllib.request, "urlopen",
                          side_effect=urllib.error.HTTPError(
                              "url", 401, "Unauthorized", {}, io.BytesIO(b"{}"))):
            assert checker.try_refresh() is True   # 启动了后台线程
            _wait_poll(checker)
            assert checker.balance is None
            assert "无效" in checker.last_error

    def test_429_rate_limit(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        with patch.object(urllib.request, "urlopen",
                          side_effect=urllib.error.HTTPError(
                              "url", 429, "Too Many Requests", {}, io.BytesIO(b"{}"))):
            assert checker.try_refresh() is True
            _wait_poll(checker)
            assert "频繁" in checker.last_error

    def test_network_error(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        with patch.object(urllib.request, "urlopen",
                          side_effect=urllib.error.URLError("connection refused")):
            assert checker.try_refresh() is True
            _wait_poll(checker)
            assert "网络" in checker.last_error

    def test_oserror(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        with patch.object(urllib.request, "urlopen",
                          side_effect=OSError("模拟系统错误")):
            assert checker.try_refresh() is True
            _wait_poll(checker)
            assert checker.last_error is not None

    def test_http_500_generic(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        with patch.object(urllib.request, "urlopen",
                          side_effect=urllib.error.HTTPError(
                              "url", 500, "Server Error", {}, io.BytesIO(b"{}"))):
            assert checker.try_refresh() is True
            _wait_poll(checker)
            assert checker.last_error is not None


class TestReset:
    def test_reset_clears_state(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        checker._last_fetch_time = time.time()
        checker._last_error = "some error"
        checker.reset()
        assert checker._last_fetch_time == 0.0
        assert checker.last_error is None

    def test_reset_allows_immediate_refetch(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="sk-abc"))
        checker._last_fetch_time = time.time()
        assert checker.try_refresh() is False  # 被节流
        checker.reset()
        mock_data = {
            "is_available": True,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "200.00",
                "granted_balance": "100.00",
                "topped_up_balance": "100.00",
            }],
        }
        with patch.object(urllib.request, "urlopen",
                          return_value=_mock_response(mock_data)):
            assert checker.try_refresh() is True   # 重置后可立即启动查询
            _wait_poll(checker)
            assert checker.balance.total_balance == "200.00"

    def test_reset_clears_error_on_next_success(self):
        checker = DeepSeekBalanceChecker(_make_config(api_key="bad"))
        # 先触发一次 401 错误
        with patch.object(urllib.request, "urlopen",
                          side_effect=urllib.error.HTTPError(
                              "url", 401, "Unauthorized", {}, io.BytesIO(b"{}"))):
            checker.try_refresh()
            _wait_poll(checker)
        assert checker.last_error is not None

        # 更换有效 key 并 reset
        checker._config.deepseek_api_key = "sk-good"
        checker.reset()
        with patch.object(urllib.request, "urlopen",
                          return_value=_mock_response({
                              "is_available": True,
                              "balance_infos": [{
                                  "currency": "CNY",
                                  "total_balance": "30.00",
                                  "granted_balance": "0.00",
                                  "topped_up_balance": "30.00",
                              }],
                          })):
            checker.try_refresh()
            _wait_poll(checker)
        assert checker.last_error is None
        assert checker.balance.total_balance == "30.00"


# ----------------------------------------------------------------------
# 异常类
# ----------------------------------------------------------------------


class TestDeepSeekErrors:
    def test_inheritance(self):
        assert issubclass(DeepSeekAuthError, DeepSeekError)
        assert issubclass(DeepSeekRateLimitError, DeepSeekError)
        assert issubclass(DeepSeekNetworkError, DeepSeekError)

    def test_catch_base(self):
        try:
            raise DeepSeekAuthError("test")
        except DeepSeekError:
            pass  # 基类可以捕获子类
        else:
            pytest.fail("基类应能捕获子类异常")
