# Third-party notices

The MIT license in `LICENSE` covers original TikTok Transcriber code and Nas artwork.
It does not replace the licenses of dependencies, model weights, or system
components. Supplied license texts are retained under `src/licenses` and
included in Windows packages.

## Speech recognition

| Component | License | Upstream |
|---|---|---|
| Qwen3-ASR 1.7B weights | Apache-2.0 | [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) |
| SpeechBrain VoxLingua107 ECAPA | Apache-2.0 | [Model card](https://huggingface.co/speechbrain/lang-id-voxlingua107-ecapa) |
| transcribe.cpp and ggml | MIT | [transcribe.cpp](https://github.com/handy-computer/transcribe.cpp) |
| Silero VAD | MIT | [Silero](https://github.com/snakers4/silero-vad) |
| faster-whisper / CTranslate2 | MIT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| Whisper weights | MIT | [Whisper](https://github.com/openai/whisper) |

Weights download from their upstream hosts and are not committed or bundled.
Revisions and conversion repositories are recorded in the model configuration
and [model documentation](docs/MODELS.md).

## PyAV and FFmpeg

PyAV source is BSD-3-Clause. TikTok Transcriber repacks its pinned Windows wheel as
`18.1.0+lgpl.1`, changing extension DLL import names to use a separately supplied
LGPL-only shared FFmpeg build. The original x264/x265 libraries are not included.
No PyAV recognition or decoding code is rewritten.

FFmpeg is `n8.1.3-18-g46d899d7a0`, from the BtbN `lgpl-shared` build. Its runtime
reports LGPL version 3 or later. Full LGPL-3.0 and GPL-3.0 base texts accompany
the package. Additional incorporated components retain their upstream notices.

The FFmpeg DLLs are separate replaceable files under the application runtime.
You may replace or relink the LGPL libraries and reverse engineer the combined
work as needed to debug your modifications under the applicable license terms.
TikTok Transcriber's MIT terms do not restrict those rights.

Build input checksums, upstream source revisions, the packaging modification,
and reproducible steps are in `dev/media.lock.json`, `dev/prepare_media.py`, and
[media build documentation](docs/MEDIA.md). A matching upstream build archive is
retained with the release rather than in the Git source tree.

## Interface and runtime

The Nas design system, Orbi, and TikTok Transcriber mark are by Nas. Inter is licensed
under SIL Open Font License 1.1 and requested from Google Fonts. pywebview uses
BSD-3-Clause; pythonnet uses MIT. Python uses the PSF license. WebView2 and Windows
runtime components retain Microsoft's terms. Optional NVIDIA CUDA libraries are
downloaded separately under their own vendor licenses and are not included in
the source or standard release archive.

See [dependency inventory](docs/DEPENDENCIES.md) and `docs/dependencies.json`
for the tested Python dependency closure. License metadata is descriptive;
the complete upstream license texts govern each component.
