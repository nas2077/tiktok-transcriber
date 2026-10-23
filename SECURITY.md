# Security

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/nas2077/tiktok-transcriber/security/advisories/new).
Include the affected version, reproduction steps, and the relevant boundary
or data flow. Do not publish credentials, private media, or exploit details in
a public issue. Ordinary bugs belong in the issue tracker.

## Scope

Security-sensitive areas include the Python/WebView2 bridge, handling of public
URLs and captions, local paths, downloaded model files, and native dependencies.
TikTok Transcriber must never read browser account cookies or require TikTok sign-in.

Speech recognition runs locally. TikTok requests and first-use model/library
downloads use external services; the application is not fully offline during
those operations. See [privacy](docs/PRIVACY.md).

## Maintenance

The current `main` branch is maintained. Update to the newest published version
when reporting a problem. Dependency scanning and CodeQL provide automated
checks; their results are not a guarantee that software is free of vulnerabilities.
Windows executables are unsigned unless a release explicitly says otherwise.
