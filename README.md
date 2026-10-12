# Codex + DeepSeek Harness 桌面宠物

一个 Windows 悬浮小挂件：把 **OpenAI Codex** 和 **DeepSeek Harness** 两个 AI 编程工具
的用量、额度和花费并排放在桌面指定角落里，两行、透明背景、几乎不占地方。

![预览](preview.png)

```
● Codex     gpt-5.6-sol   5h 100% · 7d 99%     0 tok · $0.00
● DeepSeek  v4-pro        余额 ¥6.90          62.3M tok · ¥23.35
```

**状态灯**：🟢 工作中　⚪ 休息中　🔴 未运行

## 下载 / 快速开始

不想自己打包的话，直接下 [Releases](https://github.com/Delta-Y123/codex-deepseek-pet/releases/latest)
里的 **`CodexDeepSeekPet.exe`** —— Windows x64 单文件，**不需要装 Python**。

```
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

上面这条会把 exe 装到 `%LOCALAPPDATA%\Programs\CodexDeepSeekPet\`，
并创建开始菜单 / 桌面 / 开机启动三个快捷方式。装完直接开始工作，无需配置。
（源码运行：`python desktop_pet.py`，依赖 Pillow + pystray。）

## 渲染方式（重要）

整幅画面由 **Pillow 绘制**（`ImageFont` + `ImageDraw`，灰度抗锯齿），不再用 Tk 画文字。

原因：Tk 在 Windows 上用 GDI **ClearType 次像素渲染**，字符边缘会带 R/G/B 分色毛边；
叠上 `-transparentcolor` 的色键后，这些毛边不会透明，于是变成一圈显眼的紫/洋红描边
（实测用户截图里有 2060 个 `#db00fe`/`#ff00db` 这类像素）。改用 Pillow 后
**彩边像素为 0**（`#000000` 描边 + 灰度抗锯齿），下面是当时的检测结果：

```
画布 (540, 90)  透明(关键色)像素=38872  非背景=9728
白字=494  Codex绿=217  DeepSeek蓝=441
★ 洋红/紫彩边=0   纯红锈边=0   纯蓝锈边=0
```

| 项 | 做法 |
| --- | --- |
| 字体 | `Segoe UI Variable`（拉丁，变体加粗）+ `Microsoft YaHei UI`（中文，ttc face 1） |
| 主文字色 | `#FFFFFF` |
| 描边 | 纯黑 `#000000`，宽度随 DPI 缩放（150% → 2px） |
| 警告色 | `#FB923C`（配额 ≥90% 或余额读取失败） |
| 列宽 | 按真实字体度量动态排版，列间固定留白，绝不重叠 |
| 窗口宽度 | 按实际内容自适应（量化 40px 台阶，只增不减 → 不抖动） |
| DPI | 进程 Per-Monitor DPI 感知；字体、留白、描边全部等比缩放 |

## 显示内容与数据来源

| 位置 | 指标 | 来源 |
| --- | --- | --- |
| 第 1 行 | Codex 模型 / 5h·7d 剩余 / 今日 Token / 今日 API 等价费用 | 本地 `codex app-server` JSON-RPC |
| 第 2 行 | DeepSeek 模型 / 余额 / 今日 Token / 今日费用 | 平台官方接口 + 本地会话数据 |

- **Codex**：`account/rateLimits/read`（5h = `primary` 300 分钟窗口，7d = `secondary`
  10080 分钟窗口）、`account/usage/read`（每日用量桶、逐线程 `estimatedUsageUsdMicros`），
  与 Codex 官方界面 / VS Code 扩展同源。
- **DeepSeek**：余额读 `platform.deepseek.com/api/v0/users/get_user_summary`；Token 取自
  `~/.dsh/storages/session_projcache` 中**今天创建的会话**。
- 模型名会自动去掉与显示名重复的部分（`deepseek-v4-pro` → `v4-pro`）。
- **只显示实时数据**：不读任何历史快照文件；某轮失败时沿用上一轮的实时结果。
- 标注 `(估)` 的费用按 `config.json` 单价估算。

## 托盘图标（所有设置都在这里）

| 菜单项 | 说明 |
| --- | --- |
| 显示宠物 | 隐藏 / 显示悬浮条 |
| 显示背景板 | 透明 ⇄ 深色圆角底板 |
| 始终置顶 | 切换置顶 |
| 显示模型名 | 精简模式（去掉模型列，宽度自动收窄） |
| 位置 | 右下角 / 左下角 / 右上角 / 左上角 |
| 刷新间隔 | 5 / 10 / 30 / 60 秒 |
| 立即刷新 / 打开配置文件 / 退出 | — |

悬浮条本身：**拖动**移动、**双击**刷新、**右键**菜单。
（透明区域点击穿透，拖动请按住文字或状态灯。）

## 安装位置

| 内容 | 路径 |
| --- | --- |
| 程序 | `%LOCALAPPDATA%\Programs\CodexDeepSeekPet\CodexDeepSeekPet.exe` |
| 配置 | 同目录 `config.json` |
| 运行日志 | 同目录 `pet.log`（每次启动重写） |
| 快捷方式 | 开始菜单 / 桌面 / 启动（开机自启） |

- **关闭开机自启**：删除
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CodexDeepSeekPet.lnk`
- **卸载**：删除安装目录与三个快捷方式即可（不写注册表）
- **重新安装**：`powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1`

## 配置 `config.json`

```json
{
  "refresh_seconds": 10,
  "position": "bottom-right",
  "visible": true,
  "show_panel": false,
  "show_model": true,
  "always_on_top": true,
  "pricing": {
    "codex": { "currency": "USD", "input_per_1m": 1.25,
               "cached_input_per_1m": 0.125, "output_per_1m": 10.0 },
    "dsh":   { "currency": "CNY", "input_per_1m": 2.0,
               "cached_input_per_1m": 0.5, "output_per_1m": 8.0 }
  }
}
```

## 开发与打包

- 直接运行源码：`python desktop_pet.py`
- 重新打包：双击 `构建exe.bat`（需要 Python 3 + Pillow + pystray + PyInstaller）

## 实现说明

- 每次刷新只重绘一张 Pillow 图并替换 `PhotoImage`，**不会闪烁**。
- Codex 侧常驻一个 `codex app-server` 子进程做本地 JSON-RPC（官方客户端同做法），
  退出时自动关闭，不残留进程。
