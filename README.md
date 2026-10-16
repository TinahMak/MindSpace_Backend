# MindSpace — Django Backend

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your real values
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Visit http://127.0.0.1:8000/

### Database config (Supabase Postgres)

Reads its DB connection from `.env` (gitignored). Copy `.env.example` to
`.env` and fill in your Supabase pooler credentials. Set `USE_SQLITE=True`
for quick local testing without Postgres.

### AI chat (Gemini)

Add `GEMINI_API_KEY=your-key` to `.env`. Get a free key at
https://aistudio.google.com/apikey. Without it, AI chat and mood insights'
AI reflections fail gracefully (chat shows a friendly error; insights fall
back to rule-based text) rather than crashing.

### Weekly AI insights (Celery + Redis)

The weekly insight report runs on a schedule via Celery. You don't need
this running to try the feature — the **"Generate this week's insight now"**
button on the insights page runs the same logic synchronously, no broker
required.

To run it for real (automatic Monday emails):

1. Install and run Redis locally (`brew install redis && redis-server`,
   or `docker run -p 6379:6379 redis`, or your OS's package manager).
2. In separate terminals, from the project root:
   ```bash
   celery -A mindspace worker --loglevel=info
   celery -A mindspace beat --loglevel=info
   ```
3. `CELERY_BROKER_URL` defaults to `redis://localhost:6379/0` — override in
   `.env` if your Redis lives elsewhere.

## App structure

- **core** — public marketing pages (home, about, contact), Privacy Policy,
  and the Get Help page (localized crisis lines + therapist directories).
- **accounts** — custom `User` model (email login), signup, login/logout,
  password reset, email verification, "remember me", account settings
  (data export, delete account, country/weekly-insight preferences),
  dashboard.
- **wellness** — mood check-ins (multiple/day supported), 7-day chart,
  streaks, pattern insights with AI reflection, downloadable PDF report for
  sharing with a professional, weekly insight emails (Celery).
- **aichat** — AI chat companion (Gemini), deterministic crisis-language
  detection with persistent helpline banner, photo-based mood suggestions
  that can be logged to the mood tracker with one tap.

## What's implemented

**Auth & persistence**
- Email-based auth, custom `User` model, Postgres via Supabase
- Password reset (email link)
- Email verification on signup (non-blocking — banner reminds until verified)
- "Remember me" (14-day session vs. browser-close expiry)

**Mood tracking**
- Multiple check-ins/day, 7-day chart + mood-frequency breakdown, streak
  and average-mood stats

**AI chat**
- Gemini-powered conversation with memory within a thread
- Deterministic (keyword-based, not AI-judged) crisis detection → persistent
  helpline banner
- Photo upload → tentative, non-diagnostic mood read → one-tap log to mood
  tracker

**Mood insights**
- Pattern analysis (trend, low-mood ratio, common tags) with an AI-written
  plain-language reflection — deliberately never outputs a diagnostic
  "needs help: yes/no" verdict, just a "steady" / "worth a closer look"
  signal plus a rule-based fallback if the AI call fails
- Downloadable PDF report to share with a therapist — MindSpace never sends
  this anywhere automatically
- Weekly insight email (Celery-scheduled, opt-out in settings)

**Trust & safety**
- Plain-language Privacy Policy (no overclaimed compliance — honest about
  what security measures are actually in place)
- Data export (full JSON) and account deletion (password-confirmed, cascades
  correctly) from Account Settings
- Persistent "Get help now" button in every page's nav — not just triggered
  by crisis detection
- Localized crisis lines (SA, US, UK, Canada, Australia, India — verified
  against each org's own site) + findahelpline.com fallback for everywhere
  else, country preference saved per user
- Real therapist directories linked (SADAG, Psychology Today, Find A Helpline)
- Admin-visible crisis-message frequency per user, for manual safety review

## Deliberately not built (and why)

- **Rate-limiting crisis messages**: throttling someone reaching out in
  crisis would be actively harmful, so this was skipped on purpose — the
  admin report above is a review signal for a human, not an automated gate.
- **Automatic transmission of health data to a therapist**: no real
  therapist-account/consent system exists yet, so instead of building
  something that silently emails sensitive data, the PDF report puts the
  person in control of sharing it themselves.
- **Dark mode / full accessibility audit**: real work, but needs its own
  focused pass rather than being squeezed in here.
- **Monetization (freemium, payments, referrals)**: needs pricing/business
  decisions only you can make before this should be built.
- **Social login (Google/Apple)**: needs OAuth app registration in your own
  Google/Apple developer consoles — can't be done without your credentials.

## Known gaps

- Signup wizard doesn't re-populate steps 2/3 on a server-side validation
  error (falls back to step 1) — fine since JS mirrors all server rules,
  but worth tightening later.
- Journal entries and breathing exercises are still placeholders.
- The weekly insight Celery schedule needs Redis + worker/beat processes
  running for the automatic Monday send; untested against a real broker in
  the environment this was built in (see "Weekly AI insights" above) —
  please verify the scheduled path works on your machine.
