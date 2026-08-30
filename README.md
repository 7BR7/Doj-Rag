# DOJ-RAG — AI Judiciary Legal Assistant

A local, **completely free** RAG-powered legal chatbot for Indian legal documents
(Constitution, Acts, Rules, Judgments). Runs entirely on your machine — no paid
APIs, no paid vector DB, no cloud service required.

Your Constitution of India PDF is already included at
`backend/data/legal_documents/constitution.pdf` and used as the reference for
this build. Add more PDFs to the same folder any time.

---

## 1. How retrieval actually works (read this first)

The single most important requirement — **"What is Article 21?" must return the
real Article 21 text, never a table-of-contents line, a page number, or the
wrong Article** — is solved like this:

1. **Query understanding** (`app/utils/legal_query_parser.py`) — regex detects
   "Article 21" instantly, no LLM call needed.
2. **Exact metadata lookup** (`app/rag/retriever.py`) — MongoDB is queried for
   a chunk with `article: "21"` and `source_type: "actual_law"`. This always
   wins over BM25/FAISS.
3. **Parsing that tells TOC apart from real law** (`app/rag/constitution_parser.py`) —
   verified against your actual PDF: a TOC entry is `21.` and a title on
   separate lines with no dash; the real Article is
   `21. Protection of life and personal liberty.—No person shall be…` — the
   em-dash (`—`) joining title to body is the reliable signal. TOC pages are
   also independently detected and excluded (`app/rag/document_loader.py`).
4. If no exact match exists (e.g. "Article 212"), **RapidFuzz**
   (`app/utils/typo_handler.py`) looks for close valid numbers and either
   suggests one, asks you to clarify between a few, or says clearly that
   nothing was found — it never guesses silently.
5. For general questions ("What are fundamental rights?"), **BM25 + FAISS**
   hybrid retrieval (reciprocal rank fusion) is used instead.

This was tested against your uploaded PDF during development: Article 21,
Article 21A, and Article 19 all parse to their correct titles/bodies/pages,
distinct from their TOC entries. Two real bugs were caught and fixed this way:
Schedule paragraphs reusing Article numbers (e.g. paragraph "21" inside the
Fifth Schedule) were overriding the real Article 21 until number-reuse was
handled; and a per-Part running header, `(Part III.—Fundamental Rights)`,
was leaking into chunk text until `text_cleaner.py` learned to recognize
repeated section headers (which only repeat within one Part's page range,
not across the whole 403-page document) in addition to document-wide
repeated lines. `act_parser.py` and `judgment_parser.py` were verified
against representative synthetic Bare-Act and judgment text (chapter/section
extraction and case-name/court/judges/date extraction both correct).

**Not yet run end-to-end**: this sandbox has no network access, so I
couldn't `pip install`/`npm install` the actual dependencies or start
MongoDB/Ollama here. Everything above was validated by exercising each
module directly with real and representative text. Once you install
dependencies locally, run `python scripts/test_retrieval.py` to confirm the
full pipeline (embeddings, FAISS, BM25, MongoDB) end to end — if anything
doesn't match this write-up, send me the output.

---

## 2. Project structure

```text
doj-rag/
├── frontend/                  React + Vite + Tailwind chat UI
│   └── src/
│       ├── components/        Sidebar, ChatWindow, MessageBubble, InputBar, SourcePanel, LanguageSelector
│       ├── hooks/useSpeech.js Browser TTS + microphone recording
│       ├── services/api.js    Backend API client
│       └── App.jsx
│
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app + CORS + error handlers
│   │   ├── config.py               All settings, from .env
│   │   ├── database/mongodb.py     Mongo connection + collections + indexes
│   │   ├── models/schemas.py       Pydantic request/response models
│   │   ├── routes/                 chat.py, voice.py, conversations.py
│   │   ├── rag/
│   │   │   ├── document_loader.py      PDF → pages, doc-type detection, TOC-page detection
│   │   │   ├── parser_router.py        Routes to the right parser
│   │   │   ├── constitution_parser.py  Articles/Parts/Chapters
│   │   │   ├── act_parser.py           Sections/Chapters
│   │   │   ├── judgment_parser.py      Case name/court/judges/date/paragraphs
│   │   │   ├── chunker.py              Structure-aware parent/child chunking
│   │   │   ├── embeddings.py           SentenceTransformers wrapper
│   │   │   ├── vectorstore.py          FAISS index build/search
│   │   │   ├── bm25_search.py          BM25 index build/search
│   │   │   └── retriever.py            Exact → fuzzy → hybrid pipeline
│   │   ├── services/
│   │   │   ├── llm.py                  Ollama client + grounded prompting
│   │   │   ├── speech_to_text.py       Faster-Whisper
│   │   │   ├── language.py             Language detection/normalization
│   │   │   └── chat_service.py         Full chat-turn orchestration
│   │   ├── utils/
│   │   │   ├── legal_query_parser.py   Regex intent detection
│   │   │   └── typo_handler.py         RapidFuzz suggestion/clarification
│   │   └── prompts/system_prompt.py
│   ├── scripts/
│   │   ├── process_documents.py    Run this to ingest your PDFs
│   │   └── test_retrieval.py       Runs the required test cases
│   ├── data/legal_documents/       Put your ~25 PDFs here
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## 3. Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB (local install or Docker)
- Ollama (local LLM runner)

---

## 4. Installation

### 4.1 Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env if you want to change the Ollama model, ports, etc.
```

### 4.2 Frontend

```bash
cd frontend
npm install
```

### 4.3 MongoDB

Option A — local install: start it with `mongod` (default URI
`mongodb://localhost:27017` already matches `.env.example`).

Option B — Docker Compose (included at the project root):
```bash
docker compose up -d
```

Option C — plain Docker:
```bash
docker run -d -p 27017:27017 --name doj-rag-mongo mongo:7
```

### 4.4 Ollama

```bash
# Install: https://ollama.com/download
ollama serve                    # starts the local Ollama server
ollama pull llama3.2:3b         # lightweight, runs fine on a normal laptop
```

If your laptop has less RAM, try an even smaller model, e.g. `ollama pull qwen2.5:1.5b`,
and set `OLLAMA_MODEL` in `.env` to match.

---

## 5. Adding and processing legal PDFs

```bash
cd backend
# constitution.pdf is already here. Add up to ~25 more PDFs (Acts, Rules, Judgments):
cp /path/to/your/pdfs/*.pdf data/legal_documents/

source venv/bin/activate
python scripts/process_documents.py
```

This parses every PDF with the correct structure-aware parser, builds
structure-aware chunks, stores metadata in MongoDB, generates embeddings, and
builds the FAISS + BM25 indexes in `backend/storage/`. Re-run it any time you
add new PDFs — it's idempotent (upserts by `chunk_id`/`document_id`).

---

## 6. Running the application

**Terminal 1 — backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** and click **Register** to create your account
(this is a real login system now - the chat UI is unreachable until you sign
in, and each account's conversation history is private to it).

Check overall health any time at **http://localhost:8000/api/health** (reports
MongoDB, Ollama, and index status).

---

## 7. Testing

```bash
cd backend
source venv/bin/activate
python scripts/test_retrieval.py
```

Covers:
- **Article 21** → must return the real legal text, not TOC/page-number noise
- **Article 21A** → must return the correct provision
- **Invalid Article 396** → must trigger clarification (Article 396 doesn't exist - the Constitution has 395 Articles - so it should suggest the nearest real ones), never a hallucinated answer
- **General question** ("What are fundamental rights?") → hybrid BM25+FAISS retrieval

Manual checks:
- **Voice input** — click the mic in the UI, speak, confirm the transcription appears and is editable.
- **Multilingual** — switch the language selector to any of the 12 supported languages and ask "What is Article 21?" - the answer text itself should come back in that language (not just labeled as it), since it's translated via the local LLM and cached. Also try a casual message like "Tamil theriyuma?" (do you know Tamil?) - it should get an instant scripted reply, not a rambling RAG answer.
- **Accounts** — register a new account, send a few messages, log out, log back in, and confirm the conversation history is still there. Then register a second account and confirm it does NOT see the first account's conversations.
- **Chat history** — refresh the page, reopen a past conversation from the sidebar, confirm messages and sources persist.
- **Editing a message** — hover a message you sent, click the edit (✎) icon, change the text, resend, and confirm everything after the original message is replaced rather than duplicated.

---

## 8. API reference

| Method | Path | Purpose | Auth required |
|---|---|---|---|
| POST | `/api/auth/register` | Create an account | No |
| POST | `/api/auth/login` | Log in, get a session token | No |
| GET | `/api/auth/me` | Get the logged-in user's profile | Yes |
| POST | `/api/chat` | Send a message, get an answer + sources | Yes |
| POST | `/api/transcribe` | Upload audio, get transcribed text | Yes |
| GET | `/api/conversations` | List the logged-in user's conversations | Yes |
| POST | `/api/conversations` | Create a new empty conversation | Yes |
| GET | `/api/conversations/{id}` | Get full message history | Yes (must own it) |
| DELETE | `/api/conversations/{id}` | Delete a conversation | Yes (must own it) |
| DELETE | `/api/conversations/{id}/messages` | Clear messages, keep the conversation | Yes (must own it) |
| PUT | `/api/conversations/{id}/truncate?keep_count=N` | Drop messages after position N (used by message editing) | Yes (must own it) |
| POST | `/api/feedback` | Thumbs up/down on a message | Yes |
| GET/PUT | `/api/settings/me` | Read/write language & voice preferences | Yes |
| GET | `/api/health` | MongoDB / Ollama / index status | No |

Authenticated routes expect `Authorization: Bearer <token>`, where `<token>`
is the `access_token` returned by `/api/auth/register` or `/api/auth/login`.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `503` on `/api/chat`, "Could not connect to MongoDB" | Start MongoDB (`mongod` or the Docker command above) |
| "Could not reach Ollama" | Run `ollama serve` in a terminal and keep it open |
| "Is the model pulled?" | `ollama pull <model>` matching `OLLAMA_MODEL` in `.env` |
| "FAISS index not found" | Run `python scripts/process_documents.py` |
| Mic button does nothing | Browser blocked microphone permission — check the address bar's permission icon |
| No sound on Play | Some browsers require a user gesture before `speechSynthesis` works — click Play again, or check system volume/voice packs for the selected language |

### If responses still feel slow

Check these in order - each one matters:

1. **What kind of question is it?** "What is Article 21?" (an exact
   Article/Section/Rule lookup) should be near-instant in English, and
   fast in any language once that Article has been asked once (or
   pre-warmed - see below). Open-ended questions like "What are fundamental
   rights?" always call the LLM and will be the slowest category no matter
   what - that's inherent to generating a synthesized answer, not a bug.
2. **Is this the FIRST time this Article has been asked in this language?**
   The first request pays a one-time LLM translation cost; every request
   after that is served from the MongoDB cache. Run
   `python scripts/pretranslate.py --language <name>` once, offline, for
   any language you expect real users to pick, so they never hit that cost.
3. **Is your Ollama model too large for your hardware?** This matters more
   than anything else here. Try a smaller model for chat
   (`OLLAMA_MODEL`) and/or translation (`OLLAMA_TRANSLATE_MODEL`) in
   `.env`, e.g. `ollama pull qwen2.5:1.5b`.
4. **Is the model being reloaded every message?** Confirm `ollama serve`
   has been running continuously and `OLLAMA_KEEP_ALIVE` (default `30m`)
   hasn't expired between messages - reloading a multi-GB model from disk
   can itself take a minute or more.

---

## 10. Update log

### Latest revision — real streaming, cancellable requests, copy buttons

**The architecture changed, not just the tuning.** The actual bug behind
the timeout error some users hit (`ReadTimeoutError` after 120s, resulting
in a 500) was structural: `/api/chat` waited for the ENTIRE answer to be
generated before sending anything back. On a general question with slower
hardware, that can genuinely take longer than any fixed timeout - so the
real fix is to stop waiting for the whole thing.

`/api/chat` now streams the answer as newline-delimited JSON events
(`app/services/chat_service.stream_chat_message`), forwarded to the browser
token-by-token as Ollama generates them
(`app/services/llm.stream_ollama_chat`, using `httpx`'s async streaming).
Practically, this means:
- **The answer appears within seconds and builds up live**, instead of the
  UI sitting blank for however long full generation takes. Exact-match
  Article/Section/Rule lookups are unaffected (still instant, no LLM call).
- **Editing mid-response now genuinely stops generation**, not just the UI.
  Clicking edit (✎) on any message aborts the fetch; because the backend
  uses `httpx`'s real async context-managed stream, closing that connection
  propagates all the way to closing the connection to Ollama - so the model
  actually stops computing tokens nobody will see, instead of finishing in
  the background and wasting time/compute. This was tested directly: a
  simulated slow stream was cancelled after 1 of 5 tokens, and no partial
  answer was saved to the conversation.
- **A translating phase, not a second silent wait.** For non-English hybrid
  (general-question) answers, the model composes the answer in English
  first (streamed live), then a short second call - using the small,
  dedicated translation model - converts it, shown as a brief "Translating
  into {language}…" indicator rather than more blank waiting.
- **`requirements.txt` gained `httpx`** for the async streaming client -
  re-run `pip install -r requirements.txt`.

**Copy buttons.** Every message (yours and the assistant's) now has a copy
icon; user messages show it alongside the existing edit (✎) button on hover.

**Stronger language enforcement.** Hybrid/general answers now carry an
explicit "(Please answer in {language})" reminder placed right next to the
question itself, not just buried in the system prompt - models tend to
follow instructions positioned closer to the actual query more reliably.

### Previous revision — native-script languages and faster translation

**Native scripts, not transliteration.** The previous revision's language
templates were written in Romanized text (e.g. "Namaste! Main DOJ-RAG
hoon...") - readable but unprofessional for a legal assistant. Every
scripted message (greetings, clarification, not-found, etc.) in
`app/i18n/messages.py` is now written in its actual native script
(Devanagari, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati,
Gurmukhi, Odia, and Urdu in its own Arabic-derived script), in a plain,
everyday register rather than stiff legal phrasing - this is meant for
ordinary people, not lawyers.

**Translation is now much faster, with a real fix, not just a tweak.**
The previous revision made English exact-match answers instant but
re-introduced slowness for every OTHER language, because each first-time
translation still called the full LLM live, in front of the waiting user.
Two real fixes:
1. **A separate, smaller, dedicated translation model** is now configurable
   (`OLLAMA_TRANSLATE_MODEL` in `.env`) - translation is a simpler task than
   open-ended legal reasoning, so a small model translates just as
   accurately but several times faster. Leave it blank to keep using your
   main model, or set it to something small like `qwen2.5:1.5b` for the
   biggest speed win.
2. **`scripts/pretranslate.py`** - a new offline warming script. Run it
   once per language you expect people to actually use
   (`python scripts/pretranslate.py --language Hindi`, or `--all` for
   every supported language) and every Article/Section/Rule in that
   language is pre-cached in MongoDB before anyone ever asks - so the
   *first* real user request is just as instant as English, not the one
   paying the translation cost live. This is the real answer to "the user
   won't wait": shift the one-time cost to you, running it offline, instead
   of to them, waiting in the chat.

Already-cached translations from before this update aren't invalidated -
they'll just gradually be replaced by the (usually faster) translate-model
path as they're re-requested, or immediately if you re-run `pretranslate.py`.

### Previous revision — languages, translation, and accounts

**Full Indian-language support with real translation** — the language
selector now covers English, Hindi, Tamil, Telugu, Kannada, Malayalam,
Bengali, Marathi, Gujarati, Punjabi, Odia, and Urdu (`app/i18n/messages.py`
is the single source of truth - add more languages there). Selecting a
language now actually changes the answer's language, not just its label:
a new `app/services/translator.py` uses the local Ollama LLM to translate
the fast-path exact-match answers (which come from the English source PDF)
into whichever language is selected, and caches every translation in
MongoDB so the same Article is never re-translated on a later request. All
short template messages (clarification, not-found, greetings, "who are
you", etc.) are scripted natively in every supported language rather than
machine-translated, since correctness matters more than flexibility for
short, fixed phrasing.

**Chit-chat detection hardened** — extended to the new languages and their
colloquial phrasing ("Kannada gottha?", "do you know Tamil"), while fixing
a false-positive I found while testing: a genuine in-context request like
"explain this article in Hindi" was at risk of being caught as chit-chat
instead of a real translation request - the pattern is now anchored to the
whole message so it only fires on a bare capability question.

**Register / login, with per-user history** — accounts are created via
`POST /api/auth/register` and authenticated via `POST /api/auth/login`
(bcrypt-hashed passwords, JWT sessions). Every chat and conversation route
now requires a valid session and is scoped to that account - conversations
are private per user, and a tampered request carrying another user's
`conversation_id` is rejected rather than allowed to read or append to it
(this was tested directly - see the "Testing" section below). The frontend
gained `/login` and `/register` pages, a logout button in the sidebar, and
route protection so the chat UI is unreachable while logged out.

**New required setting**: `SECRET_KEY` in `.env` signs login sessions.
The example value is fine for local use; generate a real one for anything
beyond that (command is in `.env.example`).

### Previous revision — speed, chit-chat, editing, redesign

**Speed** — "What is Article 21?" and similar exact Article/Section/Rule
lookups now skip the LLM entirely and return the verified legal text
directly (near-instant instead of 1-3 minutes). Clarification and
not-found messages are also template-based now (no LLM round-trip). Only
genuinely open-ended questions ("What are fundamental rights?") still call
the LLM, with a capped output length (`OLLAMA_NUM_PREDICT`), a smaller
context window (`OLLAMA_NUM_CTX`), and `keep_alive` so the model stays
resident in memory instead of reloading from disk on every message — all
configurable in `.env`. If it's still slow, the single biggest lever left is
the model itself: swap `OLLAMA_MODEL` for something smaller,
e.g. `ollama pull qwen2.5:1.5b`.

**Chit-chat / meta questions** — messages like "Hindi aati hai?" (do you
know Hindi?), greetings, thanks, or "who are you?" are now detected
(`app/utils/chitchat_handler.py`) and answered directly, instead of being
sent through legal retrieval where a stray keyword match could produce an
irrelevant, rambling answer.

**Edit and resend** — hover a message you sent to reveal an edit (✎)
button; editing and resending truncates everything after that point (via
the new `PUT /api/conversations/{id}/truncate` endpoint) so the
conversation continues from the edited message instead of branching.

**Real "new page" navigation** — the app uses `react-router-dom`.
`/` is a genuinely blank conversation; picking or starting a conversation
navigates to `/c/:id`, so the browser back/forward buttons and page
refresh all work as expected.

**Redesign** — maroon/charcoal/gold "official portal" visual identity
(replacing the earlier navy/parchment/brass look), document-card style
message bubbles instead of rounded chat-app bubbles, and a seal-style
brand mark in the sidebar/header.

**Re-run `npm install`** if you're updating from before this revision —
`react-router-dom` was added as a frontend dependency.

---

## 11. Notes on scaling this further

- **Reranking**: `app/rag/retriever.py` is structured so a cross-encoder
  reranker can be dropped into `hybrid_retrieve()` before returning the final
  top-k, if you find hybrid ranking alone isn't precise enough for your PDFs.
- **More languages**: add entries to `SUPPORTED_LANGUAGES` in `app/config.py`
  and to `VOICE_LOCALES` in `frontend/src/hooks/useSpeech.js`.
- **More document types**: add a new parser under `app/rag/`, normalize its
  output in `parser_router.py`, and it plugs straight into chunking/indexing.
