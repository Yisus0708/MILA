import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


LEARNING_PATH = get_base_dir() / "memory" / "learning_data.json"
RECAP_PATH    = get_base_dir() / "memory" / "session_recap.json"
_lock = Lock()
MAX_CORRECTIONS = 500
MAX_KNOWLEDGE = 300
MAX_FAILURES = 100
MAX_RECAP_LINES = 20


def _empty() -> dict:
    return {
        "corrections": [], "knowledge": [], "user_preferences": {},
        "tool_failures": [],
        "interaction_stats": {"total_questions": 0, "total_corrections": 0, "subjects_asked": {}, "last_interaction": None},
    }


def load():
    if not LEARNING_PATH.exists():
        return _empty()
    with _lock:
        try:
            d = json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
            base = _empty()
            for k in base:
                if k not in d:
                    d[k] = base[k]
            return d
        except Exception:
            return _empty()


def save(data: dict):
    LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        LEARNING_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def record_correction(topic: str, correction: str, context: str = ""):
    data = load()
    data["corrections"].append({"topic": topic.lower(), "correction": correction, "context": context, "timestamp": datetime.now().isoformat()})
    if len(data["corrections"]) > MAX_CORRECTIONS:
        data["corrections"] = data["corrections"][-MAX_CORRECTIONS:]
    data["interaction_stats"]["total_corrections"] += 1
    save(data)


def add_knowledge(topic: str, fact: str):
    data = load()
    for k in data["knowledge"]:
        if SequenceMatcher(None, k["topic"].lower(), topic.lower()).ratio() > 0.8:
            k["fact"] = fact
            k["updated"] = datetime.now().isoformat()
            save(data)
            return
    data["knowledge"].append({"topic": topic.lower(), "fact": fact, "created": datetime.now().isoformat(), "updated": datetime.now().isoformat()})
    if len(data["knowledge"]) > MAX_KNOWLEDGE:
        data["knowledge"] = data["knowledge"][-MAX_KNOWLEDGE:]
    save(data)


def search_corrections(query: str, top_k: int = 5) -> list:
    data = load()
    qw = set(re.findall(r'\w+', query.lower()))
    scored = []
    for c in reversed(data["corrections"]):
        tw = set(re.findall(r'\w+', c["topic"]))
        cw = set(re.findall(r'\w+', c["correction"].lower()))
        overlap = len(qw & (tw | cw))
        sim = SequenceMatcher(None, query.lower(), c["topic"]).ratio()
        score = overlap * 0.3 + sim * 0.4 + (0.1 if query.lower() in c["topic"] else 0)
        if score > 0.1:
            scored.append({**c, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def search_knowledge(query: str, top_k: int = 5) -> list:
    data = load()
    qw = set(re.findall(r'\w+', query.lower()))
    scored = []
    for k in reversed(data["knowledge"]):
        kw = set(re.findall(r'\w+', k["topic"]))
        fw = set(re.findall(r'\w+', k["fact"].lower()))
        overlap = len(qw & (kw | fw))
        score = overlap * 0.3 + SequenceMatcher(None, query.lower(), k["topic"]).ratio() * 0.4
        if score > 0.1:
            scored.append({**k, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def record_tool_failure(tool: str, args: dict, error: str):
    data = load()
    data.setdefault("tool_failures", [])
    data["tool_failures"].append({
        "tool": tool,
        "args": {k: str(v) for k, v in (args or {}).items()},
        "error": str(error)[:300],
        "timestamp": datetime.now().isoformat(),
    })
    if len(data["tool_failures"]) > MAX_FAILURES:
        data["tool_failures"] = data["tool_failures"][-MAX_FAILURES:]
    save(data)


def get_session_context(max_knowledge: int = 8, max_corrections: int = 5, max_failures: int = 5) -> str:
    data = load()
    corrections = data["corrections"][-max_corrections:]
    knowledge = data["knowledge"][-max_knowledge:]
    failures = data.get("tool_failures", [])[-max_failures:]
    lines = []
    if corrections:
        lines.append("[PAST CORRECTIONS — do not repeat these mistakes]")
        for c in reversed(corrections):
            lines.append(f"- On '{c['topic']}': {c['correction']}")
    if knowledge:
        lines.append("[KNOWLEDGE LEARNED IN PRIOR CONVERSATIONS]")
        for k in reversed(knowledge):
            lines.append(f"- {k['topic'].title()}: {k['fact']}")
    if failures:
        lines.append("[RECENT TOOL FAILURES — these tool/argument combos recently errored, don't blindly retry them the same way]")
        for f in reversed(failures):
            lines.append(f"- {f['tool']}({f['args']}): {f['error']}")
    return "\n".join(lines)


def save_session_recap(lines: list):
    if not lines:
        return
    RECAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        RECAP_PATH.write_text(json.dumps({
            "lines": lines[-MAX_RECAP_LINES:],
            "timestamp": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")


def get_session_recap() -> str:
    if not RECAP_PATH.exists():
        return ""
    try:
        data = json.loads(RECAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    lines = data.get("lines") or []
    if not lines:
        return ""
    ts = data.get("timestamp", "")
    header = f"[LAST SESSION RECAP — {ts}]" if ts else "[LAST SESSION RECAP]"
    return header + "\n" + "\n".join(lines)


def get_learning_context(query: str = "general") -> str:
    corrections = search_corrections(query, 3)
    knowledge = search_knowledge(query, 3)
    lines = []
    if corrections:
        lines.append("[LEARNED FROM CORRECTIONS]")
        for c in corrections:
            lines.append(f"- You corrected me about '{c['topic']}': {c['correction']}")
    if knowledge:
        lines.append("[KNOWLEDGE ACQUIRED]")
        for k in knowledge:
            lines.append(f"- {k['topic'].title()}: {k['fact']}")
    return "\n".join(lines)


def record_interaction(subject: str = "general"):
    data = load()
    s = data["interaction_stats"]
    s["total_questions"] += 1
    s["subjects_asked"][subject] = s["subjects_asked"].get(subject, 0) + 1
    s["last_interaction"] = datetime.now().isoformat()
    save(data)


def format_summary() -> str:
    data = load()
    s = data["interaction_stats"]
    lines = [f"Questions: {s['total_questions']}", f"Corrections: {s['total_corrections']}", f"Knowledge: {len(data['knowledge'])}", f"Corrections stored: {len(data['corrections'])}"]
    if s["subjects_asked"]:
        top = sorted(s["subjects_asked"].items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("Top subjects: " + ", ".join(f"{sub}({c})" for sub, c in top))
    return "\n".join(lines)
