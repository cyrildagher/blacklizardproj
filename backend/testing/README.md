# Proxy Testing Harness

This harness validates that each account proxy presents the correct public
footprint before we wire it into the main betting pipeline.

## Setup

1. **Install dependencies**
   ```bash
   cd backend/testing
   python -m venv .venv
   .venv\Scripts\activate  # PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Configure proxies** in `proxies.yaml`:
   - Replace the example `proxy` endpoints with real sticky residential IPs.
   - Keep one proxy per account; add `backup_proxy` if you maintain a hot spare.
   - Match `user_agent`, `geo.country`, and `geo.timezone` to the proxy’s
     location for consistency.
   - Extend the `accounts` list for every Stake account you operate.
3. **Optional**: adjust or add HTTP endpoints under `checks` if you need to hit
   additional services for validation.

## Running the probe

```bash
python proxy_probe.py --config proxies.yaml
```

### Command-line flags

- `--config`: Alternate path to the YAML file (default `proxies.yaml`).
- `--output`: Override the CSV destination (defaults to `output_file` in the
  config).

## Interpreting results

- Console output shows the success/failure of each account per check, which
  proxy slot was used (`primary` vs `backup`), latency in milliseconds, and any
  HTTP errors.
- The CSV (default `proxy_probe_results.csv`) captures a row for every
  account/check combination with timestamps, outbound IP metadata, and errors
  for historical tracking.

## Next steps

- Integrate this probe into account node start-up to fail fast on bad proxies.
- Extend checks with Stake-specific health endpoints before enabling betting.
- Store validated IP/geolocation data alongside each account profile for audit
  trails.
