import io
import os
import sys
import importlib
from PIL import Image
from fastapi.testclient import TestClient

def fresh_app():
    for name in ("main", "photo_uploads", "golf_features"):
        sys.modules.pop(name, None)
    import main
    return main.app

def test_private_photo_access(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    app = fresh_app()
    with TestClient(app) as client:
        def register(email, name):
            r = client.post("/api/register", json={"email":email,"password":"test-password-123","name":name,"age":30,"location":"Dublin"})
            assert r.status_code == 200, r.text
            return r.json()
        a = register("a@example.test", "Alice")
        b = register("b@example.test", "Bob")
        auth_a = {"Authorization":"Bearer "+a["token"]}
        auth_b = {"Authorization":"Bearer "+b["token"]}
        image = Image.new("RGB",(16,16),"green")
        data = io.BytesIO(); image.save(data,format="PNG")
        upload = client.post("/api/me/photo",data=data.getvalue(),headers={**auth_a,"Content-Type":"image/png"})
        assert upload.status_code == 200,upload.text
        path=upload.json()["photo"]
        assert client.get(path).status_code == 401
        assert client.get(path,headers=auth_a).status_code == 200
        assert client.get(path,headers=auth_b).status_code == 200
        assert client.post("/api/block/"+str(a["user_id"]),headers=auth_b).status_code == 200
        assert client.get(path,headers=auth_b).status_code == 404
        assert client.get(path,headers=auth_a).status_code == 200
        assert client.post("/api/logout",headers=auth_a).status_code == 200
        assert client.get(path,headers=auth_a).status_code == 401

def test_admin_mfa_and_login_lockout(tmp_path,monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("ADMIN_EMAIL","admin@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD","test-admin-password")
    monkeypatch.setenv("ADMIN_TOTP_SECRET","JBSWY3DPEHPK3PXP")
    import pyotp
    app = fresh_app()
    with TestClient(app) as client:
        credentials={"email":"admin@example.test","password":"test-admin-password"}
        assert client.post("/api/admin/login",json=credentials).status_code==401
        credentials["otp"]=pyotp.TOTP("JBSWY3DPEHPK3PXP").now()
        result=client.post("/api/admin/login",json=credentials)
        assert result.status_code==200,result.text
        auth={"Authorization":"Bearer "+result.json()["token"]}
        assert client.get("/api/admin/stats",headers=auth).status_code==200
        assert client.post("/api/admin/logout",headers=auth).status_code==200
        assert client.get("/api/admin/stats",headers=auth).status_code==401
        for i in range(5):
            client.post("/api/login",json={"email":"wrong@example.test","password":"wrong"})
        assert client.post("/api/login",json={"email":"wrong@example.test","password":"wrong"}).status_code==429

def test_club_login_lockout_and_logout(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app=fresh_app()
    with TestClient(app) as client:
        club={"name":"Test Golf Club","location":"Dublin","email":"club@example.test","password":"club-test-password"}
        created=client.post("/api/clubs/register",json=club)
        assert created.status_code==200,created.text
        token=created.json()["token"]
        auth={"Authorization":"Bearer "+token}
        assert client.get("/api/clubs/me",headers=auth).status_code==200
        assert client.post("/api/clubs/logout",headers=auth).status_code==200
        assert client.get("/api/clubs/me",headers=auth).status_code==401
        for i in range(5):
            client.post("/api/clubs/login",json={"email":club["email"],"password":"wrong"})
        assert client.post("/api/clubs/login",json={"email":club["email"],"password":club["password"]}).status_code==429
