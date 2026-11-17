#!/data/data/com.termux/files/usr/bin/bash
set -eu

SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEST_DIR="$HOME/.shortcuts"
mkdir -p "$DEST_DIR"

install_if_missing() {
    source_file="$1"
    shortcut_name="$2"
    destination="$DEST_DIR/$shortcut_name"

    if [ -e "$destination" ]; then
        printf 'Preserved existing shortcut: %s\n' "$destination"
        printf 'Move/rename it yourself if you want to replace it with the bundled version.\n'
        return 0
    fi

    install -m 700 "$source_file" "$destination"
    printf 'Installed: %s\n' "$destination"
}

install_if_missing "$SOURCE_DIR/si-ai-start" "SI-AI Start"
install_if_missing "$SOURCE_DIR/si-ai-stop" "SI-AI Stop"
install_if_missing "$SOURCE_DIR/si-ai-dry-run" "SI-AI Dry Run"
install_if_missing "$SOURCE_DIR/si-ai-check" "SI-AI Check"

printf 'SI-AI shortcut installation check complete in %s\n' "$DEST_DIR"
printf 'Existing shortcuts were preserved; open/refresh Termux:Widget if needed.\n'
