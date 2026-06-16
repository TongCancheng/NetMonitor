# NetMonitor — 网络流量监控悬浮窗

> 透明悬浮窗实时显示上下行网速、DeepSeek API 余额、键盘鼠标点击计数。

---

## 功能概览

| 功能 | 说明 |
|------|------|
| **实时网速** | 每秒更新，显示 ▲ 上行 / ▼ 下行速率 |
| **波形图** | 60 秒历史波形，绿色上行 / 蓝色下行 |
| **DeepSeek 余额** | 自动每 300 秒查询一次，显示总余额 |
| **键盘/鼠标计数** | 全局监听，记录键盘敲击和鼠标点击次数 |
| **今日/本月流量** | 每天自动重置日统计，跨月重置月统计 |
| **开机自启** | 支持添加快捷方式到启动文件夹 |
| **系统托盘** | 托盘图标实时显示网速，左键切换显隐 |

---

## 运行方式

### 从源码运行

```powershell
# 安装依赖
pip install PyQt5 psutil pynput

# 无黑窗运行（推荐）
pythonw net_monitor.py

# 调试模式（有控制台窗口）
python net_monitor.py
```

### 打包的 EXE

直接双击 `NetMonitor.exe` 即可运行。程序会在同目录下自动创建 `config.json`（配置）和 `stats.json`（统计数据）。

---

## 使用说明

### 悬浮窗

- **左键拖拽** → 移动窗口位置
- **右键** → 打开菜单

### 右键菜单

| 菜单项 | 功能 |
|--------|------|
| 查看流量统计 | 弹窗显示详细流量和余额信息 |
| 设置 DeepSeek API Key | 输入 API Key 以启用余额查询 |
| **显示 DeepSeek 余额** | 勾选/去勾切换余额显示（关闭后停止 API 请求） |
| **显示键盘鼠标计数** | 勾选/去勾切换击键计数显示（关闭后停止监听） |
| 开机自启 | 勾选后开机自动启动 |
| 隐藏到托盘 | 隐藏悬浮窗，托盘图标继续运行 |
| 退出 | 完全退出程序 |

### 托盘图标

- **左键** → 显示/隐藏悬浮窗
- **右键** → 打开菜单

---

## 配置文件 `config.json`

程序退出时自动保存，结构如下：

```json
{
  "window_x": 1546,
  "window_y": 770,
  "autostart": true,
  "nic_name": "WLAN",
  "deepseek_api_key": "sk-...",
  "show_deepseek_balance": true,
  "show_input_counter": true,
  "saved_key_count": 0,
  "saved_click_count": 0
}
```

- 手动修改后重启即可生效
- API Key 以**明文**存储，请注意安全

---

## 项目结构

```
net_monitor.py      # 主入口，应用控制器
net_engine.py       # 网络流量采集引擎
net_store.py        # 统计 & 配置持久化
net_deepseek.py     # DeepSeek API 余额查询
net_tray.py         # 系统托盘图标渲染
overlay.py          # 透明悬浮窗 UI
input_counter.py    # 键盘鼠标全局计数
```

---

## 依赖

| 库 | 用途 |
|----|------|
| PyQt5 | GUI 框架 |
| psutil | 网卡流量采集 |
| pynput | 全局键盘/鼠标监听 |

---

## 打包

```powershell
pip install pyinstaller
pyinstaller --name NetMonitor --onefile --noconsole net_monitor.py
```

输出文件：`dist/NetMonitor.exe`

---

## 许可证

MIT
