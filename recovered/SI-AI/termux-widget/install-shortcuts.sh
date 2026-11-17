#!/data/data/com.termux/files/usr/bin/bash
set -eu

SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEST_DIR="$HOME/.shortcuts"
mkdir -p "$DEST_DIR"

for name in "SI-AI Start" "SI-AI Stop" "SI-AI Dry Run" "SI-AI Check"; do
    if [ -e "$DEST_DIR/$name" ]; then
        printf 'Refusing to overwrite existing shortcut: %s\n' "$DEST_DIR/$name" >&2
        printf 'Move or rename that file yourself, then rerun this installer.\n' >&2
        exit 1
    fi
done

install -m 700 "$SOURCE_DIR/si-ai-start" "$DEST_DIR/SI-AI Start"
install -m 700 "$SOURCE_DIR/si-ai-stop" "$DEST_DIR/SI-AI Stop"
install -m 700 "$SOURCE_DIR/si-ai-dry-run" "$DEST_DIR/SI-AI Dry Run"
install -m 700 "$SOURCE_DIR/si-ai-check" "$DEST_DIR/SI-AI Check"

printf 'Installed four SI-AI shortcuts in %s\n' "$DEST_DIR"
printf 'Open Termux:Widget and refresh its shortcut list if needed.\n'
