# PlasticPaths story backend

This isolated FastAPI service turns a simulation summary into a sourced, child-friendly story and,
when configured, ElevenLabs narration. The React map remains independent.

## What runs without credentials

`RETRIEVAL_MODE=local` uses a small deterministic lexical search over the curated passages in
`app/education.py`. It is a development mode only. It is **not** a live TiDB integration and the API
labels responses with `"retrieval_mode": "local"`.

Without `GEMINI_API_KEY`, story requests use a deterministic 50–80-word fallback and return
`"generation_mode": "fallback"`. A missing ElevenLabs configuration returns a clear `503`; it does
not create fake audio.

## Local setup

Python 3.11 or newer is required.

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
cp ../.env.example ../.env.local
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health`

The ignored `backend/.data/` directory stores SQLite cache metadata and generated audio. Story cache
keys include the complete normalized simulation input, prompt version, retrieval version, retrieval
mode, and Gemini model. Audio cache keys include the script, voice, model, and output format.

## Live configuration

Place secrets in the ignored root `.env.local` (never in frontend code):

```dotenv
RETRIEVAL_MODE=tidb
GEMINI_API_KEY=your-secret-key
GEMINI_MODEL=gemini-3.8-flash
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768
TIDB_DATABASE_URL=mysql+pymysql://user:password@host:4000/database?ssl_verify_cert=true&ssl_verify_identity=true
ELEVENLABS_API_KEY=your-secret-key
ELEVENLABS_VOICE_ID=your-voice-id
ELEVENLABS_MODEL_ID=eleven_v4
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

The collection uses `gemini-embedding-2` at 768 dimensions for both stored documents and search
queries. If either value changes, update the `VECTOR(...)` dimension in `sql/schema.sql`, recreate or
migrate the table, and reseed every row because embeddings from different models are incompatible.

### Explicit TiDB setup and seed

The server never runs migrations or seeds a database at startup. Run these steps yourself against the
intended TiDB database:

```bash
mysql --ssl-mode=VERIFY_IDENTITY -h YOUR_HOST -P 4000 -u YOUR_USER -p YOUR_DATABASE \
  < sql/schema.sql
plasticpaths-seed-tidb
```

The seed command uses upserts keyed by `document_id`, so it is idempotent. It does make paid Gemini
embedding calls and requires `GEMINI_API_KEY`. TiDB vector search is performed with cosine distance.

## API

Create a story:

```bash
curl -X POST http://localhost:8000/api/stories \
  -H 'Content-Type: application/json' \
  -d '{
    "simulation_id": "sim-001",
    "litter_type": "plastic_bottle",
    "particle_id": "particle-001",
    "duration_hours": 24,
    "events": [
      {"elapsed_hours": 0, "type": "released"},
      {"elapsed_hours": 6, "type": "beached"}
    ],
    "final_status": "beached",
    "assumptions": ["Ocean currents only", "Wind and waves excluded"]
  }'
```

Response shape:

```json
{
  "story_id": "story-...",
  "simulation_id": "sim-001",
  "particle_id": "particle-001",
  "title": "...",
  "script": "...",
  "sources": [{"document_id": "...", "title": "...", "url": "https://..."}],
  "generation_mode": "live",
  "retrieval_mode": "tidb"
}
```

Create or reuse narration:

```bash
curl -X POST http://localhost:8000/api/stories/STORY_ID/audio
```

The JSON response includes the unchanged `script` for captions, `content_type`, and a relative
same-backend-origin `audio_url`. The frontend should show a ready state only after this request
finishes, then resolve `audio_url` against `VITE_API_BASE_URL` and pass it to an `<audio>` element.
`src/storyApi.ts` already implements both requests. Do not send arbitrary text to the audio route;
it narrates only a saved server-side story.

## Teammate handoff

- Simulation: convert the final particle history to `SimulationSummary`. Event times must be ordered,
  fall between zero and `duration_hours`, and use one of the five documented final statuses. Optional
  event `location` values are passed through; absent locations are never invented. The boundary is
  isolated in `app/adapters.py` for later contract changes.
- Frontend: call `requestOceanStory(summary)`, display `script` and `sources`, then call
  `requestStoryAudio(story_id)`. Playback timing remains a frontend concern.
- Backend operator: run the schema and seed commands explicitly, then restart the API after changing
  environment variables.

## Verification

```bash
cd backend
pytest
```

Paid APIs are mocked in tests. A live smoke test should be run only when real credentials are already
configured.

## Implementation references

- [Gemini structured output with Pydantic](https://googleapis.github.io/python-genai/#json-response-schema)
- [Gemini embeddings and supported dimensions](https://ai.google.dev/gemini-api/docs/embeddings)
- [TiDB vector search using SQL](https://docs.pingcap.com/tidb/stable/vector-search-get-started-using-sql/)
- [TiDB SQLAlchemy vector integration](https://docs.pingcap.com/tidbcloud/vector-search-integrate-with-sqlalchemy/)
- [ElevenLabs Python TTS quickstart](https://elevenlabs.io/docs/eleven-api/quickstart/)

The curated educational passages are short paraphrases verified against their stored NOAA and EPA
source URLs. Those URLs are resolved from known document IDs on the server and are never generated
by Gemini.
