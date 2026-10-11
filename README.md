# Find the Imposter 🕵️

A pass-the-phone party game in a **single file** (`index.html`, zero dependencies, no network
requests). Everyone secretly sees the same word — except one or two imposters, who see nothing.
Trade clues, sniff out the fake, and vote them out before they figure out your word.

## How to play

1. Open `index.html` in any mobile or desktop browser (or serve the folder with any static server).
2. **Setup** — pick 4–12 players, 1–2 imposters and an optional discussion timer.
3. **Private reveal** — each player holds their card to peek at their role in secret.
4. **Clues & discussion** — everyone says one clue word, then debate. Pause/resume the timer anytime.
5. **Secret ballot** — vote one suspect at a time; you can never vote for yourself.
6. **Outcomes**
   - Catch the *last* imposter → they get one final guess at the word: right = imposters steal **+2**, wrong = crew scores **+1** each.
   - An imposter survives (or ballots deadlock twice) → **Deception**, imposters score **+3** each.
7. Run as many rounds as you like — scores accumulate and the word never repeats back-to-back.

## Development

```bash
# Serve locally
python3 -m http.server 8000

# Smoke tests (requires playwright + a Chromium at /usr/bin/chromium)
python tests/smoke_browser.py
```

The whole game lives in `index.html`; global state is exposed on `window.state` and the
anti-double-tap guard on `window.clickGuard`, which the tests drive directly.
