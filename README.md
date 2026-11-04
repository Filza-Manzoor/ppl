# Halal Check

Scan or search a food and see *why* it looks halal, doubtful or not halal. It shows its reasons, what to ask the maker, and where scholars differ.

> **Halal Check gives information, not a religious ruling.** Scholars and certifiers differ, and recipes change. Look for a halal logo from a certifier you trust.

## How it is different

- **The AI reads, the rules decide.** Gemini only reads text from photos. Every verdict comes from `halalcheck/data/rules.json`, so text printed on a pack cannot talk the app into an answer.
- **It explains.** Each flagged ingredient shows a reason, a note where views differ, and a question to ask.
- **It leans toward caution.** Unknown ingredient sources are "doubtful", not "ok". A missing ingredient list is "can't tell", never "halal".
- **A dish photo never gets a halal verdict.** A photo can't show how meat was sourced. It lists likely ingredients and questions to ask.
- **Country aware.** Pick your country. If the product record is for another country's version, you get a warning.
- **Private.** Photos are resized, stripped of EXIF/GPS, sent to Gemini and not stored. Location is never saved.

## Input order (most to least reliable)

1. Barcode: exact product record from Open Food Facts.
2. Ingredient label photo: reads the pack in your hand.
3. Product name: search, you pick a match, with a warning that recipes differ.
4. Dish photo: likely ingredients and questions only.

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your free Gemini key
export $(grep -v '^#' .env | xargs)
streamlit run app.py
pytest                        # 169 tests, no network needed
```

Free Gemini key: https://aistudio.google.com/apikey. Without a key, typed barcodes and name search still work.

## Put it online for free (Streamlit Community Cloud)

1. Push this folder to a **public GitHub repo** (never commit `.env`; `.gitignore` already blocks it).
2. Go to https://share.streamlit.io, sign in with GitHub, choose the repo, main file `app.py`.
3. Under **Advanced settings > Secrets** paste:
   ```toml
   GEMINI_API_KEY = "your-key"
   ```
4. Deploy. Share the link. Free apps sleep when idle and wake on the next visit.

## Keep feedback in a Google Sheet (optional)

Free hosts delete local files on restart. To keep reports:

1. Create a Google Sheet. Extensions > Apps Script. Paste:
   ```javascript
   function doPost(e) {
     var d = JSON.parse(e.postData.contents);
     SpreadsheetApp.getActiveSheet().appendRow([d.time, d.source, d.verdict, d.reason, d.comment, d.product_code, (d.rule_ids || []).join(","), d.rulebook_version]);
     return ContentService.createTextOutput("ok");
   }
   ```
2. Deploy > New deployment > Web app, access "Anyone". Copy the URL.
3. Add `FEEDBACK_WEBHOOK_URL = "that-url"` to your secrets.

## Limits to know before testing with people

- **Free Gemini limits are small.** The app caps photo checks per visit (`VISION_CALLS_PER_SESSION`, default 12) and caches product lookups. Many testers at once can still hit the daily limit; the app then shows a "busy" message.
- **The model name may change.** If photo reading fails with a model error, set `GEMINI_MODEL` to a current Gemini Flash model.
- **Open Food Facts is crowd-sourced.** Records can be old, wrong or missing. Be gentle with it: don't build bulk scrapers on this.
- **The rulebook is a starting point, not a fatwa.** Have a knowledgeable person review `rules.json` and add sources before a public launch. Each rule has `examples` and `non_examples` that the tests check, so add those when you add rules.

## Add or change a rule

Edit `halalcheck/data/rules.json`. Status is `prohibited`, `doubtful`, `check` or `ok`. `ok` rules exist to cancel false alarms (for example "ginger beer"); the longest match wins. `cleared_by_claim: true` means a halal label on the product lowers a `doubtful` item. Run `pytest`.

## Layout

```
app.py                  Streamlit UI
halalcheck/rules.py     rule engine and verdicts
halalcheck/off.py       Open Food Facts client
halalcheck/vision.py    Gemini photo reading
halalcheck/pipeline.py  connects data to rules
halalcheck/feedback.py  report logging
halalcheck/data/rules.json
tests/
```

Product data from Open Food Facts, under the Open Database License.
