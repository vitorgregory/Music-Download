# Apple Music Downloader Web UI (Dockerized & Enhanced)

A robust, Docker-based web interface for Apple Music Downloader, featuring a modern UI, smart selection, and ZimaOS compatibility.

## 🎵 About

This project is a completely refactored web wrapper built around the excellent work of the Apple Music downloading community. Unlike previous versions, this project is **Docker-first**, meaning it runs in an isolated, immutable container with all dependencies (Go 1.23, Bento4, FFmpeg, Python) pre-configured.

It transforms the command-line experience into a rich visual interface with enhanced controls like metadata preview, smart selection badges, and download management.

**Core backend tools powered by:**
- **[zhaarey/apple-music-downloader](https://github.com/zhaarey/apple-music-downloader)**
- **[zhaarey/wrapper](https://github.com/zhaarey/wrapper)**

## ✨ New Features (Refactored Version)

- **🐳 Docker Native**: Zero system dependencies. Runs on Ubuntu 22.04 base with fixed libraries (libssl1.1) for maximum tool compatibility.
- **🔍 Link Analysis**: Preview album art and metadata before starting the download process.
- **🎨 Smart Selection UI**:
    - **Visual Badges**: Automatically distinguishes between **[Single]**, **[EP]**, **[Album]**, and **[Deluxe]** editions.
    - **Year Display**: Shows release dates to help differentiate albums with same names.
- **⏭️ Flow Control**:
    - **Skip/Finish**: Skip specific steps (like Music Videos) without aborting the whole queue.
    - **Global Cancel**: Instantly stop processes if you change your mind.
- **🛡️ Robust Architecture**: Rewritten Python backend using Clean Architecture (ProcessManager) for stability and thread-safe logging.
- **🖥️ ZimaOS Ready**: Optimized file structure for easy deployment on ZimaBoard/ZimaCube.

## 🚀 Quick Start

### Prerequisites

- **Docker** & **Docker Compose** (Installed by default on ZimaOS, CasaOS, Unraid, etc.)

### Installation

1. **Get the files:**
   Clone this repository or upload the files to your server (e.g., `/DATA/AppData/apple-music-downloader` on ZimaOS).

2. **Build and Run:**
   Navigate to the folder and run:
   ```bash
   docker-compose up --build -d

*Note: The first build may take a few minutes as it compiles Go 1.23 and sets up Bento4 tools.*

3. **Access the UI:**
Open your browser and navigate to:
`http://YOUR-SERVER-IP:5000`

### Volume Mapping (docker-compose.yml)

* `./downloads`: Where your music/videos will appear.
* `./data`: Stores your credentials and config files persistently.

## 📖 Usage Guide

### 1. Authentication

1. Click **"Login to Wrapper"**.
2. Enter your Apple Music credentials.
3. If requested, a **2FA Modal** will appear automatically. Enter the code sent to your device.
4. Wait for the green "Login successful" log.

### 2. Downloading

1. **Analyze**: Paste an Apple Music link and click `🔍 Analyze` to confirm the content.
2. **Download**: Choose your format (**ATMOS**, **AAC**, or Standard) and click Download.
3. **Select**:
* A list will appear showing Tracks/Videos.
* Use the checkboxes to select what you want.
* **Tip**: Look for the colored badges (Blue for Singles, Green for EPs) to guide you.
* Click **Confirm & Download**.
* *Optional*: Click **Skip / Finish** to bypass a selection step (useful if you want the Music but not the Videos).



### 3. Settings

Click the ⚙️ icon to configure:

* Folder naming structures.
* Audio quality limits.
* Embedding lyrics/cover art.
* Region/Storefront settings.

## 🛠️ For Developers / Technical Details

This version moves away from runtime installation scripts (`main.py` install logic) to a build-time approach:

* **Dockerfile**: Handles the compilation of Go 1.23, installation of `gpac` (MP4Box) and `libssl1.1` (for Bento4 legacy support).
* **App Structure**:
* `process_manager.py`: Handles subprocess streams (stdin/stdout) without blocking Flask.
* `utils.py`: Centralized regex parsers for metadata and config handling.
* `static/script.js`: Isolated frontend logic for polling logs and UI rendering.



## ⚠️ Disclaimer

This tool is for educational purposes and personal use only. Please respect Apple's Terms of Service. The developers of this UI wrapper are not responsible for any misuse.

## 🙏 Acknowledgments

* **@zhaarey** for the heavy lifting on the core downloader tools.
* **Open Source Community** for keeping media preservation tools alive.
