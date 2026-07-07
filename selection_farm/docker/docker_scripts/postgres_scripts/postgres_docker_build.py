#!/usr/bin/env python3
"""
Postgres Docker Build Script - Selection Farm
Opens terminal and builds/starts only the postgres container.

Data directory is a BIND MOUNT (not a named volume):
    docker/docker_scripts/postgres_scripts/pgdata/
This directory is created here if missing, before the container starts,
so Postgres data lives on the host filesystem and survives container
removal, image removal, and `docker volume prune`.
"""

import subprocess
import shutil
from pathlib import Path

CONTAINER_NAME = "selection_farm_postgres"

script_dir = Path(__file__).resolve().parent
docker_dir = script_dir.parent.parent  # selection_farm/docker
compose_file = docker_dir / "docker-compose.yml"
env_file = docker_dir / ".env"
pgdata_dir = script_dir / "pgdata"


def main():
    pgdata_dir.mkdir(parents=True, exist_ok=True)

    bash_script = f"""#!/bin/bash
export DOCKER_BUILDKIT=1
cd "{docker_dir}"

echo "==================================="
echo "   SELECTION FARM"
echo "   Postgres Docker Build Script"
echo ""
echo "   Container: {CONTAINER_NAME}"
echo "   Image:     ankane/pgvector:latest"
echo "   Data dir (bind mount, persists across rebuilds):"
echo "     {pgdata_dir}"
echo "   Working dir: {docker_dir}"
echo "==================================="
echo ""

echo ">>> Building and starting postgres only..."
echo "\\$ docker compose --env-file .env up -d --build postgres"
docker compose --env-file .env up -d --build postgres
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "WARNING: Command exited with code $exit_code"
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
echo "To view logs:"
echo "  docker logs -f {CONTAINER_NAME}"
echo ""
echo "Terminal will close in 10 seconds..."
sleep 10
"""

    temp_script = "/tmp/selection_farm_postgres_build.sh"
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
        print(f"Data directory (bind mount): {pgdata_dir}")
        print("Opening terminal and building Postgres container...")
        subprocess.Popen(terminal_command)
        print("Terminal opened. Build started.")
    except Exception as e:
        print(f"Error starting terminal: {e}")


if __name__ == "__main__":
    main()
