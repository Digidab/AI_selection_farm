#!/usr/bin/env python3
"""
Ollama Docker Build Script - Selection Farm
Opens terminal and starts only the ollama container.

Ollama is NOT part of docker-compose.yml - it runs standalone and is
reached by the other services via host.docker.internal:11434 (see
docker/.env.example). This mirrors the Postgres build script's approach.

Model data directory is a BIND MOUNT (not a named volume):
    selection_farm/db/ollama_volume/
This directory is created here if missing, before the container starts,
so pulled models live on the host filesystem and survive container
removal, image removal, and `docker volume prune`.
"""

import subprocess
import shutil
from pathlib import Path

CONTAINER_NAME = "selection_farm_ollama"
IMAGE_NAME = "ollama/ollama:latest"
HOST_PORT = "11434"

script_dir = Path(__file__).resolve().parent
docker_dir = script_dir.parent.parent  # selection_farm/docker
selection_farm_dir = docker_dir.parent  # selection_farm
ollama_data_dir = selection_farm_dir / "db" / "ollama_volume"


def main():
    ollama_data_dir.mkdir(parents=True, exist_ok=True)

    bash_script = f"""#!/bin/bash
cd "{docker_dir}"

echo "==================================="
echo "   SELECTION FARM"
echo "   Ollama Docker Build Script"
echo ""
echo "   Container: {CONTAINER_NAME}"
echo "   Image:     {IMAGE_NAME}"
echo "   Port:      {HOST_PORT} (CPU-only mode)"
echo "   Data dir (bind mount, persists across rebuilds):"
echo "     {ollama_data_dir}"
echo "   Working dir: {docker_dir}"
echo "==================================="
echo ""

echo ">>> Starting ollama (standalone, not part of docker-compose.yml)..."
echo "\\$ docker run -d --name {CONTAINER_NAME} -p {HOST_PORT}:11434 \\\\"
echo "    -v {ollama_data_dir}:/root/.ollama --restart unless-stopped {IMAGE_NAME}"
docker run -d --name {CONTAINER_NAME} -p {HOST_PORT}:11434 \\
    -v "{ollama_data_dir}:/root/.ollama" --restart unless-stopped {IMAGE_NAME}
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "WARNING: Command exited with code $exit_code (container may already exist - trying start instead)"
    docker start {CONTAINER_NAME} 2>/dev/null || true
else
    echo "OK"
fi

echo ""
echo "==================================="
echo "    Build Completed!"
echo "==================================="
echo ""
echo "Container status:"
docker ps --filter "name={CONTAINER_NAME}" \\
          --format "table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}"
echo ""
echo "To pull a model:"
echo "  docker exec {CONTAINER_NAME} ollama pull qwen3:0.6b"
echo ""
echo "To view logs:"
echo "  docker logs -f {CONTAINER_NAME}"
echo ""
echo "Terminal will close in 10 seconds..."
sleep 10
"""

    temp_script = "/tmp/selection_farm_ollama_build.sh"
    with open(temp_script, "w") as f:
        f.write(bash_script)
    Path(temp_script).chmod(0o755)

    terminals = [
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("xterm", ["-e"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["-e"]),
        ("mate-terminal", ["-e"]),
        ("lxterminal", ["-e"]),
        ("terminator", ["-e"]),
    ]

    terminal_found = None
    terminal_args = None

    for term_name, args in terminals:
        if shutil.which(term_name):
            terminal_found = term_name
            terminal_args = args
            print(f"Found terminal: {term_name}")
            break

    if not terminal_found:
        print("Error: No terminal emulator found!")
        return

    terminal_command = [terminal_found] + terminal_args + ["bash", temp_script]

    try:
        print(f"Working directory: {docker_dir}")
        print(f"Data directory (bind mount): {ollama_data_dir}")
        print("Opening terminal and starting Ollama container...")
        subprocess.Popen(terminal_command)
        print("Terminal opened. Build started.")
    except Exception as e:
        print(f"Error starting terminal: {e}")


if __name__ == "__main__":
    main()
