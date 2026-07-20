"""Agent-callable data tools.

Each tool is a plain function with JSON-serializable inputs/outputs so the
agent layer can expose it via tool-use. Tools fetch data; they never invent
it. Every value that had to be estimated is flagged as such.
"""
