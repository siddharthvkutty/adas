#!/usr/bin/env bash
# Start all 4 ADAS nodes in a 4-pane tmux dashboard
SESSION="adas"
tmux kill-session -t $SESSION 2>/dev/null || true

tmux new-session -d -s $SESSION -n "dashboard" "python3 ./architect.py"
tmux split-window -h -t $SESSION:0 "python3 ./forge.py"
tmux split-window -v -t $SESSION:0.0 "python3 ./nexus.py"
tmux split-window -v -t $SESSION:0.1 "python3 ./sentry.py"

echo "ADAS 4-node dashboard launched in tmux session '$SESSION'."
echo "Attach with: tmux attach -t $SESSION"
