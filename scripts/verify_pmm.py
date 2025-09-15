#!/usr/bin/env python3
import json
import sys
import re
import subprocess
import pathlib

LOG_DIR = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".logs")
DB_PATH = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".data/pmm.db")
LOG_DIR.mkdir(parents=True, exist_ok=True)
CHAT_LOG = LOG_DIR / "verify_chat.log"
EVENTS_JSON = LOG_DIR / "events.json"

dialogue = """--@metrics on
Hi!
Nice to meet you.
What's your name?
I'll call you Logos.
Cool. What are you working on right now?
Give me your top two priorities.
Okay — pick one and outline 3 concrete next steps.
Great. What's the smallest step you can do in 2 minutes?
Please reflect briefly on your last answer.
Based on that reflection, propose a tiny policy/curriculum tweak.
Confirm one open commitment in one sentence.
What evidence would close that commitment?
Summarize your current commitments in one bullet list.
Okay, switch to the other commitment and outline 2 steps.
If you had to improve your helpfulness by 1%, what would you try?
Note one thing to avoid repeating.
What's one trait you want to nudge slightly this session?
Explain why (one line).
Recap: name, 2 commitments, and the next step you're taking now.
Thanks.
"""

print("[*] Running chat…")
proc = subprocess.run(
    [sys.executable, "-m", "pmm.cli.chat"],
    input=dialogue.encode(),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    check=True,
)
CHAT_LOG.write_bytes(proc.stdout)

print("[*] Exporting events…")
proc2 = subprocess.run(
    [
        sys.executable,
        "-m",
        "pmm.api.probe",
        "snapshot",
        "--db",
        str(DB_PATH),
        "--limit",
        "2000",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    check=True,
)
EVENTS_JSON.write_bytes(proc2.stdout)
events = json.loads(proc2.stdout)


def count(kind):
    return sum(1 for e in events["events"] if e.get("kind") == kind)


assert count("identity_propose") >= 1, "no identity_propose"
assert count("identity_adopt") >= 1, "no identity_adopt"
assert count("trait_update") >= 1, "no trait_update"
assert count("curriculum_update") >= 1, "no curriculum_update"
assert count("policy_update") >= 1, "no policy_update"

cu_ids = [e["id"] for e in events["events"] if e.get("kind") == "curriculum_update"]
pu_srcs = [
    e.get("meta", {}).get("src_id")
    for e in events["events"]
    if e.get("kind") == "policy_update"
]
assert all(cid in pu_srcs for cid in cu_ids), "CU without matching PU.meta.src_id"

txt = CHAT_LOG.read_text()
assert re.search(
    r"^You are .+\. Speak in first person\.", txt, re.M
), "identity header missing"
assert "Open commitments:" in txt, "commitments header missing"

print("[*] OK — verification passed. Logs:", LOG_DIR)
