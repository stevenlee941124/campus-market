import json
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from jose import jwt

import auth_utils
import database
import models

router = APIRouter(prefix="/chat", tags=["chat"])
templates = Jinja2Templates(directory="templates")


class ConnectionManager:
    def __init__(self):
        # 鍵為 room_id，值為該聊天室中所有的 websocket 連線
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, room_id: int, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, room_id: int, websocket: WebSocket):
        if room_id in self.active_connections:
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast(self, room_id: int, data: dict):
        if room_id in self.active_connections:
            message_text = json.dumps(data)
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_text(message_text)
                except Exception:
                    pass


manager = ConnectionManager()


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return jwt.decode(
            token.replace("Bearer ", ""),
            auth_utils.SECRET_KEY,
            algorithms=[auth_utils.ALGORITHM],
        )
    except Exception:
        return None


def get_current_user_ws(websocket: WebSocket):
    token = websocket.cookies.get("access_token")
    if not token:
        return None
    try:
        return jwt.decode(
            token.replace("Bearer ", ""),
            auth_utils.SECRET_KEY,
            algorithms=[auth_utils.ALGORITHM],
        )
    except Exception:
        return None


@router.get("")
@router.get("/")
def chat_page(
    request: Request,
    room_id: int = None,
    user = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "user": user, "room_id": room_id}
    )


@router.get("/rooms/start")
def start_chat_room(
    product_id: int,
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="找不到此商品")

    buyer_id = user.get("user_id")
    seller_id = product.owner_id

    if buyer_id == seller_id:
        # 自己跟自己聊天，直接導向聊天大廳
        return RedirectResponse(url="/chat", status_code=303)

    # 檢查是否已有該商品的聊天室
    room = db.query(models.ChatRoom).filter(
        models.ChatRoom.product_id == product_id,
        models.ChatRoom.buyer_id == buyer_id
    ).first()

    if not room:
        room = models.ChatRoom(
            product_id=product_id,
            buyer_id=buyer_id,
            seller_id=seller_id
        )
        db.add(room)
        db.commit()
        db.refresh(room)
    else:
        room.buyer_deleted = False
        room.seller_deleted = False
        db.commit()

    return RedirectResponse(url=f"/chat?room_id={room.id}", status_code=303)


@router.get("/api/rooms")
def get_chat_rooms(
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="未登入")

    user_id = user.get("user_id")

    # 查詢使用者身為買家或賣家的所有聊天室
    rooms = db.query(models.ChatRoom).filter(
        (models.ChatRoom.buyer_id == user_id) | (models.ChatRoom.seller_id == user_id)
    ).order_by(models.ChatRoom.id.desc()).all()

    result = []
    for room in rooms:
        if not room.product:
            continue
        other_user = room.seller if room.buyer_id == user_id else room.buyer
        if not other_user:
            continue
            
        # 判斷當前使用者是買家還是賣家，若已標記刪除則不顯示
        if room.buyer_id == user_id:
            if room.buyer_deleted:
                continue
            is_archived = room.buyer_archived
        else:
            if room.seller_deleted:
                continue
            is_archived = room.seller_archived

        last_msg = db.query(models.ChatMessage).filter(
            models.ChatMessage.room_id == room.id
        ).order_by(models.ChatMessage.id.desc()).first()

        result.append({
            "room_id": room.id,
            "is_archived": bool(is_archived),
            "is_blocked": bool(room.is_blocked),
            "product": {
                "id": room.product.id,
                "name": room.product.name,
                "price": room.product.price,
                "image": room.product.image,
                "status": room.product.status
            },
            "other_user": {
                "id": other_user.id,
                "username": other_user.username,
                "nickname": other_user.nickname or other_user.username,
                "avatar": other_user.avatar or "/static/assets/icon-profile.png"
            },
            "last_message": last_msg.message if last_msg else "尚無訊息",
            "last_message_time": last_msg.created_at.strftime("%m/%d %H:%M") if last_msg else ""
        })
    return result


@router.get("/api/unread")
def get_unread_messages(
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        return {"unread_count": 0, "notifications": []}

    user_id = user.get("user_id")

    # 查詢使用者身為買家或賣家的所有聊天室
    rooms = db.query(models.ChatRoom).filter(
        (models.ChatRoom.buyer_id == user_id) | (models.ChatRoom.seller_id == user_id)
    ).all()

    room_ids = [r.id for r in rooms]
    if not room_ids:
        return {"unread_count": 0, "notifications": []}

    # 統計非當前使用者發送且未讀的訊息
    unread_msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.room_id.in_(room_ids),
        models.ChatMessage.sender_id != user_id,
        models.ChatMessage.is_read == False
    ).order_by(models.ChatMessage.id.desc()).all()

    unread_count = len(unread_msgs)

    notifications = []
    seen_rooms = set()
    for msg in unread_msgs:
        if msg.room_id not in seen_rooms:
            seen_rooms.add(msg.room_id)
            sender = db.query(models.User).filter(models.User.id == msg.sender_id).first()
            notifications.append({
                "room_id": msg.room_id,
                "sender": sender.username if sender else "系統",
                "message": msg.message[:30] + ("..." if len(msg.message) > 30 else ""),
                "created_at": msg.created_at.strftime("%H:%M")
            })

    return {
        "unread_count": unread_count,
        "notifications": notifications
    }


@router.get("/api/rooms/{room_id}/messages")
def get_messages(
    room_id: int,
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="未登入")

    user_id = user.get("user_id")
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    if room.buyer_id != user_id and room.seller_id != user_id:
        raise HTTPException(status_code=403, detail="無權存取此聊天室")

    # 標記對方發送的訊息為已讀
    unread_messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.room_id == room_id,
        models.ChatMessage.sender_id != user_id,
        models.ChatMessage.is_read == False
    ).all()
    for msg in unread_messages:
        msg.is_read = True
    db.commit()

    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.room_id == room_id
    ).order_by(models.ChatMessage.id.asc()).all()

    return [
        {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "message": msg.message,
            "created_at": msg.created_at.strftime("%H:%M"),
            "is_me": msg.sender_id == user_id,
            "sender_name": msg.sender.nickname or msg.sender.username,
            "sender_avatar": msg.sender.avatar or "/static/assets/icon-profile.png"
        } for msg in messages
    ]


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: int
):
    user = get_current_user_ws(websocket)
    if not user:
        await websocket.close(code=4003)
        return

    user_id = user.get("user_id")
    
    # 1. 驗證聊天室與權限 (獨立的短時間資料庫對談)
    with database.SessionLocal() as db:
        room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
        if not room or (room.buyer_id != user_id and room.seller_id != user_id):
            await websocket.close(code=4003)
            return

    await manager.connect(room_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            message_text = payload.get("message", "").strip()

            if not message_text:
                continue

            # 1.5 檢查對話框是否已被封鎖
            with database.SessionLocal() as db:
                chk_room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
                if chk_room and chk_room.is_blocked:
                    try:
                        await websocket.send_text(json.dumps({
                            "error": "此對話已封鎖，無法發送訊息。",
                            "sender_id": user_id
                        }))
                    except Exception:
                        pass
                    continue

            # 2. 寫入新訊息 (在 loop 內獨立進行 try-catch，寫入失敗絕不中斷整個 WebSocket 通道！)
            try:
                now = datetime.now()
                with database.SessionLocal() as db:
                    new_msg = models.ChatMessage(
                        room_id=room_id,
                        sender_id=user_id,
                        message=message_text,
                        created_at=now
                    )
                    db.add(new_msg)
                    
                    chk_room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
                    if chk_room:
                        chk_room.buyer_deleted = False
                        chk_room.seller_deleted = False
                        
                    db.commit()
                    # 直接在 Python 端取得時間與 ID，完全免除 db.refresh 的二次讀取，減少 SQLite 鎖定時間
                    created_at_str = now.strftime("%H:%M")
                    msg_id = new_msg.id
            except Exception as db_err:
                # 僅發送錯誤給目前發送者，不中斷連線
                try:
                    await websocket.send_text(json.dumps({
                        "error": "儲存訊息失敗，請稍候重試",
                        "sender_id": user_id
                    }))
                except Exception:
                    pass
                continue

            # 查詢發送者的暱稱和頭像以進行廣播
            with database.SessionLocal() as db:
                sender_user = db.query(models.User).filter(models.User.id == user_id).first()
                sender_name = sender_user.nickname or sender_user.username if sender_user else user.get("sub")
                sender_avatar = sender_user.avatar or "/static/assets/icon-profile.png" if sender_user else "/static/assets/icon-profile.png"

            # 廣播給聊天對象
            broadcast_data = {
                "id": msg_id,
                "sender_id": user_id,
                "username": user.get("sub"),
                "message": message_text,
                "created_at": created_at_str,
                "sender_name": sender_name,
                "sender_avatar": sender_avatar
            }
            await manager.broadcast(room_id, broadcast_data)
    except WebSocketDisconnect:
        manager.disconnect(room_id, websocket)
    except Exception:
        manager.disconnect(room_id, websocket)


@router.post("/rooms/{room_id}/delete")
def delete_chat_room(
    room_id: int,
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="未登入")

    user_id = user.get("user_id")
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    # 驗證權限：使用者必須是該聊天室的買家或賣家
    if room.buyer_id != user_id and room.seller_id != user_id:
        raise HTTPException(status_code=403, detail="無權刪除此對話框")

    # 根據角色設定對應的刪除標記
    if room.buyer_id == user_id:
        room.buyer_deleted = True
    else:
        room.seller_deleted = True

    # 如果雙方皆已標記刪除，則物理從資料庫級聯清理
    if room.buyer_deleted and room.seller_deleted:
        db.query(models.ChatMessage).filter(models.ChatMessage.room_id == room_id).delete()
        db.delete(room)
        
    db.commit()

    return {"success": True}


@router.post("/rooms/{room_id}/archive")
def toggle_archive_room(
    room_id: int,
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="未登入")

    user_id = user.get("user_id")
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    if room.buyer_id != user_id and room.seller_id != user_id:
        raise HTTPException(status_code=403, detail="權限不足")

    if room.buyer_id == user_id:
        room.buyer_archived = not room.buyer_archived
        is_arch = room.buyer_archived
    else:
        room.seller_archived = not room.seller_archived
        is_arch = room.seller_archived
    db.commit()
    return {"success": True, "is_archived": is_arch}


@router.post("/rooms/{room_id}/block")
def toggle_block_room(
    room_id: int,
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        raise HTTPException(status_code=401, detail="未登入")

    user_id = user.get("user_id")
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    if room.buyer_id != user_id and room.seller_id != user_id:
        raise HTTPException(status_code=403, detail="權限不足")

    room.is_blocked = not room.is_blocked
    db.commit()
    return {"success": True, "is_blocked": room.is_blocked}
