# Nas design system

The bundled Nas kit provides semantic colors, tactile controls, and Orbi pixel art.
The public API and selectors use English names. TikTok Transcriber selects the `workshop`
preset with compact density and quiet motion. Application layout remains in
`src/ui.html`.

`Nas.orbi()` applies saved and system motion preferences. The renderer preserves
its static pose during theme changes and ignores invalid pointer coordinates
or hidden canvases. Regression checks compare rendered pixels in both themes.

`app.read_interface()` embeds these local assets in WebView2; no browser framework
is required. Nas and Orbi are by Nas and are covered by the project MIT license.
