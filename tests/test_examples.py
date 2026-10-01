import importlib.util
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dropped_webhook_example_after_reconcile_target_has_latest_state(capsys):
    target = _load("dropped_webhook").main()

    assert target.get("order-42") == {"status": "shipped"}
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "after webhook 1:   {'status': 'paid'}",
        "webhook 2 dropped: {'status': 'paid'}",
        "after reconcile:   {'status': 'shipped'}",
    ]
