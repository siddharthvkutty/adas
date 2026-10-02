# Autonomous Distributed Agentic Scaffolding (ADAS)

A zero-dependency distributed multi-agent coding framework powered by local LLMs via Ollama.

## Architecture

| Node | Port | Role | Specialized Model |
|------|------|------|-------------------|
| **Nexus** | 8001 | User CLI & Pipeline Coordinator | None (Interface) |
| **Architect** | 8002 | System Blueprint & Spec Generator | `qwen2.5:7b` |
| **Forge** | 8003 | Code Synthesizer & Workspace Builder | `qwen2.5-coder:14b` |
| **Sentry** | 8004 | QA, Syntax Checking & Rejection Loop | `deepseek-r1:8b` |

## Quick Start

### 1. Download Specialized Models
```bash
./download_models.sh
```
*(If models are not yet pulled, ADAS automatically falls back to any installed Ollama model).*

### 2. Launch the 4 Processes

Open 4 terminals in this directory and launch each node:

- **Terminal 1:**
  ```bash
  ./nexus.py
  ```
- **Terminal 2:**
  ```bash
  ./architect.py
  ```
- **Terminal 3:**
  ```bash
  ./forge.py
  ```
- **Terminal 4:**
  ```bash
  ./sentry.py
  ```

*(Alternatively, launch all 4 in a split tmux dashboard with `./start_tmux.sh` and attach via `tmux attach -t adas`)*.

### 3. Usage

In **Terminal 1 (Nexus)**, enter what project you want to generate:
```text
[Nexus] Enter project specification or goal: A CLI tool to convert Markdown tables to SQLite tables with tests
```

### 4. QA Loop
If **Sentry** finds syntax errors, failing tests, or architectural omissions, it rejects the build and sends feedback back to **Forge** up to 3 times before final sign-off.
Generated projects are saved under `./workspace/<task_id>/`.
