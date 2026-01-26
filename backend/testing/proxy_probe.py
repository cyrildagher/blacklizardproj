from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml


@dataclass
class Check:
    name: str
    url: str
    expect_json: bool = True


@dataclass
class ProbeOutcome:
    success: bool
    latency_ms: float
    status_code: Optional[int]
    summary: str
    raw: Optional[str]
    proxy_used: str
    error: Optional[str] = None


def load_config(config_path: Path) -> Dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_checks(config: Mapping[str, Any]) -> List[Check]:
    checks: List[Check] = []
    for entry in config.get("checks", []):
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name", "unnamed")).strip()
        url = str(entry.get("url", "")).strip()
        if not name or not url:
            continue
        expect_json = bool(entry.get("expect_json", True))
        checks.append(Check(name=name, url=url, expect_json=expect_json))
    if not checks:
        checks = [
            Check(name="ipify", url="https://api.ipify.org?format=json", expect_json=True),
            Check(name="ifconfig", url="https://ifconfig.co/json", expect_json=True),
            Check(name="httpbin_headers", url="https://httpbin.org/headers", expect_json=True),
        ]
    return checks


def resolve_output_path(config_path: Path, config: Mapping[str, Any], override: Optional[str]) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    output_rel = config.get("output_file", "proxy_probe_results.csv")
    return (config_path.parent / output_rel).resolve()


def summarise_payload(check: Check, response: requests.Response, expect_json: bool) -> Tuple[str, Optional[str]]:
    raw_repr: Optional[str] = None
    payload: Any
    try:
        payload = response.json() if expect_json else response.text
    except ValueError:
        payload = response.text
    if isinstance(payload, Mapping):
        trimmed = json.dumps(payload)[:500]
        raw_repr = trimmed
    elif isinstance(payload, (list, tuple)):
        trimmed = json.dumps(payload)[:500]
        raw_repr = trimmed
    else:
        trimmed = str(payload)[:500]
        raw_repr = trimmed

    summary: Dict[str, Any] = {}
    if isinstance(payload, Mapping):
        if check.name == "ipify":
            summary["ip"] = payload.get("ip")
        elif check.name == "ifconfig":
            summary["ip"] = payload.get("ip")
            summary["asn_org"] = (payload.get("asn") or {}).get("org")
            summary["country"] = payload.get("country")
            summary["region"] = payload.get("region")
            summary["city"] = payload.get("city")
        elif check.name == "httpbin_headers":
            summary = payload.get("headers", {})
        else:
            summary = payload
    else:
        summary["value"] = trimmed

    summary_json = json.dumps(summary, ensure_ascii=True)
    return summary_json, raw_repr


def pick_proxy(account: Mapping[str, Any]) -> Tuple[Optional[MutableMapping[str, str]], Optional[MutableMapping[str, str]]]:
    primary = account.get("proxy")
    backup = account.get("backup_proxy")
    return (primary if isinstance(primary, MutableMapping) else None,
            backup if isinstance(backup, MutableMapping) else None)


def probe_account(
    account: Mapping[str, Any],
    checks: Iterable[Check],
    session: requests.Session,
    default_timeout: float,
) -> List[Tuple[Check, ProbeOutcome]]:
    account_id = str(account.get("id", "unknown"))
    user_agent = str(account.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36"))
    timeout = float(account.get("timeout_seconds", default_timeout))
    primary_proxy, backup_proxy = pick_proxy(account)

    outcomes: List[Tuple[Check, ProbeOutcome]] = []
    for check in checks:
        headers = {"User-Agent": user_agent}
        chosen_proxy_label = "primary"
        proxies = primary_proxy
        attempt = 0
        response: Optional[requests.Response] = None
        error_text: Optional[str] = None

        while attempt < 2:
            try:
                start = time.perf_counter()
                response = session.get(
                    check.url,
                    headers=headers,
                    proxies=proxies,
                    timeout=timeout,
                )
                latency_ms = (time.perf_counter() - start) * 1000.0
                summary, raw_repr = summarise_payload(check, response, check.expect_json)
                outcome = ProbeOutcome(
                    success=response.ok,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    summary=summary,
                    raw=raw_repr,
                    proxy_used=chosen_proxy_label,
                    error=None if response.ok else f"HTTP {response.status_code}",
                )
                outcomes.append((check, outcome))
                break
            except requests.RequestException as exc:
                latency_ms = 0.0
                error_text = str(exc)
                outcome = ProbeOutcome(
                    success=False,
                    latency_ms=latency_ms,
                    status_code=None,
                    summary="{}",
                    raw=None,
                    proxy_used=chosen_proxy_label,
                    error=error_text,
                )
                outcomes.append((check, outcome))

            if attempt == 0 and backup_proxy:
                proxies = backup_proxy
                chosen_proxy_label = "backup"
                attempt += 1
                continue
            break

    return outcomes


def write_results(
    account_id: str,
    check: Check,
    outcome: ProbeOutcome,
    timestamp: datetime,
    writer: csv.DictWriter,
) -> None:
    writer.writerow(
        {
            "timestamp_utc": timestamp.isoformat(),
            "account_id": account_id,
            "check_name": check.name,
            "url": check.url,
            "success": str(outcome.success),
            "latency_ms": f"{outcome.latency_ms:.2f}",
            "status_code": outcome.status_code if outcome.status_code is not None else "",
            "proxy_used": outcome.proxy_used,
            "summary": outcome.summary,
            "error": outcome.error or "",
        }
    )


def run_probe(config: Mapping[str, Any], output_path: Path) -> int:
    checks = build_checks(config)
    accounts = config.get("accounts", [])
    if not accounts:
        print("No accounts defined in configuration. Nothing to probe.", file=sys.stderr)
        return 1

    default_timeout = float(config.get("default_timeout_seconds", 10.0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp_utc",
        "account_id",
        "check_name",
        "url",
        "success",
        "latency_ms",
        "status_code",
        "proxy_used",
        "summary",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        session = requests.Session()
        try:
            for account in accounts:
                account_id = str(account.get("id", "unknown"))
                timestamp = datetime.now(timezone.utc)
                outcomes = probe_account(account, checks, session, default_timeout)
                for check, outcome in outcomes:
                    write_results(account_id, check, outcome, timestamp, writer)
                    status = "OK" if outcome.success else "FAIL"
                    print(
                        f"[{timestamp.isoformat()}] {account_id:<20} {check.name:<20} {status} "
                        f"{outcome.latency_ms:.1f}ms {outcome.proxy_used} "
                        f"{('status=' + str(outcome.status_code)) if outcome.status_code else ''} "
                        f"{('err=' + outcome.error) if outcome.error else ''}"
                    )
        finally:
            session.close()

    print(f"\nResults written to {output_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe configured proxies to validate external IP masking and latency."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="proxies.yaml",
        help="Path to the proxy configuration YAML file (default: proxies.yaml).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path for CSV output. Defaults to value specified in config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Configuration file not found: {config_path}", file=sys.stderr)
        return 1
    config = load_config(config_path)
    output_path = resolve_output_path(config_path, config, args.output)
    return run_probe(config, output_path)


if __name__ == "__main__":
    sys.exit(main())
