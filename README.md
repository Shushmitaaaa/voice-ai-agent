# Saffron AI Voice Booking Agent

A production voice AI agent that takes restaurant table reservations over a real-time voice conversation. Built with [Pipecat](https://github.com/pipecat-ai/pipecat), deployed on Render, using LiveKit for real-time audio transport and MongoDB Atlas for reservation data.

The bot plays the role of **Rina**, the reservations host at Saffron, a mid-range Indian restaurant. It collects five required details (name, date, time, party size, seating preference) through natural conversation, checks table availability, and books confirmed reservations — all while speaking naturally, asking only one question per turn, and never hallucinating a confirmation that didn't actually happen.


## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Voice pipeline framework | Pipecat | Orchestrates STT → LLM → TTS as a streaming pipeline of frames |
| Speech-to-text | Deepgram | Real-time transcription with tuned endpointing |
| LLM | Groq (`openai/gpt-oss-120b`) | Fast inference, function/tool calling support |
| Text-to-speech | Cartesia | Natural-sounding voice output |
| Real-time transport | LiveKit | Cloud media relay connecting browser client ↔ bot server |
| Database | MongoDB Atlas | Stores `tables` (seed data) and `reservations` (bookings) |
| Hosting | Render | Runs the bot server as a web service |
| Package manager | `uv` | Fast Python dependency management |


## Project structure

```
restaurant-booking-agent/
├── 08-restaurant-booking.py   # main bot — the only file actually deployed/run
├── seed_tables.py              # one-time script to populate the `tables` collection
├── pyproject.toml              # dependencies (managed by uv)
├── uv.lock
├── env.example                 # template for required environment variables
└── src/                        # earlier learning-stage Pipecat examples (01–07)
```

Everything before `08-restaurant-booking.py` in the numbered files is prior learning/scaffolding from working through Pipecat's examples  `01-say-one-thing.py` through `07-function-calling.py`. Only `08-restaurant-booking.py` is the production bot.


<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/e2ff1566-e4be-4dc1-b508-e6078f4e7adc" />



## Environment variables

Set these in `.env` locally and in Render's **Environment** tab for production:

| Variable | Purpose |
|---|---|
| `DEEPGRAM_API_KEY` | STT |
| `CARTESIA_API_KEY` | TTS |
| `GROQ_API_KEY` | LLM |
| `MONGO_URI` | MongoDB Atlas connection string |
| `MONGO_DB` | Database name (`saffron`) |
| `LIVEKIT_URL` | LiveKit project WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit auth |
| `LIVEKIT_API_SECRET` | LiveKit auth |


## Running locally

```bash
uv sync
uv run python 08-restaurant-booking.py
```

Open `http://localhost:7860/client/`  Pipecat Playground and pick a transport (SmallWebRTC works fine locally since client and server share a machine).

## Deploying to Render

**Build command:**
```
pip install uv && uv sync
```

**Start command:**
```
uv run python 08-restaurant-booking.py --host 0.0.0.0 --port $PORT
```

Root directory should be blank (repo root), since `pyproject.toml` and `uv.lock` live there.


## Database schema

**`tables` collection** — static seed data, one document per physical table:
```json
{ "_id": "T1", "capacity": 2, "seating": "indoor" }
```

**`reservations` collection** — created automatically on first booking:
```json
{
  "table_id": "T1",
  "name": "Shushmita",
  "date": "2026-09-10",
  "time": "10:00",
  "pax": 2,
  "seating": "indoor",
  "status": "confirmed",
  "created_at": "2026-09-09T08:20:13.380+00:00"
}
```

A unique index on `(table_id, date, time)` prevents double-booking the same table/slot this is what makes the retry loop in `book_table` safe under concurrent requests.


## Conversation logic

The system prompt enforces:
- Exactly one missing detail is asked per turn never two questions stacked.
- Relative dates ("tomorrow", "next Friday") are converted to absolute `YYYY-MM-DD` before any tool call the LLM never passes relative words as data.
- A booking is never narrated as confirmed unless `book_table` actually returned `status: confirmed`.
- Booking IDs and raw dates are never spoken aloud (spoken output must be natural: "tomorrow", "Sunday the seventeenth").
- `check_availability` and `book_table` are never called in the same turn — the guest must hear the availability summary and explicitly confirm before `book_table` runs.

A custom Pipecat frame processor, `OneQuestionGuardrail`, sits between the LLM and TTS as a hard backstop: it streams the LLM's text token-by-token, and the moment it sees the first `?` in a turn, it truncates everything after it so even if the model tries to ask two questions, only the first is ever spoken.

### Tool calls

**`check_availability(date, time, pax)`**
1. Validates `pax >= 1`.
2. Validates the time falls within operating hours (09:00–23:00).
3. Queries `tables`, excluding any table already booked (via `reservations`) for that exact date/time, filtered by capacity, sorted smallest-first.
4. Returns `available`, `tables_left`, and the distinct `seating_options` still open no table IDs are exposed to the guest.

**`book_table(name, date, time, pax, seating, confirmed)`**
1. Rejects the call outright unless `confirmed=true` this is only set once the guest has explicitly agreed to the reservation just read back to them.
2. Validates name, party size, and operating hours again (defense in depth the guest may have taken time to respond after `check_availability`, so state could have changed).
3. Re-queries free tables fresh (not reusing the earlier `check_availability` result)  this closes a race condition where another guest could have booked the same slot in the gap between the check and this confirmation.
4. Loops through candidate tables smallest-first, attempting `insert_one` into `reservations`. If a `DuplicateKeyError` fires (another booking beat this one to that exact table+slot), it moves to the next candidate.
5. On success, returns `status: confirmed` and a real MongoDB-generated `booking_id`. If every candidate table is exhausted, returns an error telling the guest to try a different time.

