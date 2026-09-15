#!/usr/bin/env python3
"""
华尔街见闻 全球快讯抓取
API: api-one.wallstcn.com/apiv1/content/lives
用法: python3 wscn_capture.py [输出文件] [条数]
"""
import sys
import json
import re
import html
import urllib.request
from datetime import datetime

API = "https://api-one.wallstcn.com/apiv1/content/lives?channel={ch}&limit={n}"


def fetch(channel="global-channel", limit=40):
    url = API.format(ch=channel, n=limit)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def fmt_time(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%m-%d %H:%M")
    except Exception:
        return "?"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "news_capture_2026-09-12.md"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40

    data = fetch("global-channel", limit)
    items = data.get("data", {}).get("items", [])

    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# 华尔街见闻 {datetime.now():%Y-%m-%d} 捕获")
    lines.append(f"\n> 抓取时间: {now} CST | 来源: global-channel | 条目: {len(items)}\n")

    for it in items:
        t = fmt_time(it.get("display_time"))
        content = strip_html(it.get("content", ""))
        title = strip_html(it.get("title", ""))
        author = (it.get("author") or {}).get("display_name", "")
        chans = ",".join(it.get("channels", [])[:4])
        if not content and not title:
            continue
        lines.append(f"### [{t}] {title}" if title else f"### [{t}]")
        lines.append(f"{content}")
        if author:
            lines.append(f"*— {author} | {chans}*")
        lines.append("")

    text = "\n".join(lines)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ 已保存 {len(items)} 条 → {out}")
    # 预览
    print("\n--- 预览前 3 条 ---")
    print(text[:800])


if __name__ == "__main__":
    main()
