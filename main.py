import re
import secrets

import socketio
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal, User, Community, Membership, Channel, Message

app = FastAPI(title="QWK")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
hasher = PasswordHash.recommended()
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

sid_user = {}
voice_rooms = {}


def current_user(request: Request):
    try:
        uid = int(request.cookies.get("qwk_uid", ""))
    except (ValueError, TypeError):
        return None

    with SessionLocal() as db:
        user = db.get(User, uid)
        if user is None:
            return None
        return {"id": user.id, "username": user.username}


def communities_for(uid: int):
    with SessionLocal() as db:
        communities = db.scalars(
            select(Community)
            .join(Membership, Membership.community_id == Community.id)
            .where(Membership.user_id == uid)
            .order_by(Community.id)
        ).all()
        return [
            {"id": c.id, "name": c.name, "invite_code": c.invite_code}
            for c in communities
        ]


def payload(uid: int, cid: int):
    with SessionLocal() as db:
        community = db.get(Community, cid)
        membership = db.scalar(
            select(Membership).where(
                Membership.community_id == cid,
                Membership.user_id == uid,
            )
        )
        if community is None or membership is None:
            return None

        channels = db.scalars(
            select(Channel)
            .where(Channel.community_id == cid)
            .order_by(Channel.id)
        ).all()
        members = db.execute(
            select(User.id, User.username)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.community_id == cid)
            .order_by(User.username)
        ).all()

        return {
            "id": community.id,
            "name": community.name,
            "invite_code": community.invite_code,
            "channels": [
                {"id": channel.id, "name": channel.name, "kind": channel.kind}
                for channel in channels
            ],
            "members": [
                {"id": member.id, "username": member.username}
                for member in members
            ],
        }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    communities = communities_for(user["id"])
    default_cid = communities[0]["id"] if communities else 0
    try:
        cid = int(request.query_params.get("community", default_cid))
    except (ValueError, TypeError):
        cid = 0

    community_data = payload(user["id"], cid) if cid else None
    if community_data is None and communities:
        community_data = payload(user["id"], communities[0]["id"])

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user, "communities": communities, "community": community_data},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"mode": "login", "error": ""},
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"mode": "register", "error": ""},
    )


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]{3,32}", username) or len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            status_code=400,
            context={
                "mode": "register",
                "error": "اسم المستخدم من 3 إلى 32 حرفًا، ويقبل الحروف الإنجليزية والأرقام والنقطة والشرطة السفلية؛ كلمة المرور 8 أحرف على الأقل",
            },
        )

    try:
        with SessionLocal() as db:
            user = User(username=username, password_hash=hasher.hash(password))
            db.add(user)
            db.flush()
            user_id = user.id

            community = Community(
                name=f"سيرفر {username}",
                invite_code=secrets.token_urlsafe(6)[:8],
                owner_id=user_id,
            )
            db.add(community)
            db.flush()
            community_id = community.id

            db.add(Membership(community_id=community_id, user_id=user_id))
            db.add_all(
                [
                    Channel(community_id=community_id, name="عام", kind="text"),
                    Channel(community_id=community_id, name="الألعاب", kind="text"),
                    Channel(community_id=community_id, name="الصوت العام", kind="voice"),
                ]
            )
            db.commit()
    except IntegrityError:
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            status_code=400,
            context={"mode": "register", "error": "اسم المستخدم مستخدم بالفعل"},
        )

    response = RedirectResponse("/", status_code=303)
    response.set_cookie("qwk_uid", str(user_id), httponly=True, samesite="lax")
    return response


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username.strip()))
        if user is not None:
            user_id = user.id
            password_hash = user.password_hash
        else:
            user_id = None
            password_hash = None

    if user_id is None or not hasher.verify(password, password_hash):
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            status_code=400,
            context={
                "mode": "login",
                "error": "اسم المستخدم أو كلمة المرور غير صحيحة",
            },
        )

    response = RedirectResponse("/", status_code=303)
    response.set_cookie("qwk_uid", str(user_id), httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("qwk_uid")
    return response


@app.post("/create-community")
async def create_community(request: Request, name: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    name = name.strip()[:80]
    if not name:
        raise HTTPException(status_code=400, detail="اسم السيرفر مطلوب")

    with SessionLocal() as db:
        community = Community(
            name=name,
            invite_code=secrets.token_urlsafe(6)[:8],
            owner_id=user["id"],
        )
        db.add(community)
        db.flush()
        community_id = community.id

        db.add(Membership(community_id=community_id, user_id=user["id"]))
        db.add_all(
            [
                Channel(community_id=community_id, name="عام", kind="text"),
                Channel(community_id=community_id, name="الألعاب", kind="text"),
                Channel(community_id=community_id, name="الصوت العام", kind="voice"),
            ]
        )
        db.commit()

    return RedirectResponse(f"/?community={community_id}", status_code=303)


@app.post("/join")
async def join(request: Request, invite_code: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with SessionLocal() as db:
        community = db.scalar(
            select(Community).where(Community.invite_code == invite_code.strip())
        )
        if community is None:
            raise HTTPException(status_code=404, detail="رمز الدعوة غير صحيح")
        community_id = community.id

        membership = db.scalar(
            select(Membership).where(
                Membership.community_id == community_id,
                Membership.user_id == user["id"],
            )
        )
        if membership is None:
            db.add(Membership(community_id=community_id, user_id=user["id"]))
            db.commit()

    return RedirectResponse(f"/?community={community_id}", status_code=303)


@app.post("/create-channel")
async def create_channel(
    request: Request,
    community_id: int = Form(...),
    name: str = Form(...),
    kind: str = Form(...),
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if kind not in ("text", "voice") or not name.strip():
        raise HTTPException(status_code=400, detail="بيانات القناة غير صحيحة")

    with SessionLocal() as db:
        membership = db.scalar(
            select(Membership).where(
                Membership.community_id == community_id,
                Membership.user_id == user["id"],
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="ليس لديك صلاحية")
        db.add(
            Channel(
                community_id=community_id,
                name=name.strip()[:80],
                kind=kind,
            )
        )
        db.commit()

    return RedirectResponse(f"/?community={community_id}", status_code=303)


@app.get("/api/messages")
async def get_messages(request: Request, channel_id: int):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="سجّل الدخول")

    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if channel is None:
            raise HTTPException(status_code=403, detail="القناة غير متاحة")
        community_id = channel.community_id
        membership = db.scalar(
            select(Membership).where(
                Membership.community_id == community_id,
                Membership.user_id == user["id"],
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="القناة غير متاحة")

        messages = db.scalars(
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(Message.id.desc())
            .limit(100)
        ).all()
        return [
            {
                "id": message.id,
                "username": message.username,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in reversed(messages)
        ]


@app.post("/api/messages")
async def post_message(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="سجّل الدخول")

    try:
        data = await request.json()
        channel_id = int(data.get("channel_id", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="بيانات الرسالة غير صحيحة")

    content = str(data.get("content", "")).strip()
    if not content or len(content) > 4000:
        raise HTTPException(status_code=400, detail="الرسالة فارغة أو طويلة جدًا")

    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if channel is None or channel.kind != "text":
            raise HTTPException(status_code=403, detail="القناة غير متاحة")

        membership = db.scalar(
            select(Membership).where(
                Membership.community_id == channel.community_id,
                Membership.user_id == user["id"],
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="القناة غير متاحة")

        message = Message(
            channel_id=channel_id,
            user_id=user["id"],
            username=user["username"],
            content=content,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        result = {
            "id": message.id,
            "username": message.username,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "channel_id": channel_id,
        }

    await sio.emit("new_message", result, room=f"channel:{channel_id}")
    return result


@sio.event
async def identify(sid, data):
    data = data or {}
    sid_user[sid] = {
        "username": str(data.get("username", "مستخدم"))[:32],
        "community_id": str(data.get("community_id", "")),
    }
    community_id = sid_user[sid]["community_id"]
    if community_id:
        await sio.enter_room(sid, f"community:{community_id}")
        await broadcast_online(community_id)


async def broadcast_online(community_id):
    members = [
        member for member in sid_user.values()
        if member.get("community_id") == str(community_id)
    ]
    await sio.emit(
        "online_members",
        {"members": members},
        room=f"community:{community_id}",
    )


@sio.event
async def join_channel(sid, data):
    data = data or {}
    channel = str(data.get("channel_id", ""))
    for room in list(sio.rooms(sid)):
        if room.startswith("channel:"):
            await sio.leave_room(sid, room)
    if channel:
        await sio.enter_room(sid, f"channel:{channel}")


@sio.event
async def join_voice(sid, data):
    data = data or {}
    room = str(data.get("room", ""))
    if not room:
        return

    await remove_voice(sid)
    voice_rooms.setdefault(room, {})[sid] = {
        "sid": sid,
        "username": str(
            data.get("username", sid_user.get(sid, {}).get("username", "مستخدم"))
        )[:32],
    }
    await sio.enter_room(sid, f"voice:{room}")
    await sio.emit(
        "voice_members",
        {"room": room, "members": list(voice_rooms[room].values())},
        room=f"voice:{room}",
    )
    await sio.emit(
        "voice_peer_joined",
        {"sid": sid, "username": voice_rooms[room][sid]["username"]},
        room=f"voice:{room}",
        skip_sid=sid,
    )


async def remove_voice(sid):
    for room, members in list(voice_rooms.items()):
        if sid in members:
            del members[sid]
            await sio.leave_room(sid, f"voice:{room}")
            await sio.emit(
                "voice_members",
                {"room": room, "members": list(members.values())},
                room=f"voice:{room}",
            )
            if not members:
                del voice_rooms[room]


@sio.event
async def leave_voice(sid, data=None):
    await remove_voice(sid)


@sio.event
async def voice_signal(sid, data):
    data = data or {}
    target = data.get("target")
    if target:
        await sio.emit(
            "voice_signal",
            {"from": sid, "signal": data.get("signal")},
            to=target,
        )


@sio.event
async def disconnect(sid, reason=None):
    await remove_voice(sid)
    old_user = sid_user.pop(sid, None)
    if old_user and old_user.get("community_id"):
        await broadcast_online(old_user["community_id"])
