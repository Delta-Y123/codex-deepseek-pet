# -*- coding: utf-8 -*-
"""
Codex + DeepSeek Harness 桌面宠物（极简两行 · 透明背景 · 托盘设置）
====================================================================
    ● Codex     gpt-5.6-sol   5h 100% · 7d 99%    0 tok · $0.00
    ● DeepSeek  v4-pro        余额 ¥7.60         41.8M tok · ¥23.35

· 状态灯：绿=工作中，灰=休息中，红=未运行（判据与刷新节奏同步，默认 3 个刷新周期）
· 背景完全透明；文字 #FFFFFF + 纯黑描边
· 全部画面用 Pillow 灰度抗锯齿绘制（不使用 GDI ClearType），
  因此不会出现次像素彩边（之前那条"紫边"的来源）
· 列宽按真实字体度量动态排版；DPI 感知，高分屏不发虚
"""

import os
import re
import ssl
import sys
import json
import glob
import time
import atexit
import ctypes
import threading
import datetime
import subprocess
import urllib.request

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH = os.path.join(BASE_DIR, "pet.log")

HOME = os.path.expanduser("~")
CODEX_HOME = os.path.join(HOME, ".codex")
CODEX_CONFIG = os.path.join(CODEX_HOME, "config.toml")

DSH_HOME = os.path.join(HOME, ".dsh")
CRED_PATH = os.path.join(DSH_HOME, ".credentials.yaml")
DSH_PROJCACHE = os.path.join(DSH_HOME, "storages", "session_projcache", "sessions")

PLATFORM_ORIGIN = "https://platform.deepseek.com"
SUMMARY_URL = PLATFORM_ORIGIN + "/api/v0/users/get_user_summary"


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


def log_reset():
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                    f"start frozen={getattr(sys,'frozen',False)}\n")
    except Exception:
        pass


def enable_dpi():
    """进程 DPI 感知：高分屏下按原生像素渲染，避免位图拉伸发虚。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 外观
# --------------------------------------------------------------------------- #
KEY = "#010101"                 # 透明关键色（近黑：抗锯齿边缘融进黑色描边，无彩边）
STROKE_COLOR = (0, 0, 0)        # 描边纯黑
C_TEXT, C_DIM = (255, 255, 255), (185, 192, 212)
C_CODEX, C_DSH = (46, 230, 168), (107, 140, 255)
C_OK, C_IDLE, C_ERR = (34, 197, 94), (124, 135, 152), (239, 68, 68)
C_WARN = (251, 146, 60)         # #FB923C
C_PANEL, C_BORDER = (18, 22, 42), (43, 51, 80)
C_LED_RING = (5, 7, 13)

FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_F = lambda n: os.path.join(FONT_DIR, n)
# (文件, ttc 内的 face 索引)；msyh.ttc 的 1 号 face 是 "Microsoft YaHei UI"
LATIN = [(_F("SegUIVar.ttf"), 0), (_F("segoeui.ttf"), 0), (_F("arial.ttf"), 0)]
LATIN_B = [(_F("SegUIVar.ttf"), 0), (_F("segoeuib.ttf"), 0), (_F("arialbd.ttf"), 0)]
CJK = [(_F("msyh.ttc"), 1), (_F("msyh.ttc"), 0), (_F("msyh.ttf"), 0),
       (_F("simhei.ttf"), 0)]
CJK_B = [(_F("msyhbd.ttc"), 1), (_F("msyhbd.ttc"), 0), (_F("msyh.ttc"), 1),
         (_F("msyh.ttc"), 0), (_F("simhei.ttf"), 0)]

BASE_PAD, BASE_GAP, BASE_LED, BASE_LED_GAP = 9, 15, 11, 8
BASE_H = 60

DEFAULT_CONFIG = {
    "refresh_seconds": 10,
    "position": "bottom-right",
    "visible": True,
    "show_panel": False,
    "show_model": True,
    "always_on_top": True,
    "pricing": {
        "codex": {"currency": "USD", "input_per_1m": 1.25,
                  "cached_input_per_1m": 0.125, "output_per_1m": 10.0},
        "dsh": {"currency": "CNY", "input_per_1m": 2.0,
                "cached_input_per_1m": 0.5, "output_per_1m": 8.0},
    },
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    need_save = not os.path.exists(CONFIG_PATH)
    try:
        if not need_save:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                user = json.load(f)
            for k in DEFAULT_CONFIG:
                if k == "pricing":
                    continue
                if k in user:
                    cfg[k] = user[k]
                else:
                    need_save = True
            for side in ("codex", "dsh"):
                cfg["pricing"][side].update((user.get("pricing") or {}).get(side) or {})
        if need_save:
            save_config(cfg)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def today_midnight():
    d = datetime.date.today()
    return datetime.datetime(d.year, d.month, d.day)


def process_running(exe_name):
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                             capture_output=True, text=True, timeout=8,
                             creationflags=flags).stdout
        return exe_name.lower() in out.lower()
    except Exception:
        return None


def fmt_num(n):
    try:
        n = int(n)
    except Exception:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def money(v, cur):
    if v is None:
        return "—"
    return (f"${v:.2f}") if cur == "USD" else (f"¥{v:.2f}")


def cost_of(uncached, cached, output, pricing):
    return (uncached * pricing["input_per_1m"]
            + cached * pricing["cached_input_per_1m"]
            + output * pricing["output_per_1m"]) / 1_000_000.0


def short_model(display_name, model):
    """模型名里已含显示名时去掉重复（DeepSeek / deepseek-v4-pro → v4-pro）。"""
    if not model:
        return ""
    dn = (display_name or "").strip().lower()
    if dn and model.lower().startswith(dn):
        rest = model[len(dn):].lstrip("-_ ")
        return rest or model
    return model


# --------------------------------------------------------------------------- #
# Codex：直连本地 app-server（实时，绝不用历史快照）
# --------------------------------------------------------------------------- #
def find_codex_exe():
    try:
        txt = open(CODEX_CONFIG, encoding="utf-8", errors="replace").read()
        m = re.search(r"CODEX_CLI_PATH\s*=\s*['\"]([^'\"]*codex\.exe)['\"]", txt)
        if m and os.path.exists(m.group(1)):
            return m.group(1)
    except Exception:
        pass
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin")
    cands = glob.glob(os.path.join(base, "*", "codex.exe"))
    if cands:
        return max(cands, key=os.path.getmtime)
    for p in os.environ.get("PATH", "").split(os.pathsep):
        c = os.path.join(p, "codex.exe")
        if os.path.exists(c):
            return c
    return None


CODEX_POLL_SECONDS = 30       # 后台抓取 Codex 的间隔（这些接口走网络，慢）
CODEX_THREAD_BUDGET = 8.0     # 每轮花在"逐线程账单"上的时间上限（秒）


class CodexClient:
    def __init__(self):
        self.exe = find_codex_exe()
        self.proc = None
        self.pending = {}
        self.lock = threading.Lock()
        self.spawn_lock = threading.Lock()
        self.next_id = 1
        self.last_good = None
        self.latest = None                 # 后台轮询的最新结果（界面直接读它，不阻塞）
        self.interval = CODEX_POLL_SECONDS
        self.thread_budget = CODEX_THREAD_BUDGET
        self._threads = {}                 # threadId -> (updatedAt, usd_micros)
        self._stop = threading.Event()
        self._poller = None

    def _spawn(self):
        if not self.exe:
            raise RuntimeError("codex.exe not found")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            [self.exe, "app-server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
        with self.lock:
            self.pending = {}
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        if self._call("initialize",
                      {"clientInfo": {"name": "dsh-pet", "version": "4.0"}},
                      timeout=40) is None:
            raise RuntimeError("initialize failed")

    def _reader(self, proc):
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if isinstance(o, dict) and "id" in o:
                    with self.lock:
                        if o["id"] in self.pending:
                            self.pending[o["id"]] = o
        except Exception:
            pass

    def _call(self, method, params=None, timeout=20):
        if self.proc is None or self.proc.poll() is not None:
            return None
        rid = self.next_id
        self.next_id += 1
        with self.lock:
            self.pending[rid] = None
        msg = {"id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except Exception:
            with self.lock:
                self.pending.pop(rid, None)
            return None
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                v = self.pending.get(rid)
            if v is not None:
                with self.lock:
                    self.pending.pop(rid, None)
                return v.get("result")
            time.sleep(0.02)
        with self.lock:
            self.pending.pop(rid, None)
        return None

    def close(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
        self.proc = None

    def _ensure(self):
        with self.spawn_lock:
            if self.proc is None or self.proc.poll() is not None:
                self.close()
                self._spawn()

    def _fetch(self):
        """一次完整抓取。
        账户级接口各要 5~8s（走网络），逐线程账单每条 1~5s，所以线程结果按
        (threadId, updatedAt) 缓存，并给逐线程那一段设总时间预算。"""
        self._ensure()
        rl = self._call("account/rateLimits/read", None, timeout=20)
        if not isinstance(rl, dict):
            return None
        snap = (rl.get("rateLimitsByLimitId") or {}).get("codex") or rl.get("rateLimits") or {}
        p, s = snap.get("primary") or {}, snap.get("secondary") or {}
        out = {
            "primary": {"used": p.get("usedPercent"), "window": p.get("windowDurationMins")},
            "secondary": {"used": s.get("usedPercent"), "window": s.get("windowDurationMins")},
            "plan": snap.get("planType"),
            "today_tokens": None, "today_usd": None, "model": None, "last_active": None,
        }
        us = self._call("account/usage/read", {"threadId": None}, timeout=20)
        if isinstance(us, dict):
            key = datetime.date.today().isoformat()
            out["today_tokens"] = 0
            for b in (us.get("dailyUsageBuckets") or []):
                if b.get("startDate") == key:
                    out["today_tokens"] = int(b.get("tokens") or 0)
                    break
        tl = self._call("thread/list", {"limit": 20, "sortKey": "updated_at",
                                       "sortDirection": "desc"})
        t0 = today_midnight().timestamp()
        usd, n, missing = 0.0, 0, 0
        deadline = time.time() + self.thread_budget
        if isinstance(tl, dict):
            items = tl.get("data") or []
            if items:
                out["model"] = items[0].get("model")
            for t in items:
                ts = t.get("updatedAt") or 0
                if ts > 1e12:
                    ts /= 1000.0
                if ts and (out["last_active"] is None or ts > out["last_active"]):
                    out["last_active"] = ts
                if not ts or ts < t0:
                    continue
                tid = t.get("id")
                hit = self._threads.get(tid)
                if hit and hit[0] == ts and hit[1] is not None:      # 命中缓存
                    usd += hit[1]
                    n += 1
                    continue
                if time.time() > deadline:                            # 超预算：先用旧值
                    if hit and hit[1] is not None:
                        usd += hit[1]
                        n += 1
                    else:
                        missing += 1
                    continue
                u = self._call("account/usage/read", {"threadId": tid}, timeout=12)
                tu = (u or {}).get("threadUsage") if isinstance(u, dict) else None
                val = None
                if isinstance(tu, dict) and tu.get("estimatedUsageUsdMicros") is not None:
                    val = int(tu["estimatedUsageUsdMicros"])
                self._threads[tid] = (ts, val)
                if val is not None:
                    usd += val
                    n += 1
                else:
                    missing += 1
        if n:
            out["today_usd"] = usd / 1_000_000.0
            out["usd_missing"] = missing
        return out

    # ---- 后台轮询：界面刷新不再被这些慢接口阻塞 ----
    def start(self):
        if self._poller is not None:
            return
        self._poller = threading.Thread(target=self._loop, name="codex-poll", daemon=True)
        self._poller.start()

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            for attempt in (1, 2):
                try:
                    r = self._fetch()
                except Exception:
                    r = None
                if r:
                    self.latest = r
                    self.last_good = r
                    break
                if attempt == 1:
                    self.close()
                    time.sleep(0.4)
            self._stop.wait(max(5.0, self.interval - (time.time() - t0)))

    def snapshot(self):
        """非阻塞：返回后台轮询拿到的最新结果（首轮可能还没拿到）。"""
        return self.latest


_codex = CodexClient()


def _codex_shutdown():
    _codex._stop.set()
    _codex.close()


atexit.register(_codex_shutdown)


def codex_model_config():
    try:
        with open(CODEX_CONFIG, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*model\s*=\s*"([^"]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "?"


# --------------------------------------------------------------------------- #
# DeepSeek Harness
# --------------------------------------------------------------------------- #
def _read_dsh_token():
    if not os.path.exists(CRED_PATH):
        return None
    try:
        txt = open(CRED_PATH, encoding="utf-8").read()
    except Exception:
        return None
    m = re.search(r"deepseek-account-platform/default:.*?token:\s*(\S+)", txt, re.S)
    if m:
        return m.group(1)
    m = re.search(r"token:\s*(\S+)", txt)
    return m.group(1) if m else None


_bal_cache = {"t": 0, "v": None}


def dsh_balance(min_interval=8):
    now = time.time()
    if _bal_cache["v"] is not None and now - _bal_cache["t"] < min_interval:
        return _bal_cache["v"]
    token = _read_dsh_token()
    if not token:
        return None
    headers = {
        "x-dsh-auth-token": token,
        "x-client-bundle-id": "", "x-client-platform": "web", "x-client-version": "1.0.0",
        "x-client-locale": "zh_CN", "x-client-timezone-offset": str(-time.timezone),
        "accept": "application/json",
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
        "referer": PLATFORM_ORIGIN + "/", "origin": PLATFORM_ORIGIN,
    }
    try:
        req = urllib.request.Request(SUMMARY_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=12,
                                    context=ssl.create_default_context()) as r:
            j = json.loads(r.read().decode("utf-8"))
        biz = ((j or {}).get("data") or {}).get("biz_data") or {}

        def add(w):
            s, cur = 0.0, None
            for it in w:
                try:
                    s += float(it.get("balance", "0"))
                except Exception:
                    pass
                cur = cur or it.get("currency")
            return s, cur
        n, cur = add(biz.get("normal_wallets") or [])
        b, cur2 = add(biz.get("bonus_wallets") or [])
        tc = 0.0
        for c in (biz.get("total_costs") or []):
            try:
                tc += float(c.get("amount", "0"))
            except Exception:
                pass
        v = {"balance": n, "bonus": b, "currency": cur or cur2 or "CNY", "total_costs": tc}
        _bal_cache.update(t=now, v=v)
        return v
    except Exception:
        return _bal_cache["v"]


def _today_session_ids():
    t0 = today_midnight().timestamp()
    base = os.path.join(DSH_HOME, "sessions")
    ids = set()
    if not os.path.isdir(base):
        return ids
    base_depth = base.rstrip(os.sep).count(os.sep)
    for root, dirs, _f in os.walk(base):
        depth = root.rstrip(os.sep).count(os.sep) - base_depth
        for d in dirs:
            try:
                if os.stat(os.path.join(root, d)).st_ctime >= t0:
                    ids.add(d)
            except OSError:
                pass
        if depth >= 3:
            dirs[:] = []
    return ids


def dsh_today_usage():
    ids = _today_session_ids()
    t = {"uncachedInputTokens": 0, "outputTokens": 0,
         "cacheReadTokens": 0, "cacheWriteTokens": 0}
    cnt, last = 0, 0.0
    if os.path.isdir(DSH_PROJCACHE):
        for fp in glob.glob(os.path.join(DSH_PROJCACHE, "*.json")):
            if os.path.splitext(os.path.basename(fp))[0] not in ids:
                continue
            try:
                last = max(last, os.path.getmtime(fp))
                j = json.load(open(fp, encoding="utf-8"))
                tu = (((j.get("record") or {}).get("rows") or {})
                      .get("tokenUsage", {}).get("val", {}).get("totals")) or {}
                for k in t:
                    t[k] += int(tu.get(k) or 0)
                cnt += 1
            except Exception:
                continue
    return t, cnt, last


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def collect_all(cfg):
    snap = _codex.snapshot()
    cx = {"running": process_running("codex.exe"), "model": codex_model_config(),
          "quota": None, "today_tokens": None, "cost": None, "last_active": None}
    if snap:
        cx["quota"] = snap
        cx["model"] = snap.get("model") or cx["model"]
        cx["today_tokens"] = snap.get("today_tokens")
        cx["cost"] = snap.get("today_usd")
        cx["last_active"] = snap.get("last_active")
        if cx["cost"] is None and cx["today_tokens"] is not None:
            n = cx["today_tokens"]
            cx["cost"] = cost_of(n * 0.25, n * 0.6, n * 0.15, cfg["pricing"]["codex"])
            cx["cost_est"] = True

    totals, sess, last = dsh_today_usage()
    unc, cac, out = (totals["uncachedInputTokens"], totals["cacheReadTokens"],
                     totals["outputTokens"])
    dsh = {
        "running": process_running("DeepSeek Harness.exe"),
        "model": "deepseek-v4-pro",
        "balance": dsh_balance(),
        "total_tokens": unc + cac + out,
        "sessions": sess,
        "last_active": last or None,
    }
    dsh["cost"] = cost_of(unc, cac, out, cfg["pricing"]["dsh"])
    return {"codex": cx, "dsh": dsh}


# --------------------------------------------------------------------------- #
# 状态灯：与刷新节奏同步
# --------------------------------------------------------------------------- #
# 判据取"最近"的一个：
#   1) 指标本身还在变（token / 费用 / 余额 / 配额 任一与上一轮不同）
#   2) 工具自报的最近活动时间戳还很近（Codex 线程 updatedAt / DSH 会话缓存 mtime）
# 窗口 = 3 个刷新周期（下限 30s、上限 300s）：刷新调快，灯也跟着更灵敏。
ACTIVE_FLOOR, ACTIVE_CAP = 60, 300
_activity = {"prev": {}, "at": {}}


def active_window(refresh_seconds):
    try:
        n = int(refresh_seconds)
    except Exception:
        n = 10
    return max(ACTIVE_FLOOR, min(ACTIVE_CAP, n * 3))


def led_color(key, fingerprint, last_ts, running, window):
    if running is False:
        return C_ERR
    now = time.time()
    prev = _activity["prev"].get(key)
    if prev is not None and fingerprint != prev:
        _activity["at"][key] = now
    _activity["prev"][key] = fingerprint
    marks = [_activity["at"].get(key, 0.0)]
    if last_ts:
        marks.append(last_ts)
    t = max(marks)
    return C_OK if t and (now - t) <= window else C_IDLE


# --------------------------------------------------------------------------- #
# 字体
# --------------------------------------------------------------------------- #
def load_font(specs, px, bold=False):
    """specs: [(字体文件, ttc face 索引)]，按优先级尝试。"""
    for path, index in specs:
        if not os.path.exists(path):
            continue
        try:
            f = ImageFont.truetype(path, px, index=index)
        except Exception:
            continue
        if bold and "SegUIVar" in os.path.basename(path):
            applied = False
            for how in (lambda: f.set_variation_by_name("Bold"),
                        lambda: f.set_variation_by_axes([700])):
                try:
                    how()
                    applied = True
                    break
                except Exception:
                    pass
            if not applied:
                continue                    # 该文件无法加粗，换下一个候选
        return f
    try:
        return ImageFont.truetype(CJK[0][0], px, index=CJK[0][1])
    except Exception:
        return ImageFont.load_default()


def tray_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = int(size * 0.08)
    d.ellipse([m, m, size - m, size - m], fill=(16, 163, 127, 255),
              outline=(255, 255, 255, 255), width=max(2, size // 20))
    ey = int(size * 0.44)
    r = int(size * 0.08)
    for cx in (int(size * 0.37), int(size * 0.63)):
        d.ellipse([cx - r, ey - r, cx + r, ey + r], fill=(6, 18, 14, 255))
    d.arc([int(size * 0.34), int(size * 0.56), int(size * 0.66), int(size * 0.80)],
          20, 160, fill=(6, 18, 14, 255), width=max(2, size // 26))
    return img


class Pet:
    """两行极简状态条；整幅画面由 Pillow 绘制（灰度抗锯齿，无次像素彩边）。"""

    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.data = None
        self.busy = False
        self.tray = None
        self._dragp = None
        self._photo = None

        try:
            dpi = root.winfo_fpixels("1i")
        except Exception:
            dpi = 96.0
        self.scale = max(1.0, dpi / 96.0)
        self.dpi = dpi
        s = self.scale
        self.PAD = int(round(BASE_PAD * s))
        self.GAP = int(round(BASE_GAP * s))
        self.LED = int(round(BASE_LED * s))
        self.LED_GAP = int(round(BASE_LED_GAP * s))
        self.HEIGHT = int(round(BASE_H * s))
        self.STROKE = 2 if s >= 1.25 else 1

        px = lambda pt: max(8, int(round(pt * dpi / 72.0)))
        self.F_NAME = load_font(LATIN_B, px(9), bold=True)
        self.F_NAME_CJK = load_font(CJK_B, px(9), bold=True)
        self.F_MODEL = load_font(LATIN, px(8))
        self.F_MAIN = load_font(LATIN, px(9))
        self.F_CJK = load_font(CJK, px(9))
        self.F_RIGHT = load_font(LATIN, px(8))

        self.WIDTH = int(round(340 * s))

        root.overrideredirect(True)
        root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
        try:
            root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        root.config(bg=KEY)
        self.cv = tk.Canvas(root, width=self.WIDTH, height=self.HEIGHT, bg=KEY,
                            highlightthickness=0, bd=0)
        self.cv.pack()
        self._img_item = self.cv.create_image(0, 0, anchor="nw")
        self._panel_item = None

        self.rows = (int(self.HEIGHT * 0.30), int(self.HEIGHT * 0.74))
        self._place_self()
        self._bind()
        self._start_tray()
        _codex.start()                  # Codex 侧后台轮询，界面刷新不再等它
        if not self.cfg.get("visible", True):
            root.withdraw()
        self.refresh()

    # ---------- 度量 ----------
    def _w(self, font, text):
        return font.getlength(text) if text else 0

    def _ensure_width(self, need):
        step = max(8, int(round(40 * self.scale)))
        floor = int(round(300 * self.scale))
        w = max(floor, -(-int(need) // step) * step)
        if w > self.WIDTH:
            self.WIDTH = w
            self.cv.config(width=w)
            self._place_self()

    def _prepare(self, name, model, metric, right,
                 f_name, f_model, f_metric, f_right):
        w_name = self._w(f_name, name)
        model = model or ""
        w_model = self._w(f_model, model)
        w_metric = self._w(f_metric, metric)
        w_right = self._w(f_right, right)

        cap_right = int(round(230 * self.scale))
        if w_right > cap_right:
            right = self._clip(right, f_right, cap_right)
            w_right = self._w(f_right, right)

        cap = int(round(620 * self.scale))

        def total():
            return (self.PAD + self.LED + self.LED_GAP + w_name + self.GAP
                    + (w_model + self.GAP if w_model else 0) + w_metric
                    + self.GAP + w_right + self.PAD)

        if model and total() > cap:
            model, w_model = "", 0
        if total() > cap:
            room = cap - (total() - w_metric)
            metric = self._clip(metric, f_metric, max(24, room))
            w_metric = self._w(f_metric, metric)
        return {"name": name, "model": model, "metric": metric, "right": right,
                "f_name": f_name, "f_model": f_model, "f_metric": f_metric,
                "f_right": f_right, "w_name": w_name, "w_model": w_model,
                "w_metric": w_metric, "w_right": w_right, "need": total()}

    def _clip(self, text, font, maxw):
        if font.getlength(text) <= maxw:
            return text
        while text and font.getlength(text + "…") > maxw:
            text = text[:-1]
        return text + "…"

    # ---------- 窗口 ----------
    def _place_self(self):
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        pos = self.cfg.get("position", "bottom-right")
        if pos == "bottom-left":
            x, y = 8, sh - self.HEIGHT - int(52 * self.scale)
        elif pos == "top-right":
            x, y = sw - self.WIDTH - 8, int(44 * self.scale)
        elif pos == "top-left":
            x, y = 8, int(44 * self.scale)
        else:
            x, y = sw - self.WIDTH - 8, sh - self.HEIGHT - int(52 * self.scale)
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _bind(self):
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<Double-Button-1>", lambda e: self.refresh())
        self.cv.bind("<Button-3>", self._popup)

    def _press(self, e):
        self._dragp = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag(self, e):
        if self._dragp:
            self.root.geometry(f"+{e.x_root - self._dragp[0]}+{e.y_root - self._dragp[1]}")

    def _popup(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="立即刷新", command=self.refresh)
        m.add_separator()
        m.add_command(label="退出", command=self.quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ---------- 托盘 ----------
    def _start_tray(self):
        try:
            import pystray
        except Exception:
            log("pystray 不可用")
            return

        def act(fn):
            return lambda *a: self.root.after(0, fn)

        def set_pos(p):
            def go():
                self.cfg["position"] = p
                save_config(self.cfg)
                self._place_self()
            return lambda *a: self.root.after(0, go)

        def set_refresh(sec):
            def go():
                self.cfg["refresh_seconds"] = sec
                save_config(self.cfg)
            return lambda *a: self.root.after(0, go)

        menu = pystray.Menu(
            pystray.MenuItem("显示宠物", act(self.toggle_show),
                             checked=lambda i: bool(self.cfg.get("visible", True))),
            pystray.MenuItem("显示背景板", act(self.toggle_panel),
                             checked=lambda i: bool(self.cfg.get("show_panel", False))),
            pystray.MenuItem("始终置顶", act(self.toggle_top),
                             checked=lambda i: bool(self.cfg.get("always_on_top", True))),
            pystray.MenuItem("显示模型名", act(self.toggle_model),
                             checked=lambda i: bool(self.cfg.get("show_model", True))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("位置", pystray.Menu(*[
                pystray.MenuItem(t, set_pos(v),
                                 checked=lambda i, v=v: self.cfg.get("position") == v,
                                 radio=True)
                for t, v in (("右下角", "bottom-right"), ("左下角", "bottom-left"),
                             ("右上角", "top-right"), ("左上角", "top-left"))])),
            pystray.MenuItem("刷新间隔", pystray.Menu(*[
                pystray.MenuItem(f"{sec} 秒", set_refresh(sec),
                                 checked=lambda i, sec=sec:
                                 int(self.cfg.get("refresh_seconds", 10)) == sec,
                                 radio=True)
                for sec in (5, 10, 30, 60)])),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("立即刷新", act(self.refresh)),
            pystray.MenuItem("打开配置文件", act(self.open_config)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", act(self.quit)),
        )
        try:
            self.tray = pystray.Icon("dsh-pet", tray_image(), "Codex · DeepSeek 状态宠物", menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
            log("tray started")
        except Exception as e:  # noqa: BLE001
            self.tray = None
            log(f"tray failed: {e}")

    def _tray_refresh(self):
        try:
            if self.tray:
                self.tray.update_menu()
        except Exception:
            pass

    # ---------- 设置 ----------
    def toggle_show(self):
        v = not self.cfg.get("visible", True)
        self.cfg["visible"] = v
        save_config(self.cfg)
        if v:
            self.root.deiconify()
            self.root.attributes("-topmost", bool(self.cfg.get("always_on_top", True)))
        else:
            self.root.withdraw()
        self._tray_refresh()

    def toggle_panel(self):
        self.cfg["show_panel"] = not self.cfg.get("show_panel", False)
        save_config(self.cfg)
        self._render()
        self._tray_refresh()

    def toggle_top(self):
        self.cfg["always_on_top"] = not self.cfg.get("always_on_top", True)
        save_config(self.cfg)
        self.root.attributes("-topmost", bool(self.cfg["always_on_top"]))
        self._tray_refresh()

    def toggle_model(self):
        self.cfg["show_model"] = not self.cfg.get("show_model", True)
        save_config(self.cfg)
        self._render()
        self._tray_refresh()

    def open_config(self):
        try:
            os.startfile(CONFIG_PATH)
        except Exception:
            pass

    def quit(self):
        log("quit")
        _codex_shutdown()
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    # ---------- 刷新 ----------
    def refresh(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        t0 = time.time()
        try:
            data = collect_all(self.cfg)
        except Exception as e:  # noqa: BLE001
            log(f"collect error: {type(e).__name__}: {e}")
            data = None
        if data is None:
            log("collect returned None")
        log(f"collect took {time.time()-t0:.1f}s")
        self.root.after(0, lambda: self._apply(data))

    def _apply(self, data):
        self.busy = False
        if data:
            self.data = data
            self._render()
            if not getattr(self, "_logged", False):
                self._logged = True
                q = (data["codex"].get("quota") or {}).get("primary", {})
                log(f"first data ok codex_5h={q.get('used')} "
                    f"bal={(data['dsh'].get('balance') or {}).get('balance')}")
        else:
            log("collect failed")
        self.root.after(max(3, int(self.cfg.get("refresh_seconds", 10))) * 1000, self.refresh)

    # ---------- 绘制 ----------
    def _render(self):
        show_model = bool(self.cfg.get("show_model", True))
        if self.data:
            cx, ds = self.data["codex"], self.data["dsh"]
            q = cx.get("quota") or {}
            p = (q.get("primary") or {}).get("used")
            s = (q.get("secondary") or {}).get("used")
            p_txt = f"5h {100-p:.0f}%" if isinstance(p, (int, float)) else "5h —"
            s_txt = f"7d {100-s:.0f}%" if isinstance(s, (int, float)) else "7d —"
            tok = cx.get("today_tokens")
            a = self._prepare(
                "Codex", short_model("Codex", cx.get("model") or "") if show_model else "",
                f"{p_txt} · {s_txt}",
                f"{fmt_num(tok) if tok is not None else '—'} tok · "
                f"{money(cx.get('cost'), self.cfg['pricing']['codex']['currency'])}",
                self.F_NAME, self.F_MODEL, self.F_MAIN, self.F_RIGHT)
            bal = ds.get("balance")
            if bal:
                total = float(bal.get("balance") or 0) + float(bal.get("bonus") or 0)
                bal_txt = f"余额 ¥{total:.2f}"
            else:
                total, bal_txt = None, "余额 —"
            b = self._prepare(
                "DeepSeek", short_model("DeepSeek", ds.get("model") or "") if show_model else "",
                bal_txt,
                f"{fmt_num(ds.get('total_tokens', 0))} tok · "
                f"{money(ds.get('cost'), self.cfg['pricing']['dsh']['currency'])}",
                self.F_NAME_CJK, self.F_MODEL, self.F_CJK, self.F_RIGHT)
            win = active_window(self.cfg.get("refresh_seconds", 10))
            led_a = led_color(
                "codex",
                (cx.get("today_tokens"), cx.get("cost"), p, s, cx.get("model"),
                 cx.get("running")),
                cx.get("last_active"), cx.get("running"), win)
            led_b = led_color(
                "dsh",
                (ds.get("total_tokens"), round(float(ds.get("cost") or 0), 6), total,
                 ds.get("running")),
                ds.get("last_active"), ds.get("running"), win)
            warn_a = isinstance(p, (int, float)) and p >= 90
            warn_b = bal is None
        else:
            a = self._prepare("Codex", "", "读取中…", "", self.F_NAME, self.F_MODEL,
                              self.F_MAIN, self.F_RIGHT)
            b = self._prepare("DeepSeek", "", "读取中…", "", self.F_NAME_CJK,
                              self.F_MODEL, self.F_CJK, self.F_RIGHT)
            led_a = led_b = C_IDLE
            warn_a = warn_b = False

        self._ensure_width(max(a["need"], b["need"]))

        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), KEY)
        d = ImageDraw.Draw(img)
        if self.cfg.get("show_panel"):
            d.rounded_rectangle([0, 0, self.WIDTH - 1, self.HEIGHT - 1], radius=12,
                                fill=C_PANEL, outline=C_BORDER, width=max(1, self.STROKE - 1))
        self._draw_row(d, 0, a, led_a, warn_a)
        self._draw_row(d, 1, b, led_b, warn_b)

        self._photo = ImageTk.PhotoImage(img)
        self.last_image = img
        self.cv.itemconfigure(self._img_item, image=self._photo)

    def _draw_row(self, d, idx, p, led, warn):
        y = self.rows[idx]
        x0 = self.PAD + self.LED + self.LED_GAP
        right_x = self.WIDTH - self.PAD

        # 状态灯
        r = self.LED // 2
        d.ellipse([self.PAD - 1, y - r - 1, self.PAD + self.LED + 1, y + r + 1],
                  fill=C_LED_RING, outline=STROKE_COLOR, width=self.STROKE)
        d.ellipse([self.PAD, y - r, self.PAD + self.LED, y + r], fill=led)

        def text(x, s, font, fill, anchor="lm"):
            d.text((x, y), s, font=font, fill=fill, anchor=anchor,
                   stroke_width=self.STROKE, stroke_fill=STROKE_COLOR)

        text(x0, p["name"], p["f_name"], C_CODEX if idx == 0 else C_DSH)
        mx = x0 + p["w_name"] + self.GAP
        if p["model"]:
            text(mx, p["model"], p["f_model"], C_DIM)
            mx += p["w_model"] + self.GAP
        text(mx, p["metric"], p["f_metric"], C_WARN if warn else C_TEXT)
        text(right_x, p["right"], p["f_right"], C_TEXT, anchor="rm")


def main():
    log_reset()
    enable_dpi()
    root = tk.Tk()
    Pet(root)
    log("ui ready")
    root.mainloop()


if __name__ == "__main__":
    main()
