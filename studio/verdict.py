import re


def extract_verdict(text: str) -> str:
    """Return APPROVED/REJECTED/UNKNOWN verdict from agent output."""
    match = re.search(r"VERDICT:\s*(APPROVED|REJECTED)", text, re.IGNORECASE)
    return match.group(1).upper() if match else "UNKNOWN"
