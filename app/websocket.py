from fastapi import WebSocket
from typing import Dict, List, Set, Any
import json
import uuid
import os
from datetime import datetime
from .firestore_manager import FirestoreManager
import asyncio

class ConnectionManager:
    def __init__(self, firestore_manager=None):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.room_users: Dict[str, Set[str]] = {}
        self.user_rooms: Dict[str, str] = {}  # user_id -> room_id
        self.user_names: Dict[str, str] = {}  # user_id -> user_name
        self.connection_users: Dict[WebSocket, Dict] = {}  # websocket -> user_info
        self.canvas_states: Dict[str, List[Dict[str, Any]]] = {}
        self.active_strokes: Dict[str, Dict[str, Dict]] = {}  # room_id -> stroke_id -> stroke_data
        self.empty_rooms_scheduled: Dict[str, datetime] = {}
        self.last_cleanup_time = datetime.now()
        self._disconnecting: Set[WebSocket] = set()  # Prevent recursive disconnect calls
        
        # NEW: Heartbeat tracking for connection health
        self.connection_heartbeats: Dict[WebSocket, datetime] = {}  # websocket -> last_heartbeat
        self.connection_timeout_minutes = int(os.getenv("WEBSOCKET_CONNECTION_TIMEOUT", "300000")) // 60000  # Convert milliseconds to minutes
        
        # Use provided FirestoreManager or create new one
        if firestore_manager:
            self.firestore_manager = firestore_manager
        else:
            from .firestore_manager import FirestoreManager
            self.firestore_manager = FirestoreManager()
        
        print("🔄 ConnectionManager initialized with cleanup system and heartbeat tracking")

    async def _cleanup_scheduler(self):
        """Scheduler that runs every minute to clean up empty rooms after 5 minutes and stale connections"""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._cleanup_empty_rooms()
                await self._cleanup_stale_connections()
            except Exception as e:
                print(f"Error in cleanup scheduler: {e}")

    async def _cleanup_stale_connections(self):
        """Clean up connections that haven't sent a heartbeat in the timeout period"""
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(minutes=self.connection_timeout_minutes)
        
        stale_connections = []
        for websocket, last_heartbeat in self.connection_heartbeats.items():
            if last_heartbeat < cutoff_time:
                stale_connections.append(websocket)
        
        if stale_connections:
            print(f"🧹 Found {len(stale_connections)} stale connections (no heartbeat for {self.connection_timeout_minutes}+ minutes)")
            
            for websocket in stale_connections:
                try:
                    # Find which room this connection belongs to
                    room_id = None
                    for room, connections in self.active_connections.items():
                        if websocket in connections:
                            room_id = room
                            break
                    
                    if room_id:
                        print(f"🔄 Disconnecting stale connection from room {room_id}")
                        try:
                            # Send a specific close code for stale connections
                            await websocket.close(code=4002, reason="Connection timeout - no heartbeat received")
                        except:
                            # If close fails, just remove from tracking
                            pass
                        await self.disconnect(websocket, room_id)
                    else:
                        # Connection not in any room, just remove from tracking
                        if websocket in self.connection_heartbeats:
                            del self.connection_heartbeats[websocket]
                        if websocket in self.connection_users:
                            del self.connection_users[websocket]
                            
                except Exception as e:
                    print(f"❌ Error cleaning up stale connection: {e}")
                    # Remove from tracking even if disconnect fails
                    if websocket in self.connection_heartbeats:
                        del self.connection_heartbeats[websocket]
                    if websocket in self.connection_users:
                        del self.connection_users[websocket]
        else:
            print(f"✅ No stale connections found. Active connections: {len(self.connection_heartbeats)}")

    async def _cleanup_empty_rooms(self):
        """Clean up rooms that have been empty for 5+ minutes"""
        from datetime import timedelta
        room_cleanup_delay = int(os.getenv("ROOM_CLEANUP_DELAY", "300")) // 60  # Convert seconds to minutes
        cutoff_time = datetime.now() - timedelta(minutes=room_cleanup_delay)
        
        rooms_to_cleanup = []
        for room_id, scheduled_time in self.empty_rooms_scheduled.items():
            if scheduled_time < cutoff_time:
                rooms_to_cleanup.append(room_id)
        
        for room_id in rooms_to_cleanup:
            room_cleanup_delay = int(os.getenv("ROOM_CLEANUP_DELAY", "300")) // 60
            print(f"🧹 Cleaning up room {room_id} (empty for {room_cleanup_delay}+ minutes)")
            await self._cleanup_room_data(room_id)
            del self.empty_rooms_scheduled[room_id]

    async def _cleanup_room_data(self, room_id: str):
        """Clean up all data for a specific room"""
        try:
            # Clean up in-memory data
            if room_id in self.canvas_states:
                del self.canvas_states[room_id]
            if room_id in self.active_strokes:
                del self.active_strokes[room_id]
            if room_id in self.room_users:
                del self.room_users[room_id]
            
            # Clean up Firestore data
            self.firestore_manager.cleanup_room_data(room_id)
            
            print(f"✅ Cleaned up room {room_id}")
        except Exception as e:
            print(f"❌ Error cleaning up room {room_id}: {e}")

    def _schedule_room_cleanup(self, room_id: str):
        """Schedule a room for cleanup in 5 minutes"""
        self.empty_rooms_scheduled[room_id] = datetime.now()
        room_cleanup_delay = int(os.getenv("ROOM_CLEANUP_DELAY", "300")) // 60
        print(f"📅 Scheduled cleanup: {room_id} ({room_cleanup_delay}min)")
        print(f"📊 Scheduled rooms: {list(self.empty_rooms_scheduled.keys())}")

    def trigger_cleanup_if_needed(self):
        """Manually trigger cleanup if enough time has passed"""
        from datetime import timedelta
        current_time = datetime.now()
        
        # Check if it's time to run cleanup (every minute)
        if current_time - self.last_cleanup_time > timedelta(minutes=1):
            print(f"🕐 Cleanup check triggered")
            self.last_cleanup_time = current_time
            
            # First, clean up stuck auto-generated users
            self._cleanup_stuck_auto_users()
            
            # Run cleanup synchronously
            room_cleanup_delay = int(os.getenv("ROOM_CLEANUP_DELAY", "300")) // 60
            cutoff_time = current_time - timedelta(minutes=room_cleanup_delay)
            rooms_to_cleanup = []
            
            for room_id, scheduled_time in self.empty_rooms_scheduled.items():
                if scheduled_time < cutoff_time:
                    rooms_to_cleanup.append(room_id)
            
            if rooms_to_cleanup:
                print(f"🧹 Cleaning up {len(rooms_to_cleanup)} rooms: {rooms_to_cleanup}")
                for room_id in rooms_to_cleanup:
                    print(f"🧹 Cleaning up: {room_id}")
                    self._cleanup_room_data_sync(room_id)
                    del self.empty_rooms_scheduled[room_id]
            else:
                print(f"ℹ️ No rooms ready for cleanup")

    def _cleanup_room_data_sync(self, room_id: str):
        """Synchronous version of room data cleanup"""
        try:
            print(f"🧹 Cleaning up: {room_id}")
            
            # Clean up in-memory data
            if room_id in self.canvas_states:
                del self.canvas_states[room_id]
            if room_id in self.active_strokes:
                del self.active_strokes[room_id]
            if room_id in self.room_users:
                del self.room_users[room_id]
            
            # Clean up Firestore data
            success = self.firestore_manager.cleanup_room_data(room_id)
            if success:
                print(f"✅ Cleaned up: {room_id}")
            else:
                print(f"❌ Failed to clean up: {room_id}")
                
        except Exception as e:
            print(f"❌ Error cleaning up {room_id}: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_stuck_auto_users(self):
        """Clean up auto-generated users that are stuck in rooms"""
        try:
            for room_id in list(self.active_connections.keys()):
                if room_id not in self.active_connections:
                    continue
                    
                connections_to_remove = []
                for ws in self.active_connections[room_id]:
                    if ws in self.connection_users:
                        user_info = self.connection_users[ws]
                        user_name = user_info.get("name", "")
                        user_id = user_info.get("id", "")
                        
                        # If it's an auto-generated user, mark for removal
                        if user_name.startswith("User "):
                            print(f"🧹 Removing stuck auto-user: {user_name} from {room_id}")
                            connections_to_remove.append(ws)
                            
                            # Remove from room_users and Firestore
                            if room_id in self.room_users:
                                self.room_users[room_id].discard(user_id)
                            self.firestore_manager.remove_user_from_room(room_id, user_id)
                
                # Remove the connections
                for ws in connections_to_remove:
                    if ws in self.active_connections[room_id]:
                        self.active_connections[room_id].remove(ws)
                    if ws in self.connection_users:
                        del self.connection_users[ws]
                
                # If room is now empty, schedule cleanup
                if room_id in self.active_connections and len(self.active_connections[room_id]) == 0:
                    print(f"🔄 Room {room_id} is now empty after auto-user cleanup. Scheduling cleanup.")
                    self._schedule_room_cleanup(room_id)
                    
        except Exception as e:
            print(f"❌ Error cleaning up stuck auto-users: {e}")
            import traceback
            traceback.print_exc()

    async def connect(self, websocket: WebSocket, room_id: str, user_name: str = None):
        await websocket.accept()
        
        # Check if room exists in Firestore - don't create automatically
        if not self.firestore_manager.room_exists(room_id):
            print(f"❌ Room {room_id} doesn't exist in Firestore. User must create room first.")
            await websocket.close(code=4004, reason="Room does not exist")
            raise Exception(f"Room {room_id} does not exist")
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
            self.room_users[room_id] = set()
        
        self.active_connections[room_id].append(websocket)
        
        # Check if user with this name already exists in the room
        existing_user_id = None
        if user_name:
            # Look for existing user with the same name in this room
            for ws, user_info in self.connection_users.items():
                if (user_info.get("name") == user_name and 
                    user_info.get("room_id") == room_id and
                    ws in self.active_connections.get(room_id, [])):
                    existing_user_id = user_info.get("id")
                    break
        
        if existing_user_id:
            # Reuse existing user
            user_id = existing_user_id
            print(f"Reusing existing user '{user_name}' (ID: {user_id}) in room '{room_id}'")
            
            # Update global user status to online for rejoining users
            if not user_name.startswith("User "):
                self.firestore_manager.update_global_user_status(user_name, is_online=True)
                print(f"Updated global user {user_name} status to online (rejoining)")
        else:
            # Generate new user ID if not provided
            user_id = str(uuid.uuid4())[:8]
            if not user_name:
                user_name = f"User {user_id}"
            print(f"Creating new user '{user_name}' (ID: {user_id}) in room '{room_id}'")
            
            # Check global username availability for non-auto-generated usernames
            if not user_name.startswith("User "):
                is_available = self.firestore_manager.is_username_available_globally(user_name)
                if not is_available:
                    # Username is taken globally - reject the connection instead of creating auto-user
                    print(f"❌ Username '{user_name}' is taken globally. Rejecting connection.")
                    await websocket.close(code=4001, reason="Username is already taken")
                    raise Exception(f"Username '{user_name}' is taken globally.")
                else:
                    # Register the username globally
                    self.firestore_manager.register_global_user(user_name, user_id, room_id)
                    print(f"Registered global user: {user_name}")
            
        # Store user information
        user_info = {
            "id": user_id,
            "name": user_name,
            "room_id": room_id,
            "joined_at": datetime.now().isoformat()
        }
        self.connection_users[websocket] = user_info
        
        # NEW: Initialize heartbeat tracking
        self.connection_heartbeats[websocket] = datetime.now()
        
        # Add user to room
        if room_id not in self.room_users:
            self.room_users[room_id] = set()
        self.room_users[room_id].add(user_id)
        
        # Only add to room_users if this is a new user
        if not existing_user_id:
            self.room_users[room_id].add(user_id)
            # Add user to Firestore only for new users
            self.firestore_manager.add_user_to_room(room_id, user_id, user_name)
        
        # Cancel scheduled cleanup if this room was scheduled for cleanup
        if room_id in self.empty_rooms_scheduled:
            del self.empty_rooms_scheduled[room_id]
            print(f"✅ Cancelled cleanup for room {room_id} - user rejoined")
        
        # Debug: Print connection info
        print(f"Room '{room_id}' has {len(self.active_connections[room_id])} connections")
        print(f"Users: {[self.connection_users.get(ws, {}).get('name', 'Unknown') for ws in self.active_connections[room_id]]}")
        
        # Send current room info to the new user
        room_info = self.get_room_info(room_id)
        await websocket.send_text(json.dumps({
            "type": "room_info",
            "data": room_info,
            "timestamp": datetime.now().isoformat()
        }))
        
        # Send current canvas state to the new user
        # First try to get from in-memory state (most up-to-date)
        canvas_state = []
        if room_id in self.canvas_states:
            canvas_state = self.canvas_states[room_id].copy()
            print(f"📊 Canvas: {len(canvas_state)} strokes (memory) -> {user_name}")
        
        # If no in-memory state, try to load from Firestore
        if not canvas_state:
            canvas_state = self.firestore_manager.get_canvas_state(room_id)
            if canvas_state:
                # Also load into memory for future use
                self.canvas_states[room_id] = canvas_state.copy()
                print(f"📊 Canvas: {len(canvas_state)} strokes (Firestore) -> {user_name}")
        
        # Send canvas state to the new user
        if canvas_state:
            canvas_message = {
                "type": "canvas_state",
                "data": {
                    "drawings": canvas_state
                },
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(canvas_message))
            print(f"✅ Canvas sent to {user_name}")
        else:
            print(f"ℹ️ No canvas data for room {room_id}")
        
        # Only notify others if this is a new user
        if not existing_user_id:
            await self.broadcast_user_joined(room_id, {
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": datetime.now().isoformat()
            }, websocket)

            # Send updated room info to all users in the room
            await self.broadcast_room_info(room_id)

    async def disconnect(self, websocket: WebSocket, room_id: str):
        # Prevent recursive disconnect calls
        if websocket in self._disconnecting:
            return
        
        self._disconnecting.add(websocket)
        
        try:
            if room_id in self.active_connections:
                if websocket in self.active_connections[room_id]:
                    self.active_connections[room_id].remove(websocket)
                
                # Remove user from room
                if websocket in self.connection_users:
                    user_id = self.connection_users[websocket]["id"]
                    user_name = self.connection_users[websocket].get("name", f"User {user_id}")
                    print(f"User {user_name} (ID: {user_id}) leaving room {room_id}")
                    
                    # Check if this user has other active connections in the same room
                    other_connections = [
                        ws for ws in self.active_connections[room_id]
                        if ws in self.connection_users and 
                        self.connection_users[ws].get("id") == user_id
                    ]
                    
                    # Always remove auto-generated users immediately
                    is_auto_generated = user_name.startswith("User ")
                    
                    # For auto-generated users, always remove them immediately
                    if is_auto_generated:
                        print(f"🧹 Removing auto-generated user {user_name} immediately")
                        if room_id in self.room_users:
                            self.room_users[room_id].discard(user_id)
                        self.firestore_manager.remove_user_from_room(room_id, user_id)
                        
                        # Notify others that user left
                        await self.broadcast_user_left(room_id, {
                            "user_id": user_id,
                            "user_name": user_name,
                            "timestamp": datetime.now().isoformat()
                        }, websocket)
                        
                        # Send updated room info to remaining users
                        await self.broadcast_room_info(room_id)
                    else:
                        # Only remove from room_users and Firestore if no other connections exist
                        if not other_connections:
                            if room_id in self.room_users:
                                self.room_users[room_id].discard(user_id)
                            
                            # Remove user from Firestore
                            self.firestore_manager.remove_user_from_room(room_id, user_id)
                            
                            # Update global user status to offline instead of unregistering
                            # This allows the user to rejoin with the same username
                            self.firestore_manager.update_global_user_status(user_name, is_online=False)
                            print(f"Updated global user {user_name} status to offline")
                            
                            # Notify others that user left
                            await self.broadcast_user_left(room_id, {
                                "user_id": user_id,
                                "user_name": user_name,
                                "timestamp": datetime.now().isoformat()
                            }, websocket)
                            
                            # Send updated room info to remaining users
                            room_info = self.get_room_info(room_id)
                            print(f"Room {room_id} now has {room_info['count']} users: {[u.get('name', 'Unknown') for u in room_info['users']]}")
                            await self.broadcast_room_info(room_id)
                        else:
                            print(f"User {user_name} still has {len(other_connections)} other connections in room {room_id}")
                    
                    del self.connection_users[websocket]
                
                # Check if room is empty (no real users, only auto-generated users)
                real_users_in_room = []
                auto_users_in_room = []
                if room_id in self.active_connections:
                    for ws in self.active_connections[room_id]:
                        if ws in self.connection_users:
                            user_info = self.connection_users[ws]
                            user_name = user_info.get("name", "")
                            # Separate real users from auto-generated users
                            if user_name.startswith("User "):
                                auto_users_in_room.append(user_name)
                            else:
                                real_users_in_room.append(user_name)
                
                # If there are only auto-generated users, remove them immediately
                if len(real_users_in_room) == 0 and len(auto_users_in_room) > 0:
                    print(f"🧹 Room {room_id} has only auto-generated users. Removing them immediately.")
                    # Remove all auto-generated users
                    for ws in list(self.active_connections[room_id]):
                        if ws in self.connection_users:
                            user_info = self.connection_users[ws]
                            user_name = user_info.get("name", "")
                            if user_name.startswith("User "):
                                user_id = user_info.get("id", "")
                                print(f"🧹 Removing auto-user: {user_name}")
                                self.firestore_manager.remove_user_from_room(room_id, user_id)
                                if room_id in self.room_users:
                                    self.room_users[room_id].discard(user_id)
                                del self.connection_users[ws]
                                self.active_connections[room_id].remove(ws)
                
                # Clean up empty rooms (no real users left)
                if room_id in self.active_connections and len(self.active_connections[room_id]) == 0:
                    del self.active_connections[room_id]
                    # Schedule cleanup for this room in 5 minutes
                    self._schedule_room_cleanup(room_id)
                    # Trigger cleanup check
                    self.trigger_cleanup_if_needed()
                elif len(real_users_in_room) == 0 and room_id in self.active_connections:
                    # No real users left, only auto-generated users - schedule cleanup
                    print(f"🔄 No real users left in {room_id}, only auto-generated users. Scheduling cleanup.")
                    self._schedule_room_cleanup(room_id)
                    self.trigger_cleanup_if_needed()
                
                if room_id in self.room_users and len(self.room_users[room_id]) == 0:
                    del self.room_users[room_id]
                # Don't immediately clean up canvas state - keep it for 5 minutes
        finally:
            # Always remove from disconnecting set
            self._disconnecting.discard(websocket)
            
            # NEW: Clean up heartbeat tracking
            if websocket in self.connection_heartbeats:
                del self.connection_heartbeats[websocket]

    async def broadcast_draw(self, room_id: str, data: dict, sender: WebSocket):
        if room_id in self.active_connections:
            # Store the drawing in canvas state (in-memory for performance)
            if room_id not in self.canvas_states:
                self.canvas_states[room_id] = []
            self.canvas_states[room_id].append(data)
            
            # Save canvas state to Firestore
            self.firestore_manager.save_canvas_state(room_id, self.canvas_states[room_id])
            
            message = {
                "type": "draw",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                        await self.disconnect(connection, room_id)

    async def broadcast_stroke_start(self, room_id: str, stroke_data: dict, sender: WebSocket):
        """Broadcast stroke start event"""
        if room_id in self.active_connections:
            # Initialize active strokes for this room if not exists
            if room_id not in self.active_strokes:
                self.active_strokes[room_id] = {}
            
            # Store the stroke
            stroke_id = stroke_data.get("id")
            self.active_strokes[room_id][stroke_id] = stroke_data
            
            message = {
                "type": "stroke_start",
                "data": stroke_data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Broadcast to all other users
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        broken_connections.append(connection)
            
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    async def broadcast_stroke_point(self, room_id: str, stroke_id: str, point: dict, sender: WebSocket):
        """Broadcast stroke point event"""
        if room_id in self.active_connections and room_id in self.active_strokes:
            # Update the stroke with new point
            if stroke_id in self.active_strokes[room_id]:
                stroke = self.active_strokes[room_id][stroke_id]
                if "points" not in stroke:
                    stroke["points"] = []
                stroke["points"].append(point)
            
            message = {
                "type": "stroke_point",
                "data": {
                    "strokeId": stroke_id,
                    "point": point
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Broadcast to all other users
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        broken_connections.append(connection)
            
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    async def broadcast_stroke_end(self, room_id: str, stroke_id: str, sender: WebSocket):
        """Broadcast stroke end event and save to canvas state"""
        if room_id in self.active_connections and room_id in self.active_strokes:
            # Get the completed stroke
            if stroke_id in self.active_strokes[room_id]:
                stroke = self.active_strokes[room_id][stroke_id]
                
                # Add to canvas state
                if room_id not in self.canvas_states:
                    self.canvas_states[room_id] = []
                self.canvas_states[room_id].append(stroke)
                
                # Save to Firestore
                self.firestore_manager.save_canvas_state(room_id, self.canvas_states[room_id])
                
                # Remove from active strokes
                del self.active_strokes[room_id][stroke_id]
            
            message = {
                "type": "stroke_end",
                "data": {
                    "strokeId": stroke_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Broadcast to all other users
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        broken_connections.append(connection)
            
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    async def broadcast_chat(self, room_id: str, data: dict, sender: WebSocket):
        if room_id in self.active_connections:
            # Save chat message to Firestore
            user_id = data.get("userId", "unknown")
            user_name = data.get("userName", "Unknown")
            message_text = data.get("message", "")
            file_url = data.get("fileUrl")
            file_name = data.get("fileName")
            file_type = data.get("fileType")
            
            self.firestore_manager.save_chat_message(
                room_id, user_id, user_name, message_text, file_url, file_name, file_type
            )
            
            message = {
                "type": "chat",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            print(f"Broadcasting chat message to {len(connections)} connections in room {room_id}")
            print(f"Sender excluded, broadcasting to {len([c for c in connections if c != sender])} other connections")
            
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                        print(f"Sent chat message to connection")
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
                        print(f"Failed to send chat message to connection")
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                        await self.disconnect(connection, room_id)

    async def broadcast_user_joined(self, room_id: str, data: dict, sender: WebSocket):
        if room_id in self.active_connections:
            message = {
                "type": "user_joined",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                        await self.disconnect(connection, room_id)

    async def broadcast_user_left(self, room_id: str, data: dict, sender: WebSocket):
        if room_id in self.active_connections:
            message = {
                "type": "user_left",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                        await self.disconnect(connection, room_id)

    def get_room_users(self, room_id: str) -> List[str]:
        if room_id in self.room_users:
            return list(self.room_users[room_id])
        return []

    def get_connection_count(self, room_id: str) -> int:
        if room_id in self.active_connections:
            return len(self.active_connections[room_id])
        return 0 

    async def update_user_name(self, websocket: WebSocket, new_name: str):
        """Update user name and handle global registration"""
        if websocket in self.connection_users:
            old_name = self.connection_users[websocket]["name"]
            user_id = self.connection_users[websocket]["id"]
            room_id = self.connection_users[websocket]["room_id"]
            
            # Check if new username is available globally
            if not new_name.startswith("User "):
                is_available = self.firestore_manager.is_username_available_globally(new_name, user_id)
                if not is_available:
                    print(f"Username {new_name} is not available globally")
                    return False
            
            # Update the username in connection_users
            self.connection_users[websocket]["name"] = new_name
            
            # Update in Firestore
            self.firestore_manager.update_user_name(room_id, user_id, new_name)
            
            # Handle global registration
            if not old_name.startswith("User "):
                self.firestore_manager.unregister_global_user(old_name)
            
            if not new_name.startswith("User "):
                self.firestore_manager.register_global_user(new_name, user_id, room_id)
            
            # Broadcast name change to other users
            await self.broadcast_name_change(room_id, {
                "user_id": user_id,
                "old_name": old_name,
                "new_name": new_name,
                "timestamp": datetime.now().isoformat()
            }, websocket)
            
            print(f"User {old_name} changed name to {new_name}")
            return True
        
        return False

    async def broadcast_name_change(self, room_id: str, data: dict, sender: WebSocket):
        """Broadcast user name change to all users in room"""
        if room_id in self.active_connections:
            message = {
                "type": "name_change",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    def get_room_info(self, room_id: str) -> dict:
        """Get detailed information about a room"""
        if room_id not in self.active_connections:
            return {"room_id": room_id, "users": [], "count": 0}
        
        # Clean up any broken connections first
        active_connections = []
        for websocket in self.active_connections[room_id]:
            if websocket in self.connection_users:
                active_connections.append(websocket)
            else:
                # Remove orphaned connections
                self.active_connections[room_id].remove(websocket)
        
        # Update the active connections list
        self.active_connections[room_id] = active_connections
        
        # Get users from Firestore
        firestore_users = self.firestore_manager.get_room_users(room_id)
        
        # Filter out auto-generated usernames and convert datetime objects
        users = []
        for user in firestore_users:
            if user.get("name") and not user["name"].startswith("User "):
                # Convert datetime objects to ISO strings for JSON serialization
                user_data = {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "joined_at": user.get("joined_at").isoformat() if hasattr(user.get("joined_at"), 'isoformat') else str(user.get("joined_at", "")),
                    "is_online": user.get("is_online", True)
                }
                users.append(user_data)
        
        print(f"Room {room_id} - Firestore users: {[u.get('name', 'Unknown') for u in users]}")
        
        return {
            "room_id": room_id,
            "users": users,
            "count": len(users)
        }

    async def broadcast_room_info(self, room_id: str):
        """Broadcast updated room info to all users in the room"""
        if room_id in self.active_connections:
            room_info = self.get_room_info(room_id)
            message = {
                "type": "room_info",
                "data": room_info,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    # Mark for removal instead of immediate disconnect
                    broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    def get_all_users(self) -> List[str]:
        """Get all currently active usernames (excluding auto-generated ones)"""
        usernames = set()
        for user_info in self.connection_users.values():
            if "name" in user_info:
                username = user_info["name"]
                # Only include usernames that are not auto-generated (not starting with "User ")
                if not username.startswith("User "):
                    usernames.add(username)
        return list(usernames)

    def is_username_available(self, username: str, current_username: str = None) -> bool:
        """Check if a username is available"""
        # Don't allow usernames that start with "User " (auto-generated)
        if username.startswith("User "):
            return False
            
        all_users = self.get_all_users()
        # If checking for current username, exclude it from the check
        if current_username and username == current_username:
            return True
        return username not in all_users

    def change_username(self, old_username: str, new_username: str) -> bool:
        """Change a user's username across all connections"""
        if not self.is_username_available(new_username, old_username):
            return False
        
        # Find all connections with the old username and update them
        updated_count = 0
        for websocket, user_info in self.connection_users.items():
            if user_info.get("name") == old_username:
                user_info["name"] = new_username
                updated_count += 1
        
        return updated_count > 0

    def get_all_rooms(self) -> List[Dict]:
        """Get all active rooms with metadata"""
        rooms = []
        for room_id in self.active_connections.keys():
            room_info = self.get_room_info(room_id)
            room_meta = self.room_metadata.get(room_id, {})
            
            rooms.append({
                "id": room_id,
                "name": room_id,  # For now, room_id is the name
                "userCount": room_info["count"],
                "createdAt": room_meta.get("created_at", datetime.now().isoformat()),
                "createdBy": room_meta.get("created_by", "Unknown")
            })
        return rooms

    def create_room(self, room_name: str, created_by: str) -> str:
        """Create a new room"""
        room_id = room_name  # Use room name as ID for simplicity

        # Initialize room if it doesn't exist
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
            self.room_users[room_id] = set()

        # Store room metadata
        self.room_metadata[room_id] = {
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "name": room_name
        }

        return room_id

    async def broadcast_clear_canvas(self, room_id: str, sender: WebSocket):
        """Clear canvas and notify all users"""
        if room_id in self.active_connections:
            # Clear canvas state (in-memory for performance)
            if room_id in self.canvas_states:
                self.canvas_states[room_id] = []
            
            # Clear canvas state in Firestore
            self.firestore_manager.save_canvas_state(room_id, [])
            
            message = {
                "type": "clear_canvas",
                "data": {},
                "timestamp": datetime.now().isoformat()
            }
            
            # Create a copy of the list to avoid modification during iteration
            connections = self.active_connections[room_id].copy()
            broken_connections = []
            for connection in connections:
                if connection != sender:  # Don't send back to sender
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        # Mark for removal instead of immediate disconnect
                        broken_connections.append(connection)
            
            # Remove broken connections after iteration
            for connection in broken_connections:
                await self.disconnect(connection, room_id)

    def cleanup_connections(self):
        """Clean up broken connections and auto-generated usernames"""
        # Remove broken connections
        for room_id in list(self.active_connections.keys()):
            active_connections = []
            for websocket in self.active_connections[room_id]:
                if websocket in self.connection_users:
                    active_connections.append(websocket)
                else:
                    # Remove orphaned connections
                    if websocket in self.active_connections[room_id]:
                        self.active_connections[room_id].remove(websocket)
            
            # Update the active connections list
            self.active_connections[room_id] = active_connections
            
            # Clean up empty rooms
            if len(active_connections) == 0:
                del self.active_connections[room_id]
                if room_id in self.room_users:
                    del self.room_users[room_id]
                if room_id in self.canvas_states:
                    del self.canvas_states[room_id]
        
        # Clean up duplicate and auto-generated users
        self.cleanup_duplicate_users()

    def cleanup_duplicate_users(self):
        """Remove duplicate users and auto-generated users that are no longer connected"""
        # Track users by name in each room
        room_user_names = {}
        
        # Build a map of room -> set of usernames
        for websocket, user_info in self.connection_users.items():
            room_id = user_info.get("room_id")
            user_name = user_info.get("name")
            
            if room_id and user_name:
                if room_id not in room_user_names:
                    room_user_names[room_id] = set()
                room_user_names[room_id].add(user_name)
        
        # Clean up auto-generated users that are no longer connected
        for room_id in list(self.room_users.keys()):
            if room_id in room_user_names:
                connected_names = room_user_names[room_id]
                
                # Get all users from Firestore for this room
                firestore_users = self.firestore_manager.get_room_users(room_id)
                
                for user in firestore_users:
                    user_name = user.get("name")
                    user_id = user.get("id")
                    
                    # Remove auto-generated users that are not connected
                    if (user_name and user_name.startswith("User ") and 
                        user_name not in connected_names):
                        print(f"Removing disconnected auto-generated user: {user_name}")
                        self.firestore_manager.remove_user_from_room(room_id, user_id)
                        if room_id in self.room_users:
                            self.room_users[room_id].discard(user_id)
        
        print("Cleanup completed - removed disconnected auto-generated users") 