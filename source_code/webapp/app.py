import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
import httpx

# ---- Konfig per ENV (unter Settings → Variables eintragen) ----
APP_URL = os.getenv("APP_URL")                               # z.B. https://<user>-mlops-hs25-auth.hf.space
SIMAP_AUTH_URL = os.getenv("SIMAP_AUTH_URL")                 # aus OIDC-Discovery (authorization_endpoint)
SIMAP_TOKEN_URL = os.getenv("SIMAP_TOKEN_URL")               # aus OIDC-Discovery (token_endpoint)
SIMAP_API_BASE = os.getenv("SIMAP_API_BASE", "https://www.simap.ch/api")
SIMAP_CLIENT_ID = os.getenv("SIMAP_CLIENT_ID")               # kommt von SIMAP
SIMAP_CLIENT_SECRET = os.getenv("SIMAP_CLIENT_SECRET", None) # evtl. leer bei PKCE-only
SIMAP_SCOPES = os.getenv("SIMAP_SCOPES", "openid profile")
REDIRECT_URI = f"{APP_URL}/auth/callback"

app = FastAPI()

# ---- Öffentlicher Test-Endpunkt (ohne Login) ----
@app.get("/public/ping")
async def public_ping():
    url = f"{SIMAP_API_BASE}/publications/v2/project/project-search"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params={"search": "", "lang": "DE"})
    r.raise_for_status()
    data = r.json()
    return {"ok": True, "items": len(data.get("projects") or []), "pagination": data.get("pagination")}

# ---- OAuth Client ----
oauth = OAuth()
oauth.register(
    name="simap",
    client_id=SIMAP_CLIENT_ID,
    client_secret=SIMAP_CLIENT_SECRET,
    authorize_url=SIMAP_AUTH_URL,
    access_token_url=SIMAP_TOKEN_URL,
    client_kwargs={"scope": SIMAP_SCOPES},
)

SESSIONS = {}  # MVP – für Produktion später Redis/DB

@app.get("/")
async def index():
    return HTMLResponse('<h3>SIMAP OAuth Demo</h3>'
                        '<a href="/public/ping">/public/ping</a><br>'
                        '<a href="/auth/login">Login mit SIMAP</a>')

@app.get("/auth/login")
async def auth_login(request: Request):
    return await oauth.simap.authorize_redirect(request, REDIRECT_URI)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.simap.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(400, f"Token-Austausch fehlgeschlagen: {e}")
    SESSIONS["demo-user"] = token
    return HTMLResponse('<p>Login OK.</p><a href="/me">/me</a> | <a href="/private/projects">/private/projects</a>')

@app.get("/me")
async def me():
    t = SESSIONS.get("demo-user")
    if not t: raise HTTPException(401, "Nicht eingeloggt")
    redacted = {**t, "access_token": (t.get("access_token","")[:8] + "...")}
    return JSONResponse(redacted)

@app.get("/private/projects")
async def private_projects():
    t = SESSIONS.get("demo-user")
    if not t: raise HTTPException(401, "Nicht eingeloggt")
    headers = {"Authorization": f"Bearer {t['access_token']}"}
    # TODO: hier später den echten privaten Pfad aus eurer simap.yaml einsetzen
    url = f"{SIMAP_API_BASE}/<PRIVATE_ENDPOINT_PATH>"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params={"limit": 10})
    if r.status_code == 401:
        raise HTTPException(401, "Token abgelaufen/ungültig")
    r.raise_for_status()
    return r.json()
