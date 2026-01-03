# BetweenLines - WhatsApp Chat Analyzer

A Flask web app to analyze WhatsApp chats and assign personality roles using AI.

**Branded by opencode** - Modern, AI-powered chat insights.

## Installation

1. Clone or download the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with `GROQ_API_KEY=your_key_here`
4. Run locally: `python app.py`

## Deployment with Docker

1. Build image: `docker build -t betweenlines .`
2. Run container: `docker run -p 5000:5000 betweenlines`

## Features

- Upload WhatsApp .txt exports
- Automatic participant detection
- AI-powered personality role scoring and explanations
- Modern UI with Tailwind CSS animations
- Export results as JSON or branded PDF