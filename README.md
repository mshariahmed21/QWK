# QWK starter
A Discord-inspired community web app starter, structured to support desktop/mobile clients later.

## Run on Windows
1. Extract the ZIP and open the QWK folder in PyCharm.
2. Open PyCharm Terminal.
3. Run: `python -m venv .venv`
4. Activate: `.venv\\Scripts\\activate`
5. Install: `pip install -r requirements.txt`
6. Start: `python -m uvicorn main:socket_app --reload`
7. Open http://127.0.0.1:8000

Features: accounts, login/logout, create communities, invite codes, text/voice channel records, persistent messages, live message updates, room presence, join sound and microphone permission UI.

Important: voice-room membership and mic permission are present, but real audio/video between users still needs complete WebRTC negotiation plus STUN/TURN configuration. This is a starter, not a production-secure public service. Public launch requires HTTPS, rate limits, backups, account recovery, moderation and security review. QWK is independent and is not affiliated with Discord.
