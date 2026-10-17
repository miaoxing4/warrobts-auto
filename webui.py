# -*- coding: utf-8 -*-
"""
War Robots 自动化 —— 网页图形界面（Web UI）

设计约束：
  * 只用 Python 标准库（http.server / threading / json），**不装任何第三方包**
  * 任务在后台线程跑，页面轮询状态与日志
  * 同一时间只允许一个任务（设备是独占资源）
  * 支持"停止"（协作式取消：在每次界面检测时抛出取消异常）

启动方式：双击 web.bat，或
    python webui.py [--port 8765] [--no-browser]
"""
import os
import sys
import io
import json
import time
import threading
import traceback
import webbrowser
import collections
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJ_DIR not in sys.path:
    sys.path.insert(0, PROJ_DIR)

# 控制台中文
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import device as d
import ui_state as u
import engine as e
import rating_reader as rr

DEFAULT_PORT = 8765


# ============================================================ 日志捕获
class LogBuffer:
    """线程安全的日志环形缓冲，供网页轮询"""

    def __init__(self, maxlen=1200):
        self._buf = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, msg):
        with self._lock:
            self._buf.append({"t": time.strftime("%H:%M:%S"), "m": str(msg)})

    def snapshot(self, since=0):
        with self._lock:
            items = list(self._buf)
        return items[since:] if since < len(items) else []

    def total(self):
        with self._lock:
            return len(self._buf)


LOG = LogBuffer()

_orig_log = d.log


def _patched_log(msg, file="run.log"):
    LOG.add(msg)
    try:
        _orig_log(msg, file)
    except Exception:
        pass


d.log = _patched_log


# ============================================================ 任务取消
class TaskCancelled(Exception):
    pass


CANCEL = threading.Event()

_orig_detect = u.detect
_last_state = {"v": None}

# 这些状态下不允许中断（保护 1 分钟规则 / 不误点"离开"）
UNINTERRUPTIBLE = ("battle", "battle_prep", "leave_warning")


def _guarded_detect(*args, **kwargs):
    """
    包装 ui_state.detect：
      * 记录最近状态，供取消判定
      * 收到停止请求时，**只在非战斗状态**抛出取消异常
        （战斗中会延后到安全点，避免违反"1分钟内不得退出"）
    """
    res = _orig_detect(*args, **kwargs)
    try:
        _last_state["v"] = res.get("state")
    except Exception:
        pass
    if CANCEL.is_set() and _last_state["v"] not in UNINTERRUPTIBLE:
        raise TaskCancelled("用户已请求停止")
    return res


u.detect = _guarded_detect

# 让冷却等待等长耗时环节也能响应停止
e.STOP_HOOK = CANCEL.is_set


# ============================================================ 任务执行器
class TaskRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.action = None
        self.started_at = None
        self.finished_at = None
        self.result = None
        self.error = None
        self.running = False

    def is_running(self):
        with self.lock:
            return self.running

    def start(self, action, params):
        with self.lock:
            if self.running:
                return False, "已有任务在运行，请先停止或等待完成"
            self.running = True
            self.action = action
            self.params = params
            self.started_at = time.time()
            self.finished_at = None
            self.result = None
            self.error = None
            CANCEL.clear()
            LOG.add("=" * 60)
            LOG.add("▶ 开始任务：%s  参数=%s" % (action, params))
            LOG.add("=" * 60)
            self.thread = threading.Thread(target=self._run, args=(action, params),
                                           daemon=True)
            self.thread.start()
            return True, "已启动"

    def _run(self, action, params):
        try:
            res = dispatch(action, params)
            self.result = res
            d.log("✔ 任务完成：%s → %s" % (action, res))
        except TaskCancelled:
            self.error = "已取消"
            d.log("■ 任务已停止：%s" % action)
        except Exception as ex:
            self.error = "%s: %s" % (type(ex).__name__, ex)
            d.log("✘ 任务异常：%s" % self.error)
            d.log(traceback.format_exc()[-1500:])
        finally:
            with self.lock:
                self.running = False
                self.finished_at = time.time()

    def stop(self):
        if not self.running:
            return False, "当前没有运行中的任务"
        CANCEL.set()
        LOG.add("… 收到停止请求，正在安全退出（当前步骤结束后生效）")
        return True, "已请求停止"

    def status(self):
        with self.lock:
            elapsed = None
            if self.started_at:
                end = self.finished_at or time.time()
                elapsed = round(end - self.started_at, 1)
            return {
                "running": self.running,
                "action": self.action,
                "elapsed": elapsed,
                "result": self.result if isinstance(self.result, (int, float, str, bool, type(None))) else str(self.result),
                "error": self.error,
            }


RUNNER = TaskRunner()


# ============================================================ 动作分发
def _battle_once(_p):
    return e.goal_battle()


def _loop(p):
    cycles = int(p.get("cycles", 3))
    e.get_rating(note="循环前基线")
    ok = 0
    for i in range(cycles):
        d.log("=== 循环 %d/%d ===" % (i + 1, cycles))
        if e.goal_battle():
            ok += 1
        e.get_rating(note="第 %d 轮后" % (i + 1))
        if CANCEL.is_set():
            break
        time.sleep(3)
    e.rating_history_report()
    return "%d/%d 局完成" % (ok, cycles)


def _ads(p):
    w, c, dr = e.goal_ads(
        rounds=int(p.get("rounds", 8)),
        minutes=float(p.get("minutes", 25)),
        lottery=bool(p.get("lottery", False)),
        replenish=int(p.get("replenish", 0)),
        wait_cooldown=bool(p.get("wait", True)),
        upgrade=bool(p.get("upgrade", True)),
    )
    return "广告 %d 次 / 领奖 %d 次 / 抽奖 %d 次" % (w, c, dr)


def _daily(p):
    if not e.nav_to_daily_tasks():
        return "无法进入每日任务页"
    w, c = e.watch_daily_task_ads(max_ads=int(p.get("rounds", 6)))
    return "广告 %d 次 / 领奖 %d 次" % (w, c)


def _lottery(p):
    n = e.run_lottery(max_draws=int(p.get("draws", 3)),
                      wait_cooldown=bool(p.get("wait", True)))
    return "抽奖 %d 次" % n


def _upgrade(p):
    n = e.upgrade_by_ads(max_ads=int(p.get("max_ads", 12)))
    return "升级加速 %d 次（约 -%d 小时）" % (n, n * 4)


def _deals(p):
    a2, c2 = e.watch_deals_ads(cards=int(p.get("cards", 3)),
                               replenish=int(p.get("replenish", 0)))
    return "特惠礼包：广告 %d 次 / 领取 %d 次" % (a2, c2)


def _claim(p):
    if not e.nav_to_tasks():
        return "无法进入活动任务页"
    return "领取 %d 次" % e.claim_task_rewards()


def _rating(p):
    r = e.get_rating(note="网页读取")
    return r.get("rating")


def _history(p):
    t = e.rating_history_report()
    if not t:
        return "样本不足"
    return "首 %s → 末 %s （%+d）" % (t["first"], t["last"], t["delta"])


def _state(p):
    info = u.detect(save_name="state_now.png")
    return "当前界面：%s" % info["state"]


def _home(p):
    return "回到机库" if e.go_home() else "未能回到机库"


ACTIONS = {
    "state":   (lambda p: e.go_home() and _state(p), "识别当前界面"),
    "home":    (_home, "回到机库"),
    "claim":   (_claim, "领取活动任务奖励"),
    "daily":   (_daily, "每日任务：看广告 + 领奖"),
    "lottery": (_lottery, "供给中心抽奖（3 次/天）"),
    "upgrade": (_upgrade, "升级加速：看广告减 4 小时"),
    "deals":   (_deals, "特惠礼包：看广告领前 3 个"),
    "ads":     (_ads, "广告流程（多来源）"),
    "battle":  (_battle_once, "打一局（≥70 秒）"),
    "loop":    (_loop, "多轮对局 + 记录分值"),
    "rating":  (_rating, "读取荣誉积分"),
    "history": (_history, "分值历史趋势"),
    "all":     (_ads, "完整日常（广告+抽奖+补充）"),
}


def dispatch(action, params):
    fn, _ = ACTIONS[action]
    return fn(params)


# ============================================================ 截图
_shot_cache = {"ts": 0.0, "png": None}
_shot_lock = threading.Lock()


def get_screenshot(max_age=2.5):
    """返回 PNG bytes（带短缓存，减少对设备的压力）"""
    with _shot_lock:
        now = time.time()
        if _shot_cache["png"] and (now - _shot_cache["ts"]) < max_age:
            return _shot_cache["png"]
        try:
            from PIL import Image
            arr, _ = d.screenshot(None, save=False)
            if arr is None:
                return _shot_cache["png"]
            im = Image.fromarray(arr)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=70)
            png = buf.getvalue()
            _shot_cache["png"] = png
            _shot_cache["ts"] = now
            return png
        except Exception:
            return _shot_cache["png"]


# ============================================================ 页面
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>War Robots 自动化控制台</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2230; --line:#2d3646;
    --txt:#e6edf3; --dim:#8b949e; --acc:#2f81f7; --ok:#3fb950;
    --warn:#d29922; --err:#f85149; --purple:#a371f7;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font:14px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
  header{display:flex;align-items:center;gap:14px;padding:12px 18px;
         background:var(--panel);border-bottom:1px solid var(--line);
         position:sticky;top:0;z-index:5}
  header h1{font-size:16px;margin:0;font-weight:600}
  .badge{padding:3px 10px;border-radius:99px;font-size:12px;font-weight:600}
  .b-idle{background:#21262d;color:var(--dim)}
  .b-run{background:#1f6feb33;color:#79c0ff;border:1px solid #1f6feb}
  .b-ok{background:#2ea04326;color:var(--ok);border:1px solid #2ea043}
  .b-err{background:#f8514926;color:var(--err);border:1px solid #f85149}
  .spacer{flex:1}
  main{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:14px;padding:14px}
  @media(max-width:1100px){main{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
        padding:14px}
  .card h2{font-size:13px;margin:0 0 12px;color:var(--dim);
           text-transform:uppercase;letter-spacing:.06em;font-weight:600}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);
         background:var(--panel2);color:var(--txt);padding:11px 12px;
         text-align:left;transition:.15s;line-height:1.35}
  button:hover:not(:disabled){border-color:var(--acc);background:#22304a}
  button:disabled{opacity:.42;cursor:not-allowed}
  button .t{display:block;font-weight:600;font-size:14px}
  button .s{display:block;font-size:11px;color:var(--dim);margin-top:3px}
  .btn-primary{border-color:#238636;background:#1a7f37}
  .btn-primary:hover:not(:disabled){background:#238636;border-color:#3fb950}
  .btn-danger{border-color:#8b2d2d;background:#4a1d1d}
  .btn-danger:hover:not(:disabled){background:#6e2b2b;border-color:#f85149}
  .btn-warn{border-color:#7a5c15;background:#3d2f0a}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
  label.opt{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dim)}
  input[type=number],input[type=text]{width:74px;background:#0d1117;color:var(--txt);
       border:1px solid var(--line);border-radius:6px;padding:5px 7px;font:inherit}
  input[type=checkbox]{accent-color:var(--acc)}
  #log{height:300px;overflow:auto;background:#0a0d12;border:1px solid var(--line);
       border-radius:8px;padding:10px;font:12px/1.5 Consolas,"Courier New",monospace;
       white-space:pre-wrap;word-break:break-all}
  #log div{margin:1px 0}
  #log .t{color:#6e7681;margin-right:8px}
  #log .e{color:var(--err)}
  #log .o{color:var(--ok)}
  #shot{width:100%;border-radius:8px;border:1px solid var(--line);background:#000;
        aspect-ratio:20/9;object-fit:contain}
  .kv{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;
      border-bottom:1px dashed #21262d}
  .kv span:first-child{color:var(--dim)}
  .chart{display:flex;align-items:flex-end;gap:3px;height:74px;margin-top:8px}
  .chart div{flex:1;background:linear-gradient(180deg,#2f81f7,#1a4f9e);
             border-radius:2px 2px 0 0;min-height:3px;position:relative}
  .chart div[data-d]{position:relative}
  .hint{font-size:12px;color:var(--dim);margin-top:8px;line-height:1.6}
  .toast{position:fixed;right:18px;bottom:18px;background:#21262d;color:var(--txt);
         border:1px solid var(--line);border-left:3px solid var(--acc);
         padding:11px 15px;border-radius:8px;font-size:13px;opacity:0;
         transform:translateY(8px);transition:.25s;max-width:340px;z-index:20}
  .toast.show{opacity:1;transform:none}
</style>
</head>
<body>
<header>
  <h1>War Robots 自动化控制台</h1>
  <span style="color:#6e7681;font-size:11px;letter-spacing:.04em">build 2</span>
  <span id="badge" class="badge b-idle">空闲</span>
  <span id="elapsed" style="color:var(--dim);font-size:12px"></span>
  <span class="spacer"></span>
  <span id="ui" class="badge b-idle">界面：—</span>
  <button id="btnStop" class="btn-danger" style="padding:7px 14px" disabled>■ 停止</button>
</header>

<main>
  <div>
    <div class="card" style="margin-bottom:14px">
      <h2>常用操作</h2>
      <div class="grid">
        <button data-a="state"><span class="t">识别界面</span><span class="s">看当前在哪个界面</span></button>
        <button data-a="home"><span class="t">回到机库</span><span class="s">任意界面复位</span></button>
        <button data-a="claim"><span class="t">领取任务奖励</span><span class="s">活动任务礼包</span></button>
        <button data-a="rating"><span class="t">读取荣誉积分</span><span class="s">当前难度分值</span></button>
        <button data-a="history"><span class="t">分值趋势</span><span class="s">历史变化</span></button>
        <button data-a="battle" class="btn-primary"><span class="t">打一局</span><span class="s">停留 ≥70 秒</span></button>
      </div>
    </div>

    <div class="card" style="margin-bottom:14px">
      <h2>广告 / 领资源</h2>
      <div class="grid">
        <button data-a="daily"><span class="t">每日任务</span><span class="s">看广告 + 领奖</span></button>
        <button data-a="lottery" class="btn-warn"><span class="t">供给中心抽奖</span><span class="s">3 次/天，含冷却等待</span></button>
        <button data-a="upgrade"><span class="t">升级减时</span><span class="s">看广告 −4 小时升级</span></button>
        <button data-a="deals"><span class="t">特惠礼包</span><span class="s">购物车 → 看广告领前 3 个</span></button>
        <button data-a="ads"><span class="t">广告流程</span><span class="s">每日/活动/黑市自动切换</span></button>
        <button data-a="all" class="btn-primary"><span class="t">完整日常</span><span class="s">领奖 + 广告 + 抽奖 + 升级</span></button>
      </div>
      <div class="row">
        <label class="opt">广告轮数 <input type="number" id="p_rounds" value="8" min="1" max="30"></label>
        <label class="opt">补充战斗 <input type="number" id="p_replenish" value="0" min="0" max="6"></label>
        <label class="opt"><input type="checkbox" id="p_lottery"> 含抽奖</label>
        <label class="opt"><input type="checkbox" id="p_wait" checked> 等冷却</label>
      </div>
    </div>

    <div class="card">
      <h2>降难度（循环对局）</h2>
      <div class="grid">
        <button data-a="loop" class="btn-primary"><span class="t">循环打局</span><span class="s">每局 ≥70 秒 + 记录分值</span></button>
      </div>
      <div class="row">
        <label class="opt">局数 <input type="number" id="p_cycles" value="6" min="1" max="30"></label>
      </div>
      <div class="hint">
        技巧：不要指望单局就降分。建议每天点一次「循环打局」（6 局约 15 分钟），
        再用「分值趋势」对比首末值。目标分值与难度正相关，越低越好。
      </div>
    </div>
  </div>

  <div>
    <div class="card" style="margin-bottom:14px">
      <h2>手机画面 <span id="shotTs" style="color:var(--dim);font-weight:400;text-transform:none"></span></h2>
      <img id="shot" alt="手机截图">
      <div class="row">
        <label class="opt"><input type="checkbox" id="autoShot" checked> 自动刷新（3 秒）</label>
        <button id="btnShot" style="padding:6px 12px;font-size:12px">立即刷新</button>
      </div>
    </div>

    <div class="card" style="margin-bottom:14px">
      <h2>分值记录</h2>
      <div id="kvbox"></div>
      <div class="chart" id="chart"></div>
    </div>

    <div class="card">
      <h2>运行日志</h2>
      <div id="log"></div>
      <div class="row">
        <label class="opt"><input type="checkbox" id="autoScroll" checked> 自动滚动</label>
        <button id="btnClear" style="padding:6px 12px;font-size:12px">清空显示</button>
      </div>
    </div>
  </div>
</main>

<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
let logSince = 0, busy = false, toastTimer = null;

function toast(msg){
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>el.classList.remove('show'), 3200);
}

function params(){
  return {
    rounds: +$('#p_rounds').value || 8,
    replenish: +$('#p_replenish').value || 0,
    cycles: +$('#p_cycles').value || 6,
    lottery: $('#p_lottery').checked,
    wait: $('#p_wait').checked,
    minutes: 25
  };
}

document.querySelectorAll('button[data-a]').forEach(b=>{
  b.addEventListener('click', async ()=>{
    if (busy) { toast('已有任务在运行，请先停止'); return; }
    const a = b.dataset.a;
    const title = b.querySelector('.t').textContent;
    // 立即禁用，避免连点
    document.querySelectorAll('button[data-a]').forEach(x=>{ x.disabled = true; });
    try{
      const r = await fetch('/api/run', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({action:a, params: params()})
      });
      const j = await r.json();
      toast(j.ok ? ('▶ 已启动：' + title) : ('启动失败：' + j.msg));
    }catch(e){
      toast('请求失败：' + e);
    }
    refresh();
  });
});

$('#btnStop').addEventListener('click', async ()=>{
  const r = await fetch('/api/stop', {method:'POST'});
  const j = await r.json();
  toast(j.msg || '已请求停止');
  refresh();
});

$('#btnClear').addEventListener('click', ()=>{ $('#log').innerHTML=''; });
$('#btnShot').addEventListener('click', ()=> refreshShot(true));

async function refreshShot(force){
  if(!force && !$('#autoShot').checked) return;
  try{
    const r = await fetch('/api/shot?t=' + Date.now());
    if(!r.ok) return;
    const blob = await r.blob();
    if(blob.size < 500) return;
    $('#shot').src = URL.createObjectURL(blob);
    $('#shotTs').textContent = new Date().toLocaleTimeString();
  }catch(e){}
}

function addLogs(items){
  const box = $('#log');
  const frag = document.createDocumentFragment();
  for(const it of items){
    const div = document.createElement('div');
    const cls = /✘|异常|失败|ERROR/.test(it.m) ? 'e'
              : (/✔|完成|已恢复|OK/.test(it.m) ? 'o' : '');
    div.className = cls;
    div.innerHTML = '<span class="t">' + it.t + '</span>' +
                    it.m.replace(/[<>&]/g, c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
    frag.appendChild(div);
  }
  box.appendChild(frag);
  if($('#autoScroll').checked) box.scrollTop = box.scrollHeight;
}

async function refresh(){
  try{
    const r = await fetch('/api/status?since=' + logSince);
    const j = await r.json();

    busy = j.task.running;
    const b = $('#badge');
    if(busy){
      b.className = 'badge b-run'; b.textContent = '运行中：' + j.task.action;
      $('#elapsed').textContent = j.task.elapsed != null ? (j.task.elapsed + ' 秒') : '';
    }else{
      if(j.task.error){
        b.className = 'badge b-err'; b.textContent = '上次失败';
        $('#elapsed').textContent = j.task.error;
      }else if(j.task.result !== null && j.task.result !== undefined && j.task.action){
        b.className = 'badge b-ok'; b.textContent = '上次完成';
        $('#elapsed').textContent = String(j.task.result);
      }else{
        b.className = 'badge b-idle'; b.textContent = '空闲';
        $('#elapsed').textContent = '';
      }
    }
    $('#btnStop').disabled = !busy;
    document.querySelectorAll('button[data-a]').forEach(x=>{ x.disabled = busy; });

    const uiEl = $('#ui');
    uiEl.textContent = '界面：' + (j.ui_state || '—');
    uiEl.className = 'badge ' + (j.ui_state === 'battle' ? 'b-run'
                     : j.ui_state === 'hangar' ? 'b-ok' : 'b-idle');

    if(j.logs && j.logs.length){ addLogs(j.logs); }
    logSince = j.log_total;

    // 分值
    if(j.rating && j.rating.length){
      const hist = j.rating;
      const last = hist[hist.length-1];
      const first = hist[0];
      $('#kvbox').innerHTML =
        '<div class="kv"><span>最新分值</span><span style="color:var(--acc);font-weight:700">' + last.rating + '</span></div>' +
        '<div class="kv"><span>样本数</span><span>' + hist.length + '</span></div>' +
        '<div class="kv"><span>首值 → 末值</span><span>' + first.rating + ' → ' + last.rating +
          ' <b style="color:' + (last.rating < first.rating ? 'var(--ok)':'var(--warn)') + '">' +
          (last.rating - first.rating >= 0 ? '+' : '') + (last.rating - first.rating) + '</b></span></div>';
      const vals = hist.map(h=>h.rating);
      const mn = Math.min(...vals), mx = Math.max(...vals);
      $('#chart').innerHTML = hist.slice(-24).map(h=>{
        const pct = mx===mn ? 55 : 12 + (h.rating-mn)/(mx-mn)*84;
        return '<div style="height:' + pct + '%" title="' + h.ts + ' ' + h.rating + '"></div>';
      }).join('');
    }
  }catch(e){ /* 网络抖动忽略 */ }
}

setInterval(refresh, 1500);
setInterval(()=>{ if(!$('#autoShot').checked) return; refreshShot(false); }, 3000);
refresh(); refreshShot(true);
</script>
</body>
</html>
"""


# ============================================================ HTTP 服务
class Handler(BaseHTTPRequestHandler):
    server_version = "WRAuto/1.0"

    def log_message(self, fmt, *args):
        pass  # 静默，避免刷屏

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    # ---------------- GET ----------------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
            return

        if self.path.startswith("/api/status"):
            since = 0
            if "since=" in self.path:
                try:
                    since = int(self.path.split("since=")[1].split("&")[0])
                except Exception:
                    since = 0
            st = RUNNER.status()
            try:
                ui_state = _orig_detect(keep=False)["state"]
            except Exception:
                ui_state = None
            hist = rr.load_history()[-30:]
            self._json({
                "task": st,
                "ui_state": ui_state,
                "logs": LOG.snapshot(since),
                "log_total": LOG.total(),
                "rating": hist,
            })
            return

        if self.path.startswith("/api/shot"):
            png = get_screenshot()
            if not png:
                self._send(503, b"no screenshot", "text/plain")
                return
            self._send(200, png, "image/jpeg")
            return

        self._send(404, "not found", "text/plain; charset=utf-8")

    # ---------------- POST ----------------
    def do_POST(self):
        if self.path == "/api/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:
                self._json({"ok": False, "msg": "请求体解析失败"}, 400)
                return
            action = data.get("action")
            params = data.get("params") or {}
            if action not in ACTIONS:
                self._json({"ok": False, "msg": "未知动作：%s" % action}, 400)
                return
            ok, msg = RUNNER.start(action, params)
            self._json({"ok": ok, "msg": msg})
            return

        if self.path == "/api/stop":
            ok, msg = RUNNER.stop()
            self._json({"ok": ok, "msg": msg})
            return

        self._json({"ok": False, "msg": "not found"}, 404)


# ============================================================ 启动
def main():
    ap = argparse.ArgumentParser(description="War Robots 自动化 Web UI")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    # 启动前检查设备
    d.ensure_server()
    devs = [x for x in d.devices() if x["state"] == "device"]
    url = "http://%s:%d/" % (args.host, args.port)

    print("=" * 62)
    print(" War Robots 自动化 Web UI")
    print("=" * 62)
    if devs:
        print(" 设备: %s" % devs[0]["raw"].strip())
    else:
        print(" ⚠ 未检测到已授权设备！请在手机允许 USB 调试后再操作")
        print("   （页面仍可打开，执行任务时会报错）")
    print(" 地址: %s" % url)
    print(" 关闭本窗口即停止服务")
    print("=" * 62)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
