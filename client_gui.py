#!/usr/bin/env python3
"""
Chatroom Client (Tkinter) with Rooms + History support
Fixed version with proper room-based user lists
"""

import socket, threading, json, queue, base64, os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from datetime import datetime

HOST = '127.0.0.1'
PORT = 5000
ENC = 'utf-8'
DEFAULT_ROOM = 'Lobby'

def now_str():
    return datetime.now().strftime('%H:%M:%S')

class ChatClient:
    def __init__(self, master):
        self.master = master
        self.master.title("PyChatroom (Rooms + History)")
        self.master.geometry("900x560")
        self.sock = None
        self.queue = queue.Queue()
        self.username = None
        self.current_room = None
        self.rooms = [DEFAULT_ROOM]
        self._files = []

        self.build_ui()
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.ask_and_connect()
        self.master.after(100, self.process_queue)

    def build_ui(self):
        top = ttk.Frame(self.master)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(top, text="PyChatroom", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        self.status_lbl = ttk.Label(top, text="Not connected")
        self.status_lbl.pack(side=tk.RIGHT)

        main = ttk.Frame(self.master)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # left: chat + entry
        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # room controls
        room_frame = ttk.Frame(left)
        room_frame.pack(fill=tk.X, pady=(0,4))
        ttk.Label(room_frame, text="Room:").pack(side=tk.LEFT)
        self.room_var = tk.StringVar(value=DEFAULT_ROOM)
        self.room_cb = ttk.Combobox(room_frame, textvariable=self.room_var, values=self.rooms, state='readonly', width=20)
        self.room_cb.pack(side=tk.LEFT, padx=4)
        self.join_btn = ttk.Button(room_frame, text="Join", command=self.join_room)
        self.join_btn.pack(side=tk.LEFT)
        self.create_btn = ttk.Button(room_frame, text="Create", command=self.create_room)
        self.create_btn.pack(side=tk.LEFT, padx=(4,0))
        self.loadhist_btn = ttk.Button(room_frame, text="Load history", command=self.load_history)
        self.loadhist_btn.pack(side=tk.LEFT, padx=(6,0))

        self.text = tk.Text(left, state=tk.DISABLED, wrap='word', padx=6, pady=6)
        self.text.tag_configure('time', foreground='#666', font=("Segoe UI", 7))
        self.text.tag_configure('me', foreground='#1a73e8', font=("Segoe UI", 10, "bold"))
        self.text.tag_configure('other', foreground='#000000', font=("Segoe UI", 10))
        self.text.tag_configure('notice', foreground='#666666', font=("Segoe UI", 9, "italic"))
        self.text.pack(fill=tk.BOTH, expand=True)

        scr = ttk.Scrollbar(left, command=self.text.yview)
        scr.pack(side=tk.RIGHT, fill=tk.Y)
        self.text['yscrollcommand'] = scr.set

        bottom = ttk.Frame(self.master)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)
        self.entry = tk.Text(bottom, height=3, wrap='word')
        self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,6))
        self.entry.bind('<Control-Return>', self.on_send_shortcut)
        self.send_btn = ttk.Button(bottom, text="Send", command=self.on_send_click)
        self.send_btn.pack(side=tk.RIGHT, padx=(4,0))

        # right: user list + actions
        right = ttk.Frame(main, width=220)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        self.room_label = ttk.Label(right, text="Users in Room", font=("Segoe UI", 10, "bold"))
        self.room_label.pack(anchor='nw', pady=(2,0), padx=4)
        self.user_list = tk.Listbox(right, height=20)
        self.user_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.user_list.bind('<Double-Button-1>', self.on_user_double_click)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(btn_frame, text="Private Message", command=self.start_pm).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,4))
        ttk.Button(btn_frame, text="Send File", command=self.send_file).pack(side=tk.LEFT, expand=True, fill=tk.X)

        hint = ttk.Label(self.master, text="Tip: double-click a user to private-message. /pm username message also works.", font=("Segoe UI", 8))
        hint.pack(side=tk.BOTTOM, anchor='w', padx=8)

    def ask_and_connect(self):
        while True:
            name = simpledialog.askstring("Choose name", "Enter a username:", parent=self.master)
            if name is None:
                self.master.quit()
                return
            name = name.strip()
            if not name:
                messagebox.showwarning("Invalid", "Name can't be empty.")
                continue
            self.username = name
            break
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self.sock.setblocking(True)
        except Exception as e:
            messagebox.showerror("Connection error", f"Could not connect to server {HOST}:{PORT}\n{e}")
            self.master.quit()
            return
        
        # Start reader thread
        threading.Thread(target=self.sock_reader, daemon=True).start()
        
        # Set name first
        self.send_json({'type': 'SETNAME', 'name': self.username})
        
        # Wait a moment for server to process SETNAME, then join default room
        self.master.after(200, self.initial_join)
        
        self.status_lbl.config(text=f"Connected as {self.username}")

    def initial_join(self):
        """Join default room after connection established"""
        # Request room list
        self.send_json({'type': 'LISTROOMSREQ'})
        # Join default room
        self.send_json({'type': 'JOINROOM', 'room': DEFAULT_ROOM})
        self.current_room = DEFAULT_ROOM
        self.room_var.set(DEFAULT_ROOM)

    def send_json(self, obj):
        try:
            raw = json.dumps(obj, separators=(',', ':')) + '\n'
            self.sock.sendall(raw.encode(ENC))
        except Exception as e:
            self.append_notice(f"Send failed: {e}")

    def sock_reader(self):
        buf = ''
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    self.queue.put(('notice', 'Server disconnected.'))
                    break
                buf += data.decode(ENC, errors='replace')
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        self.queue.put(('msg', obj))
                    except Exception:
                        pass
        except Exception as e:
            self.queue.put(('error', f"Connection error: {e}"))
        finally:
            try: self.sock.close()
            except: pass

    def process_queue(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == 'msg':
                    self.handle_server_msg(data)
                elif kind == 'notice':
                    self.append_notice(data)
                elif kind == 'error':
                    self.append_notice(data)
        except queue.Empty:
            pass
        self.master.after(100, self.process_queue)

    def append_text(self, text, tags=()):
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, text + '\n', tags)
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def append_notice(self, text):
        ts = now_str()
        self.append_text(f"[{ts}] {text}", ('notice',))

    def handle_server_msg(self, obj):
        typ = obj.get('type')
        if typ == 'OK':
            self.append_notice(obj.get('message', 'OK'))
        elif typ == 'ERR':
            self.append_notice("Error: " + obj.get('message', ''))
        elif typ == 'NOTICE':
            self.append_notice(obj.get('message', ''))
        elif typ == 'LIST':
            users = obj.get('users', [])
            room = obj.get('room')
            # Only update if it's for current room
            if room == self.current_room or room is None:
                self.update_user_list(users)
        elif typ == 'LISTROOMS':
            rooms = obj.get('rooms', [])
            self.update_room_list(rooms)
        elif typ == 'MSG':
            frm = obj.get('from', 'unknown')
            room = obj.get('room')
            msg = obj.get('message', '')
            private = obj.get('private', False)
            ts = now_str()
            if private:
                self.append_text(f"[{ts}] (PM from {frm}): {msg}", ('other',))
            else:
                # Only display if belongs to current room
                if room == self.current_room:
                    tag = 'me' if frm==self.username else 'other'
                    self.append_text(f"[{ts}] {frm}: {msg}", (tag,))
        elif typ == 'HISTORY':
            room = obj.get('room')
            messages = obj.get('messages', [])
            # Only display if for current room
            if room == self.current_room:
                self.append_notice(f"--- History for {room} ({len(messages)} messages) ---")
                for m in messages:
                    ts = m.get('timestamp', '')[:19].replace('T',' ')
                    frm = m.get('from')
                    txt = m.get('message')
                    tag = 'me' if frm==self.username else 'other'
                    self.append_text(f"[{ts}] {frm}: {txt}", (tag,))
                self.append_notice(f"--- End of history ---")
        else:
            pass

    def update_user_list(self, users):
        self.user_list.delete(0, tk.END)
        for u in users:
            if u == self.username:
                self.user_list.insert(tk.END, f"{u} (you)")
            else:
                self.user_list.insert(tk.END, u)
        # Update label to show room info
        if self.current_room:
            self.room_label.config(text=f"Users in {self.current_room} ({len(users)})")

    def update_room_list(self, rooms):
        self.rooms = rooms if rooms else [DEFAULT_ROOM]
        if DEFAULT_ROOM not in self.rooms:
            self.rooms.append(DEFAULT_ROOM)
        self.rooms.sort()
        self.room_cb['values'] = self.rooms
        # Ensure current room is selected
        if self.current_room:
            self.room_var.set(self.current_room)

    def on_send_shortcut(self, event=None):
        self.on_send_click()
        return 'break'

    def on_send_click(self):
        text = self.entry.get('1.0', tk.END).strip()
        if not text:
            return
        
        if not self.current_room:
            messagebox.showwarning("Not in room", "Please join a room first.")
            return
            
        if text.startswith('/pm '):
            try:
                rest = text[4:].strip()
                to, msg = rest.split(' ', 1)
                self.send_json({'type': 'PM', 'to': to, 'message': msg})
                ts = now_str()
                self.append_text(f"[{ts}] To {to} (PM): {msg}", ('me',))
            except Exception:
                messagebox.showinfo("PM format", "Use: /pm username message")
        else:
            payload = {'type': 'MSG', 'room': self.current_room, 'message': text}
            self.send_json(payload)
        self.entry.delete('1.0', tk.END)

    def on_user_double_click(self, event=None):
        sel = self.user_list.curselection()
        if not sel:
            return
        val = self.user_list.get(sel[0])
        to = val.replace(' (you)', '')
        if to == self.username:
            return  # Can't PM yourself
        self.pm_to_user(to)

    def start_pm(self):
        sel = self.user_list.curselection()
        if not sel:
            messagebox.showinfo("Select user", "Choose a user from the list to private message.")
            return
        val = self.user_list.get(sel[0])
        to = val.replace(' (you)', '')
        if to == self.username:
            messagebox.showinfo("Invalid", "Cannot send message to yourself.")
            return
        self.pm_to_user(to)

    def pm_to_user(self, to):
        text = simpledialog.askstring("Private message", f"Send private message to {to}:", parent=self.master)
        if text:
            self.send_json({'type': 'PM', 'to': to, 'message': text})
            ts = now_str()
            self.append_text(f"[{ts}] To {to} (PM): {text}", ('me',))

    def send_file(self):
        if not self.current_room:
            messagebox.showwarning("Not in room", "Please join a room first.")
            return
            
        path = filedialog.askopenfilename(title="Choose file to send")
        if not path:
            return
        
        try:
            # Check file size (limit to 5MB for demo)
            file_size = os.path.getsize(path)
            if file_size > 5 * 1024 * 1024:
                messagebox.showwarning("File too large", "File must be under 5MB.")
                return
                
            with open(path, 'rb') as f:
                data_b64 = base64.b64encode(f.read()).decode('ascii')
        except Exception as e:
            messagebox.showerror("File error", f"Could not read file: {e}")
            return
            
        filename = os.path.basename(path)
        to = simpledialog.askstring("Send file", "Send to (leave blank to broadcast within room):", parent=self.master)
        payload = {'type': 'FILE', 'filename': filename, 'data': data_b64}
        if to:
            payload['to'] = to.strip()
        else:
            payload['room'] = self.current_room
        self.send_json(payload)
        self.append_notice(f"Sent file {filename} {'to '+to if to else 'to room '+self.current_room}")

    def create_room(self):
        name = simpledialog.askstring("Create room", "Enter new room name:", parent=self.master)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        # To create room, simply join a new room name; server will create it
        self.room_var.set(name)
        self.join_room()

    def join_room(self):
        room = self.room_var.get().strip() or DEFAULT_ROOM
        if room == self.current_room:
            messagebox.showinfo("Info", f"Already in {room}")
            return
        
        # Clear chat window for new room
        self.text.config(state=tk.NORMAL)
        self.text.delete('1.0', tk.END)
        self.text.config(state=tk.DISABLED)
        
        # Send join request
        self.send_json({'type': 'JOINROOM', 'room': room})
        
        # Update local state
        self.current_room = room
        self.append_notice(f"Joining room {room}...")
        
        # Request updated room list after joining
        self.master.after(500, lambda: self.send_json({'type': 'LISTROOMSREQ'}))

    def load_history(self):
        if not self.current_room:
            messagebox.showwarning("Not in room", "Please join a room first.")
            return
            
        limit = simpledialog.askinteger("Load history", "How many last messages?", 
                                       initialvalue=50, parent=self.master, 
                                       minvalue=1, maxvalue=1000)
        if not limit:
            return
        self.send_json({'type': 'HISTORYREQ', 'room': self.current_room, 'limit': limit})

    def on_close(self):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        self.master.quit()

def main():
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except:
        pass
    app = ChatClient(root)
    root.mainloop()

if __name__ == '__main__':
    main()