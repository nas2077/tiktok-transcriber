# Privacy and network access

TikTok Transcriber reads public TikTok video/profile metadata and downloads selected media.
It does not read browser sessions, import account cookies, request TikTok login,
or upload audio to a transcription service. Recognition runs on your computer.
Ordinary anonymous website cookies may be used within a public HTTP session;
these are unrelated to your browser or TikTok account.

## Connections

| Destination | Purpose |
|---|---|
| TikTok and its media hosts | Public discovery, covers, audio, and video downloads |
| Hugging Face | First-use downloads of pinned speech/language models |
| Python package services | Optional Whisper GPU libraries and source-development dependencies |
| Google Fonts | Inter font requested by the interface |

Downloaded models and libraries are reused. Opening the app alone does not
start a model download. TikTok Transcriber has no analytics or remote crash-reporting
endpoint. External errors retain their original diagnostic text.

## Local files

Transcripts go to `Documents\TikTok Transcripts` by default, or to the folder
you choose. Settings, the WebView cache, logs, and optional Whisper GPU libraries
use `%LOCALAPPDATA%\TikTok Transcriber`. This established storage name is retained
across the TikTok Transcriber rename. Hugging Face cache settings are respected.

Uninstall by deleting the unpacked application folder. Remove its settings/cache
folder and downloaded models separately if no longer needed. Your transcripts
remain in their output folder.

Only download or transcribe material you have permission to use. Public
availability does not grant ownership or redistribution rights.
