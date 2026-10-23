# Contributing

TikTok Transcriber is a Windows desktop application. Development uses Python 3.12,
pywebview/WebView2, and plain HTML, CSS, and JavaScript.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File dev\setup.ps1 -Quiet
dev\run.bat
```

Use `dev/.venv/Scripts/python.exe`. Keep application dependencies in
`dev/requirements.txt`; tested versions are recorded in `dev/constraints.txt`.

## Changes

Keep changes focused. Explain the problem, the resulting behavior, and how it
was checked. Comments should explain constraints or non-obvious decisions.
Code, filenames, comments, and project documentation use English. Translation
catalog values and multilingual test fixtures retain their own languages.

The Nas palette, spacing, tactile controls, and pixel artwork are shared design
rules. Use semantic CSS tokens instead of adding unrelated colors or effects.

Interface strings belong in every catalog under `src/locales`, with matching
keys and placeholders. The interface language is independent of the spoken
language. README content lives in `docs/readme-texts.json`; regenerate it with
`python dev/build_docs.py`.

## Checks

```powershell
dev\.venv\Scripts\python.exe dev\core_check.py
dev\.venv\Scripts\python.exe dev\access_check.py
dev\.venv\Scripts\python.exe dev\readability_check.py
dev\.venv\Scripts\python.exe dev\natural_contract_check.py
dev\.venv\Scripts\python.exe dev\model_matrix_check.py
dev\.venv\Scripts\python.exe dev\repository_check.py
```

These checks use temporary outputs and simulated media or engines. Desktop
checks require a Windows desktop session: `ui_check.py`, `controls_check.py`,
`localization_check.py`, `design_check.py`, `navigation_check.py`, and
`access_ui_check.py`. Report live TikTok/model tests separately from offline
regressions. See [validation](docs/VALIDATION.md).

## Public access

TikTok Transcriber works with public content. Do not add account login, imported cookies,
browser-session reads, or authentication setup controls. Profile embeds are
discovery inputs, not complete account feeds. Preserve pagination, photo-post
audio, canonical links, and clear errors for unavailable content.

## Builds

Changing source does not update an executable. Build and verify the Windows
package before attaching it to a release. Do not commit environments, model
weights, generated runtime files, downloaded media, or release binaries.
See [release preparation](docs/RELEASING.md).
