# LLM — Protocol Generation Scripts

**Owner:** Simon  
**Stack:** Python · Anthropic/OpenAI SDK · jsonschema

---

## Setup (to be completed by Simon — Sprint 1)

```bash
cd llm/
pip install anthropic jsonschema python-dotenv
cp ../.env.example .env   # add your API key
```

---

## Key Files (to be created by Simon)

| File                        | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `generate_protocol.py`      | Calls LLM, returns raw protocol JSON         |
| `validate_schema.py`        | Validates LLM output against schema          |
| `SPRINT1_NOTES.md`          | Findings from first LLM test runs            |
| `test_outputs/`             | Saved raw LLM responses for debugging        |

---

## Schema Reference

Protocol JSON schema lives at: `/docs/protocol_schema.json`  
JSON Schema validator lives at: `/docs/protocol_schema_validator.json`
