# MindSpring AI — Complete Local Website Project

## Features
- User registration and login (passwords hashed)
- SQLite storage for each user's notes, tests and teacher chat
- AI Note Studio: Simple, Detailed, Exam Preparation and Quick Revision
- Interactive MCQ mock tests with selectable answers and submission
- Learning-gap analysis based on actual submitted mock-test answers
- AI Voice Teacher: text chat, browser speech-to-text where supported, and text-to-speech replies
- Test history and saved notes

## Requirements
- Windows 10/11
- Python 3.10+
- OpenRouter API key and access to a model (free model availability and limits can change)

## Run on Windows
1. Extract the ZIP.
2. Open the `MindSpringAI_Complete` folder in VS Code (the folder containing `app.py` and `requirements.txt`).
3. Open Terminal > New Terminal.
4. Create environment:
   `py -m venv .venv`
5. Activate PowerShell environment:
   `.\.venv\Scripts\Activate.ps1`
   If PowerShell blocks it, run:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
   then activate again.
6. Install:
   `py -m pip install -r requirements.txt`
7. Copy `.env.example` to a new file named `.env`.
8. Put your own API key after `OPENROUTER_API_KEY=`. Keep `OPENROUTER_MODEL=openrouter/free`.
9. Start:
   `py app.py`
10. Open `http://127.0.0.1:5000` in Chrome and register an account.

## Important
- Keep `.env` private. Never upload it to GitHub or share it.
- This is a local development website, not a publicly hosted website. To submit a live public URL, deploy it to a hosting provider and configure environment variables securely.
- The voice features use browser speech recognition and speech synthesis. Recognition support varies by browser/device; Chrome is recommended.
- The AI needs a working API key and available model quota. The `openrouter/free` route can be rate-limited or temporarily unavailable.
- This project is a functional student-project baseline, not a production service. For public deployment, add HTTPS, CSRF protection, stronger session configuration, rate limiting, backups and privacy review.
