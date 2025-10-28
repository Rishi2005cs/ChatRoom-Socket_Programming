#!/usr/bin/env python3
"""
Chatroom Server with Rooms + Persistent Message History (SQLite)
Fixed version with proper room-based user lists and synchronization
"""

import socket, threading, json, traceback, sqlite3
from datetime import datetime

HOST = '0.0.0.0'
PORT = 5000
ENC = 'utf-8'
DEFAULT_ROOM = 'Lobby'
DB_PATH = 'chat_history.db'

clients_lock = threading.Lock()
clients = {}    # username -> (conn, addr, current_room)
rooms_lock = threading.Lock()
rooms = {}      # room_name -> set(usernames)

db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                room TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()

def save_message(room, sender, message):
    ts = datetime.utcnow().isoformat()
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT INTO messages (timestamp, room, sender, message) VALUES (?, ?, ?, ?)',
                  (ts, room, sender, message))
        conn.commit()
        conn.close()

def load_history(room, limit=50):
    with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT id, timestamp, sender, message FROM messages WHERE room=? ORDER BY id DESC LIMIT ?',
                  (room, limit))
        rows = c.fetchall()
        conn.close()
    rows.reverse()
    return [{'id': r[0], 'timestamp': r[1], 'from': r[2], 'message': r[3]} for r in rows]

def send_json(conn, obj):
    try:
        raw = json.dumps(obj, separators=(',', ':')) + '\n'
        conn.sendall(raw.encode(ENC))
    except Exception:
        pass

def broadcast_room(room, obj, exclude_conn=None):
    with rooms_lock:
        members = set(rooms.get(room, set()))
    with clients_lock:
        for uname in members:
            entry = clients.get(uname)
            if not entry:
                continue
            conn, _, cur_room = entry
            if conn is exclude_conn:
                continue
            # Double check user is still in the room
            if cur_room == room:
                send_json(conn, obj)

def broadcast_all(obj, exclude_conn=None):
    with clients_lock:
        for uname, (conn, _, _) in list(clients.items()):
            if conn is exclude_conn:
                continue
            send_json(conn, obj)

def add_user_to_room(username, room):
    with rooms_lock:
        if room not in rooms:
            rooms[room] = set()
        rooms[room].add(username)

def remove_user_from_room(username, room):
    with rooms_lock:
        if room in rooms and username in rooms[room]:
            rooms[room].remove(username)
            # remove empty rooms except DEFAULT_ROOM
            if not rooms[room] and room != DEFAULT_ROOM:
                del rooms[room]

def list_rooms():
    with rooms_lock:
        return sorted(list(rooms.keys()))

def get_room_users(room):
    """Get list of users in a specific room"""
    with rooms_lock:
        if room in rooms:
            return sorted(list(rooms[room]))
        return []

def send_user_list_for_room(conn, room):
    """Send user list for a specific room"""
    users = get_room_users(room)
    send_json(conn, {'type': 'LIST', 'users': users, 'room': room})

def broadcast_user_list_to_room(room):
    """Broadcast updated user list to all members of a room"""
    users = get_room_users(room)
    broadcast_room(room, {'type': 'LIST', 'users': users, 'room': room})

def send_room_list(conn):
    send_json(conn, {'type': 'LISTROOMS', 'rooms': list_rooms()})

def broadcast_room_list():
    broadcast_all({'type': 'LISTROOMS', 'rooms': list_rooms()})

def handle_client(conn, addr):
    uname = None
    current_room = None
    buf = ''
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buf += data.decode(ENC, errors='replace')
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    send_json(conn, {'type': 'ERR', 'message': 'Bad JSON.'})
                    continue

                typ = msg.get('type')
                
                if typ == 'SETNAME':
                    requested = msg.get('name', '').strip()
                    if not requested:
                        send_json(conn, {'type': 'ERR', 'message': 'Empty name not allowed.'})
                        continue
                    with clients_lock:
                        if requested in clients:
                            send_json(conn, {'type': 'ERR', 'message': 'Name already taken.'})
                        else:
                            uname = requested
                            current_room = None  # Not in any room yet
                            clients[uname] = (conn, addr, None)
                            send_json(conn, {'type': 'OK', 'message': f'Welcome {uname}!'})
                            print(f"[+] {uname} connected from {addr}")
                            
                elif typ == 'JOINROOM':
                    if not uname:
                        send_json(conn, {'type': 'ERR', 'message': 'Set a name first.'})
                        continue
                    room = msg.get('room', DEFAULT_ROOM).strip() or DEFAULT_ROOM
                    
                    # If already in this room, just send confirmation
                    if current_room == room:
                        send_json(conn, {'type': 'OK', 'message': f'Already in {room}.'})
                        # Still send history and user list
                        hist = load_history(room, limit=50)
                        send_json(conn, {'type': 'HISTORY', 'room': room, 'messages': hist})
                        send_user_list_for_room(conn, room)
                        continue
                    
                    # Leave previous room if any
                    if current_room:
                        remove_user_from_room(uname, current_room)
                        broadcast_room(current_room, {'type': 'NOTICE', 'message': f'{uname} has left {current_room}.'})
                        broadcast_user_list_to_room(current_room)
                    
                    # Join new room
                    add_user_to_room(uname, room)
                    current_room = room
                    
                    # Update client's current room
                    with clients_lock:
                        if uname in clients:
                            clients[uname] = (conn, addr, room)
                    
                    send_json(conn, {'type': 'OK', 'message': f'Joined room {room}.'})
                    
                    # Notify room members
                    broadcast_room(room, {'type': 'NOTICE', 'message': f'{uname} has joined {room}.'}, exclude_conn=conn)
                    
                    # Send history
                    hist = load_history(room, limit=50)
                    send_json(conn, {'type': 'HISTORY', 'room': room, 'messages': hist})
                    
                    # Update user lists
                    broadcast_user_list_to_room(room)
                    broadcast_room_list()
                    
                elif typ == 'LEAVEROOM':
                    if not uname:
                        send_json(conn, {'type': 'ERR', 'message': 'Set a name first.'})
                        continue
                    if not current_room:
                        send_json(conn, {'type': 'ERR', 'message': 'Not in any room.'})
                        continue
                        
                    old_room = current_room
                    remove_user_from_room(uname, old_room)
                    
                    # Join default room
                    add_user_to_room(uname, DEFAULT_ROOM)
                    current_room = DEFAULT_ROOM
                    
                    with clients_lock:
                        if uname in clients:
                            clients[uname] = (conn, addr, DEFAULT_ROOM)
                    
                    send_json(conn, {'type': 'OK', 'message': f'Left room {old_room}, joined {DEFAULT_ROOM}.'})
                    broadcast_room(old_room, {'type': 'NOTICE', 'message': f'{uname} has left {old_room}.'})
                    broadcast_room(DEFAULT_ROOM, {'type': 'NOTICE', 'message': f'{uname} has joined {DEFAULT_ROOM}.'})
                    
                    broadcast_user_list_to_room(old_room)
                    broadcast_user_list_to_room(DEFAULT_ROOM)
                    broadcast_room_list()
                    
                elif typ == 'MSG':
                    if not uname:
                        send_json(conn, {'type': 'ERR', 'message': 'Set a name first.'})
                        continue
                    if not current_room:
                        send_json(conn, {'type': 'ERR', 'message': 'Join a room first.'})
                        continue
                        
                    room = msg.get('room', current_room)
                    text = msg.get('message', '')
                    
                    # Ensure user is in the room they're trying to message
                    if room != current_room:
                        send_json(conn, {'type': 'ERR', 'message': f'You are not in room {room}.'})
                        continue
                    
                    save_message(room, uname, text)
                    payload = {'type': 'MSG', 'from': uname, 'room': room, 'message': text, 'private': False}
                    broadcast_room(room, payload)
                    
                elif typ == 'PM':
                    to = msg.get('to')
                    text = msg.get('message', '')
                    if not uname:
                        send_json(conn, {'type': 'ERR', 'message': 'Set a name first.'})
                        continue
                    with clients_lock:
                        target = clients.get(to)
                    if target:
                        target_conn, _, _ = target
                        send_json(target_conn, {'type': 'MSG', 'from': uname, 'message': text, 'private': True})
                    else:
                        send_json(conn, {'type': 'ERR', 'message': f'User {to} not found.'})
                        
                elif typ == 'LISTREQ':
                    # Send user list for current room
                    if current_room:
                        send_user_list_for_room(conn, current_room)
                    else:
                        send_json(conn, {'type': 'LIST', 'users': [], 'room': None})
                        
                elif typ == 'LISTROOMSREQ':
                    send_room_list(conn)
                    
                elif typ == 'HISTORYREQ':
                    room = msg.get('room', DEFAULT_ROOM)
                    limit = int(msg.get('limit', 50))
                    hist = load_history(room, limit=limit)
                    send_json(conn, {'type': 'HISTORY', 'room': room, 'messages': hist})
                    
                else:
                    send_json(conn, {'type': 'ERR', 'message': 'Unknown command.'})
                    
    except Exception as e:
        print('Exception in client handler:', e)
        traceback.print_exc()
    finally:
        # cleanup
        if uname:
            with clients_lock:
                if uname in clients and clients[uname][0] is conn:
                    del clients[uname]
            
            if current_room:
                remove_user_from_room(uname, current_room)
                broadcast_room(current_room, {'type': 'NOTICE', 'message': f'{uname} has left {current_room}.'})
                broadcast_user_list_to_room(current_room)
            
            broadcast_room_list()
            print(f"[-] {uname} disconnected")
        conn.close()

def accept_loop(sock):
    print(f"Server listening on {HOST}:{PORT}")
    while True:
        conn, addr = sock.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()

def main():
    init_db()
    # ensure default room exists
    with rooms_lock:
        rooms[DEFAULT_ROOM] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(200)
    try:
        accept_loop(sock)
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        sock.close()

if __name__ == '__main__':
    main()