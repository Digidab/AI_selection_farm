import argparse
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

ID_MAPPING_DIR = Path(__file__).resolve().parent.parent / "configs" / "id_mapping"
DIRECTORY_FILE = ID_MAPPING_DIR / "id_directory.json"
COUNTERS_FILE = ID_MAPPING_DIR / "id_counters.json"


class UnknownEntityError(Exception):
    pass


def _load_directory() -> dict:
    with open(DIRECTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_full_prefix(key: str) -> str:
    """Resolve an entity name or an existing full_prefix (e.g. 'MO00') to a
    registered full_prefix. Never invents a new one — unregistered entities
    must be added to id_directory.json by a human first."""
    key = key.strip()
    directory = _load_directory()
    all_entries = [entry for entries in directory["registry"].values() for entry in entries]

    if len(key) == 4 and key[:2].isalpha() and key[2:].isdigit():
        candidate = key.upper()
        for entry in all_entries:
            if entry["full_prefix"] == candidate:
                return candidate
        raise UnknownEntityError(
            f"'{candidate}' is not a registered full_prefix in id_directory.json. "
            "Propose it to the user for confirmation before registering — prefixes are permanent."
        )

    key_lower = key.lower()
    for entry in all_entries:
        if key_lower in (entry["entity_name_en"].lower(), entry["entity_name_ru"].lower()):
            return entry["full_prefix"]

    raise UnknownEntityError(
        f"Entity '{key}' is not registered in id_directory.json. "
        "Propose a new prefix/index to the user for confirmation before adding it — "
        "prefixes are permanent once assigned."
    )


def _next_counter(value: int, width: int) -> tuple[str, int]:
    while value >= 10 ** width:
        width += 1
    return f"{value:0{width}d}", width


def generate_id(entity_key: str) -> str:
    full_prefix = resolve_full_prefix(entity_key)

    with open(COUNTERS_FILE, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            state = json.load(f)
            counters = state["counters"]
            entry = counters.setdefault(
                full_prefix,
                {"last_issued": None, "counter_width": 4, "last_full_id": None, "updated_at": None},
            )

            next_value = 0 if entry["last_issued"] is None else entry["last_issued"] + 1
            counter_str, new_width = _next_counter(next_value, entry["counter_width"])
            full_id = f"{full_prefix}{counter_str}"

            entry["last_issued"] = next_value
            entry["counter_width"] = new_width
            entry["last_full_id"] = full_id
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()

            f.seek(0)
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return full_id


def parse_id(full_id: str) -> dict:
    """Split an ID into its components. Counter width grows over time, so the
    counter must be sliced as everything after position 4 — never a fixed
    id[4:8] — or parsing breaks after the first overflow."""
    return {
        "prefix": full_id[:2],
        "index": full_id[2:4],
        "counter": full_id[4:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a new Selection Farm ID.")
    parser.add_argument("entity", help="full_prefix (e.g. MO00) or entity name (e.g. models)")
    args = parser.parse_args()
    print(generate_id(args.entity))


if __name__ == "__main__":
    main()
