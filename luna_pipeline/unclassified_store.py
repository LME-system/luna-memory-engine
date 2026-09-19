"""未覆盖案例存储 — P2 自我强化学习的基础设施

记录 symbolic 未命中的案例，供每日聚合 + 人工 review → 新公理。
"""
import json, os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_DIR = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = DATA_DIR / "unclassified_log.jsonl"


class UncoveredStore:
    def __init__(self, path: Path = LOG_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, article_id: str, title: str, text: str, reason: str = "no_axiom_hit",
            geometric_hint: Optional[Dict[str, Any]] = None, timestamp: Optional[str] = None):
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        entry = {
            "id": article_id,
            "title": title,
            "text_preview": text[:300],
            "reason": reason,
            "geometric_hint": geometric_hint or {},
            "timestamp": ts,
            "reviewed": False,
            "new_axiom_id": None,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def recent(self, n: int = 20, unreviewed_only: bool = False) -> List[Dict[str, Any]]:
        lines = self.load_all()
        if unreviewed_only:
            lines = [l for l in lines if not l.get("reviewed")]
        return lines[-n:]

    def daily_digest(self, day_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """返回指定日期（默认今天）未 review 的未覆盖案例。"""
        target = day_iso or date.today().isoformat()
        lines = self.load_all()
        return [l for l in lines if l["timestamp"].startswith(target) and not l.get("reviewed")]

    def mark_reviewed(self, entry_id: str, new_axiom_id: Optional[str] = None) -> bool:
        lines = self.load_all()
        modified = False
        for l in lines:
            if l.get("id") == entry_id:
                l["reviewed"] = True
                if new_axiom_id:
                    l["new_axiom_id"] = new_axiom_id
                modified = True
                break
        if modified:
            with open(self.path, "w", encoding="utf-8") as f:
                for l in lines:
                    f.write(json.dumps(l, ensure_ascii=False) + "\n")
        return modified

    def stats(self) -> Dict[str, Any]:
        lines = self.load_all()
        unreviewed = [l for l in lines if not l.get("reviewed")]
        today = date.today().isoformat()
        today_cnt = len([l for l in unreviewed if l["timestamp"].startswith(today)])
        return {
            "total": len(lines),
            "unreviewed": len(unreviewed),
            "today_unreviewed": today_cnt,
        }

    def top_candidates(self, n: int = 3) -> List[Dict[str, Any]]:
        """按 geometric_hint 特异度排序，返回最值得 review 的 top-n。"""
        lines = self.recent(n=100, unreviewed_only=True)
        # 有 pattern_alert 的优先，然后按时间倒序
        def score(l):
            hint = l.get("geometric_hint", {})
            s = 0
            if hint.get("max_poincare_norm", 0) > 0.7:
                s += 10
            if "dimension_spike" in " ".join(hint.get("reasons", [])):
                s += 5
            return s
        lines.sort(key=lambda x: (score(x), x["timestamp"]), reverse=True)
        return lines[:n]
