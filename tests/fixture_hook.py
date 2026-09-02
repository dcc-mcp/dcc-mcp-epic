from __future__ import annotations

import json
import sys

request = json.load(sys.stdin)
print(
    json.dumps(
        {
            "ok": True,
            "operation": request.get("operation"),
            "payload": request.get("payload"),
        }
    )
)
