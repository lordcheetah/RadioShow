# RadioShow
Create Multivoice Audiobooks from Ebooks

## Development

Instructions for developing on RadioShow live here.

## Running tests ✅

Use the repository virtualenv when running tests to ensure imports and test stubs load consistently.

- Run the cross-platform helper script:

```bash
python scripts/run_tests.py [pytest args]
```

- On Windows with PowerShell you can use the helper:

```powershell
./scripts/run_tests.ps1 -Args "-k test_name"
```

- Or run pytest directly with the repo venv python (common default is `.venv_chatterbox`):

```powershell
.\.venv_chatterbox\Scripts\python.exe -m pytest tests/test_speaker_validation.py -q
```

If pytest is not installed in your venv, install it with:

```powershell
.\.venv_chatterbox\Scripts\python.exe -m pip install pytest
```

- There's also a VS Code task named `pytest: repo venv` available in the Command Palette → Run Task… that runs pytest using `${workspaceFolder}/.venv_chatterbox/Scripts/python.exe`.

If you keep different venv names, adjust the script or the task to point to your virtualenv path.
