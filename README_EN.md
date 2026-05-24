[中文](README.md) | [English](README_EN.md)

# 🌟 VLM Renamer (Image Smart Renaming & Classification Tool)

This is a fully automated local image organization tool based on **Vision-Language Models (VLM)**.
It calls large models like Volcengine Doubao (or any API compatible with OpenAI format) to accurately recognize image content, automatically generates fluent descriptions as filenames, and intelligently distributes images into appropriate category folders based on semantics and rules. It features a modern Web UI and supports one-click processing of massive image libraries.

---

## ✨ Core Features

- 🤖 **AI Smart Recognition & Renaming**: Say goodbye to `IMG_20230101.jpg` and automatically convert them into `Sunset city coastal landscape.jpg`.
- 📂 **Dynamic Classification System**: Intelligently categorizes images into 18 predefined clear categories (customizable via the frontend) based on VLM content analysis, strong filename features, and image aspect ratios.
- ⚖️ **High-Priority Aspect Ratio Detection**: Built-in rules for "Landscape (Wallpaper)" and "1:1 (Avatar)" with the highest priority to automatically isolate high-quality assets.
- 🌐 **Modern Web UI**: A minimalist console built with Vue 3 + FastAPI. Supports one-click API configuration, category management, real-time progress monitoring, and error log viewing.
- ⚡ **High Performance & Safety Mechanisms**:
  - Supports multi-account concurrent API requests and multi-threaded MD5 pre-scanning acceleration.
  - **Dual Deduplication System** (MD5 checksum + path recording) with a one-click cache clearing feature.
  - Conflict prevention: Automatically appends incremental numbers to duplicate filenames.

## 🚀 Running Modes

The tool provides three flexible running modes:
1. **Default Mode**: Analyzes, renames, and moves images to their corresponding category folders.
2. **Rename-Only Mode**: Analyzes and renames images but keeps them in their original directory.
3. **Organize Scattered Images**: Deeply scans (recursive subdirectories) unclassified files, re-analyzes them using AI, and moves them to valid existing category folders. Ideal for secondary organization.

---

## 💻 Installation & Usage

### Method 1: Using the Standalone Installer (Windows)
If you are a regular user, you can directly download the latest `.exe` installer from the [Releases](../../releases) page.
After installation, simply double-click the desktop shortcut to open the console in your browser. **No Python environment configuration is required.**

### Method 2: Running from Source (Developers)

Ensure you have Python 3.10+ installed.

```bash
# 1. Clone the repository
git clone https://github.com/qingxuandaoming/Picture.git
cd Picture/_app

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the service
python main.py
# The program will automatically open http://127.0.0.1:8000 in your browser
```

---

## ⚙️ Configuration & Data Storage

The system implements complete data isolation. Your configuration information (such as API Keys) and processing records are securely stored in the local data directory of your OS to prevent accidental leakage with the source code:
- **Windows**: `C:\Users\<Username>\AppData\Local\qingxuandaoming\Picture`
- **macOS**: `~/Library/Application Support/qingxuandaoming/Picture`
- **Linux**: `~/.local/share/qingxuandaoming/Picture`

You can directly configure the API keys and the root directory of the photos you want to process in the "Settings" of the Web page. All modifications will be automatically and persistently saved.

## 📜 License

This project is open-sourced under the [Apache License 2.0](LICENSE).
