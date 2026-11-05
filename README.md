# Peopl

*Good food travels between friends.* A small closed-loop community app for UChicago: share a plate, find a plate, see events, and check what is in your food.

> The food check gives information, not a religious ruling. Scholars and certifiers differ, and recipes change. Peopl is a student project and is not run by the University of Chicago.

## What it does

- **Plates.** Post it like you would tell a friend: "I made rice and have one plate left. Want it?" Friends tap "I'd love a plate". Afterwards they can tell the cook how it was.
- **Events.** Posted by approved organizers only.
- **Say hi.** A small message thread under each plate.
- **Food check.** Barcode, label photo, name search or dish photo. Rules decide the verdict; the AI only reads photos. No chatbot.
- **Closed loop.** Sign in with a uchicago.edu email and a 6-digit code. No password. Email addresses are not stored, only a keyed hash.

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export APP_SECRET=anything DEV_SHOW_CODE=1 ADMIN_EMAILS=you@uchicago.edu
streamlit run app.py
```

With `DEV_SHOW_CODE=1` the sign-in code appears on screen, so no email setup is needed. Never use that in production.

Tests: `python -m pytest -q` (202 pass).

## Settings

See `.env.example`. Key ones: `APP_SECRET`, `DATABASE_URL`, `ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `SMTP_*`, `GEMINI_API_KEY`.

## Deploy free (Streamlit Community Cloud)

1. Push to GitHub, then create the app at share.streamlit.io with `app.py`.
2. Streamlit Cloud wipes local files on restart, so SQLite will not last. Make a free Supabase project and put its Postgres connection string in `DATABASE_URL`.
3. Set `APP_SECRET`, `ADMIN_EMAILS`, the `SMTP_*` values and `GEMINI_API_KEY` in Settings > Secrets. Leave `DEV_SHOW_CODE` off.

## Before a real pilot

- Talk to the MSA board and UChicago Student Life about sharing home-cooked food. Get legal advice.
- Test sign-in email, Postgres and the Gemini calls live. Only mocked tests exist so far.
- Have a knowledgeable person review `halalcheck/data/rules.json`.
- Start with 10 to 15 students.

## Safety and limits

Plates need an ingredients and allergens note and a "packed and stored safely" tick. Daily limits: 6 posts, 4 claims, 30 messages. Anyone can report a post; admins can hide, dismiss, ban. People can delete their account and all their data. No money moves through the app.

Product data: Open Food Facts (ODbL).
