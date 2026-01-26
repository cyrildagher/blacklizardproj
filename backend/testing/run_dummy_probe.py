from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from dummy_probe_server import create_server
from proxy_probe import load_config, resolve_output_path, run_probe


def main() -> int:
    base_dir = Path(__file__).parent
    config_path = base_dir / "sample_config_local.yaml"
    if not config_path.exists():
        print(f"Sample configuration not found: {config_path}", file=sys.stderr)
        return 1

    config = load_config(config_path)
    output_path = resolve_output_path(config_path, config, override=None)

    server = create_server()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    try:
        exit_code = run_probe(config, output_path)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    print(f"Dummy probe completed with exit code {exit_code}. Results: {output_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
