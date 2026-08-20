# Ducks for Ducks

A privacy-friendly frontend for GeeksforGeeks.

This is a fork of [PrivateCoffee/ducksforducks](https://git.private.coffee/PrivateCoffee/ducksforducks)
with additional fixes and features. See [Differences from upstream](#differences-from-upstream).

## Usage

Replace `geeksforgeeks.org` with your instance's domain in any article URL:

```
https://www.geeksforgeeks.org/dsa/bubble-sort-algorithm/
https://your-instance.example/dsa/bubble-sort-algorithm/
```

Images are proxied through the instance, so your browser never contacts
GeeksforGeeks.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8113` | Port the development server listens on |
| `DEBUG` | unset | Enables Flask's debugger. Accepts `1`, `true`, `yes`, `on` |
| `REQUEST_TIMEOUT` | `20` | Timeout in seconds for outbound requests |
| `MAX_PROXY_BYTES` | `10485760` | Maximum size in bytes accepted when proxying a resource |

## Running with Docker

```bash
docker compose up -d --build
```

`docker-compose.yml`:

```yaml
services:
  ducksforducks:
    build: .
    container_name: ducksforducks_app
    restart: unless-stopped
    ports:
      - "8113:8113"
```

The image runs the application with gunicorn. `main()` and the `PORT`
variable only apply when running the development server directly.

## Running from source

```bash
pip install .
ducksforducks
```

Or, for development:

```bash
python -m ducksforducks.app
```

## Differences from upstream

- Code samples in multiple languages are rebuilt as JavaScript-free tabs
  instead of being stacked one after another
- Syntax highlighting using the Monokai palette, matching GeeksforGeeks
- "Copy" and "Run on tio.run" buttons on every code block
- Practice problems (`/problems/<slug>/<n>`) are rendered by the instance,
  with an embedded tio.run editor per language
- Image carousels are recovered as vertical image lists
- Dark theme, on Bootstrap 5.3
- Styled tables and blockquotes
- Requests for paths that cannot be articles (`/favicon.ico`, `/.env`,
  scanner probes) are rejected without hitting GeeksforGeeks
- Timeouts and a size limit on outbound requests
- Dockerfile

## Known limitations

- The GeeksforGeeks home page and user profiles are not implemented
- tio.run expands its Header and Footer sections automatically, so the
  problem driver is visible in the embedded editor
- Complexity expressions are shown as plain text, as on GeeksforGeeks

## License

MIT. See [LICENSE](LICENSE).

Original work by the [Private.coffee](https://private.coffee) Team.