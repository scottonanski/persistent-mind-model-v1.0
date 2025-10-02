import json
import os


class PersistentStorage:
    def __init__(self, db_path):
        """
        Initialize persistent storage with a file-based database path.
        """
        self.db_path = db_path
        self.identity_file = os.path.join(db_path, "identity.json")
        os.makedirs(db_path, exist_ok=True)

    def save_identity(self, identity_data):
        """
        Save identity data to persistent storage.
        """
        try:
            with open(self.identity_file, "w") as f:
                json.dump(identity_data, f, indent=2)
        except Exception as e:
            print(f"Error saving identity data: {e}")

    def load_identity(self):
        """
        Load identity data from persistent storage.
        Returns None if no data exists or on error.
        """
        try:
            if os.path.exists(self.identity_file):
                with open(self.identity_file) as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading identity data: {e}")
        return None

    def save_event(self, event):
        """
        Save an event to persistent storage with a timestamp.
        """
        try:
            events_file = os.path.join(self.db_path, "events.jsonl")
            with open(events_file, "a") as f:
                json.dump(event, f)
                f.write("\n")
        except Exception as e:
            print(f"Error saving event: {e}")

    def load_events(self, limit=100):
        """
        Load recent events from persistent storage.
        Returns a list of events, most recent first, up to the specified limit.
        """
        try:
            events_file = os.path.join(self.db_path, "events.jsonl")
            if os.path.exists(events_file):
                events = []
                with open(events_file) as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))
                return events[-limit:] if limit else events
        except Exception as e:
            print(f"Error loading events: {e}")
        return []
