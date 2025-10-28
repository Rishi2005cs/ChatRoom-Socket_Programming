# Python Multi-Room Chatroom

A feature-rich chatroom application built with Python, supporting multiple chat rooms, private messaging, message history, and file sharing.

## Features

- 🏠 **Multiple Chat Rooms**: Create and join different chat rooms
- 💬 **Real-time Messaging**: Instant message delivery across rooms
- 🔒 **Private Messages**: Send direct messages to specific users
- 📜 **Message History**: Persistent chat history stored in SQLite
- 📁 **File Sharing**: Share files with room members or individuals
- 👥 **User Lists**: See who's online in each room
- 🎨 **Modern GUI**: Clean Tkinter-based interface

## Requirements

- Python 3.7 or higher
- Tkinter (usually comes with Python)
- SQLite3 (included with Python)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/YOUR_USERNAME/python-chatroom.git
cd python-chatroom
```

2. No additional dependencies needed! All modules are part of Python's standard library.

## Usage

### Starting the Server
```bash
python server.py
```

The server will start on `localhost:5000` by default.

### Connecting Clients

In separate terminal windows, run:
```bash
python client.py
```

Enter a username when prompted, and you'll be connected to the default "Lobby" room.

## Features Guide

### Chat Rooms
- **Join Room**: Select a room from the dropdown and click "Join"
- **Create Room**: Click "Create" and enter a new room name
- **Load History**: Click "Load history" to retrieve past messages

### Private Messaging
- **Method 1**: Double-click a username in the user list
- **Method 2**: Select a user and click "Private Message"
- **Method 3**: Type `/pm username message` in the chat box

### File Sharing
- Click "Send File" button
- Choose a file (max 5MB)
- Optionally specify a recipient (leave blank for room broadcast)

## Technical Details

- **Protocol**: JSON-based message protocol over TCP sockets
- **Threading**: Multi-threaded server handling concurrent connections
- **Database**: SQLite for persistent message storage
- **GUI**: Tkinter with ttk styling

## Configuration

Edit these variables in the source files to customize:

**server.py:**
- `HOST`: Server IP address (default: '0.0.0.0')
- `PORT`: Server port (default: 5000)
- `DEFAULT_ROOM`: Initial room name (default: 'Lobby')
- `DB_PATH`: Database file location (default: 'chat_history.db')

**client.py:**
- `HOST`: Server IP to connect to (default: '127.0.0.1')
- `PORT`: Server port (default: 5000)

## Protocol Messages

The application uses JSON messages with these types:
- `SETNAME`: Set username
- `JOINROOM`: Join a chat room
- `MSG`: Send room message
- `PM`: Send private message
- `HISTORYREQ`: Request message history
- `LISTROOMSREQ`: Request available rooms list

## Known Limitations

- File size limited to 5MB
- Files transmitted as base64 (not optimal for large files)
- No encryption (messages sent in plaintext)
- No user authentication

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

## Author

Your Name - [Rishi Ramesh](https://github.com/Rishi2005cs)

## Acknowledgments

- Built with Python's socket and threading modules
- GUI powered by Tkinter
- Persistent storage with SQLite
