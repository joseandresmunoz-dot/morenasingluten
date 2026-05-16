# AGENTS.md - Morena Sin Gluten

## Quick Start

```bash
# 1. Create PostgreSQL database (must exist first)
# 2. Copy and configure .env
cp .env.example .env
# 3. Activate venv and install
source venv/bin/activate
pip install -r requirements.txt
# 4. Seed database
python seed.py
# 5. Run dev server
python app.py
```

Admin login: `admin@morenasingluten.com` / `admin123`

## Dev Commands

- `python app.py` - Run Flask dev server (port 5000, debug mode)
- `python seed.py` - Re-seed database (preserves existing data)

## Database

- PostgreSQL required (no SQLite)
- SQLAlchemy ORM with automatic column additions in `app.py:57-88`
- No Flask-Migrate commands needed - schema updates auto-applied on startup (only ADD COLUMN, not migrations)

## Architecture

- Single Flask app with 3 blueprints: `auth`, `shop`, `admin`
- Models in `models.py`
- Templates in `templates/{auth,shop,admin}/`
- Static assets in `static/`
- Uploads served from `uploads/` and `images/`

## Key Config (`.env` required)

- `SECRET_KEY` - Flask secret
- `DATABASE_URL` - PostgreSQL connection string
- `WHATSAPP_NUMBER` - For order notifications
- `MERCADOPAGO_ALIAS` - Payment alias
- `GOOGLE_CLIENT_ID/SECRET` - Optional (for Google OAuth login)
- `MAIL_*` vars - Optional (for email verification)

## Testing

- No test framework installed; test manually via browser

## Production

- Run with: `gunicorn -w 4 -b 0.0.0.0:5000 app:app`
- Requires proper `SECRET_KEY` and `DATABASE_URL` in `.env`