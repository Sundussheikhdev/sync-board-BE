import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from google.cloud import firestore

class FirestoreManager:
    def __init__(self):
        # Initialize Firestore client
        try:
            # Try service account JSON first (for local development)
            import os
            key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "board-sync-466501-c38a2cead941.json")
            if os.path.exists(key_file):
                self.db = firestore.Client.from_service_account_json(key_file)
                print(f"✅ Firestore client initialized with service account: {key_file}")
            else:
                # Use default credentials (for Cloud Run)
                self.db = firestore.Client()
                print("✅ Firestore client initialized with default credentials (Cloud Run)")
        except Exception as e:
            print(f"❌ Failed to initialize Firestore client: {e}")
            self.db = None
        
        # Initialize GCP Storage client (optional)
        try:
            from google.cloud import storage
            # Try service account JSON first (for local development)
            if os.path.exists(key_file):
                self.storage_client = storage.Client.from_service_account_json(key_file)
                print(f"✅ GCP Storage client initialized with service account: {key_file}")
            else:
                # Use default credentials (for Cloud Run)
                self.storage_client = storage.Client()
                print("✅ GCP Storage client initialized with default credentials (Cloud Run)")
        except Exception as e:
            print(f"⚠️ GCP Storage client not available: {e}")
            self.storage_client = None

    def is_username_available_globally(self, username: str, exclude_user_id: str = None) -> bool:
        """Check if a username is available globally across all rooms"""
        if not self.db:
            return True
        
        try:
            # Check in global users collection
            global_user_ref = self.db.collection('global_users').document(username)
            global_user = global_user_ref.get()
            
            if global_user.exists:
                global_user_data = global_user.to_dict()
                user_id = global_user_data.get('user_id')
                
                # If this is the same user checking their own username, it's available
                if exclude_user_id and user_id == exclude_user_id:
                    return True
                
                # Check if the user is currently online
                is_online = global_user_data.get('is_online', False)
                last_seen = global_user_data.get('last_seen')
                
                # If user is online, username is taken
                if is_online:
                    return False
                
                # If user hasn't been seen recently (within 2 minutes), username is available
                if last_seen:
                    from datetime import timedelta
                    if hasattr(last_seen, 'timestamp'):
                        time_diff = datetime.now() - last_seen
                        if time_diff > timedelta(minutes=2):
                            # User has been offline for more than 2 minutes, username is available
                            print(f"Username {username} is available (user offline for {time_diff.total_seconds():.0f}s)")
                            return True
                        else:
                            # User was seen recently, username is still taken
                            print(f"Username {username} is taken (user seen {time_diff.total_seconds():.0f}s ago)")
                            return False
                
                # If no last_seen timestamp, assume username is available
                print(f"Username {username} is available (no last_seen timestamp)")
                return True
            
            # Username not found in global users, so it's available
            print(f"Username {username} is available (not registered)")
            return True
        except Exception as e:
            print(f"Error checking global username availability: {e}")
            return True

    def register_global_user(self, username: str, user_id: str, room_id: str) -> bool:
        """Register a user globally to claim the username"""
        if not self.db:
            return False
        
        try:
            global_user_ref = self.db.collection('global_users').document(username)
            global_user_data = {
                'user_id': user_id,
                'username': username,
                'room_id': room_id,
                'is_online': True,
                'last_seen': datetime.now(),
                'registered_at': datetime.now()
            }
            global_user_ref.set(global_user_data)
            print(f"Registered global user: {username} (ID: {user_id})")
            return True
        except Exception as e:
            print(f"Error registering global user: {e}")
            return False

    def unregister_global_user(self, username: str) -> bool:
        """Unregister a user globally"""
        if not self.db:
            return False
        
        try:
            global_user_ref = self.db.collection('global_users').document(username)
            global_user_ref.delete()
            print(f"Unregistered global user: {username}")
            return True
        except Exception as e:
            print(f"Error unregistering global user: {e}")
            return False

    def update_global_user_status(self, username: str, is_online: bool = True) -> bool:
        """Update global user online status"""
        if not self.db:
            return False
        
        try:
            global_user_ref = self.db.collection('global_users').document(username)
            global_user_ref.update({
                'is_online': is_online,
                'last_seen': datetime.now()
            })
            return True
        except Exception as e:
            print(f"Error updating global user status: {e}")
            return False

    def room_exists(self, room_id: str) -> bool:
        """Check if a room exists in Firestore"""
        if not self.db:
            return False
        
        try:
            room_ref = self.db.collection('rooms').document(room_id)
            room_doc = room_ref.get()
            return room_doc.exists
        except Exception as e:
            print(f"Error checking if room exists: {e}")
            return False

    def create_room(self, room_name: str, created_by: str) -> str:
        """Create a new room in Firestore"""
        if not self.db:
            return None
        
        try:
            room_ref = self.db.collection('rooms').document()
            room_data = {
                'name': room_name,
                'created_by': created_by,
                'created_at': datetime.now(),
                'last_activity': datetime.now(),
                'user_count': 0,
                'is_active': True
            }
            room_ref.set(room_data)
            return room_ref.id
        except Exception as e:
            print(f"Error creating room: {e}")
            return None

    def create_room_with_id(self, room_id: str, room_name: str, created_by: str) -> bool:
        """Create a room with a specific ID"""
        if not self.db:
            return False
        
        try:
            room_ref = self.db.collection('rooms').document(room_id)
            room_data = {
                'name': room_name,
                'created_by': created_by,
                'created_at': datetime.now(),
                'last_activity': datetime.now(),
                'user_count': 0,
                'is_active': True
            }
            room_ref.set(room_data)
            print(f"✅ Created room {room_id} in Firestore")
            return True
        except Exception as e:
            print(f"Error creating room with ID: {e}")
            return False

    def get_all_rooms(self) -> List[Dict[str, Any]]:
        """Get all active rooms"""
        if not self.db:
            return []
        
        try:
            rooms = []
            rooms_ref = self.db.collection('rooms').where('is_active', '==', True)
            for room in rooms_ref.stream():
                room_data = room.to_dict()
                room_data['id'] = room.id
                
                # Convert datetime objects to ISO strings for JSON serialization
                if 'created_at' in room_data and hasattr(room_data['created_at'], 'isoformat'):
                    room_data['created_at'] = room_data['created_at'].isoformat()
                if 'last_activity' in room_data and hasattr(room_data['last_activity'], 'isoformat'):
                    room_data['last_activity'] = room_data['last_activity'].isoformat()
                
                rooms.append(room_data)
            return rooms
        except Exception as e:
            print(f"Error getting rooms: {e}")
            return []

    def add_user_to_room(self, room_id: str, user_id: str, user_name: str) -> bool:
        """Add user to room"""
        if not self.db:
            return False
        
        try:
            # First check if room exists
            room_ref = self.db.collection('rooms').document(room_id)
            room_doc = room_ref.get()
            
            if not room_doc.exists:
                print(f"❌ Room {room_id} doesn't exist in Firestore. Cannot add user.")
                return False
            
            # Check if user already exists in this room
            user_ref = self.db.collection('rooms').document(room_id).collection('users').document(user_id)
            existing_user = user_ref.get()
            
            if existing_user.exists:
                # User already exists, just update online status
                user_ref.update({
                    'is_online': True,
                    'last_seen': datetime.now()
                })
                print(f"User {user_name} already exists in room {room_id}, updated online status")
                return True
            
            # Add new user to room's users subcollection
            user_data = {
                'name': user_name,
                'joined_at': datetime.now(),
                'is_online': True,
                'last_seen': datetime.now()
            }
            user_ref.set(user_data)
            
            # Update room's user count
            room_ref = self.db.collection('rooms').document(room_id)
            room_ref.update({
                'user_count': firestore.Increment(1),
                'last_activity': datetime.now()
            })
            print(f"Added new user {user_name} to room {room_id}")
            return True
        except Exception as e:
            print(f"Error adding user to room: {e}")
            return False

    def remove_user_from_room(self, room_id: str, user_id: str) -> bool:
        """Remove user from room"""
        if not self.db:
            return False
        
        try:
            # First check if room exists
            room_ref = self.db.collection('rooms').document(room_id)
            room_doc = room_ref.get()
            
            if not room_doc.exists:
                print(f"⚠️ Room {room_id} doesn't exist in Firestore, skipping user removal")
                return True  # Return True to avoid error cascading
            
            # Get user data before removing
            user_ref = self.db.collection('rooms').document(room_id).collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                print(f"⚠️ User {user_id} not found in room {room_id}")
                return True  # Return True to avoid error cascading
            
            user_data = user_doc.to_dict()
            user_name = user_data.get('name', 'Unknown')
            
            # Remove user from room's users subcollection
            user_ref.delete()
            
            # Update room's user count
            room_ref.update({
                'user_count': firestore.Increment(-1),
                'last_activity': datetime.now()
            })
            
            print(f"Removed user {user_name} (ID: {user_id}) from room {room_id}")
            return True
        except Exception as e:
            print(f"Error removing user from room: {e}")
            return False

    def save_chat_message(self, room_id: str, user_id: str, user_name: str, message: str, 
                         file_url: Optional[str] = None, file_name: Optional[str] = None, 
                         file_type: Optional[str] = None) -> bool:
        """Save chat message to Firestore"""
        if not self.db:
            return False
        
        try:
            message_ref = self.db.collection('rooms').document(room_id).collection('messages').document()
            message_data = {
                'user_id': user_id,
                'user_name': user_name,
                'message': message,
                'timestamp': datetime.now(),
                'file_url': file_url,
                'file_name': file_name,
                'file_type': file_type
            }
            message_ref.set(message_data)
            return True
        except Exception as e:
            print(f"Error saving chat message: {e}")
            return False

    def get_room_messages(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent messages for a room"""
        if not self.db:
            return []
        
        try:
            messages = []
            messages_ref = self.db.collection('rooms').document(room_id).collection('messages').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            for message in messages_ref.stream():
                message_data = message.to_dict()
                message_data['id'] = message.id
                messages.append(message_data)
            return list(reversed(messages))  # Return in chronological order
        except Exception as e:
            print(f"Error getting room messages: {e}")
            return []

    def save_canvas_state(self, room_id: str, drawings: List[Dict[str, Any]]) -> bool:
        """Save canvas state to Firestore"""
        if not self.db:
            return False
        
        try:
            canvas_ref = self.db.collection('rooms').document(room_id).collection('canvas').document('current')
            canvas_data = {
                'drawings': drawings,
                'updated_at': datetime.now()
            }
            canvas_ref.set(canvas_data)
            return True
        except Exception as e:
            print(f"Error saving canvas state: {e}")
            return False

    def get_canvas_state(self, room_id: str) -> List[Dict[str, Any]]:
        """Get current canvas state for a room"""
        if not self.db:
            return []
        
        try:
            canvas_ref = self.db.collection('rooms').document(room_id).collection('canvas').document('current')
            canvas_doc = canvas_ref.get()
            if canvas_doc.exists:
                canvas_data = canvas_doc.to_dict()
                return canvas_data.get('drawings', [])
            return []
        except Exception as e:
            print(f"Error getting canvas state: {e}")
            return []

    def update_user_name(self, room_id: str, user_id: str, new_name: str) -> bool:
        """Update user name in room"""
        if not self.db:
            return False
        
        try:
            user_ref = self.db.collection('rooms').document(room_id).collection('users').document(user_id)
            user_ref.update({
                'name': new_name,
                'updated_at': datetime.now()
            })
            return True
        except Exception as e:
            print(f"Error updating user name: {e}")
            return False

    def get_room_users(self, room_id: str) -> List[Dict[str, Any]]:
        """Get all users in a room"""
        if not self.db:
            return []
        
        try:
            users = []
            users_ref = self.db.collection('rooms').document(room_id).collection('users')
            for user in users_ref.stream():
                user_data = user.to_dict()
                user_data['id'] = user.id
                users.append(user_data)
            return users
        except Exception as e:
            print(f"Error getting room users: {e}")
            return []

    def cleanup_auto_generated_users(self) -> int:
        """Remove all auto-generated users from all rooms"""
        if not self.db:
            return 0
        
        try:
            total_removed = 0
            
            # Get all rooms
            rooms_ref = self.db.collection('rooms')
            rooms = list(rooms_ref.stream())
            
            for room in rooms:
                room_id = room.id
                print(f"Cleaning up room: {room_id}")
                
                # Get all users in this room
                users_ref = self.db.collection('rooms').document(room_id).collection('users')
                users = list(users_ref.stream())
                
                removed_count = 0
                for user in users:
                    user_data = user.to_dict()
                    user_name = user_data.get('name', '')
                    
                    # Check if this is an auto-generated user
                    if user_name.startswith('User '):
                        print(f"  Removing auto-generated user: {user_name}")
                        user.reference.delete()
                        removed_count += 1
                
                total_removed += removed_count
                
                # Update room user count
                if removed_count > 0:
                    room_ref = self.db.collection('rooms').document(room_id)
                    current_count = room.to_dict().get('user_count', 0)
                    new_count = max(0, current_count - removed_count)
                    room_ref.update({
                        'user_count': new_count,
                        'last_activity': datetime.now()
                    })
                    print(f"  Updated room {room_id} user count: {current_count} -> {new_count}")
            
            print(f"Cleanup completed: removed {total_removed} auto-generated users")
            return total_removed
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
            return 0

    def remove_duplicate_users(self, room_id: str) -> int:
        """Remove duplicate users in a specific room"""
        if not self.db:
            return 0
        
        try:
            users_ref = self.db.collection('rooms').document(room_id).collection('users')
            users = list(users_ref.stream())
            
            # Group users by name
            users_by_name = {}
            for user in users:
                user_data = user.to_dict()
                user_name = user_data.get('name', '')
                
                if user_name not in users_by_name:
                    users_by_name[user_name] = []
                users_by_name[user_name].append(user)
            
            removed_count = 0
            for user_name, user_list in users_by_name.items():
                if len(user_list) > 1:
                    # Keep the first user, remove the rest
                    for user in user_list[1:]:
                        print(f"Removing duplicate user: {user_name} (ID: {user.id})")
                        user.reference.delete()
                        removed_count += 1
            
            # Update room user count
            if removed_count > 0:
                room_ref = self.db.collection('rooms').document(room_id)
                current_count = room_ref.get().to_dict().get('user_count', 0)
                new_count = max(0, current_count - removed_count)
                room_ref.update({
                    'user_count': new_count,
                    'last_activity': datetime.now()
                })
                print(f"Updated room {room_id} user count: {current_count} -> {new_count}")
            
            return removed_count
            
        except Exception as e:
            print(f"Error removing duplicate users: {e}")
            return 0

    def cleanup_global_users(self) -> int:
        """Clean up stale global users that have been offline for too long"""
        if not self.db:
            return 0
        
        try:
            removed_count = 0
            global_users_ref = self.db.collection('global_users')
            global_users = list(global_users_ref.stream())
            
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(minutes=10)  # Remove users offline for 10+ minutes
            
            for user in global_users:
                user_data = user.to_dict()
                username = user_data.get('username')
                is_online = user_data.get('is_online', False)
                last_seen = user_data.get('last_seen')
                
                # Remove if user is offline and hasn't been seen recently
                if not is_online and last_seen:
                    # Handle both timezone-aware and timezone-naive datetimes
                    if hasattr(last_seen, 'replace'):
                        # Convert to timezone-naive datetime for comparison
                        if hasattr(last_seen, 'tzinfo') and last_seen.tzinfo is not None:
                            # Timezone-aware datetime, convert to naive
                            last_seen_naive = last_seen.replace(tzinfo=None)
                        else:
                            # Already timezone-naive
                            last_seen_naive = last_seen
                        
                        if last_seen_naive < cutoff_time:
                            print(f"Removing stale global user: {username} (offline since {last_seen})")
                            user.reference.delete()
                            removed_count += 1
            
            print(f"Cleanup completed: removed {removed_count} stale global users")
            return removed_count
            
        except Exception as e:
            print(f"Error during global user cleanup: {e}")
            return 0

    def cleanup_room_data(self, room_id: str) -> bool:
        """Clean up all data for a specific room (canvas, messages, users, and GCP files)"""
        if not self.db:
            return False
        
        try:
            print(f"🧹 Firestore cleanup: {room_id}")
            
            # First check if room exists
            room_ref = self.db.collection('rooms').document(room_id)
            room_doc = room_ref.get()
            
            if not room_doc.exists:
                print(f"⚠️ Room {room_id} doesn't exist in Firestore, nothing to clean up")
                return True
            
            # Get all file URLs from this room before deleting messages
            room_files = set()
            messages_ref = self.db.collection('rooms').document(room_id).collection('messages')
            messages_docs = list(messages_ref.stream())
            
            for message in messages_docs:
                message_data = message.to_dict()
                file_url = message_data.get('file_url')
                if file_url:
                    room_files.add(file_url)
            
            # Clean up canvas data
            canvas_ref = self.db.collection('rooms').document(room_id).collection('canvas')
            canvas_docs = list(canvas_ref.stream())
            for doc in canvas_docs:
                doc.reference.delete()
            
            # Clean up messages
            for doc in messages_docs:
                doc.reference.delete()
            
            # Clean up users
            users_ref = self.db.collection('rooms').document(room_id).collection('users')
            users_docs = list(users_ref.stream())
            for doc in users_docs:
                doc.reference.delete()
            
            # Update room status to inactive
            room_ref.update({
                'is_active': False,
                'cleaned_up_at': datetime.now(),
                'user_count': 0
            })
            
            print(f"✅ Firestore cleaned: {room_id} ({len(canvas_docs)} canvas, {len(messages_docs)} messages, {len(users_docs)} users)")
            
            # Clean up GCP files associated with this room
            if room_files and hasattr(self, 'storage_client') and self.storage_client is not None:
                try:
                    bucket_name = "board-sync-466501.appspot.com"
                    bucket = self.storage_client.bucket(bucket_name)
                    
                    files_deleted = 0
                    for file_url in room_files:
                        # Extract filename from URL
                        if file_url.startswith(f"https://storage.googleapis.com/{bucket_name}/"):
                            filename = file_url.replace(f"https://storage.googleapis.com/{bucket_name}/", "")
                            try:
                                blob = bucket.blob(filename)
                                if blob.exists():
                                    blob.delete()
                                    print(f"  🗑️ Deleted room file: {filename}")
                                    files_deleted += 1
                            except Exception as e:
                                print(f"  ⚠️ Error deleting file {filename}: {e}")
                    
                    print(f"✅ GCP files cleaned: {room_id} ({files_deleted} files deleted)")
                except Exception as e:
                    print(f"⚠️ GCP Storage cleanup skipped for room {room_id}: {e}")
            elif room_files:
                print(f"⚠️ GCP Storage not configured, {len(room_files)} room files not cleaned up")
            
            return True
            
        except Exception as e:
            print(f"❌ Firestore cleanup error {room_id}: {e}")
            return False

    def cleanup_orphaned_files(self) -> int:
        """Clean up orphaned files in GCP Storage that are not referenced in any room"""
        if not self.db:
            return 0
        
        try:
            print("🧹 Cleaning up orphaned files in GCP Storage")
            
            # Get all file URLs from ALL rooms (not just active ones)
            # This prevents files from being orphaned when chat history isn't loaded
            referenced_files = set()
            
            # Get file URLs from messages in ALL rooms
            rooms_ref = self.db.collection('rooms')
            rooms = list(rooms_ref.stream())
            
            total_rooms = 0
            for room in rooms:
                total_rooms += 1
                room_id = room.id
                messages_ref = self.db.collection('rooms').document(room_id).collection('messages')
                messages = list(messages_ref.stream())
                
                for message in messages:
                    message_data = message.to_dict()
                    file_url = message_data.get('file_url')
                    if file_url:
                        referenced_files.add(file_url)
            
            print(f"Found {len(referenced_files)} referenced files in {total_rooms} total rooms")
            
            # Check if GCP Storage is configured
            if not hasattr(self, 'storage_client') or self.storage_client is None:
                print("⚠️ GCP Storage not configured, skipping file cleanup")
                return 0
            
            # Get all files in GCP Storage bucket
            try:
                bucket_name = "board-sync-466501.appspot.com"
                bucket = self.storage_client.bucket(bucket_name)
                blobs = list(bucket.list_blobs())
                
                print(f"Found {len(blobs)} total files in GCP Storage")
                
                orphaned_count = 0
                for blob in blobs:
                    blob_url = f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
                    if blob_url not in referenced_files:
                        print(f"  🗑️ Deleting orphaned file: {blob.name}")
                        blob.delete()
                        orphaned_count += 1
                
                print(f"✅ GCP Storage cleanup completed: removed {orphaned_count} orphaned files")
                return orphaned_count
                
            except Exception as e:
                print(f"⚠️ GCP Storage cleanup skipped (credentials issue): {e}")
                return 0
                
        except Exception as e:
            print(f"❌ Error cleaning up orphaned files: {e}")
            return 0

    def cleanup_orphaned_data(self) -> dict:
        """Comprehensive cleanup of all orphaned data (files, users, rooms)"""
        if not self.db:
            return {"error": "Firestore not available"}
        
        try:
            print("🧹 Starting comprehensive orphaned data cleanup")
            results = {
                "orphaned_files": 0,
                "orphaned_users": 0,
                "orphaned_rooms": 0,
                "stale_global_users": 0
            }
            
            # 1. Clean up orphaned files
            results["orphaned_files"] = self.cleanup_orphaned_files()
            
            # 2. Clean up orphaned users in inactive rooms
            rooms_ref = self.db.collection('rooms')
            rooms = list(rooms_ref.stream())
            
            for room in rooms:
                room_data = room.to_dict()
                is_active = room_data.get('is_active', True)
                
                if not is_active:
                    room_id = room.id
                    users_ref = self.db.collection('rooms').document(room_id).collection('users')
                    users = list(users_ref.stream())
                    
                    for user in users:
                        user.reference.delete()
                        results["orphaned_users"] += 1
                    
                    print(f"  🗑️ Cleaned {len(users)} orphaned users from inactive room: {room_id}")
            
            # 3. Clean up stale global users (offline for more than 30 minutes)
            global_users_ref = self.db.collection('global_users')
            global_users = list(global_users_ref.stream())
            
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(minutes=30)
            
            for user in global_users:
                user_data = user.to_dict()
                username = user_data.get('username')
                is_online = user_data.get('is_online', False)
                last_seen = user_data.get('last_seen')
                
                if not is_online and last_seen:
                    # Handle both timezone-aware and timezone-naive datetimes
                    if hasattr(last_seen, 'replace'):
                        if hasattr(last_seen, 'tzinfo') and last_seen.tzinfo is not None:
                            last_seen_naive = last_seen.replace(tzinfo=None)
                        else:
                            last_seen_naive = last_seen
                        
                        if last_seen_naive < cutoff_time:
                            print(f"  🗑️ Removing stale global user: {username}")
                            user.reference.delete()
                            results["stale_global_users"] += 1
            
            # 4. Clean up completely empty inactive rooms
            for room in rooms:
                room_data = room.to_dict()
                is_active = room_data.get('is_active', True)
                user_count = room_data.get('user_count', 0)
                
                if not is_active and user_count == 0:
                    room_id = room.id
                    # Check if room has any data
                    canvas_ref = self.db.collection('rooms').document(room_id).collection('canvas')
                    messages_ref = self.db.collection('rooms').document(room_id).collection('messages')
                    
                    canvas_count = len(list(canvas_ref.stream()))
                    messages_count = len(list(messages_ref.stream()))
                    
                    if canvas_count == 0 and messages_count == 0:
                        print(f"  🗑️ Removing empty inactive room: {room_id}")
                        room.reference.delete()
                        results["orphaned_rooms"] += 1
            
            print(f"✅ Comprehensive orphaned data cleanup completed:")
            print(f"   - {results['orphaned_files']} orphaned files removed")
            print(f"   - {results['orphaned_users']} orphaned users removed")
            print(f"   - {results['orphaned_rooms']} empty rooms removed")
            print(f"   - {results['stale_global_users']} stale global users removed")
            
            return results
            
        except Exception as e:
            print(f"❌ Error during comprehensive orphaned data cleanup: {e}")
            return {"error": str(e)}

    def force_cleanup_stuck_users(self) -> int:
        """Force cleanup of users that appear online but haven't been seen recently"""
        if not self.db:
            return 0
        
        try:
            updated_count = 0
            global_users_ref = self.db.collection('global_users')
            global_users = list(global_users_ref.stream())
            
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(minutes=5)  # Mark as offline if not seen in 5 minutes
            
            for user in global_users:
                user_data = user.to_dict()
                username = user_data.get('username')
                is_online = user_data.get('is_online', False)
                last_seen = user_data.get('last_seen')
                
                # If user appears online but hasn't been seen recently, mark as offline
                if is_online and last_seen:
                    # Handle both timezone-aware and timezone-naive datetimes
                    if hasattr(last_seen, 'replace'):
                        # Convert to timezone-naive datetime for comparison
                        if hasattr(last_seen, 'tzinfo') and last_seen.tzinfo is not None:
                            # Timezone-aware datetime, convert to naive
                            last_seen_naive = last_seen.replace(tzinfo=None)
                        else:
                            # Already timezone-naive
                            last_seen_naive = last_seen
                        
                        if last_seen_naive < cutoff_time:
                            print(f"Marking stuck user as offline: {username} (last seen: {last_seen})")
                            user.reference.update({
                                'is_online': False,
                                'last_seen': last_seen
                            })
                            updated_count += 1
            
            print(f"Force cleanup completed: marked {updated_count} stuck users as offline")
            return updated_count
            
        except Exception as e:
            print(f"Error during force cleanup: {e}")
            return 0 