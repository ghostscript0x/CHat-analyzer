# BetweenLines - WhatsApp Chat Analyzer

A Flask web app to analyze WhatsApp chats and assign personality roles using AI.

**Branded by opencode** - Modern, AI-powered chat insights.

## Installation

1. Clone or download the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with `GROQ_API_KEY=your_key_here` and optionally `TELEGRAM_BOT_TOKEN=your_token_here` for bot
4. Run: `python app.py`

## Usage

### Web App
1. Export your WhatsApp chat as .txt (exclude media) or ZIP file.
2. Upload the file.
3. Select participants.
4. View AI-powered personality analysis.

### Telegram Bot (optional)
1. Set TELEGRAM_BOT_TOKEN in .env
2. Start bot with /start
3. Send ZIP file with .txt export
4. Receive analysis

## Deployment with Docker

1. Build image: `docker build -t betweenlines .`
2. Run container: `docker run -p 5000:5000 betweenlines`

## Features

- Upload WhatsApp .txt or .zip files (auto-extracts .txt)
- Automatic participant detection
- AI-powered personality role scoring and explanations
- Modern UI with Tailwind CSS animations
- Privacy-focused: files deleted after processing