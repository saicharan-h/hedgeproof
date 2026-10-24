"""Runs INSIDE the sandbox container. Trusted code baked into the image.

Protocol (JSON lines over stdin/stdout):
  1. first line: {"source": <estimator source>, "config": {...}}
     reply:      {"ok": true, "loaded": true} or {"ok": false, "error": ...}
  2. then one window per line: {"id": ..., "window": [rows]}
     reply per window: {"ok": true, "id": ..., "estimate": x} or {"ok": false, "id": ..., "error": ...}
The next window arrives only after the previous reply, so later data is never
inside the container when an earlier estimate is made.

Defense in depth only: the real isolation is the container (no network,
read-only root, non-root user, no capabilities, CPU/memory/process limits).
"""

import builtins
import io
import json
import math
import sys

ALLOWED_MODULES = {"math", "statistics", "numpy"}
SAFE_NAMES = [
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
    "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set", "sorted", "str", "sum",
    "tuple", "zip", "Exception", "ValueError", "ZeroDivisionError", "TypeError", "KeyError", "IndexError",
    "ArithmeticError", "FloatingPointError", "RuntimeError", "StopIteration", "True", "False", "None",
]


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0 or name.split(".")[0] not in ALLOWED_MODULES:
        raise ImportError(f"import of {name!r} is not allowed in the sandbox")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _safe_builtins():
    safe = {n: getattr(builtins, n) for n in SAFE_NAMES if hasattr(builtins, n)}
    safe["__import__"] = _restricted_import
    safe["__build_class__"] = builtins.__build_class__
    return safe


def main():
    channel = sys.stdout
    sys.stdout = io.StringIO()  # anything the estimator prints is discarded

    def reply(obj):
        text = json.dumps(obj, allow_nan=False)
        channel.write(text[:10000] + "\n")
        channel.flush()
        sys.stdout = io.StringIO()

    first = sys.stdin.readline()
    try:
        msg = json.loads(first)
        ns = {"__name__": "estimator", "__builtins__": _safe_builtins()}
        exec(compile(msg["source"], "<estimator>", "exec"), ns)
        fn = ns["estimate"]
        config = msg.get("config", {})
    except Exception as exc:  # noqa: BLE001 - report any load failure
        reply({"ok": False, "error": f"load failed: {type(exc).__name__}: {exc}"[:300]})
        return
    reply({"ok": True, "loaded": True})
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            reply({"ok": False, "id": None, "error": "bad request line"})
            continue
        try:
            value = float(fn(req["window"], dict(config)))
            if not math.isfinite(value):
                raise ValueError("estimate is not finite")
            reply({"ok": True, "id": req["id"], "estimate": value})
        except Exception as exc:  # noqa: BLE001 - every estimator error is reported, never raised
            reply({"ok": False, "id": req["id"], "error": f"{type(exc).__name__}: {exc}"[:300]})


if __name__ == "__main__":
    main()
