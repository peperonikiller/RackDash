from __future__ import annotations
import hashlib, hmac, json, os, secrets, time
from pathlib import Path
from flask import session

class AdminSecurity:
    def __init__(self,state_file:Path):
        self.state_file=Path(state_file);self.state_file.parent.mkdir(parents=True,exist_ok=True)
        self._state=self._load()
    def _load(self):
        try:
            data=json.loads(self.state_file.read_text(encoding="utf-8"))
            if "secret_key" not in data:
                data["secret_key"]=secrets.token_hex(32);self._save(data)
            return data
        except Exception:
            data={"enabled":False,"salt":"","password_hash":"","secret_key":secrets.token_hex(32)}
            self._save(data);return data
    def _save(self,data=None):
        if data is not None:self._state=data
        self.state_file.write_text(json.dumps(self._state,indent=2),encoding="utf-8")
        try:os.chmod(self.state_file,0o600)
        except OSError:pass
    @property
    def secret_key(self):return self._state["secret_key"]
    @property
    def enabled(self):return bool(self._state.get("enabled"))
    @property
    def configured(self):return bool(self._state.get("password_hash"))
    def status(self):return {"enabled":self.enabled,"configured":self.configured,"authenticated":self.is_authenticated()}
    def _derive(self,password,salt):return hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    def set_password(self,password):
        if len(password)<4:raise ValueError("Admin password/PIN must contain at least 4 characters.")
        salt=secrets.token_bytes(16);self._state["salt"]=salt.hex();self._state["password_hash"]=self._derive(password,salt).hex();self._state["enabled"]=True;self._save()
    def set_enabled(self,enabled):
        if enabled and not self.configured:raise ValueError("Set an admin password/PIN before enabling authentication.")
        self._state["enabled"]=bool(enabled);self._save()
    def verify(self,password):
        if not self.configured:return False
        try:return hmac.compare_digest(self._derive(password,bytes.fromhex(self._state["salt"])),bytes.fromhex(self._state["password_hash"]))
        except Exception:return False
    def login(self,password):
        if self.verify(password):
            session["rackdash_admin"]=True;session["rackdash_admin_at"]=int(time.time());return True
        return False
    def logout(self):session.pop("rackdash_admin",None);session.pop("rackdash_admin_at",None)
    def is_authenticated(self):return True if not self.enabled else bool(session.get("rackdash_admin"))
    def require(self):return self.is_authenticated()
