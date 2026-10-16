# Hickmet voucher bot

Telegram bot for passenger and flight vouchers from Google Sheets.

## Local start

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Set `BOT_TOKEN` in `.env`. Put the Google service account key at
`pligrim_bot/credentials/service_account.json`, or set
`GOOGLE_APPLICATION_CREDENTIALS` to its absolute path. On the server, the JSON
can instead be passed in `GOOGLE_CREDS` (also accepts `GOOGLE_CREDS_JSON`).
Share the required spreadsheets with the service account. The bot requests
read-only access. Set `ALLOWED_USER_IDS` to staff Telegram IDs to restrict use.
The bot accepts private chats only.

```sh
.venv/bin/python -m pligrim_bot.main
```

Docker: pass `BOT_TOKEN`, `GOOGLE_CREDS`, and optional `ALLOWED_USER_IDS` as
runtime environment variables. Keys and `.env` are excluded from the image.

## Worksheet format

A passenger block starts with a package title (for example,
`20.10-27.10 NIYET/7d`) followed by a header row. Supported name headers include
`Last name` / `First name`, `Name`, `First/Last Name`, `ФИО`, and bilingual
headers. Use `Room type` / `Type of room` / `Тип номера` for placement and
`Meal a day` / `Питание` for INF/CHD markers. A nonempty placement starts a new
room; blank cells continue the previous room. Adults beyond room capacity
start another room. Children stay with the current room.

Hotel configurations contain the package family, a city (`Madinah` or
`Makkah` and their aliases), hotel, check-in date, and check-out date.
Configurations may be under each passenger block or in a shared footer.
Matching uses family, hotel variant, duration where specified, and tour dates;
a hotel check-in one day before the departure date is supported. Duplicate
or missing configurations require manual correction in preview. The bot
never borrows passengers from the next package. Entries after hotel
configurations are excluded from the passenger list.

Each selected city needs a hotel and valid dates before PDF generation.
Individual vouchers are created from the main menu and completed in preview.
`/cancel`, `/start`, or “Создать ваучер” resets the user's current workflow.
Sessions and old buttons expire after one hour. Sessions are held in memory;
a restart requires choosing the package again.

Flight vouchers use a sheet with package labels and two full dates, plus
`расписание рейсов` in the same spreadsheet. Supported Air Astana flight
codes: KC263/264/265/266/8201/8202. Only matching routes from the schedule are
shown; other airlines need an explicit route mapping before use.

## Tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests
```

Tests use generated data and mock Telegram delivery, without Google requests.

## Telegram Mini App and website

The web interface supports package selection, manual vouchers, guest/room edits,
hotels, services, optional flight pages, preview, PDF/ZIP downloads, and delivery
to the authenticated user's Telegram chat. Manual flight fields accept any airline.
The older chat flight flow uses the Air Astana mappings described above.

Run the web process alongside the bot:

```sh
.venv/bin/python -m uvicorn pligrim_bot.web.app:app --host 127.0.0.1 --port 8000
```

Set `WEBAPP_URL` to the public HTTPS address. Both processes must use the same
`BOT_TOKEN`, `ALLOWED_USER_IDS`, and writable `WEB_STATE_DIR`. Telegram opens the
app from `/start` and the chat menu. The standalone site asks the user to confirm
login in the bot. Browser login approvals require the bot process to be running.
The site never accepts a user-supplied Telegram chat ID for document delivery.
Jobs/files expire after 24 hours; login sessions also last 24 hours.

## Existing server and Caddy

This server already has a Docker container named `caddy` on ports 80/443. Keep it;
the supplied Compose file starts only the bot and web app. Proxy configuration
belongs to the separate infrastructure deployment; this project has no Caddy
service or local Caddyfile. Transfer code changes through GitHub, then pull them
in the server's existing checkout.

On the inspected server the mounted configuration is `/root/infra/Caddyfile`
and the suitable existing network is `infra_infra_net` (the Compose default).
`CADDY_NETWORK` can override it if needed. The web container joins it under alias
`hickmet-voucher-web`.
If Caddy only uses Docker's default `bridge`, create a dedicated user-defined
network, connect Caddy to it, and persist that network in Caddy's own deployment
configuration before using it here.

Place the server Google key at `pligrim_bot/credentials/service_account.json`.
Keep `.env` and credentials on the server; do not include them in Git or archives.
Back up the current Caddy configuration and record the old bot's launch settings.
From the project directory on the server, pull the published changes, build,
and start only the web service first:

```sh
git pull --ff-only
docker compose build
docker compose up -d --wait web
docker compose exec web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
docker compose exec web python -m pligrim_bot.diagnostics
```

Back up and open the infrastructure configuration, preserving all other domains:

```sh
cp -p /root/infra/Caddyfile "/root/infra/Caddyfile.bak.$(date +%Y%m%d-%H%M%S)"
nano /root/infra/Caddyfile
```

Add this block once:

```caddyfile
voucherhickmet.duckdns.org {
    encode zstd gzip
    reverse_proxy hickmet-voucher-web:8000
}
```

Because this is a single-file bind mount, make sure the container sees the saved
block (`docker exec caddy cat /etc/caddy/Caddyfile`). If it still shows the old
file after an editor replaced its inode, restore the original mounted inode or
recreate Caddy through its infrastructure deployment before proceeding.
Validate, then reload only if validation succeeded:

```sh
docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
curl -I https://voucherhickmet.duckdns.org/
```

DNS for `voucherhickmet.duckdns.org` must point to `65.21.188.181`. Once HTTPS and
the catalog work, replace the old polling process. Never run both simultaneously:

```sh
docker stop pilgrim-bot
docker compose up -d bot
docker compose logs --tail 80 bot web
```

If the new bot fails, stop it before restoring the old one:

```sh
docker compose stop bot
docker start pilgrim-bot
```

Finally check `/start`, Mini App login on phone and desktop, a package voucher,
a manual voucher with and without flights, PDFs in the private chat, native
downloads, and the standalone website login. Local tests mock Telegram delivery;
they do not replace this server check. Track unfinished work in `PROJECT_STATUS.md`.

If only June appears, compare `python -m pligrim_bot.diagnostics` in the deployed
environment with the local result. It prints document titles and detected months,
without keys or passenger data. Months currently come from English month names
in accessible spreadsheet document titles. Missing months can indicate different
service-account permissions, naming differences, or an older deployed version.
An older version also hardcoded exclusions for February 2026, December 2025, and
January 2026. The current version shows all accessible months by default; optional
`EXCLUDED_PILGRIM_MONTHS` in `.env` can hide explicitly listed labels.
