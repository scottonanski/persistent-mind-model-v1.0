from pmm.runtime.canaries import run_canaries


def test_run_canaries_scoring_is_deterministic():
    # Fake chat that ensures first two pass, third fails
    answers = {
        "Compute 12 + 7. Respond with just the number.": "19",
        "What is pi to 3 decimal places? Respond with just the number.": "3.142",
        "Write today's date in ISO format (YYYY-MM-DD). Use YYYY-09-13 if you don't know.": "not-a-date",
    }

    def chat(prompt: str) -> str:
        return answers[prompt]

    results = run_canaries(chat)

    by_name = {r["name"]: r for r in results}
    assert by_name["math_add_12_7"]["passed"] is True
    assert by_name["factual_pi_3dp"]["passed"] is True
    assert by_name["format_date_iso"]["passed"] is False
