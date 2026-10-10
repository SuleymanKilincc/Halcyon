# Manual checks

Interactive scripts for checking things by eye: they open windows, play audio,
or wait for keyboard input. They are **not** automated tests — none of them can
fail on its own — so the test runner is configured to ignore this folder.
Automated tests are in [`tests/`](../../tests).

Run them from the repository root so imports resolve:

```bash
python -m scripts.manual.check_hardware
python -m scripts.manual.check_database
```

They were originally named `test_*.py`. They were renamed because a file called
`test_` is read, by people and by pytest alike, as a test that can fail.
`check_hardware.py` was also rewritten: it imported a function that no longer
exists in `tools.py` and called a LangChain tool as a plain function, so it
crashed on startup — unnoticed, because nothing ever ran it automatically.
