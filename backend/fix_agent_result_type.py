from pathlib import Path

path = Path("app/services/agent.py")
text = path.read_text(encoding="utf-8")

old = '''        result.setdefault("type", "analysis")
'''
new = '''        # Normalize missing/None result types.
        # setdefault() does not replace an existing None value.
        if not result.get("type"):
            result["type"] = "analysis"
'''

if old not in text:
    raise SystemExit(
        "Could not find the expected result type line in app/services/agent.py. "
        "No changes were made."
    )

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("SUCCESS: app/services/agent.py updated.")
print('Changed result.setdefault("type", "analysis")')
print("to explicit None/empty-value normalization.")
