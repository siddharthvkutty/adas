#!/usr/bin/env python3
"""Autonomous Distributed Agentic Scaffolding (ADAS) - Core Engine.

A 4-node distributed agentic coding pipeline:
  1. Nexus     (Port 8001) - User interface & pipeline orchestrator
  2. Architect (Port 8002) - Decomposes user request into technical specification
  3. Forge     (Port 8003) - Synthesizes code files & applies Sentry revisions
  4. Sentry    (Port 8004) - Syntax checks, test execution & AI QA review loop
"""

import http.server
import json
import os
import py_compile
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Configuration & Defaults
PORTS = {
    "nexus": int(os.getenv("NEXUS_PORT", 8001)),
    "architect": int(os.getenv("ARCHITECT_PORT", 8002)),
    "forge": int(os.getenv("FORGE_PORT", 8003)),
    "sentry": int(os.getenv("SENTRY_PORT", 8004)),
}

MODELS = {
    "architect": os.getenv("ARCHITECT_MODEL", "qwen2.5:7b"),
    "forge": os.getenv("FORGE_MODEL", "qwen2.5-coder:14b"),
    "sentry": os.getenv("SENTRY_MODEL", "deepseek-r1:8b"),
}

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
WORKSPACE_BASE = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))


# --- Stdlib HTTP & Networking ---
# ponytail: stdlib http.server and urllib instead of fastapi/flask/requests dependencies
class NodeServer(http.server.HTTPServer):
    def __init__(self, port, handler_fn):
        self.handler_fn = handler_fn
        super().__init__(("127.0.0.1", port), _RequestHandler)


class _RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        resp = self.server.handler_fn(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp or {"status": "ok"}).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # suppress raw HTTP request logs to keep terminal focused


def post_json(port, data, timeout=900):
    # ponytail: direct HTTP POST, upgrade to persistent queue if network is lossy
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- Ollama Client & Model Resolver ---
def get_installed_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def resolve_model(preferred):
    available = get_installed_models()
    if not available:
        return preferred
    # exact or prefix match
    for m in available:
        if m == preferred or m.startswith(preferred + ":") or preferred.startswith(m.split(":")[0]):
            return m
    # ponytail: fallback to first installed model so nodes run even before all models are pulled
    return available[0]


def query_ollama(model, system_prompt, user_prompt):
    active_model = resolve_model(model)
    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        # ponytail: evict model immediately after use; pipeline is sequential so only one model needs RAM at a time
        "keep_alive": 0,
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["message"]["content"]


# --- Helpers ---
def extract_json(raw_text):
    # ponytail: regex/slice parser instead of heavy json-repair dependency
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1:
        text = text[s : e + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: simple key-value file extractor if model emitted markdown sections
        files = {}
        pattern = r"(?:###|####|\*\*)\s*([a-zA-Z0-9_\-\.\/]+)\s*\n```[a-zA-Z]*\n(.*?)```"
        matches = re.findall(pattern, raw_text, re.DOTALL)
        for path, code in matches:
            files[path.strip()] = code.strip()
        if files:
            return files
        raise ValueError(f"Could not parse valid JSON file map from model output:\n{raw_text[:300]}...")


# --- Node Implementations ---

def run_nexus():
    """Terminal 1: Nexus Node."""
    completed_events = {}
    results = {}

    def handle_nexus(data):
        action = data.get("action")
        task_id = data.get("task_id")
        if action == "complete":
            results[task_id] = data
            if task_id in completed_events:
                completed_events[task_id].set()
            return {"status": "received"}
        return {"status": "unknown_action"}

    server = NodeServer(PORTS["nexus"], handle_nexus)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("=" * 60)
    print(f"  [ADAS NEXUS] Active on http://127.0.0.1:{PORTS['nexus']}")
    print("=" * 60)

    # Health check downstream nodes
    for name, port in [("Architect", PORTS["architect"]), ("Forge", PORTS["forge"]), ("Sentry", PORTS["sentry"])]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5):
                pass
        except urllib.error.HTTPError:
            pass  # 200/501 means port is alive
        except Exception:
            print(f"  [Notice] {name} node not detected on port {port}. Start it in its terminal.")

    while True:
        try:
            prompt = input("\n[Nexus] Enter project specification or goal (or 'quit'): ").strip()
            if not prompt or prompt.lower() in ("quit", "exit"):
                break

            task_id = f"task_{int(time.time())}"
            completed_events[task_id] = threading.Event()

            print(f"[NEXUS] Dispatched {task_id} to Architect (port {PORTS['architect']})...")
            try:
                # Fire and let pipeline run asynchronously across the nodes
                threading.Thread(
                    target=lambda: post_json(PORTS["architect"], {"task_id": task_id, "prompt": prompt}),
                    daemon=True,
                ).start()
            except Exception as e:
                print(f"[NEXUS] Error connecting to Architect: {e}")
                continue

            print("[NEXUS] Pipeline running across nodes. Waiting for Sentry completion...")
            completed_events[task_id].wait()

            res = results.get(task_id, {})
            status = res.get("status", "UNKNOWN")
            out_dir = res.get("workspace_dir", "N/A")
            attempts = res.get("attempt", 1)
            report = res.get("report", "")

            print("\n" + "=" * 60)
            print(f"  [NEXUS] Task {task_id} Final Status: {status}")
            print(f"  [NEXUS] Attempts: {attempts}")
            print(f"  [NEXUS] Location: {out_dir}")
            print(f"  [NEXUS] QA Report:\n{report}")
            print("=" * 60)
        except KeyboardInterrupt:
            break


def run_architect():
    """Terminal 2: Architect Node."""
    model = MODELS["architect"]
    print("=" * 60)
    print(f"  [ADAS ARCHITECT] Active on port {PORTS['architect']} (Model: {model})")
    print("=" * 60)

    def handle_task(data):
        task_id = data["task_id"]
        user_prompt = data["prompt"]
        print(f"\n[ARCHITECT] Processing task {task_id}...")
        print(f"[ARCHITECT] Input: {user_prompt}")

        system_prompt = (
            "You are the Architect node in the Autonomous Distributed Agentic Scaffolding (ADAS) system. "
            "Your job is to transform high-level user project goals into an exhaustive, unambiguous technical blueprint. "
            "Specify:\n"
            "1. Architecture overview\n"
            "2. Required files with exact relative paths\n"
            "3. Detailed component responsibilities and interfaces\n"
            "4. Explicit acceptance criteria and unit tests needed for QA."
        )
        spec = query_ollama(model, system_prompt, f"User Request: {user_prompt}")
        print(f"[ARCHITECT] Specification complete ({len(spec.split())} words). Forwarding to Forge...")

        # Relay to Forge
        threading.Thread(
            target=lambda: post_json(
                PORTS["forge"],
                {"task_id": task_id, "prompt": user_prompt, "spec": spec, "attempt": 1},
            ),
            daemon=True,
        ).start()

        return {"status": "forwarded_to_forge"}

    server = NodeServer(PORTS["architect"], handle_task)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def run_forge():
    """Terminal 3: Forge Node."""
    model = MODELS["forge"]
    print("=" * 60)
    print(f"  [ADAS FORGE] Active on port {PORTS['forge']} (Model: {model})")
    print("=" * 60)

    def handle_build(data):
        task_id = data["task_id"]
        prompt = data["prompt"]
        spec = data["spec"]
        attempt = data.get("attempt", 1)
        feedback = data.get("feedback", "")
        prev_files = data.get("previous_files", {})

        workspace_dir = WORKSPACE_BASE / task_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[FORGE] Build order for {task_id} (Attempt {attempt})...")
        system_prompt = (
            "You are the Forge node in ADAS. Generate the complete source code for the project. "
            "You MUST output ONLY a valid JSON object mapping relative file paths to their full file contents. "
            "Example format:\n"
            "{\n"
            '  "main.py": "print(\'hello\')",\n'
            '  "README.md": "# Project Title"\n'
            "}\n"
            "No explanations, no text outside the JSON structure."
        )

        if attempt == 1:
            user_msg = f"Specification:\n{spec}\n\nGenerate all project files."
        else:
            print(f"[FORGE] Applying Sentry feedback (Attempt {attempt}):\n{feedback}")
            user_msg = (
                f"Specification:\n{spec}\n\n"
                f"Previous Files:\n{json.dumps(prev_files, indent=2)}\n\n"
                f"Sentry QA Failure Feedback & Errors:\n{feedback}\n\n"
                "Fix all issues and provide the updated complete file set in JSON format."
            )

        raw_output = query_ollama(model, system_prompt, user_msg)

        try:
            files = extract_json(raw_output)
        except Exception as e:
            print(f"[FORGE] Parse error: {e}. Writing raw output as fallback.")
            files = {"output.txt": raw_output}

        for rel_path, content in files.items():
            target_path = workspace_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            print(f"  [FORGE] Wrote {rel_path} ({len(content)} bytes)")

        print(f"[FORGE] Forwarding build to Sentry (port {PORTS['sentry']})...")
        threading.Thread(
            target=lambda: post_json(
                PORTS["sentry"],
                {
                    "task_id": task_id,
                    "prompt": prompt,
                    "spec": spec,
                    "attempt": attempt,
                    "workspace_dir": str(workspace_dir),
                    "files": files,
                },
            ),
            daemon=True,
        ).start()

        return {"status": "forwarded_to_sentry"}

    server = NodeServer(PORTS["forge"], handle_build)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def run_sentry():
    """Terminal 4: Sentry Node."""
    model = MODELS["sentry"]
    print("=" * 60)
    print(f"  [ADAS SENTRY] Active on port {PORTS['sentry']} (Model: {model})")
    print("=" * 60)

    def handle_inspection(data):
        task_id = data["task_id"]
        prompt = data["prompt"]
        spec = data["spec"]
        attempt = data.get("attempt", 1)
        workspace_dir = Path(data["workspace_dir"])
        files = data.get("files", {})

        print(f"\n[SENTRY] Inspecting build {task_id} (Attempt {attempt})...")

        # Phase 1: Deterministic Syntax & Test checks
        # ponytail: direct py_compile and unittest run, no heavy test harness needed
        deterministic_errors = []
        for rel_path in files.keys():
            full_path = workspace_dir / rel_path
            if full_path.suffix == ".py" and full_path.exists():
                try:
                    py_compile.compile(str(full_path), doraise=True)
                    print(f"  [SENTRY] Syntax check {rel_path}: PASS")
                except py_compile.PyCompileError as pe:
                    err = f"Syntax error in {rel_path}: {pe.msg}"
                    deterministic_errors.append(err)
                    print(f"  [SENTRY] Syntax check {rel_path}: FAIL ({pe.msg})")

        # Execute tests if any test_*.py exists
        for test_file in workspace_dir.glob("**/test_*.py"):
            print(f"  [SENTRY] Running test suite {test_file.name}...")
            res = subprocess.run(
                [sys.executable, "-m", "unittest", test_file.name],
                cwd=test_file.parent,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode != 0:
                err = f"Test failure in {test_file.name}:\n{res.stderr or res.stdout}"
                deterministic_errors.append(err)
                print(f"  [SENTRY] Test {test_file.name}: FAIL")
            else:
                print(f"  [SENTRY] Test {test_file.name}: PASS")

        # Phase 2: LLM QA Review against Architect Spec
        system_prompt = (
            "You are the Sentry node in ADAS. You evaluate whether the generated code fulfills "
            "the Architect's specification and is free from defects or omissions.\n"
            "Output your decision in the following exact format:\n"
            "VERDICT: APPROVED or REJECTED\n"
            "SCORE: 1-10\n"
            "CRITIQUE: <Summary of evaluation>\n"
            "CORRECTIONS: <Bullet points of required fixes if rejected>"
        )
        user_msg = (
            f"Architect Specification:\n{spec}\n\n"
            f"Generated Files:\n{json.dumps(files, indent=2)}\n\n"
            f"Automated Check Errors:\n{chr(10).join(deterministic_errors) if deterministic_errors else 'None'}"
        )

        qa_review = query_ollama(model, system_prompt, user_msg)
        is_model_approved = "VERDICT: APPROVED" in qa_review.upper()
        passed = (len(deterministic_errors) == 0) and is_model_approved

        if not passed and attempt < MAX_RETRIES:
            feedback = ""
            if deterministic_errors:
                feedback += "Automated Verification Errors:\n" + "\n".join(deterministic_errors) + "\n\n"
            feedback += f"QA Review Feedback:\n{qa_review}"

            print(f"[SENTRY] Verdict: REJECTED (Attempt {attempt}/{MAX_RETRIES}). Routing back to Forge...")
            threading.Thread(
                target=lambda: post_json(
                    PORTS["forge"],
                    {
                        "task_id": task_id,
                        "prompt": prompt,
                        "spec": spec,
                        "attempt": attempt + 1,
                        "feedback": feedback,
                        "previous_files": files,
                    },
                ),
                daemon=True,
            ).start()
        else:
            final_status = "APPROVED" if passed else "FAILED_MAX_RETRIES"
            print(f"[SENTRY] Final Verdict: {final_status}! Notifying Nexus...")
            threading.Thread(
                target=lambda: post_json(
                    PORTS["nexus"],
                    {
                        "action": "complete",
                        "task_id": task_id,
                        "status": final_status,
                        "workspace_dir": str(workspace_dir),
                        "attempt": attempt,
                        "report": qa_review,
                    },
                ),
                daemon=True,
            ).start()

        return {"status": "inspected"}

    server = NodeServer(PORTS["sentry"], handle_inspection)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    roles = {
        "nexus": run_nexus,
        "architect": run_architect,
        "forge": run_forge,
        "sentry": run_sentry,
    }
    target = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if target not in roles:
        print(f"Usage: {sys.argv[0]} [nexus|architect|forge|sentry]")
        sys.exit(1)
    roles[target]()


if __name__ == "__main__":
    main()
