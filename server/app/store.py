from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, name: str) -> Path:
        return self.state_dir / name

    def read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except FileNotFoundError:
                return default
            except (json.JSONDecodeError, OSError):
                return default

    def write(self, name: str, value: Any) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
            finally:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass

    def append_activity(self, event: dict[str, Any], max_items: int = 100) -> None:
        with self._lock:
            items = self.read("activity.json", [])
            if not isinstance(items, list):
                items = []
            item = {"at": int(time.time()), **event}
            items.append(item)
            self.write("activity.json", items[-max_items:])
