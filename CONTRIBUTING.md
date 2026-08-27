# Contributing

Contributions are welcome.

For new integrations, prefer adding a self-contained plugin under `plugins/`
rather than adding service-specific code to the RackDash core.

Before a pull request:

1. Never commit API keys or `config.env`.
2. Keep plugin routes under `/api/plugin/<plugin-id>/`.
3. Test at multiple viewport sizes.
4. Test vertical touch scrolling if the page can overflow.
5. Keep browser-facing error messages free of secrets.
6. Run:

```bash
python -m py_compile app.py plugin_manager.py plugins/*.py
```
