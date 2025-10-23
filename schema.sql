CREATE TABLE events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        meta TEXT NOT NULL
                    , prev_hash TEXT, hash TEXT);
CREATE TABLE sqlite_sequence(name,seq);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_kind ON events(kind);
CREATE INDEX idx_events_kind_id ON events(kind, id);
CREATE INDEX idx_events_ts_id ON events(ts, id);
CREATE INDEX idx_metrics_lookup
                       ON events(id DESC) WHERE kind='metrics_update';
CREATE TABLE event_embeddings (
                            eid INTEGER PRIMARY KEY,
                            digest TEXT,
                            embedding BLOB,
                            summary TEXT,
                            keywords TEXT,
                            created_at INTEGER
                        );
