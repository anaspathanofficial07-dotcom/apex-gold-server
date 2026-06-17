"""
╔══════════════════════════════════════════════════════════════╗
║         APEX GOLD — LICENSE SERVER                          ║
║         FastAPI Backend | Deploy FREE on Render.com         ║
╚══════════════════════════════════════════════════════════════╝

DEPLOY STEPS:
1. Create account on render.com
2. New → Web Service → Connect GitHub repo
3. Build Command: pip install -r requirements.txt
4. Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
5. Done — free URL milegi jaise: https://apex-gold-xxx.onrender.com

ADMIN PANEL: https://your-url.onrender.com/admin
Default password: change in ADMIN_PASSWORD below
"""

import os
import json
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ApexAdmin@2025")  # CHANGE THIS!
DATA_FILE      = Path("data/licenses.json")
TRADE_FILE     = Path("data/trades.json")

# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(title="Apex Gold License Server", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()

# ── Data Helpers ──────────────────────────────────────────────

def load_data(file: Path) -> dict:
    if file.exists():
        return json.loads(file.read_text())
    return {}

def save_data(file: Path, data: dict):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2))

def generate_key() -> str:
    """Generate key like APXG-XXXX-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    parts = ["APXG"] + [
        "".join(secrets.choice(chars) for _ in range(4))
        for _ in range(3)
    ]
    return "-".join(parts)

def admin_required(credentials: HTTPBasicCredentials = Depends(security)):
    ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return credentials.username

# ── Models ────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    key: str
    machine_id: str

class CreateKeyRequest(BaseModel):
    email: str
    plan: str = "monthly"     # monthly | yearly | lifetime
    duration_days: int = 30

class TradeUpdate(BaseModel):
    key: str
    machine_id: str
    trades: list
    account_info: dict

# ── Routes ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Apex Gold License Server",
        "version": "2.0",
        "status": "running"
    }

@app.post("/verify")
def verify_license(req: VerifyRequest):
    """Called by bot on every startup to check license."""
    licenses = load_data(DATA_FILE)
    key = req.key.strip().upper()

    if key not in licenses:
        return {"valid": False, "reason": "License key not found"}

    lic = licenses[key]

    # Blocked check
    if lic.get("blocked"):
        return {"valid": False, "reason": "License has been blocked. Contact support."}

    # Machine ID binding
    if "machine_id" not in lic or lic["machine_id"] == "":
        # First activation — bind to this machine
        lic["machine_id"]    = req.machine_id
        lic["activated_at"]  = datetime.now().isoformat()
        lic["last_seen"]     = datetime.now().isoformat()
        licenses[key] = lic
        save_data(DATA_FILE, licenses)
        return {
            "valid":   True,
            "message": "License activated on this machine",
            "expires": lic.get("expires", "lifetime"),
            "plan":    lic.get("plan", "monthly")
        }

    if lic["machine_id"] != req.machine_id:
        return {
            "valid":  False,
            "reason": "License is bound to a different machine. Contact support."
        }

    # Expiry check
    if lic.get("expires") and lic["expires"] != "lifetime":
        exp = datetime.fromisoformat(lic["expires"])
        if datetime.now() > exp:
            return {
                "valid":  False,
                "reason": f"License expired on {exp.strftime('%Y-%m-%d')}. Please renew."
            }

    # Update last seen
    lic["last_seen"] = datetime.now().isoformat()
    licenses[key] = lic
    save_data(DATA_FILE, licenses)

    return {
        "valid":   True,
        "expires": lic.get("expires", "lifetime"),
        "plan":    lic.get("plan", "monthly"),
        "email":   lic.get("email", "")
    }

@app.post("/update_trades")
def update_trades(req: TradeUpdate):
    """Bot sends live trade data for mobile monitoring."""
    licenses = load_data(DATA_FILE)
    key = req.key.strip().upper()

    if key not in licenses:
        raise HTTPException(404, "Key not found")

    trades_data = load_data(TRADE_FILE)
    trades_data[key] = {
        "trades":       req.trades,
        "account_info": req.account_info,
        "updated_at":   datetime.now().isoformat()
    }
    save_data(TRADE_FILE, trades_data)
    return {"status": "ok"}

@app.get("/mobile/{key}")
def mobile_data(key: str):
    """Mobile dashboard fetches this endpoint."""
    key = key.strip().upper()
    licenses = load_data(DATA_FILE)
    if key not in licenses:
        raise HTTPException(404, "Invalid key")
    if licenses[key].get("blocked"):
        raise HTTPException(403, "License blocked")

    trades_data = load_data(TRADE_FILE)
    data = trades_data.get(key, {
        "trades": [], "account_info": {}, "updated_at": None
    })
    return {
        "email":        licenses[key].get("email", ""),
        "plan":         licenses[key].get("plan", ""),
        "expires":      licenses[key].get("expires", ""),
        "trades":       data["trades"],
        "account_info": data["account_info"],
        "updated_at":   data["updated_at"],
    }

# ── ADMIN ROUTES ──────────────────────────────────────────────

@app.get("/admin/keys", dependencies=[Depends(admin_required)])
def list_keys():
    licenses = load_data(DATA_FILE)
    result = []
    for key, lic in licenses.items():
        result.append({
            "key":          key,
            "email":        lic.get("email", ""),
            "plan":         lic.get("plan", "monthly"),
            "expires":      lic.get("expires", "lifetime"),
            "machine_id":   lic.get("machine_id", ""),
            "activated_at": lic.get("activated_at", ""),
            "last_seen":    lic.get("last_seen", ""),
            "blocked":      lic.get("blocked", False),
            "created_at":   lic.get("created_at", ""),
        })
    return result

@app.post("/admin/create_key", dependencies=[Depends(admin_required)])
def create_key(req: CreateKeyRequest):
    licenses = load_data(DATA_FILE)
    key = generate_key()

    if req.plan == "lifetime":
        expires = "lifetime"
    else:
        expires = (datetime.now() + timedelta(days=req.duration_days)).isoformat()

    licenses[key] = {
        "email":        req.email,
        "plan":         req.plan,
        "duration_days": req.duration_days,
        "expires":      expires,
        "machine_id":   "",
        "activated_at": "",
        "last_seen":    "",
        "blocked":      False,
        "created_at":   datetime.now().isoformat(),
    }
    save_data(DATA_FILE, licenses)
    return {"key": key, "expires": expires, "email": req.email}

@app.post("/admin/block/{key}", dependencies=[Depends(admin_required)])
def block_key(key: str):
    key = key.strip().upper()
    licenses = load_data(DATA_FILE)
    if key not in licenses:
        raise HTTPException(404, "Key not found")
    licenses[key]["blocked"] = True
    save_data(DATA_FILE, licenses)
    return {"status": "blocked", "key": key}

@app.post("/admin/unblock/{key}", dependencies=[Depends(admin_required)])
def unblock_key(key: str):
    key = key.strip().upper()
    licenses = load_data(DATA_FILE)
    if key not in licenses:
        raise HTTPException(404, "Key not found")
    licenses[key]["blocked"] = False
    save_data(DATA_FILE, licenses)
    return {"status": "unblocked", "key": key}

@app.delete("/admin/delete/{key}", dependencies=[Depends(admin_required)])
def delete_key(key: str):
    key = key.strip().upper()
    licenses = load_data(DATA_FILE)
    if key not in licenses:
        raise HTTPException(404, "Key not found")
    del licenses[key]
    save_data(DATA_FILE, licenses)
    return {"status": "deleted", "key": key}

@app.post("/admin/reset_machine/{key}", dependencies=[Depends(admin_required)])
def reset_machine(key: str):
    """Reset machine binding — user wants to use on new PC."""
    key = key.strip().upper()
    licenses = load_data(DATA_FILE)
    if key not in licenses:
        raise HTTPException(404, "Key not found")
    licenses[key]["machine_id"]   = ""
    licenses[key]["activated_at"] = ""
    save_data(DATA_FILE, licenses)
    return {"status": "machine reset", "key": key}

@app.get("/admin/stats", dependencies=[Depends(admin_required)])
def stats():
    licenses = load_data(DATA_FILE)
    total    = len(licenses)
    active   = sum(1 for l in licenses.values() if not l.get("blocked"))
    blocked  = sum(1 for l in licenses.values() if l.get("blocked"))
    expired  = 0
    for l in licenses.values():
        if l.get("expires") and l["expires"] != "lifetime":
            try:
                if datetime.now() > datetime.fromisoformat(l["expires"]):
                    expired += 1
            except Exception:
                pass
    return {
        "total":   total,
        "active":  active,
        "blocked": blocked,
        "expired": expired,
    }
