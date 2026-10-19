## setup: API key (needed only for Layer 1 AI refinement)
Copy `backend/.env.example` to `backend/.env` and set `GROQ_API_KEY` to your own key
(free at https://console.groq.com/keys). `backend/.env` is git-ignored, so keys are never committed.

    copy backend\.env.example backend\.env

## to run all
powershell -ExecutionPolicy Bypass -File .\run_all.ps1

## to stop all
taskkill /F /IM node.exe /T
taskkill /F /IM python.exe /T