# Authored Sandbox project

The Sandbox contains twelve neutral text-category examples and explicit authored fixture answers. It needs no provider key and makes no network request. Its displayed 75% (6/8) example accuracy is an authored test scenario, not measured model performance.

Until the CLI demo command is connected, create a project with the Python service:

```python
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from deykit.application.demo import DemoService
from deykit.storage import FileProjectSource


class Clock:
    def utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def monotonic(self) -> float:
        return monotonic()


target = Path("Sandbox")  # The parent directory must exist; Sandbox must not.
info = DemoService(lambda path, create: FileProjectSource(path, create=create), Clock()).create(
    target, operation_id="create-sandbox"
)
print(info)
```

The created project has a saved `Content category` decision, an `Examples` dataset with `ex-001` through `ex-012`, nine authored labels, and a fixture profile/set. `ex-011` has invalid input and no binding. `ex-012` has an authored response error. The other ten cases have authored answers. Two valid answered cases are intentionally unlabelled, and two labelled answers intentionally disagree with their expectations.

Fixture bindings apply only to their case and exact compiled request. Editing input, question instructions, option names or order, selected fields, model identity, or compiler bytes requires a new authored fixture set. A missing binding reports `missing_fixture`; it never invents an answer. Fixture answers may omit probabilities or confidence. The Sandbox includes one authored probability distribution for `ex-003`; no confidence, usage, or duration is fabricated.

The project is portable. Copy its directory when no write is in progress; the readable source records and operation history carry the evidence. The `.deykit` index can be rebuilt from source. The demo creates only a new destination and refuses an existing path, including one containing user files.
