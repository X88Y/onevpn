#!/usr/bin/env python3
"""Validate CIDR whitelist ranges by pinging IPs in each network.

If any probe IP in a range responds to ping, the entire CIDR is marked as
working. When the first IP fails, additional IPs in the range are tried.
Results are appended to output files as each range completes.

Usage:
    python validate_cidrwhitelist.py
    python validate_cidrwhitelist.py --limit 100 --concurrency 50
    python validate_cidrwhitelist.py --max-probes 5 --timeout 2
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import platform
import shutil
import sys
import time
from pathlib import Path


class RuntimeResultWriter:
    """Append working/failed CIDRs to output files as probes finish."""

    def __init__(
        self,
        working_path: Path,
        failed_path: Path,
        report_path: Path | None,
    ) -> None:
        self.working_path = working_path
        self.failed_path = failed_path
        self.report_path = report_path
        self._lock = asyncio.Lock()
        self.working_count = 0
        self.failed_count = 0

    def init_files(self) -> None:
        self.working_path.write_text("")
        self.failed_path.write_text("")
        if self.report_path is not None:
            self.report_path.write_text("")

    async def write_result(
        self,
        network: ipaddress.IPv4Network,
        alive: bool,
        probe_ip: str,
        tried_ips: list[str],
    ) -> None:
        cidr = str(network)
        tried = ",".join(tried_ips)
        async with self._lock:
            if alive:
                self._append_line(self.working_path, cidr)
                self.working_count += 1
                if self.report_path is not None:
                    self._append_line(
                        self.report_path,
                        f"OK   {cidr}  probe={probe_ip}  tried={tried}",
                    )
            else:
                self._append_line(self.failed_path, cidr)
                self.failed_count += 1
                if self.report_path is not None:
                    self._append_line(
                        self.report_path,
                        f"FAIL {cidr}  tried={tried}",
                    )

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{line}\n")
            f.flush()


def load_cidr_whitelist(file_path: Path) -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    with file_path.open() as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                networks.append(ipaddress.ip_network(line, strict=False))
            except ValueError as exc:
                print(f"Warning: skipping invalid CIDR on line {line_no}: {line!r} ({exc})")
    return networks


def probe_ips(network: ipaddress.IPv4Network, max_probes: int) -> list[str]:
    hosts = list(network.hosts())
    if not hosts:
        return [str(network.network_address)]
    if len(hosts) <= max_probes:
        return [str(host) for host in hosts]

    indices = {0, len(hosts) // 2, len(hosts) - 1}
    step = len(hosts) / max_probes
    for i in range(max_probes):
        indices.add(min(int(i * step), len(hosts) - 1))

    return [str(hosts[i]) for i in sorted(indices)[:max_probes]]


def build_ping_command(ip: str, timeout: float) -> list[str]:
    timeout_secs = max(1, int(timeout))
    system = platform.system()
    if system == "Darwin":
        return ["ping", "-c", "1", "-t", str(timeout_secs), ip]
    if system == "Linux":
        return ["ping", "-c", "1", "-W", str(timeout_secs), ip]
    if system == "Windows":
        return ["ping", "-n", "1", "-w", str(timeout_secs * 1000), ip]
    raise RuntimeError(f"Unsupported platform for ping: {system}")


async def is_ping_alive(ip: str, timeout: float) -> bool:
    cmd = build_ping_command(ip, timeout)
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
        return proc.returncode == 0
    except (OSError, asyncio.TimeoutError):
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
        return False


async def validate_network(
    network: ipaddress.IPv4Network,
    timeout: float,
    max_probes: int,
    semaphore: asyncio.Semaphore,
) -> tuple[ipaddress.IPv4Network, bool, str, list[str]]:
    ips = probe_ips(network, max_probes)
    async with semaphore:
        for ip in ips:
            if await is_ping_alive(ip, timeout):
                return network, True, ip, ips
    return network, False, ips[-1], ips


async def run_validation(
    networks: list[ipaddress.IPv4Network],
    timeout: float,
    max_probes: int,
    concurrency: int,
    writer: RuntimeResultWriter,
) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        validate_network(network, timeout, max_probes, semaphore)
        for network in networks
    ]

    total = len(tasks)
    completed = 0

    for coro in asyncio.as_completed(tasks):
        result = await coro
        if isinstance(result, BaseException):
            raise result

        network, alive, probe_ip, tried_ips = result
        await writer.write_result(network, alive, probe_ip, tried_ips)
        completed += 1

        if completed % 100 == 0 or completed == total:
            print(
                f"Progress: {completed}/{total} "
                f"({writer.working_count} working, {writer.failed_count} failed)"
            )


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Validate CIDR whitelist: one working IP marks the whole range as working.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=script_dir / "cidrwhitelist.txt",
        help="Input CIDR whitelist file",
    )
    parser.add_argument(
        "--working-output",
        type=Path,
        default=script_dir / "cidrwhitelist.working.txt",
        help="Output file for working CIDR ranges",
    )
    parser.add_argument(
        "--failed-output",
        type=Path,
        default=script_dir / "cidrwhitelist.failed.txt",
        help="Output file for failed CIDR ranges",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=script_dir / "cidrwhitelist.report.txt",
        help="Detailed probe report (set to empty string to skip)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Ping timeout in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=100,
        help="Maximum concurrent probes (default: 100)",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=5,
        help="Max IPs to ping per range before marking it failed (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Validate only the first N ranges (0 = all)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if shutil.which("ping") is None:
        print("Error: ping command not found in PATH.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading CIDR ranges from {args.input}...")
    networks = load_cidr_whitelist(args.input)
    if args.limit > 0:
        networks = networks[: args.limit]

    if not networks:
        print("Error: no CIDR ranges to validate.", file=sys.stderr)
        sys.exit(1)

    print(
        f"Validating {len(networks)} ranges "
        f"(ping, max_probes={args.max_probes}, timeout={args.timeout}s, "
        f"concurrency={args.concurrency})..."
    )

    report_path = args.report if str(args.report) else None
    writer = RuntimeResultWriter(args.working_output, args.failed_output, report_path)
    writer.init_files()
    print(f"Saving results live to:")
    print(f"  {args.working_output}")
    print(f"  {args.failed_output}")
    if report_path is not None:
        print(f"  {report_path}")

    started = time.monotonic()
    asyncio.run(
        run_validation(
            networks,
            timeout=args.timeout,
            max_probes=args.max_probes,
            concurrency=args.concurrency,
            writer=writer,
        )
    )
    elapsed = time.monotonic() - started

    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"  Working: {writer.working_count}")
    print(f"  Failed:  {writer.failed_count}")


if __name__ == "__main__":
    main()
