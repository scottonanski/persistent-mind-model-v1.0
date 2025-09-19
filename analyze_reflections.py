import sqlite3
import matplotlib.pyplot as plt
import json
from datetime import datetime

DB_PATH = ".data/pmm.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # --- 1. Last 10 reflections with linked policy updates ---
    print("\n=== Last 10 Reflections with Policy Updates ===")
    cursor.execute(
        """
        SELECT id, ts, content
        FROM events
        WHERE kind='reflection'
        ORDER BY ts DESC
        LIMIT 10
    """
    )
    reflections = cursor.fetchall()

    if not reflections:
        print("No reflections found in database")
    else:
        for ref_id, ts, content in reflections:
            print(f"\nReflection ID: {ref_id}, Time: {ts}")
            if content:
                print(f"  Reflection: {content[:100]}...")
            cursor.execute(
                """
                SELECT content
                FROM events
                WHERE kind='policy_update'
                  AND json_extract(meta,'$.src_id')=?
                ORDER BY ts DESC LIMIT 1
            """,
                (ref_id,),
            )
            policy = cursor.fetchone()
            if policy and policy[0]:
                print(f"  Policy Update: {policy[0]}")

    # --- 2. Trait drift (reconstructed from trait-affecting events) ---
    print("\n=== Plotting Trait Drift Over Time ===")
    cursor.execute(
        """
        SELECT id, ts, kind, meta
        FROM events
        WHERE kind IN ('trait_update','policy_update','evolution','self_model_update')
        ORDER BY id ASC
        LIMIT 2000
        """
    )
    rows = cursor.fetchall()

    # Deterministic reconstruction (O,C,E,A,N baseline 0.5)
    times = []
    o_vals, c_vals, e_vals, a_vals, n_vals = [], [], [], [], []
    traits_state = {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}
    long_to_short = {
        "openness": "O",
        "conscientiousness": "C",
        "extraversion": "E",
        "agreeableness": "A",
        "neuroticism": "N",
        "o": "O",
        "c": "C",
        "e": "E",
        "a": "A",
        "n": "N",
    }

    def _apply_absolute(tkey: str, value) -> bool:
        try:
            v = float(value)
        except Exception:
            return False
        v = max(0.0, min(1.0, v))
        if tkey in traits_state:
            traits_state[tkey] = v
            return True
        return False

    def _apply_delta(tkey: str, delta) -> bool:
        try:
            d = float(delta)
        except Exception:
            return False
        d = max(-1.0, min(1.0, d))
        if tkey in traits_state:
            traits_state[tkey] = max(0.0, min(1.0, traits_state[tkey] + d))
            return True
        return False

    for _eid, ts, kind, meta_json in rows:
        # Parse meta
        try:
            meta = (
                json.loads(meta_json)
                if isinstance(meta_json, str)
                else (meta_json or {})
            )
        except Exception:
            meta = {}

        changed = False
        k = str(kind)
        if k == "trait_update":
            delta_field = meta.get("delta")
            trait = str(meta.get("trait", "")).strip().lower()
            if isinstance(delta_field, dict) and not trait:
                for rk, rv in (delta_field or {}).items():
                    tkey = long_to_short.get(str(rk).strip().lower())
                    if tkey:
                        changed = _apply_delta(tkey, rv) or changed
            else:
                tkey = long_to_short.get(trait)
                if tkey is not None:
                    changed = _apply_delta(tkey, delta_field) or changed
        elif k == "policy_update":
            # Only personality component changes affect traits
            if (meta.get("component") or "") == "personality":
                for ch in meta.get("changes", []) or []:
                    if not isinstance(ch, dict):
                        continue
                    trait = str(ch.get("trait", "")).strip().lower()
                    tkey = long_to_short.get(trait)
                    if tkey:
                        changed = _apply_delta(tkey, ch.get("delta", 0)) or changed
        elif k == "evolution":
            changes = meta.get("changes", {}) or {}
            if isinstance(changes, dict):
                for key, value in changes.items():
                    if isinstance(key, str) and key.startswith("traits."):
                        trait = key.split(".", 1)[1].strip().lower()
                        tkey = long_to_short.get(trait) or trait.upper()
                        if tkey in traits_state:
                            changed = _apply_absolute(tkey, value) or changed
        elif k == "self_model_update":
            tdict = meta.get("traits") or {}
            if isinstance(tdict, dict):
                # Accept either short or long keys
                for rk, rv in tdict.items():
                    key_low = str(rk).strip().lower()
                    tkey = long_to_short.get(key_low) or str(rk).strip().upper()
                    if tkey in traits_state:
                        changed = _apply_absolute(tkey, rv) or changed

        if changed:
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            times.append(dt)
            o_vals.append(traits_state["O"])
            c_vals.append(traits_state["C"])
            e_vals.append(traits_state["E"])
            a_vals.append(traits_state["A"])
            n_vals.append(traits_state["N"])

    if times:
        # Primary axis: trait drift
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(times, o_vals, label="Openness (O)")
        ax.plot(times, c_vals, label="Conscientiousness (C)")
        ax.plot(times, e_vals, label="Extraversion (E)")
        ax.plot(times, a_vals, label="Agreeableness (A)")
        ax.plot(times, n_vals, label="Neuroticism (N)")
        ax.set_xlabel("Time")
        ax.set_ylabel("Trait Value")
        ax.set_title("Trait Drift Over Time")
        ax.set_ylim(0.0, 1.0)

        # Secondary axis: IAS/GAS telemetry from autonomy_tick
        cursor.execute(
            """
            SELECT ts,
                   json_extract(meta, '$.telemetry.IAS'),
                   json_extract(meta, '$.telemetry.GAS')
            FROM events
            WHERE kind='autonomy_tick'
            ORDER BY id ASC
            LIMIT 2000
            """
        )
        trows = cursor.fetchall()
        t_times, ias_vals, gas_vals = [], [], []
        for ts2, ias_v, gas_v in trows:
            try:
                t_times.append(datetime.fromisoformat(ts2))
                ias_vals.append(float(ias_v) if ias_v is not None else None)
                gas_vals.append(float(gas_v) if gas_v is not None else None)
            except Exception:
                continue

        has_telemetry = False
        if t_times:
            ax2 = ax.twinx()
            # Filter None values per-series
            i_times = [t for t, v in zip(t_times, ias_vals) if v is not None]
            i_vals = [v for v in ias_vals if v is not None]
            g_times = [t for t, v in zip(t_times, gas_vals) if v is not None]
            g_vals = [v for v in gas_vals if v is not None]
            if i_times:
                ax2.plot(
                    i_times,
                    i_vals,
                    label="IAS",
                    color="tab:purple",
                    linestyle="--",
                    alpha=0.7,
                )
                has_telemetry = True
            if g_times:
                ax2.plot(
                    g_times,
                    g_vals,
                    label="GAS",
                    color="tab:orange",
                    linestyle="--",
                    alpha=0.7,
                )
                has_telemetry = True
            if has_telemetry:
                ax2.set_ylabel("IAS / GAS")
                ax2.set_ylim(0.0, 1.0)

        # Combine legends from both axes if telemetry is present
        if has_telemetry:
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()  # type: ignore[name-defined]
            ax.legend(h1 + h2, l1 + l2, loc="upper left")
        else:
            ax.legend(loc="upper left")

        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig("trait_drift.png")
        print("Saved trait drift plot as trait_drift.png")
    else:
        print("No trait data found")

    # --- 3. Open/closed commitments timeline ---
    print("\n=== Commitment Timeline (latest 20) ===")
    cursor.execute(
        """
        SELECT ts, kind, content
        FROM events
        WHERE kind IN ('commitment_open', 'commitment_closed')
        ORDER BY ts DESC
        LIMIT 20
    """
    )
    commitments = cursor.fetchall()

    for ts, kind, content in commitments:
        status = "Open" if kind == "commitment_open" else "Closed"
        print(f"Time: {ts}, Status: {status}, Content: {content}")

    conn.close()


if __name__ == "__main__":
    main()
