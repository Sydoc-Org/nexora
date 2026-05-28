"""1-on-1 chat: conversation list, message thread, send, upload."""

import os
import re
import uuid

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from ..db import engine_nexora_db
from ..files import is_file_allowed
from ..notifications import create_notification
from ..security import page_visibility, require_permission
from ..users import get_all_portal_users, resolve_user_icon_url


@require_permission("chat.view")
def chat_page():
    if "username" not in session:
        return redirect(url_for("login"))

    portal_users = get_all_portal_users("chat", "view")
    current_user_id = session.get("userid")

    available_users = [u for u in portal_users if str(u["userID"]) != str(current_user_id)]
    return render_template(
        "chat.html",
        logged_in_user=session.get("username"),
        userid=current_user_id,
        available_users=available_users,
        pageV=page_visibility(),
    )


@require_permission("chat.view")
def get_conversations():
    if "userid" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        query = """
            SELECT
                c.ConversationID,
                u.fullname AS OtherUserName,
                u.userID AS OtherUserID,
                c.LastMessageAt,
                (SELECT TOP 1 MessageText FROM Chat_Messages m WHERE m.ConversationID = c.ConversationID ORDER BY Timestamp DESC) as LastMessage,
                (SELECT COUNT(*) FROM Chat_Messages m WHERE m.ConversationID = c.ConversationID AND m.IsRead = 0 AND m.SenderID <> ?) as UnreadCount
            FROM Chat_Conversations c
            JOIN Chat_Participants cp1 ON c.ConversationID = cp1.ConversationID
            JOIN Chat_Participants cp2 ON c.ConversationID = cp2.ConversationID
            JOIN Users u ON cp2.UserID = u.userID
            WHERE cp1.UserID = ? AND cp2.UserID <> ?
            ORDER BY c.LastMessageAt DESC
        """
        userid = session["userid"]
        cursor.execute(query, (userid, userid, userid))

        conversations = []
        for row in cursor.fetchall():
            conversations.append(
                {
                    "id": row.ConversationID,
                    "name": row.OtherUserName,
                    "other_user_id": row.OtherUserID,
                    "last_message": row.LastMessage or _("No messages yet"),
                    "last_time": row.LastMessageAt.strftime("%Y-%m-%d %H:%M"),
                    "unread": row.UnreadCount,
                    "avatar": resolve_user_icon_url(row.OtherUserID),
                }
            )

        return jsonify(conversations)
    except Exception as e:
        current_app.logger.error(f"Error fetching conversations: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("chat.view")
def start_conversation(target_user_id):
    current_user_id = session["userid"]
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        check_query = """
            SELECT cp1.ConversationID
            FROM Chat_Participants cp1
            JOIN Chat_Participants cp2 ON cp1.ConversationID = cp2.ConversationID
            WHERE cp1.UserID = ? AND cp2.UserID = ?
        """
        cursor.execute(check_query, (current_user_id, target_user_id))
        row = cursor.fetchone()

        if row:
            return jsonify({"success": True, "conversation_id": row[0]})

        cursor.execute(
            "INSERT INTO Chat_Conversations (CreatedAt) OUTPUT INSERTED.ConversationID VALUES (GETDATE())"
        )
        new_conv_id = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO Chat_Participants (ConversationID, UserID) VALUES (?, ?)",
            (new_conv_id, current_user_id),
        )
        cursor.execute(
            "INSERT INTO Chat_Participants (ConversationID, UserID) VALUES (?, ?)",
            (new_conv_id, target_user_id),
        )

        conn.commit()
        return jsonify({"success": True, "conversation_id": new_conv_id})
    except Exception as e:
        current_app.logger.error(f"Error creating conversation: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("chat.view")
def get_chat_messages(conversation_id):
    userid = session["userid"]
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM Chat_Participants WHERE ConversationID = ? AND UserID = ?",
            (conversation_id, userid),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Unauthorized"}), 403

        cursor.execute(
            "UPDATE Chat_Messages SET IsRead = 1 WHERE ConversationID = ? AND SenderID <> ?",
            (conversation_id, userid),
        )
        conn.commit()

        query = """
            SELECT m.MessageID, m.SenderID, m.MessageText, m.Timestamp, u.username
            FROM Chat_Messages m
            JOIN Users u ON m.SenderID = u.userID
            WHERE m.ConversationID = ?
            ORDER BY m.Timestamp ASC
        """
        cursor.execute(query, (conversation_id,))

        messages = []
        for row in cursor.fetchall():
            messages.append(
                {
                    "id": row.MessageID,
                    "is_me": str(row.SenderID) == str(userid),
                    "text": row.MessageText,
                    "sender": row.username,
                    "time": row.Timestamp.strftime("%H:%M"),
                    "avatar": resolve_user_icon_url(row.SenderID),
                }
            )

        return jsonify(messages)
    except Exception as e:
        current_app.logger.error(f"Error fetching messages: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("chat.view")
def send_chat_message(conversation_id):
    data = request.get_json()
    message_text = data.get("message")
    userid = session["userid"]

    if not message_text:
        return jsonify({"success": False}), 400

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM Chat_Participants WHERE ConversationID = ? AND UserID = ?",
            (conversation_id, userid),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Unauthorized"}), 403

        cursor.execute(
            """
            INSERT INTO Chat_Messages (ConversationID, SenderID, MessageText)
            VALUES (?, ?, ?)
            """,
            (conversation_id, userid, message_text),
        )

        cursor.execute(
            "UPDATE Chat_Conversations SET LastMessageAt = GETDATE() WHERE ConversationID = ?",
            (conversation_id,),
        )

        cursor.execute(
            "SELECT UserID FROM Chat_Participants WHERE ConversationID = ? AND UserID <> ?",
            (conversation_id, userid),
        )
        other_user = cursor.fetchone()
        if other_user:
            workitem_match = re.search(r"/(\d+)", message_text)
            if workitem_match:
                notif_msg = (
                    f"{session['username']} mentioned workitem {workitem_match.group(1)} in chat"
                )
            else:
                notif_msg = f"New message from {session['username']}"

            notification_link = url_for("chat_page", _external=False)
            create_notification(
                other_user.UserID, notif_msg, link=notification_link, icon="fa-comments"
            )

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error sending message: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@require_permission("chat.view")
def upload_chat_file(conversation_id):
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file"}), 400

    file = request.files["file"]
    userid = session["userid"]

    if file and is_file_allowed(file.filename, file.stream):
        filename = secure_filename(file.filename)
        unique_filename = f"chat_{uuid.uuid4().hex}_{filename}"

        upload_path = os.path.join(current_app.root_path, "static", "uploads", "chat")
        os.makedirs(upload_path, exist_ok=True)

        file.save(os.path.join(upload_path, unique_filename))

        file_url = url_for("static", filename=f"uploads/chat/{unique_filename}")
        message_text = f"FILE:{filename}|{file_url}"

        conn = None
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO Chat_Messages (ConversationID, SenderID, MessageText)
                VALUES (?, ?, ?)
                """,
                (conversation_id, userid, message_text),
            )
            cursor.execute(
                "UPDATE Chat_Conversations SET LastMessageAt = GETDATE() WHERE ConversationID = ?",
                (conversation_id,),
            )
            conn.commit()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            if conn:
                conn.close()

    return jsonify({"success": False, "message": "Invalid file type"}), 400


def register_routes(app):
    app.add_url_rule("/chat", endpoint="chat_page", view_func=chat_page)
    app.add_url_rule(
        "/api/chat/conversations", endpoint="get_conversations", view_func=get_conversations
    )
    app.add_url_rule(
        "/api/chat/start/<int:target_user_id>",
        endpoint="start_conversation",
        view_func=start_conversation,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/chat/<int:conversation_id>/messages",
        endpoint="get_chat_messages",
        view_func=get_chat_messages,
    )
    app.add_url_rule(
        "/api/chat/<int:conversation_id>/send",
        endpoint="send_chat_message",
        view_func=send_chat_message,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/chat/<int:conversation_id>/upload",
        endpoint="upload_chat_file",
        view_func=upload_chat_file,
        methods=["POST"],
    )
