# Test Fixtures

Drop PNG files here to test the transformation pipeline independently.

## How to test

1. Create or export a PNG from your Bamboo Slate
2. Place it in this directory
3. Run the test CLI:
   ```
   python tools/ingest.py tests/fixtures/your_note.png -o tests/fixtures/your_note.md
   ```
4. The output Markdown is written to `your_note.md` (omit `-o` to print it to stdout)

## Expected header format

The first line of your note (handwritten or otherwise) should follow this format:

```
VAULT_NAME  DOC_TYPE  [key=value ...]
```

Examples:
- `WORK TASK project=atlas`
- `PERSONAL NOTE`
- `WORK DIAGRAM type=flowchart format=mermaid`

Document types and required fields are defined in `workflow.json`.
