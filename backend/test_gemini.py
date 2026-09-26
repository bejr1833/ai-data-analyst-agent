from app.services.llm_analyst import client

MODEL = "gemini-3.6-flash"

prompt = """
You are a SQL generation engine.

A DuckDB table called main_table has this schema:

"Product" VARCHAR
"Region" VARCHAR
"Sales" DOUBLE
"Profit" DOUBLE

User question:

Which region has the highest sales?

Return ONLY one DuckDB SELECT query.
Do not use markdown.
"""

interaction = client.interactions.create(
    model=MODEL,
    input=prompt,
)

print("MODEL:", MODEL)
print()
print("GEMINI RESPONSE:")
print(interaction.output_text)