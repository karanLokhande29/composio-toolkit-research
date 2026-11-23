#!/usr/bin/env python3
"""Tiny local review tool for the human sample (Loop 4). Standard library only.

  python scripts/review_server.py      ->  open http://localhost:8765

Shows each sampled (app, field) with pass-1 value, final value and the evidence snippet + link.
Click y/n (or press keys) and every click is saved straight into human_review/sample.csv.
Only a human uses this; the agent never writes the human columns.
"""
import csv
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "human_review" / "sample.csv"
RES = ROOT / "data" / "results.json"

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Human review</title><style>
body{font:14px/1.45 system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1b1f24}
header{position:sticky;top:0;background:#1b1f24;color:#fff;padding:10px 16px;display:flex;gap:16px;align-items:center;z-index:2}
.card{background:#fff;margin:10px 16px;padding:12px 14px;border-radius:8px;border-left:5px solid #c9ced6}
.card.done{border-left-color:#1a7f37}.card.cur{outline:2px solid #0969da}
.f{font-weight:600}.v{font-family:ui-monospace,monospace;background:#f0f2f5;padding:2px 6px;border-radius:4px;word-break:break-word}
.diff{background:#fff4d6}.snip{color:#57606a;font-size:13px;margin:6px 0}
button{border:1px solid #c9ced6;background:#fff;border-radius:6px;padding:3px 10px;cursor:pointer;margin-right:4px}
button.on.y{background:#1a7f37;color:#fff}button.on.n{background:#cf222e;color:#fff}
input{width:60%;padding:3px 6px;border:1px solid #c9ced6;border-radius:4px}
a{color:#0969da}.row{margin:4px 0}.links a{margin-right:10px;font-size:12px}
</style></head><body><header><b>Human review</b><span id="prog"></span>
<span style="font-size:12px;opacity:.8">keys: y / n = both same answer, 1/2 = pass1 y/n, 3/4 = final y/n, j/k next/prev</span></header>
<div id="list"></div><script>
let rows=__ROWS__, links=__LINKS__, cur=0;
function save(){fetch('/save',{method:'POST',body:JSON.stringify(rows)});render()}
function set(i,k,v){rows[i][k]=v;save()}
function card(r,i){const same=r.pass1_value===r.final_value;
 const b=(k)=>['y','n'].map(v=>`<button class="${v} ${r[k]===v?'on':''}" onclick="set(${i},'${k}','${v}')">${v}</button>`).join('');
 const l=(links[r.app_id]||[]).map(u=>`<a href="${u}" target="_blank">${u.replace(/^https?:\/\//,'').slice(0,55)}</a>`).join('');
 return `<div class="card ${r.pass1_correct&&r.final_correct?'done':''} ${i===cur?'cur':''}" id="c${i}" onclick="cur=${i}">
 <div><b>#${r.app_id} ${r.app}</b> · <span class="f">${r.field}</span> · <span style="color:#57606a">${r.category}</span></div>
 <div class="row">pass 1: <span class="v ${same?'':'diff'}">${esc(r.pass1_value)}</span> ${b('pass1_correct')}</div>
 <div class="row">final: <span class="v ${same?'':'diff'}">${esc(r.final_value)}</span> ${b('final_correct')} ${same?'<i style="color:#57606a">(same value)</i>':'<b style="color:#9a6700">changed by loops</b>'}</div>
 <div class="snip">evidence: ${r.evidence_url?`<a href="${r.evidence_url}" target="_blank">${r.evidence_url}</a><br>“${esc(r.evidence_snippet)}”`:'<i>none</i>'}</div>
 <div class="links">docs: ${l}</div>
 <div class="row">correct value (if wrong): <input value="${esc(r.human_value)}" onchange="set(${i},'human_value',this.value)"> note: <input style="width:20%" value="${esc(r.note)}" onchange="set(${i},'note',this.value)"></div></div>`}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(){document.getElementById('list').innerHTML=rows.map(card).join('');
 const d=rows.filter(r=>r.pass1_correct&&r.final_correct).length;document.getElementById('prog').textContent=`${d} / ${rows.length} done`}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;const r=rows[cur];
 if(e.key==='y'||e.key==='n'){r.pass1_correct=r.pass1_value===r.final_value?e.key:r.pass1_correct;r.final_correct=e.key;
   if(r.pass1_value===r.final_value){cur=Math.min(cur+1,rows.length-1)};save()}
 else if(e.key==='1'){set(cur,'pass1_correct','y')}else if(e.key==='2'){set(cur,'pass1_correct','n')}
 else if(e.key==='3'){set(cur,'final_correct','y');cur=Math.min(cur+1,rows.length-1);render()}else if(e.key==='4'){set(cur,'final_correct','n')}
 else if(e.key==='j'){cur=Math.min(cur+1,rows.length-1);render()}else if(e.key==='k'){cur=Math.max(cur-1,0);render()}else return;
 document.getElementById('c'+cur)?.scrollIntoView({block:'center'})});
render();</script></body></html>"""


def doc_links():
    """Top docs links per app (auth/access/pricing pages) so the reviewer can open them quickly."""
    out = {}
    if RES.exists():
        for r in json.loads(RES.read_text()):
            urls = []
            for g in ("auth", "access", "api_surface"):
                urls += [e["url"] for e in r[g].get("evidence", [])]
            seen = []
            for u in urls:
                if u not in seen:
                    seen.append(u)
            out[str(r["id"])] = seen[:5]
    return out


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        rows = list(csv.DictReader(CSV.open()))
        body = PAGE.replace("__ROWS__", json.dumps(rows)).replace("__LINKS__", json.dumps(doc_links())).encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        rows = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        self.send_response(204); self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Review tool: http://localhost:8765  (Ctrl+C to stop; answers save on every click)")
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()
