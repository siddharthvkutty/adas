#!/usr/bin/env python3
"""Run self-check validation of ADAS core utilities and IPC pipeline."""

import json
import shutil
import tempfile
import threading
from pathlib import Path

import adas


def test_extract_json():
    # 1. Standard markdown json block
    raw1 = '```json\n{"main.py": "print(1)"}\n```'
    assert adas.extract_json(raw1) == {"main.py": "print(1)"}

    # 2. Raw JSON string
    raw2 = '{"a.py": "x = 1", "b.py": "y = 2"}'
    assert adas.extract_json(raw2) == {"a.py": "x = 1", "b.py": "y = 2"}

    # 3. Conversational preamble around JSON
    raw3 = 'Here are your files:\n```\n{"app.py": "import os"}\n```\nEnjoy!'
    assert adas.extract_json(raw3) == {"app.py": "import os"}
    print("[PASS] test_extract_json")


def test_resolve_model():
    # Fallback to whatever is installed or preferred
    res = adas.resolve_model("nonexistent_future_model:99b")
    assert isinstance(res, str) and len(res) > 0
    print(f"[PASS] test_resolve_model (Resolved to '{res}')")


def test_http_node_ipc():
    test_port = 8899
    received = []

    def mock_handler(data):
        received.append(data)
        return {"result": "ok", "ack": data.get("msg")}

    server = adas.NodeServer(test_port, mock_handler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    resp = adas.post_json(test_port, {"msg": "hello adas"})
    assert resp["result"] == "ok"
    assert resp["ack"] == "hello adas"
    assert len(received) == 1
    server.shutdown()
    print("[PASS] test_http_node_ipc")


def test_sentry_syntax_verification():
    temp_dir = Path(tempfile.mkdtemp())
    try:
        good_file = temp_dir / "good.py"
        good_file.write_text("def hello(): return 'world'\n", encoding="utf-8")

        bad_file = temp_dir / "bad.py"
        bad_file.write_text("def bad_syntax(: return 0\n", encoding="utf-8")

        # good file compile
        import py_compile

        py_compile.compile(str(good_file), doraise=True)

        # bad file compile must raise
        failed = False
        try:
            py_compile.compile(str(bad_file), doraise=True)
        except py_compile.PyCompileError:
            failed = True
        assert failed, "bad.py should have failed syntax compilation"
        print("[PASS] test_sentry_syntax_verification")
    finally:
        shutil.rmtree(temp_dir)


def main():
    print("Running ADAS self-check suite...")
    test_extract_json()
    test_resolve_model()
    test_http_node_ipc()
    test_sentry_syntax_verification()
    print("All ADAS checks passed!")


if __name__ == "__main__":
    main()
