#!/usr/bin/env python3
"""
Postgres Docker Down Script - Selection Farm
Opens terminal and stops/removes ONLY the postgres container + its image.
IMPORTANT: KEEPS PORTAINER AND ALL OTHER CONTAINERS UNTOUCHED!

The db/postgres_volume/ directory is a BIND MOUNT, not a named docker
volume. This script never deletes it, and no docker command here
(compose down, rm, rmi) is able to touch it either way - only an explicit
`rm -rf` on that path would destroy the data.
"""

import subprocess
import shutil
from pathlib import Path

CONTAINER_NAME = "selection_farm_postgres"
IMAGE_NAME = "ankane/pgvector:latest"
ALLOWED_CONTAINERS = [CONTAINER_NAME]

script_dir = Path(__file__).resolve().parent
docker_dir = script_dir.parent.parent  # selection_farm/docker
env_file = docker_dir / ".env"
pgdata_dir = docker_dir.parent / "db" / "postgres_volume"  # selection_farm/db/postgres_volume


def main():
    bash_script = f"""#!/bin/bash
cd "{docker_dir}"
echo "==================================="
echo "   SELECTION FARM"
echo "   Postgres Docker Down Script"
echo ""
echo "   Stopping ONLY: {CONTAINER_NAME}"
echo ""
echo "   PORTAINER WILL BE PRESERVED!"
echo "   ALL OTHER CONTAINERS PRESERVED!"
echo "   PGDATA BIND MOUNT WILL BE PRESERVED!"
echo "     {pgdata_dir}"
echo ""
echo "   Working dir: {docker_dir}"
echo "==================================="
echo ""

echo ">>> Step 1/4: Stopping via docker compose..."
echo "\\$ docker compose --env-file .env stop postgres"
docker compose --env-file .env stop postgres
echo "OK"
echo ""

echo ">>> Step 2/4: Removing container via docker compose..."
echo "\\$ docker compose --env-file .env rm -f postgres"
docker compose --env-file .env rm -f postgres
echo "OK"
echo ""

echo ">>> Step 3/4: Force removing container if still exists..."
docker rm -f {" ".join(ALLOWED_CONTAINERS)} 2>/dev/null || true
echo "OK"
echo ""

echo ">>> Step 4/4: Removing postgres image only ({IMAGE_NAME})..."
docker rmi -f {IMAGE_NAME} 2>/dev/null || true
echo "OK"
echo ""

echo "==================================="
echo "    Postgres Container Stopped!"
echo "    Image removed."
echo "    Portainer and all other containers preserved."
echo "    pgdata/ bind mount preserved - data is intact:"
echo "      {pgdata_dir}"
du -sh "{pgdata_dir}" 2>/dev/null || echo "      (directory not found - nothing was ever built)"
echo "==================================="
echo ""
echo "Remaining containers:"
docker ps --format "table {{{{.Names}}}}\\t{{{{.Status}}}}"
echo ""
echo "Terminal will close in 5 seconds..."
sleep 5
"""

    temp_script = "/tmp/selection_farm_postgres_down.sh"
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
        print(f"Data directory (preserved): {pgdata_dir}")
        print("Opening terminal and stopping Postgres container...")
        print("PORTAINER AND ALL OTHER CONTAINERS WILL BE PRESERVED!")
        subprocess.Popen(terminal_command)
        print("Terminal opened.")
    except Exception as e:
        print(f"Error starting terminal: {e}")


if __name__ == "__main__":
    main()
