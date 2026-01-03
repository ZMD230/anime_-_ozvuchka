This directory contains a simple Android WebView app that loads the web UI for "Anime AI Озвучка".

To build locally:

1. Install Android SDK and set up command-line tools.
2. From this directory run `./gradlew assembleDebug` to build a debug APK.

To build on GitHub Actions, add a workflow that runs `./gradlew assembleDebug` and uploads the artifact.

Notes:
- Replace the URL in `MainActivity.kt` with your deployed server URL or add a settings UI.
- The project uses Kotlin and Jetpack Compose for a minimal UI wrapper around the WebView.
