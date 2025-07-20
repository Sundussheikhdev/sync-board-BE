from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import uuid
import re
from typing import List, Dict, Optional
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio

from .websocket import ConnectionManager
from .storage import StorageManager
from .firestore_manager import FirestoreManager

load_dotenv()

app = FastAPI(title="Collaborative App API", version="1.0.0")

# Add CORS middleware - centralized configuration
allowed_origins_config = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_config == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = allowed_origins_config.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,  # Cache preflight for 24 hours
)



# Initialize managers
firestore_manager = FirestoreManager()
storage_manager = StorageManager()
manager = ConnectionManager(firestore_manager=firestore_manager)

# Background task for periodic cleanup
@app.on_event("startup")
async def startup_event():
    """Start background cleanup task"""
    asyncio.create_task(periodic_cleanup())

async def periodic_cleanup():
    """Run cleanup every minute"""
    cleanup_interval = int(os.getenv("CLEANUP_SCHEDULER_INTERVAL", "60"))
    while True:
        try:
            await asyncio.sleep(cleanup_interval)
            print("🕐 Running periodic cleanup check...")
            manager.trigger_cleanup_if_needed()
        except Exception as e:
            print(f"Error in periodic cleanup: {e}")
            await asyncio.sleep(cleanup_interval)

# Data models
class UserCheckRequest(BaseModel):
    username: str
    current_username: Optional[str] = None

class CreateRoomRequest(BaseModel):
    name: str
    created_by: str

class ChangeUsernameRequest(BaseModel):
    old_username: str
    new_username: str

@app.get("/")
async def root():
    return {"message": "Collaborative App API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # Get user_name from query parameters
    user_name = websocket.query_params.get("user_name")
    
    # Try to connect - this may reject the connection if username is taken
    try:
        await manager.connect(websocket, room_id, user_name)
    except Exception as e:
        # Connection was rejected (e.g., username taken, room doesn't exist)
        error_msg = str(e)
        print(f"❌ Connection rejected: {error_msg}")
        
        # Log the specific reason for debugging
        if "Username" in error_msg:
            print(f"🔍 Username '{user_name}' was rejected")
        elif "Room" in error_msg:
            print(f"🔍 Room '{room_id}' was rejected")
        
        return  # Exit early, don't try to receive messages
    
    # Only proceed with message handling if connection was successful
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message["type"] == "draw":
                # Broadcast drawing data to all users in the room
                await manager.broadcast_draw(room_id, message["data"], websocket)
            elif message["type"] == "stroke_start":
                # Handle stroke start
                await manager.broadcast_stroke_start(room_id, message["data"], websocket)
            elif message["type"] == "stroke_point":
                # Handle stroke point
                stroke_id = message["data"]["strokeId"]
                point = message["data"]["point"]
                await manager.broadcast_stroke_point(room_id, stroke_id, point, websocket)
            elif message["type"] == "stroke_end":
                # Handle stroke end
                stroke_id = message["data"]["strokeId"]
                await manager.broadcast_stroke_end(room_id, stroke_id, websocket)
            elif message["type"] == "chat":
                # Broadcast chat message to all users in the room
                print(f"Received chat message from user in room {room_id}: {message['data']}")
                await manager.broadcast_chat(room_id, message["data"], websocket)
            elif message["type"] == "join":
                # Handle user joining
                await manager.broadcast_user_joined(room_id, message["data"], websocket)
            elif message["type"] == "leave":
                # Handle user leaving - disconnect them from the room
                print(f"Received leave message from user in room {room_id}")
                await manager.disconnect(websocket, room_id)
            elif message["type"] == "name_change":
                # Handle user name change
                await manager.update_user_name(websocket, message["data"]["new_name"])
            elif message["type"] == "get_room_info":
                # Send room information back to the requesting user
                room_info = manager.get_room_info(room_id)
                await websocket.send_text(json.dumps({
                    "type": "room_info",
                    "data": room_info,
                    "timestamp": datetime.now().isoformat()
                }))
            elif message["type"] == "clear_canvas":
                # Handle canvas clear request
                await manager.broadcast_clear_canvas(room_id, websocket)
            elif message["type"] == "heartbeat":
                # NEW: Handle heartbeat messages to track active connections
                if websocket in manager.connection_heartbeats:
                    manager.connection_heartbeats[websocket] = datetime.now()
                    print(f"💓 Heartbeat received from connection in room {room_id}")
                    # Send heartbeat response
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat_response",
                        "timestamp": datetime.now().isoformat()
                    }))
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket, room_id)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        print(f"📁 File upload request: {file.filename}, type: {file.content_type}, size: {file.size}")
        
        # Validate file type
        allowed_types_str = os.getenv("ALLOWED_FILE_TYPES", "image/jpeg,image/png,image/gif,application/pdf")
        allowed_types = allowed_types_str.split(",")
        if file.content_type not in allowed_types:
            print(f"❌ File type not allowed: {file.content_type}")
            raise HTTPException(status_code=400, detail="File type not allowed")
        
        print("✅ File type validated, uploading to GCP Storage...")
        
        # Upload to GCP Storage
        file_url = await storage_manager.upload_file(file)
        
        print(f"✅ File uploaded successfully: {file_url}")
        
        return {
            "success": True,
            "file_url": file_url,
            "filename": file.filename,
            "content_type": file.content_type
        }
    except Exception as e:
        print(f"❌ File upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/rooms/{room_id}/users")
async def get_room_users(room_id: str):
    users = manager.get_room_users(room_id)
    return {"users": users}

@app.get("/rooms/{room_id}/info")
async def get_room_info(room_id: str):
    # Clean up connections before getting room info
    manager.cleanup_connections()
    room_info = manager.get_room_info(room_id)
    return room_info

@app.get("/users")
async def get_all_users():
    """Get all currently active users"""
    # Clean up connections before returning users
    manager.cleanup_connections()
    users = manager.get_all_users()
    return {"users": users}

@app.get("/users/global")
async def get_global_users():
    """Get all global users for debugging"""
    try:
        # Get all global users from Firestore
        global_users_ref = firestore_manager.db.collection('global_users')
        global_users = list(global_users_ref.stream())
        
        users = []
        for user in global_users:
            user_data = user.to_dict()
            users.append({
                "username": user_data.get('username'),
                "user_id": user_data.get('user_id'),
                "room_id": user_data.get('room_id'),
                "is_online": user_data.get('is_online'),
                "last_seen": user_data.get('last_seen').isoformat() if hasattr(user_data.get('last_seen'), 'isoformat') else str(user_data.get('last_seen', ''))
            })
        
        return {"global_users": users}
    except Exception as e:
        print(f"Error getting global users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/check")
async def check_username(request: UserCheckRequest):
    """Check if a username is available globally"""
    # Use global username checking instead of local checking
    is_available = firestore_manager.is_username_available_globally(
        request.username, 
        request.current_username
    )
    return {"available": is_available}

@app.get("/rooms")
async def get_all_rooms():
    """Get all active rooms"""
    # Clean up connections before getting rooms
    manager.cleanup_connections()
    rooms = firestore_manager.get_all_rooms()
    return {"rooms": rooms}

@app.post("/rooms")
async def create_room(request: CreateRoomRequest):
    """Create a new room"""
    room_id = firestore_manager.create_room(request.name, request.created_by)
    if room_id:
        return {"room_id": room_id, "name": request.name, "created_by": request.created_by}
    else:
        raise HTTPException(status_code=500, detail="Failed to create room")

@app.post("/users/change-username")
async def change_username(request: ChangeUsernameRequest):
    """Change a user's username globally"""
    # Check if new username is available globally
    is_available = firestore_manager.is_username_available_globally(request.new_username)
    if not is_available:
        raise HTTPException(status_code=400, detail="Username is already taken")
    
    # Unregister old username globally
    firestore_manager.unregister_global_user(request.old_username)
    
    # Register new username globally (we'll need the user_id and room_id)
    # For now, we'll let the WebSocket connection handle the registration
    success = manager.change_username(request.old_username, request.new_username)
    if success:
        return {"success": True, "message": "Username changed successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to change username")

@app.post("/cleanup")
async def cleanup_connections():
    """Clean up broken connections and auto-generated usernames"""
    try:
        manager.cleanup_connections()
        # Trigger cleanup check
        manager.trigger_cleanup_if_needed()
        return {
            "success": True, 
            "message": "Cleanup completed and cleanup check triggered",
            "scheduled_rooms": list(manager.empty_rooms_scheduled.keys())
        }
    except Exception as e:
        print(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/auto-users")
async def cleanup_auto_users():
    """Clean up auto-generated users that are stuck"""
    try:
        # Trigger auto-user cleanup
        manager._cleanup_stuck_auto_users()
        
        # Also run the Firestore cleanup
        auto_removed = firestore_manager.cleanup_auto_generated_users()
        
        return {
            "success": True,
            "message": f"Auto-user cleanup completed. Removed {auto_removed} auto-generated users from Firestore."
        }
    except Exception as e:
        print(f"Error during auto-user cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/room/{room_id}")
async def cleanup_room_users(room_id: str):
    """Clean up users in a specific room"""
    try:
        # Remove auto-generated users from this room
        auto_removed = 0
        users = firestore_manager.get_room_users(room_id)
        
        for user in users:
            user_name = user.get('name', '')
            user_id = user.get('id')
            
            if user_name.startswith('User '):
                print(f"Removing auto-generated user: {user_name}")
                firestore_manager.remove_user_from_room(room_id, user_id)
                auto_removed += 1
        
        return {
            "success": True, 
            "message": f"Removed {auto_removed} auto-generated users from room {room_id}"
        }
    except Exception as e:
        print(f"Error cleaning up room users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/room-data/{room_id}")
async def cleanup_room_data_endpoint(room_id: str):
    """Clean up all data for a specific room (canvas, messages, users)"""
    try:
        success = firestore_manager.cleanup_room_data(room_id)
        if success:
            return {
                "success": True,
                "message": f"Cleaned up all data for room {room_id}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clean up room data")
    except Exception as e:
        print(f"Error cleaning up room data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/orphaned-files")
async def cleanup_orphaned_files_endpoint():
    """Clean up orphaned files in GCP Storage"""
    try:
        orphaned_count = firestore_manager.cleanup_orphaned_files()
        return {
            "success": True,
            "message": f"Cleaned up {orphaned_count} orphaned files"
        }
    except Exception as e:
        print(f"Error cleaning up orphaned files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/comprehensive")
async def comprehensive_cleanup():
    """Run comprehensive cleanup of all stale data"""
    try:
        print("🧹 Starting comprehensive cleanup...")
        
        # Clean up auto-generated users
        auto_removed = firestore_manager.cleanup_auto_generated_users()
        
        # Clean up duplicate users
        rooms = firestore_manager.get_all_rooms()
        duplicate_removed = 0
        for room in rooms:
            room_id = room.get('id')
            if room_id:
                duplicate_removed += firestore_manager.remove_duplicate_users(room_id)
        
        # Clean up stale global users
        global_removed = firestore_manager.cleanup_global_users()
        
        # Clean up orphaned files
        orphaned_files = firestore_manager.cleanup_orphaned_files()
        
        # Trigger room cleanup check
        manager.trigger_cleanup_if_needed()
        
        return {
            "success": True,
            "message": f"Comprehensive cleanup completed! Removed {auto_removed} auto-generated users, {duplicate_removed} duplicate users, {global_removed} stale global users, and {orphaned_files} orphaned files. Room cleanup check triggered.",
            "scheduled_rooms": list(manager.empty_rooms_scheduled.keys())
        }
    except Exception as e:
        print(f"Error during comprehensive cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/trigger")
async def trigger_cleanup():
    """Manually trigger cleanup check"""
    try:
        manager.trigger_cleanup_if_needed()
        return {
            "success": True,
            "message": "Cleanup check triggered",
            "scheduled_rooms": list(manager.empty_rooms_scheduled.keys())
        }
    except Exception as e:
        print(f"Error triggering cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cleanup/status")
async def get_cleanup_status():
    """Get current cleanup status"""
    try:
        scheduled_rooms = []
        for room_id, scheduled_time in manager.empty_rooms_scheduled.items():
            time_until_cleanup = scheduled_time + timedelta(minutes=5) - datetime.now()
            scheduled_rooms.append({
                "room_id": room_id,
                "scheduled_at": scheduled_time.isoformat(),
                "cleanup_at": (scheduled_time + timedelta(minutes=5)).isoformat(),
                "time_until_cleanup": max(0, int(time_until_cleanup.total_seconds())),
                "time_until_cleanup_minutes": max(0, int(time_until_cleanup.total_seconds() / 60))
            })
        
        return {
            "scheduled_cleanups": scheduled_rooms,
            "total_scheduled": len(scheduled_rooms),
            "last_cleanup_time": manager.last_cleanup_time.isoformat(),
            "next_cleanup_check": (manager.last_cleanup_time + timedelta(minutes=1)).isoformat()
        }
    except Exception as e:
        print(f"Error getting cleanup status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/room-stats")
async def get_room_stats():
    """Get detailed statistics about rooms"""
    try:
        rooms = firestore_manager.get_all_rooms()
        room_stats = []
        
        for room in rooms:
            room_id = room.get('id')
            room_name = room.get('name', 'Unknown')
            user_count = room.get('user_count', 0)
            created_at = room.get('created_at')
            last_activity = room.get('last_activity')
            is_active = room.get('is_active', True)
            
            # Get message count
            messages_ref = firestore_manager.db.collection('rooms').document(room_id).collection('messages')
            message_count = len(list(messages_ref.stream()))
            
            # Get canvas stroke count
            canvas_ref = firestore_manager.db.collection('rooms').document(room_id).collection('canvas')
            canvas_docs = list(canvas_ref.stream())
            stroke_count = 0
            for canvas_doc in canvas_docs:
                canvas_data = canvas_doc.to_dict()
                drawings = canvas_data.get('drawings', [])
                stroke_count += len(drawings)
            
            room_stats.append({
                "room_id": room_id,
                "name": room_name,
                "user_count": user_count,
                "message_count": message_count,
                "stroke_count": stroke_count,
                "is_active": is_active,
                "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                "last_activity": last_activity.isoformat() if hasattr(last_activity, 'isoformat') else str(last_activity)
            })
        
        return {
            "rooms": room_stats,
            "total_rooms": len(rooms),
            "active_rooms": sum(1 for room in rooms if room.get('is_active', True))
        }
    except Exception as e:
        print(f"Error getting room stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/force-stuck-users")
async def force_cleanup_stuck_users():
    """Force cleanup of users that appear online but haven't been seen recently"""
    try:
        # Force cleanup of stuck users
        updated_count = firestore_manager.force_cleanup_stuck_users()
        
        # Also run the regular global user cleanup
        removed_count = firestore_manager.cleanup_global_users()
        
        return {
            "success": True,
            "message": f"Force cleanup completed. Marked {updated_count} users as offline, removed {removed_count} stale users.",
            "updated_users": updated_count,
            "removed_users": removed_count
        }
    except Exception as e:
        print(f"Error during force stuck user cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/orphaned-data")
async def cleanup_orphaned_data():
    """Comprehensive cleanup of all orphaned data (files, users, rooms)"""
    try:
        results = firestore_manager.cleanup_orphaned_data()
        
        if "error" in results:
            raise HTTPException(status_code=500, detail=results["error"])
        
        return {
            "success": True,
            "message": "Comprehensive orphaned data cleanup completed",
            "results": results
        }
    except Exception as e:
        print(f"Error during orphaned data cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rooms/{room_id}/messages")
async def get_room_messages(room_id: str, limit: int = None):
    if limit is None:
        limit = int(os.getenv("CHAT_MESSAGE_LIMIT", "100"))
    """Get chat messages for a room"""
    try:
        messages = firestore_manager.get_room_messages(room_id, limit)
        return {"messages": messages}
    except Exception as e:
        print(f"Error getting room messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/delete-all-files")
async def delete_all_files():
    """Delete ALL files from GCP Storage bucket (nuclear option)"""
    try:
        # Get all files from the bucket
        bucket_name = os.getenv("GCP_BUCKET_NAME", "collaborative-app-files-board-sync-466501")
        
        # Initialize GCP Storage client with proper authentication
        from google.cloud import storage
        from google.oauth2 import service_account
        
        # Use the same service account credentials as the storage manager
        credentials_path = "board-sync-466501-c38a2cead941.json"
        if os.path.exists(credentials_path):
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            client = storage.Client(credentials=credentials)
        else:
            # Fallback to default credentials
            client = storage.Client()
        
        bucket = client.bucket(bucket_name)
        
        # List all blobs (files) in the bucket
        blobs = list(bucket.list_blobs())
        
        print(f"🗂️  Found {len(blobs)} files in bucket {bucket_name}")
        
        # List all files that will be deleted
        file_list = []
        for blob in blobs:
            file_info = {
                "name": blob.name,
                "size": blob.size,
                "created": blob.time_created.isoformat() if blob.time_created else "Unknown",
                "updated": blob.updated.isoformat() if blob.updated else "Unknown"
            }
            file_list.append(file_info)
            print(f"   📄 {blob.name} ({blob.size} bytes)")
        
        files_removed = 0
        
        # Delete all files
        print(f"\n🗑️  Deleting {len(blobs)} files...")
        for blob in blobs:
            try:
                blob.delete()
                files_removed += 1
                print(f"   ✅ Deleted: {blob.name}")
            except Exception as e:
                print(f"   ❌ Failed to delete {blob.name}: {e}")
        
        print(f"✅ Deleted {files_removed} files from GCP bucket")
        
        return {
            "success": True,
            "message": f"Deleted {files_removed} files from GCP bucket",
            "files_removed": files_removed,
            "files_list": file_list
        }
    except Exception as e:
        print(f"❌ Error deleting all files: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/delete-all-global-users")
async def delete_all_global_users():
    """Delete ALL global users from Firestore (nuclear option)"""
    try:
        # Get all global users
        global_users_ref = firestore_manager.db.collection('global_users')
        global_users = list(global_users_ref.stream())
        
        users_removed = 0
        print(f"👥 Found {len(global_users)} global users to delete")
        
        # Delete all global users
        for user in global_users:
            try:
                user.reference.delete()
                users_removed += 1
                user_data = user.to_dict()
                username = user_data.get('username', 'Unknown')
                print(f"   🗑️  Deleted global user: {username}")
            except Exception as e:
                print(f"   ❌ Failed to delete global user: {e}")
        
        print(f"✅ Deleted {users_removed} global users")
        
        return {
            "success": True,
            "message": f"Deleted {users_removed} global users",
            "users_removed": users_removed
        }
    except Exception as e:
        print(f"❌ Error deleting all global users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup/server-restart")
async def cleanup_server_restart():
    """Clean up global users that appear online but have no active connections (server restart scenario)"""
    try:
        # Get all global users marked as online
        global_users_ref = firestore_manager.db.collection('global_users')
        online_users = list(global_users_ref.where('is_online', '==', True).stream())
        
        users_cleaned = 0
        for user in online_users:
            user_data = user.to_dict()
            username = user_data.get('username')
            user_id = user_data.get('user_id')
            
            # Check if this user has any active connections
            has_active_connection = False
            for room_connections in manager.active_connections.values():
                for ws in room_connections:
                    if ws in manager.connection_users:
                        connection_user = manager.connection_users[ws]
                        if connection_user.get('id') == user_id:
                            has_active_connection = True
                            break
                if has_active_connection:
                    break
            
            # If no active connection found, mark user as offline
            if not has_active_connection:
                print(f"🧹 Marking user {username} as offline (no active connection)")
                firestore_manager.update_global_user_status(username, is_online=False)
                users_cleaned += 1
        
        return {
            "success": True,
            "message": f"Server restart cleanup completed. Marked {users_cleaned} users as offline.",
            "users_cleaned": users_cleaned
        }
    except Exception as e:
        print(f"Error during server restart cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port) 