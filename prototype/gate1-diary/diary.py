#!/usr/bin/env python3
# ============================================================================
# 闸门1·原型：用一天存量相册照片跑通日记生成（THROWAWAY PROTOTYPE）
#
#   Issue: https://github.com/Naoki326/diary/issues/2
#   问题: AI 整理出的日记是否产出「值得回忆」的价值？上限/下限在哪？
#
#   管线: photo_dir → (sips 转 jpg/缩图) → 分批视觉打标 → 汇总生成日记
#   输出: out/<run>/ 下的 diary-<model>.md × N 档模型 + report.md + index.html
#
#   用法:
#     python3 prototype/gate1-diary/diary.py <photo_dir> [--date 2026-10-03]
#          [--models glm-5.3-flash,glm-4.6v-flashx,glm-4.6v-flash]
#          [--batch-size 12] [--max-width 1280] [--provider zai-pro] [--out out]
#
#   key 从 ~/.pi/agent/models.json 的 <provider>.apiKey 读取，绝不打印。
#   依赖: macOS 自带 sips / mdls；Python 3.9+ 标准库。
# ============================================================================
import argparse
import base64
import concurrent.futures as cf
import datetime as dt
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

HOME = os.path.expanduser("~")
PI_MODELS = os.path.join(HOME, ".pi/agent/models.json")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# 元/百万 token (input, output) — 2026-10-07 智谱官方 pricing.md
#   glm-4.6v-flashx 为 ≤32K 档价格；缓存命中价更低，此处按未命中计（上界）
PRICES = {
    "glm-5.3-flash": (0.8, 2.8),
    "glm-4.6v-flashx": (0.15, 1.5),
    "glm-4.6v-flash": (0.0, 0.0),
    "glm-4.1v-thinking-flash": (0.0, 0.0),
}


def die(msg):
    print(f"[FATAL] {msg}", file=sys.stderr)
    sys.exit(1)


def sh(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- key/config
def load_provider(provider):
    with open(PI_MODELS) as f:
        cfg = json.load(f)["providers"][provider]
    return cfg["apiKey"], cfg["baseUrl"].rstrip("/")


# ---------------------------------------------------------------- photo prep
def photo_timestamp(path):
    """EXIF 拍摄时间 → mdls; 失败退回文件 mtime。"""
    r = sh(["mdls", "-name", "kMDItemContentCreationDate", "-raw", path], timeout=15)
    s = r.stdout.strip()
    if s and s != "(null)" and "Failed" not in s:
        try:
            return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path))


def prepare_image(src, cache_dir, max_width):
    """heic→jpeg 转换 + 长边缩到 max_width；返回 (cached_path, media_type, b64)。"""
    ext = os.path.splitext(src)[1].lower()
    dst = os.path.join(cache_dir, re.sub(r"\W+", "_", os.path.basename(src)) + ".jpg")
    if not os.path.exists(dst):
        tmp = dst + ".tmp.jpg"
        c = ["sips", "-s", "format", "jpeg"]
        # 先量尺寸，长边缩放（resampleWidth/Height 分别作用于宽/高轴）
        g = sh(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src], timeout=15)
        w = h = None
        for line in g.stdout.splitlines():
            m = re.search(r"pixelWidth: (\d+)", line)
            if m:
                w = int(m.group(1))
            m = re.search(r"pixelHeight: (\d+)", line)
            if m:
                h = int(m.group(1))
        if w and h and max(w, h) > max_width:
            c += ["--resampleHeight" if h >= w else "--resampleWidth", str(max_width)]
        c += [src, "--out", tmp]
        r = sh(c, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"sips 失败 {src}: {r.stderr[:200]}")
        os.replace(tmp, dst)
    with open(dst, "rb") as f:
        data = f.read()
    return dst, "image/jpeg", base64.b64encode(data).decode()


# ---------------------------------------------------------------- API client
class Client:
    def __init__(self, key, base_url):
        self.key = key
        self.url = base_url + "/v1/messages"
        self.usage = {"input": 0, "output": 0, "calls": 0, "errors": 0}

    def call(self, model, content, max_tokens=4096, timeout=180, thinking=None):
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if thinking is not None:
            body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        for attempt in range(1, 5):  # 429 退避重试，最多 4 次
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    out = json.load(resp)
                u = out.get("usage", {})
                self.usage["input"] += u.get("input_tokens", 0)
                self.usage["output"] += u.get("output_tokens", 0)
                self.usage["calls"] += 1
                texts = [b.get("text", "") for b in out.get("content", [])
                         if b.get("type") == "text" and b.get("text")]
                if not texts:  # 思考型模型可能只吐 thinking 块
                    texts = [b.get("thinking", "") for b in out.get("content", [])
                             if b.get("type") == "thinking" and b.get("thinking")]
                return "\n".join(texts).strip()
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    wait = 30 * attempt  # 30/60/90s 退避
                    print(f"    [429 限流] 等 {wait}s 重试…", flush=True)
                    time.sleep(wait)
                    continue
                if attempt >= 4:
                    self.usage["errors"] += 1
                    raise
            except Exception:
                self.usage["errors"] += 1
                raise
        self.usage["errors"] += 1
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------- prompts
P_STAGE1 = """你是 lifelogging 管线的照片打标器。下面是同一天按时间顺序拍摄的第 {lo}~{hi} 张照片，每张照片前面的文字给出它的序号和拍摄时间。
对每张照片输出一行 JSON：
{{"i":序号,"t":"HH:MM","where":"地点或场景","who":["人物身份"],"what":"在做什么/发生了什么","detail":"值得记住的细节(食物/天气/表情/物品等)","mood":"画面情绪"}}
只输出 JSON 行，每张照片一行，不要输出其他任何文字。人物用身份称呼（如 我/孩子/爸爸/妈妈/朋友），不要猜真实姓名。看不清的字段写 ""。"""

P_STAGE2 = """你是一位帮家人写日记的 AI。下面是 {date}（{weekday}）这一天拍摄的 {n} 张照片的打标记录，按时间排序。请以照片主人（这天的「我」）的第一人称写一篇当日日记：
- 口语化、温暖、有细节，像当晚睡前自己写下的
- 按时间线自然展开，关键节点用 **HH:MM** 加粗标注；串成叙事，不要流水账
- 提到具体的人（身份称呼）和具体瞬间的小细节（一句对话、一样吃的、一个表情）
- 允许合理的轻想象填补衔接，但事实只能来自打标记录，不编造大事件
- 500~900 字；markdown 输出；第一行 "# {date} {weekday}"

打标记录：
{captions}"""


# ---------------------------------------------------------------- pipeline
def stage1_batch(cli, model, batch, lo_hi):
    lo, hi = lo_hi
    content = []
    for i, ph in enumerate(batch, start=lo):
        content.append({"type": "text",
                        "text": f"[第 {i} 张 · {ph['ts'].strftime('%H:%M')}]"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": ph["media_type"], "data": ph["b64"]}})
    content.append({"type": "text", "text": P_STAGE1.format(lo=lo, hi=hi)})
    raw = cli.call(model, content, max_tokens=8192, thinking=False)
    lines = []
    for line in raw.splitlines():
        line = line.strip().removeprefix("```json").removeprefix("```")
        if line.startswith("{") and line.endswith("}"):
            try:
                o = json.loads(line)
                lines.append(o)
                continue
            except json.JSONDecodeError:
                pass
        if line:
            lines.append({"i": None, "raw": line})  # 宽松兜底
    return lines


def run_model(cli, model, photos, date_label, batch_size):
    t0 = time.time()
    print(f"\n=== 模型 {model}：{len(photos)} 张，分 {(
        len(photos)+batch_size-1)//batch_size} 批打标 ===", flush=True)
    batches, captions = [], []
    for lo in range(0, len(photos), batch_size):
        batches.append((lo + 1, photos[lo:lo + batch_size]))
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(stage1_batch, cli, model, b, (lo, lo + len(b) - 1)): lo
                for lo, b in batches}
        results = {}
        for fut in cf.as_completed(futs):
            results[futs[fut]] = fut.result()
    for lo in sorted(results):
        captions.extend(results[lo])
    caps_text = "\n".join(
        json.dumps(c, ensure_ascii=False) for c in captions if c)
    print(f"  打标完成 {len(captions)} 行，进入日记生成…", flush=True)
    weekday = "周" + "一二三四五六日"[date_label.weekday()]
    date_str = date_label.isoformat()
    diary = cli.call(model, [{"type": "text", "text": P_STAGE2.format(
        date=date_str, weekday=weekday, n=len(photos), captions=caps_text)}],
        max_tokens=16384, thinking=True)
    wall = time.time() - t0
    return captions, caps_text, diary, wall, date_str


# ---------------------------------------------------------------- outputs
def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_html(out_dir, run_name, photos, per_model, primary):
    caps = {c.get("i"): c for c in per_model[primary]["captions"] if c.get("i")}
    cells = []
    for i, ph in enumerate(photos, 1):
        c = caps.get(i, {})
        t = ph["ts"].strftime("%H:%M")
        cap = f"{c.get('where','')} · {c.get('what','')}".strip(" ·") or (c.get("raw", "")[:60])
        cells.append(
            f'<figure><img src="{ph["cached_rel"]}">'
            f'<figcaption><b>#{i} {t}</b> {html_escape(cap)}</figcaption></figure>')
    cols = ""
    for m, d in per_model.items():
        u = d["usage"]
        cols += (f'<section><h2>{m}</h2>'
                 f'<p class="meta">¥{d["cost"]:.4f} · {u["calls"]} calls · '
                 f'in {u["input"]}/out {u["output"]} tok · {d["wall"]:.0f}s</p>'
                 f'<pre>{html_escape(d["diary"])}</pre></section>')
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{run_name} 日记对比</title>
<style>body{{font-family:-apple-system,sans-serif;margin:24px;max-width:1200px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}
figure{{margin:0}}img{{width:100%;border-radius:8px}}figcaption{{font-size:12px;color:#555;margin-top:4px}}
section{{border-top:2px solid #ddd;padding-top:12px;margin-top:24px}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:15px;line-height:1.7}}
.meta{{color:#888;font-size:13px}}h2{{margin-bottom:4px}}</style></head><body>
<h1>{run_name} · 照片 → 日记 原型对比</h1>
<p>{len(photos)} 张素材 · 打标摘自 <b>{primary}</b></p>
<div class="grid">{''.join(cells)}</div>
{cols}</body></html>"""
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser(description="闸门1原型：一天照片 → 时间线日记（throwaway）")
    ap.add_argument("photo_dir")
    ap.add_argument("--date", help="只要该日拍摄的照片 YYYY-MM-DD（mdls EXIF）")
    ap.add_argument("--models", default="glm-5.3-flash,glm-4.6v-flash",
                    help="逗号分隔，逐档跑。可用：glm-5.3-flash(0.8元/M)，"
                         "glm-4.6v-flash(免费)，glm-4.6v-flashx(0.15元/M，需账户充值，"
                         "本 key 当前报 1113 余额不足)")
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--max-width", type=int, default=1280, help="长边像素上限（控 token）")
    ap.add_argument("--provider", default="zai-pro")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    key, base_url = load_provider(args.provider)
    src_dir = os.path.abspath(args.photo_dir)
    if not os.path.isdir(src_dir):
        die(f"目录不存在: {src_dir}")
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    # 1. 收集照片
    files = []
    for root, dirs, fnames in os.walk(src_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in fnames:
            if os.path.splitext(fn)[1].lower() in IMG_EXTS:
                files.append(os.path.join(root, fn))
    if not files:
        die(f"{src_dir} 下没有图片")
    photos = []
    for p in files:
        ts = photo_timestamp(p)
        if args.date and ts.strftime("%Y-%m-%d") != args.date:
            continue
        photos.append({"path": p, "ts": ts})
    if not photos:
        die("按 --date 过滤后没有照片（检查照片 EXIP 时间或去掉 --date）")
    photos.sort(key=lambda x: x["ts"])
    if args.date:
        date_label = dt.date.fromisoformat(args.date)
    else:
        span = photos[-1]["ts"] - photos[0]["ts"]
        date_label = photos[0]["ts"] + span / 2
        date_label = date_label.date()
    run_name = f"{date_label}-{dt.datetime.now().strftime('%H%M')}"
    out_dir = os.path.join(out_root, run_name)
    cache_dir = os.path.join(out_dir, "photos")
    os.makedirs(cache_dir, exist_ok=True)
    print(f"[1/3] 收集到 {len(photos)} 张（{photos[0]['ts']} → {photos[-1]['ts']}），"
          f"产物目录 {out_dir}", flush=True)

    # 2. 预处理（转码+缩图）
    cache_rel_root = os.path.relpath(cache_dir, out_dir)
    for i, ph in enumerate(photos, 1):
        cached, mt, b64 = prepare_image(ph["path"], cache_dir, args.max_width)
        ph.update(cached=cached, cached_rel=os.path.join(cache_rel_root, os.path.basename(cached)),
                  media_type=mt, b64=b64)
    print(f"[2/3] 预处理完成（长边 ≤{args.max_width}px）", flush=True)

    # 3. 逐模型跑两阶段
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    per_model = {}
    primary = models[0]
    for m in models:
        cli = Client(key, base_url)
        try:
            captions, caps_text, diary, wall, date_str = run_model(
                cli, m, photos, date_label, args.batch_size)
        except Exception as e:
            print(f"  [WARN] {m} 失败: {str(e)[:300]}（跳过）", flush=True)
            continue
        pin, pout = PRICES.get(m, (None, None))
        cost = (pin * cli.usage["input"] + pout * cli.usage["output"]) / 1e6 \
            if pin is not None else None
        per_model[m] = {"captions": captions, "diary": diary, "usage": cli.usage,
                        "cost": cost, "wall": wall}
        with open(os.path.join(out_dir, f"captions-{m}.md"), "w") as f:
            f.write(caps_text + "\n")
        with open(os.path.join(out_dir, f"diary-{m}.md"), "w") as f:
            f.write(diary + "\n")
        c = f"¥{cost:.4f}" if cost is not None else "¥?"
        print(f"  ✔ {m}: {c}，in {cli.usage['input']}/out {cli.usage['output']} tok"
              f"，{cli.usage['calls']} 次调用，{wall:.0f}s", flush=True)
    if not per_model:
        die("所有模型都失败了")

    # 4. 报告 + HTML
    rows = ["| 模型 | 调用 | 输入 tok | 输出 tok | 成本(元) | 耗时 |",
            "|---|---|---|---|---|---|"]
    for m, d in per_model.items():
        u = d["usage"]
        rows.append(f"| {m} | {u['calls']} | {u['input']} | {u['output']} | "
                    f"{d['cost']:.4f} | {d['wall']:.0f}s |")
    total = sum(d["cost"] or 0 for d in per_model.values())
    report = (f"# 闸门1原型运行报告 · {date_label}\n\n- 素材: {len(photos)} 张"
              f"（{photos[0]['ts'].strftime('%H:%M')} → {photos[-1]['ts'].strftime('%H:%M')}，"
              f"长边 ≤{args.max_width}px）\n- 批大小: {args.batch_size}\n\n"
              + "\n".join(rows) + f"\n\n**刊例价折算合计: ¥{total:.4f}**\n\n"
              "计费口径: 本 key 为订阅用户（订阅额度覆盖 glm-5.3-flash；"
              "glm-4.6v-flash 为免费模型），上表 ¥ 为刊例价折算，实际不产生按量账单。\n"
              "价格来源: 智谱官方 pricing.md（2026-10-07）。\n"
              "日记文件: " + ", ".join(f"`diary-{m}.md`" for m in per_model) + "\n")
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(report)
    write_html(out_dir, str(date_label), photos, per_model, primary)
    print(f"\n[3/3] 完成 ✅\n  打开对比页: open {os.path.join(out_dir, 'index.html')}\n"
          f"  成本报告: {os.path.join(out_dir, 'report.md')}", flush=True)


if __name__ == "__main__":
    main()
