from pathlib import Path

path = Path("app/services/agent.py")
text = path.read_text(encoding="utf-8")

old = '''                in {"numeric", "aggregate", "analysis", "metric", ""}
'''

new = '''                in {
                    "numeric",
                    "aggregate",
                    "analysis",
                    "metric",
                    "local_analysis",
                    "",
                }
'''

if old not in text:
    raise SystemExit(
        "Could not find the visualization type allow-list in "
        "app/services/agent.py. No changes were made."
    )

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("SUCCESS: metric visualization normalization updated.")
print("Added 'local_analysis' to the single-numeric metric allow-list.")
