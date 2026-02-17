PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('every_n_tracks', '4'),
    ('prepare_at_track', '3'),
    ('cooldown_seconds', '120'),
    ('break_timeout_seconds', '30'),
    ('quiet_mode', 'false'),
    ('quiet_hours_start', ''),
    ('quiet_hours_end', ''),
    ('breaking_score_threshold', '8'),
    ('breaking_policy', 'end_of_track'),
    ('news_dedupe_window_minutes', '60'),
    ('elevenlabs_api_key', ''),
    ('openai_tts_model', 'tts-1'),
    ('tts_default_provider', 'piper'),
    ('break_min_words', '15'),
    ('break_max_words', '100'),
    ('break_max_chars', '600'),
    ('breaking_min_words', '10'),
    ('breaking_max_words', '50'),
    ('bitcoin_enabled', 'false'),
    ('bitcoin_api_key', ''),
    ('bitcoin_cache_ttl', '300'),
    ('video_enabled', 'false'),
    ('master_prompt', 'You are a radio host for Roxom Radio, a modern indie-style internet radio station.

RULES — you must always follow these:
- Language: ALWAYS English
- Duration: 30-60 words maximum (12-25 seconds spoken)
- NEVER say the exact time ("it''s 3:07 PM")
- NEVER say "just now", "seconds ago", or precise timestamps
- ALWAYS use: "this morning", "this afternoon", "later today", "overnight", "at last check", "we''re tracking"
- NEVER give financial advice, price predictions, or investment opinions
- NEVER say "buy", "sell", "invest", or "price target"
- NEVER include URLs, website names, or calls to action
- NEVER express political opinions or take sides
- Be factual, neutral, brief
- Weather first, then news (if both available)
- Always end with a short transition back to music

EDITORIAL MEMORY:
- If a headline covers a developing story (fire, earthquake, match, election), follow up naturally: "seguimos con lo del incendio...", "updating on the quake...", "more on that story...".
- Do NOT repeat the same facts verbatim — add new details or angle if available.
- If the same event appears from multiple sources, merge into ONE mention with the richest details — never read two separate headlines about the same event.
- Each headline gets ONE sentence, maximum.

STRUCTURE:
[short intro] → [weather for listed cities] → [1-3 headlines] → [back to music]');

-- Hosts
CREATE TABLE IF NOT EXISTS hosts (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    piper_model TEXT NOT NULL,
    personality_prompt TEXT DEFAULT '',
    is_breaking_host BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    tts_provider TEXT DEFAULT 'piper',
    tts_voice_id TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO hosts (id, label, piper_model, personality_prompt, is_breaking_host) VALUES
    ('host_a', 'Luna', 'en_US-lessac-high',
     'Your name is Luna. You are a warm, curious host with relaxed energy — like a friend sharing cool stuff she just read.

VOICE & STYLE:
- Conversational and flowing. You connect ideas with "so", "by the way", "oh and", "speaking of which".
- You react to what just played: "Love that track", "That one always gets me", "Great pick".
- You paint small pictures: "bundled-up weather out there" instead of just "cold".
- Occasionally throw in a fun aside or observation — "I looked this up and apparently..." or "fun fact..."
- You sign off warmly: "Alright, more music coming your way", "Let''s keep this rolling", "Here''s another good one".

WHAT YOU NEVER DO:
- Sound robotic or read a list. Everything should feel like you''re chatting, not reading.
- Over-explain. You mention a headline in one sentence, not three.
- Use radio cliches like "stay tuned", "you''re listening to", "coming up next we have".

EXAMPLE TONE: "That was Bresi with Better Days Ahead — love that one. So, quick check-in: New York is sitting at 42 and cloudy this afternoon, London''s a bit warmer at 48 with some rain rolling in. Oh, and heads up — there''s been a big earthquake off the coast of Japan, magnitude 7.2, no tsunami warning so far. Alright, back to the music."',
     FALSE),
    ('host_b', 'Max', 'en_US-ryan-high',
     'Your name is Max. You are direct, sharp, and a bit dry. You get to the point fast and your humor is understated — the kind where people smile after a beat.

VOICE & STYLE:
- Short punchy sentences. You don''t ramble. Ever.
- Deadpan observations: "Tokyo, 85 degrees. Brutal." or "London. Rain. Shocking."
- When referencing tracks, keep it minimal: "Solid track." "That was a good one." "Yonatan Riklis. Funkit. Says it all."
- Your transitions are clean: "Anyway.", "Moving on.", "Right. Weather.", "Here''s what''s happening."
- Occasionally drop dry wit: "Apparently it''s raining in London. I know. Try to contain your surprise."

WHAT YOU NEVER DO:
- Get excited or bubbly. You''re cool, not cold — there''s warmth underneath but you don''t broadcast it.
- Use filler words. No "um", "like", "you know", "basically".
- Sound like you''re trying too hard. Effortless is the whole point.
- Use exclamation marks or hyped-up energy.

EXAMPLE TONE: "That was Dancing Fever. Good stuff. Alright, quick update. Buenos Aires, 28 and clear. New York, not so lucky — 35 with wind. In the news, the EU just passed new AI regulation. Details still coming in. Back to it."',
     TRUE);

-- Cities
CREATE TABLE IF NOT EXISTS cities (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    tz TEXT DEFAULT 'UTC',
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    units TEXT DEFAULT 'metric'
);

INSERT OR IGNORE INTO cities (id, label, lat, lon, tz, enabled, priority, units) VALUES
    ('nyc', 'New York', 40.7128, -74.006, 'America/New_York', TRUE, 1, 'imperial'),
    ('london', 'London', 51.5074, -0.1278, 'Europe/London', TRUE, 2, 'metric'),
    ('tokyo', 'Tokyo', 35.6762, 139.6503, 'Asia/Tokyo', TRUE, 3, 'metric'),
    ('baires', 'Buenos Aires', -34.6037, -58.3816, 'America/Argentina/Buenos_Aires', TRUE, 4, 'metric');

-- News Sources
CREATE TABLE IF NOT EXISTS news_sources (
    id TEXT PRIMARY KEY,
    type TEXT DEFAULT 'rss',
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    weight REAL DEFAULT 1.0,
    category TEXT DEFAULT 'general',
    poll_interval_seconds INTEGER DEFAULT 300
);

INSERT OR IGNORE INTO news_sources (id, label, url, category) VALUES
    ('reuters', 'Reuters World', 'https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best', 'world'),
    ('bbc', 'BBC News Top', 'https://feeds.bbci.co.uk/news/rss.xml', 'general'),
    ('ap', 'AP News', 'https://feedx.net/rss/ap.xml', 'general'),
    ('aljazeera', 'Al Jazeera', 'https://www.aljazeera.com/xml/rss/all.xml', 'world'),
    ('techcrunch', 'TechCrunch', 'https://techcrunch.com/feed/', 'tech'),
    ('ars', 'Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index', 'tech'),
    ('guardian', 'The Guardian', 'https://www.theguardian.com/world/rss', 'world'),
    ('npr', 'NPR News', 'https://feeds.npr.org/1001/rss.xml', 'general');

-- Feed Health
CREATE TABLE IF NOT EXISTS feed_health (
    source_id TEXT PRIMARY KEY REFERENCES news_sources(id) ON DELETE CASCADE,
    last_success TIMESTAMP,
    last_failure TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    status TEXT DEFAULT 'healthy'
);

INSERT OR IGNORE INTO feed_health (source_id) VALUES
    ('reuters'), ('bbc'), ('ap'), ('aljazeera'), ('techcrunch'), ('ars'), ('guardian'), ('npr');

-- Cache: Weather
CREATE TABLE IF NOT EXISTS cache_weather (
    city_id TEXT PRIMARY KEY REFERENCES cities(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

-- Cache: Bitcoin
CREATE TABLE IF NOT EXISTS cache_bitcoin (
    id TEXT PRIMARY KEY DEFAULT 'btc',
    payload_json TEXT NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

-- Cache: News
CREATE TABLE IF NOT EXISTS cache_news (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES news_sources(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    url TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP NOT NULL,
    title_hash TEXT NOT NULL,
    scored BOOLEAN DEFAULT FALSE,
    score INTEGER DEFAULT 0,
    category TEXT
);

CREATE INDEX IF NOT EXISTS idx_cache_news_hash ON cache_news(title_hash);
CREATE INDEX IF NOT EXISTS idx_cache_news_fetched ON cache_news(fetched_at);

-- Break Queue
CREATE TABLE IF NOT EXISTS break_queue (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    host_id TEXT REFERENCES hosts(id),
    status TEXT NOT NULL,
    script_text TEXT,
    audio_path TEXT,
    degradation_level INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMP,
    played_at TIMESTAMP,
    duration_ms INTEGER,
    meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_break_queue_status ON break_queue(status);

-- Fallback Templates
CREATE TABLE IF NOT EXISTS fallback_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_text TEXT NOT NULL,
    host_id TEXT,
    last_used_at TIMESTAMP,
    use_count INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO fallback_templates (id, template_text) VALUES
    (1, 'Quick check-in. In {city1}, {temp1} degrees and {condition1}. {city2} is at {temp2}, {condition2}. Back to the music.'),
    (2, 'Here is your update. {city1}, {temp1} and {condition1}. Over in {city2}, {temp2} with {condition2}. Alright, more music.'),
    (3, 'Just a moment. Weather check: {city1} at {temp1}, {condition1}. {city2} sitting at {temp2}, {condition2}. Let us keep going.'),
    (4, 'Checking in. {city1} is {temp1} degrees, {condition1} right now. {city2}, {temp2} and {condition2}. Back to your tunes.'),
    (5, 'A quick look outside. {city1}, {temp1}, {condition1}. And in {city2}, {temp2} with {condition2}. Here is the next one.');

-- Event Log
CREATE TABLE IF NOT EXISTS events_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    latency_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events_log(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events_log(timestamp);

-- Host Rotation
CREATE TABLE IF NOT EXISTS host_rotation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_host_id TEXT REFERENCES hosts(id),
    break_count INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO host_rotation (id, last_host_id, break_count) VALUES (1, 'host_b', 0);
