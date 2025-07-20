#!/usr/bin/env python3
"""
Comprehensive Cleanup Script for Collaborative App
Combines all cleanup functionality into one script
"""

import requests
import json
import time
import sys

def cleanup_system():
    """Main cleanup function"""
    base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    print("🧹 COMPREHENSIVE CLEANUP SYSTEM")
    print("=" * 60)
    
    # Check server health
    print("1. Checking server health...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            print("   ✅ Server is running")
        else:
            print(f"   ❌ Server returned status: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Server not responding: {e}")
        return False
    
    # Check current status
    print("\n2. Current system status...")
    try:
        response = requests.get(f"{base_url}/cleanup/status", timeout=15)
        if response.status_code == 200:
            status = response.json()
            print(f"   📊 Cleanup status: {status}")
        else:
            print(f"   ❌ Failed to get cleanup status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error getting cleanup status: {e}")
    
    # Check rooms
    print("\n3. Current rooms...")
    try:
        response = requests.get(f"{base_url}/rooms", timeout=15)
        if response.status_code == 200:
            data = response.json()
            rooms = data.get('rooms', []) if isinstance(data, dict) else data
            print(f"   📊 Found {len(rooms)} rooms")
            for room in rooms:
                if isinstance(room, dict):
                    room_id = room.get('id', room.get('room_id', 'unknown'))
                    room_name = room.get('name', 'unnamed')
                    user_count = room.get('user_count', 0)
                    is_active = room.get('is_active', True)
                    status = "🟢" if is_active else "🔴"
                    print(f"      {status} {room_id}: {room_name} ({user_count} users)")
        else:
            print(f"   ❌ Failed to get rooms: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error getting rooms: {e}")
    
    # Check global users
    print("\n4. Global users...")
    try:
        response = requests.get(f"{base_url}/users/global", timeout=15)
        if response.status_code == 200:
            data = response.json()
            global_users = data.get('global_users', [])
            online_users = [u for u in global_users if u.get('is_online', False)]
            offline_users = [u for u in global_users if not u.get('is_online', False)]
            print(f"   📊 {len(global_users)} total users ({len(online_users)} online, {len(offline_users)} offline)")
            
            if global_users:
                print("   📋 Users:")
                for user in global_users:
                    status = "🟢" if user.get('is_online') else "🔴"
                    username = user.get('username', 'unknown')
                    room_id = user.get('room_id', 'none')
                    print(f"      {status} {username} (room: {room_id})")
        else:
            print(f"   ❌ Failed to get global users: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error getting global users: {e}")
    
    # Run cleanup operations
    print("\n5. Running cleanup operations...")
    
    # Force stuck users cleanup
    print("   a) Cleaning up stuck users...")
    try:
        response = requests.post(f"{base_url}/cleanup/force-stuck-users", timeout=20)
        if response.status_code == 200:
            result = response.json()
            print(f"      ✅ {result.get('message', 'Completed')}")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Error: {e}")
    
    # Auto-user cleanup
    print("   b) Cleaning up auto-generated users...")
    try:
        response = requests.post(f"{base_url}/cleanup/auto-users", timeout=20)
        if response.status_code == 200:
            result = response.json()
            print(f"      ✅ {result.get('message', 'Completed')}")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Error: {e}")
    
    # Comprehensive cleanup
    print("   c) Running comprehensive cleanup...")
    try:
        response = requests.post(f"{base_url}/cleanup/comprehensive", timeout=30)
        if response.status_code == 200:
            result = response.json()
            print(f"      ✅ {result.get('message', 'Completed')}")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Error: {e}")
    
    # Orphaned data cleanup
    print("   d) Cleaning up orphaned data...")
    try:
        response = requests.post(f"{base_url}/cleanup/orphaned-data", timeout=60)
        if response.status_code == 200:
            result = response.json()
            results = result.get('results', {})
            print(f"      ✅ Orphaned data cleanup completed:")
            print(f"         - {results.get('orphaned_files', 0)} files removed")
            print(f"         - {results.get('orphaned_users', 0)} users removed")
            print(f"         - {results.get('orphaned_rooms', 0)} rooms removed")
            print(f"         - {results.get('stale_global_users', 0)} global users removed")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except requests.exceptions.Timeout:
        print("      ⚠️ Timed out (normal for large cleanups)")
    except Exception as e:
        print(f"      ❌ Error: {e}")
    
    # Trigger general cleanup
    print("   e) Triggering general cleanup...")
    try:
        response = requests.post(f"{base_url}/cleanup/trigger", timeout=20)
        if response.status_code == 200:
            result = response.json()
            print(f"      ✅ {result.get('message', 'Completed')}")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Error: {e}")
    
    # Final status
    print("\n6. Final status...")
    try:
        response = requests.get(f"{base_url}/cleanup/status", timeout=15)
        if response.status_code == 200:
            status = response.json()
            print(f"   📊 Final cleanup status: {status}")
        else:
            print(f"   ❌ Failed to get final status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error getting final status: {e}")
    
    print("\n" + "=" * 60)
    print("✅ COMPREHENSIVE CLEANUP COMPLETED!")
    print("💡 This script cleaned up:")
    print("   - Stuck online users")
    print("   - Auto-generated users")
    print("   - Orphaned files in GCP Storage")
    print("   - Orphaned users and rooms")
    print("   - Stale global user registrations")
    print("   - Triggered general cleanup")
    
    return True

def main():
    """Main function with command line options"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "help":
            print("🧹 Cleanup Script Usage:")
            print("  python cleanup.py          - Run full cleanup")
            print("  python cleanup.py help     - Show this help")
            print("  python cleanup.py status   - Show system status only")
            return
        
        elif command == "status":
            # Just show status without running cleanup
            base_url = "http://localhost:8000"
            print("📊 SYSTEM STATUS")
            print("=" * 40)
            
            try:
                response = requests.get(f"{base_url}/cleanup/status", timeout=15)
                if response.status_code == 200:
                    status = response.json()
                    print(f"Cleanup status: {status}")
                else:
                    print(f"Failed to get status: {response.status_code}")
            except Exception as e:
                print(f"Error: {e}")
            return
    
    # Run full cleanup
    success = cleanup_system()
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 