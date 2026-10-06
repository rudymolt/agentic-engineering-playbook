"""Run independent unittest file shards concurrently without omitting failures."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess


def test_files(directory: Path) -> tuple[str, ...]:
    """Mirror unittest discovery's top-level test_*.py files in stable order."""
    return tuple(path.name for path in sorted(directory.glob("test_*.py")))


def _label(command: tuple[str, ...]) -> str:
    try:
        return command[command.index("-p") + 1]
    except (ValueError, IndexError):
        return command[0]


def run_parallel(commands, *, cwd: Path, jobs: int, env=None) -> int:
    """Run every fixed command; group output by shard and propagate failure."""
    if jobs < 1:
        raise ValueError("jobs must be positive")
    tasks = tuple(tuple(command) for command in commands)
    if not tasks:
        raise ValueError("at least one test command is required")
    results = [0] * len(tasks)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {}
        for index, command in enumerate(tasks):
            print(f"Scheduled test shard {index + 1}/{len(tasks)}: {_label(command)}", flush=True)
            future = pool.submit(subprocess.run, command, cwd=cwd, env=env, check=False,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            futures[future] = index
        for future in as_completed(futures):
            index = futures[future]
            result = future.result()
            results[index] = result.returncode
            print(f"\nTest shard {index + 1}/{len(tasks)}: {_label(tasks[index])} "
                  f"(exit {result.returncode})", flush=True)
            if result.stdout:
                print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    return next((code for code in results if code), 0)
