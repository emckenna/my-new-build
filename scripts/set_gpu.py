#!/usr/bin/env python3
"""Set the globally selected GPU in parts.json."""

import json
import sys

PARTS_FILE = "parts.json"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: set_gpu.py GPU_ID")

    gpu_id = sys.argv[1]
    with open(PARTS_FILE) as file:
        data = json.load(file)

    gpu_ids = {part["id"] for part in data["parts"] if part.get("category") == "video card"}
    if gpu_id not in gpu_ids:
        raise SystemExit(f"unknown GPU ID: {gpu_id}")

    for part in data["parts"]:
        if part.get("category") == "video card":
            part["in_build"] = part["id"] == gpu_id

    with open(PARTS_FILE, "w") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()
