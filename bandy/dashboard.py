"""Dashboard Web 服务: 模型看板 + 对话记录 + 吞吐指标"""
import json
import time
from aiohttp import web

from .config import cfg
from .metrics import store

_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bandy Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f1117;--card:#1a1d2e;--border:#2a2d3e;--text:#e4e4e7;--dim:#8b8fa3;
--accent:#6366f1;--green:#22c55e;--orange:#f59e0b;--red:#ef4444;--blue:#3b82f6}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;padding:20px}
h1{font-size:22px;font-weight:600;margin-bottom:20px;display:flex;align-items:center;gap:10px}
h1 .dot{width:10px;height:10px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px}
.card h3{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
.metric{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.metric .label{color:var(--dim);font-size:13px}
.metric .value{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}
.metric .unit{font-size:12px;color:var(--dim);margin-left:4px}
.model-badge{display:inline-flex;align-items:center;gap:6px;background:#252840;border-radius:6px;padding:4px 10px;font-size:13px;margin-bottom:6px}
.model-badge .name{color:var(--accent);font-weight:600}
.model-badge .ver{color:var(--dim)}
.sessions{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:24px}
.sessions h3{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
.session{border-left:3px solid var(--accent);padding-left:14px;margin-bottom:20px}
.session.active{border-color:var(--green)}
.session-head{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:13px;color:var(--dim)}
.session-head .sid{color:var(--accent);font-weight:600}
.session-head .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}
.session-head .badge.on{background:rgba(34,197,94,.15);color:var(--green)}
.session-head .badge.off{background:rgba(139,143,163,.1);color:var(--dim)}
.turn{display:flex;gap:10px;margin-bottom:6px;font-size:14px;line-height:1.5}
.turn .role{flex-shrink:0;width:36px;text-align:right;font-weight:600}
.turn .role.user{color:var(--blue)}
.turn .role.assistant{color:var(--green)}
.turn .text{flex:1}
.turn .perf{flex-shrink:0;color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums;text-align:right;min-width:80px}
.throughput{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px}
.throughput h3{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:6px 8px;border-bottom:1px solid rgba(42,45,62,.5);font-variant-numeric:tabular-nums}
.bar{height:6px;border-radius:3px;background:var(--accent);transition:width .6s}
.bar-bg{height:6px;border-radius:3px;background:var(--border);width:100%}
footer{text-align:center;color:var(--dim);font-size:12px;padding:20px 0}
</style>
</head>
<body>
<h1><span class="dot"></span> Bandy Dashboard</h1>
<div class="grid" id="models"></div>
<div class="grid" id="stats"></div>
<div class="sessions" id="sessions"><h3>对话记录</h3><div id="session-list"></div></div>
<div class="grid">
<div class="throughput" id="stt-table"><h3>STT 历史</h3><div id="stt-rows"></div></div>
<div class="throughput" id="llm-table"><h3>LLM 历史</h3><div id="llm-rows"></div></div>
</div>
<footer>自动刷新 3s · Bandy Voice Assistant</footer>
<script>
function fmt(ts){if(!ts)return'-';const d=new Date(ts*1000);return d.toLocaleTimeString('zh-CN',{hour12:false})}
function dur(s){if(!s||s<=0)return'-';if(s<60)return s.toFixed(1)+'s';return (s/60).toFixed(1)+'m'}

function render(d){
  // Models
  let mh='';
  for(const[k,v]of Object.entries(d.models)){
    if(!v.name)continue;
    mh+=`<div class="card"><h3>${k.toUpperCase()} 模型</h3>
      <div class="model-badge"><span class="name">${v.name}</span><span class="ver">${v.version||''}</span></div></div>`;
  }
  document.getElementById('models').innerHTML=mh;

  // Stats cards
  const s=d.stats;let sh='';
  sh+=`<div class="card"><h3>运行状态</h3>
    <div class="metric"><span class="label">运行时间</span><span class="value">${dur(d.uptime)}</span></div>
    <div class="metric"><span class="label">总会话数</span><span class="value">${d.sessions.length}</span></div></div>`;
  sh+=`<div class="card"><h3>STT 语音识别</h3>
    <div class="metric"><span class="label">总调用</span><span class="value">${s.stt.total_calls}</span></div>
    <div class="metric"><span class="label">平均耗时</span><span class="value">${s.stt.avg_process_time}<span class="unit">s</span></span></div>
    <div class="metric"><span class="label">加速比</span><span class="value">${s.stt.avg_speed_ratio}<span class="unit">x</span></span></div></div>`;
  sh+=`<div class="card"><h3>LLM 大语言模型</h3>
    <div class="metric"><span class="label">总调用</span><span class="value">${s.llm.total_calls}</span></div>
    <div class="metric"><span class="label">吞吐速度</span><span class="value">${s.llm.avg_tokens_per_sec}<span class="unit">tok/s</span></span></div>
    <div class="metric"><span class="label">首Token</span><span class="value">${s.llm.avg_ttft}<span class="unit">s</span></span></div></div>`;
  sh+=`<div class="card"><h3>TTS 语音合成</h3>
    <div class="metric"><span class="label">总调用</span><span class="value">${s.tts.total_calls}</span></div>
    <div class="metric"><span class="label">合成速度</span><span class="value">${s.tts.avg_chars_per_sec}<span class="unit">字/s</span></span></div>
    <div class="metric"><span class="label">平均耗时</span><span class="value">${s.tts.avg_synth_time}<span class="unit">s</span></span></div></div>`;
  if(s.vision.total_calls>0){
    sh+=`<div class="card"><h3>Vision 视觉识别</h3>
      <div class="metric"><span class="label">总调用</span><span class="value">${s.vision.total_calls}</span></div>
      <div class="metric"><span class="label">平均耗时</span><span class="value">${s.vision.avg_process_time}<span class="unit">s</span></span></div></div>`;
  }
  document.getElementById('stats').innerHTML=sh;

  // Sessions (newest first)
  const sess=[...d.sessions].reverse().slice(0,20);
  let sl='';
  for(const se of sess){
    const cls=se.active?'session active':'session';
    const badge=se.active?'<span class="badge on">进行中</span>':'<span class="badge off">已结束</span>';
    sl+=`<div class="${cls}"><div class="session-head"><span class="sid">#${se.id}</span>${badge}<span>${fmt(se.start)}</span>`;
    if(se.end)sl+=`<span>~ ${fmt(se.end)}</span>`;
    sl+=`</div>`;
    for(const t of se.turns){
      const rc=t.role==='user'?'user':'assistant';
      let perf='';
      if(t.stt_time)perf+=`STT ${t.stt_time.toFixed(2)}s `;
      if(t.llm_tps)perf+=`${t.llm_tps.toFixed(1)}tok/s `;
      if(t.llm_ttft)perf+=`TTFT ${t.llm_ttft.toFixed(2)}s `;
      if(t.tts_time)perf+=`TTS ${t.tts_time.toFixed(2)}s `;
      if(t.vision_time)perf+=`V ${t.vision_time.toFixed(1)}s `;
      sl+=`<div class="turn"><span class="role ${rc}">${t.role==='user'?'用户':'助手'}</span>
        <span class="text">${esc(t.text)}</span><span class="perf">${perf}</span></div>`;
    }
    sl+=`</div>`;
  }
  document.getElementById('session-list').innerHTML=sl||'<div style="color:var(--dim)">暂无会话</div>';

  // STT table
  const stt=[...d.recent_stt].reverse();
  let st='<table><tr><th>时间</th><th>文本</th><th>音频</th><th>耗时</th><th>加速比</th></tr>';
  for(const r of stt){
    st+=`<tr><td>${fmt(r.ts)}</td><td>${esc(r.text).slice(0,30)}</td><td>${r.audio_dur}s</td><td>${r.proc_time}s</td><td>${r.speed_ratio}x</td></tr>`;
  }
  document.getElementById('stt-rows').innerHTML=st+'</table>';

  // LLM table
  const llm=[...d.recent_llm].reverse();
  let lt='<table><tr><th>时间</th><th>输入</th><th>Token</th><th>吞吐</th><th>首Token</th><th>总耗时</th></tr>';
  for(const r of llm){
    lt+=`<tr><td>${fmt(r.ts)}</td><td>${esc(r.prompt).slice(0,25)}</td><td>${r.tokens}</td><td>${r.tps}tok/s</td><td>${r.ttft}s</td><td>${r.total}s</td></tr>`;
  }
  document.getElementById('llm-rows').innerHTML=lt+'</table>';
}

function esc(s){if(!s)return'';return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

async function poll(){
  try{
    const r=await fetch('/api/metrics');
    const d=await r.json();
    render(d);
  }catch(e){console.error(e)}
}
poll();
setInterval(poll,3000);
</script>
</body>
</html>"""


async def _handle_index(request):
    return web.Response(text=_HTML, content_type='text/html')


async def _handle_metrics(request):
    return web.json_response(store.snapshot())


async def start_dashboard(port=None):
    """启动 dashboard web 服务, 返回 runner (可用于清理)."""
    if port is None:
        port = cfg.DASHBOARD_PORT
    app = web.Application()
    app.router.add_get('/', _handle_index)
    app.router.add_get('/api/metrics', _handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"📊 Dashboard: http://localhost:{port}", flush=True)
    return runner
