#!/usr/bin/env python3
"""
NUCLEAR CLEANUP - True nuclear option to clear EVERYTHING
⚠️  WARNING: This will delete ALL data - use with caution!
"""

import os
import sys
import requests
import json
from datetime import datetime

def nuclear_cleanup():
    """True nuclear cleanup - clears EVERYTHING from Firestore and GCP Storage"""
    base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    print("☢️  TRUE NUCLEAR CLEANUP - CLEARING EVERYTHING")
    print("=" * 60)
    print("⚠️  WARNING: This will delete ALL data from Firestore and GCP Storage!")
    print("⚠️  This action cannot be undone!")
    print("=" * 60)
    
    # Ask for confirmation
    confirm = input("Type 'DESTROY' to confirm you want to delete everything: ")
    if confirm != "DESTROY":
        print("❌ Nuclear cleanup cancelled")
        return
    
    print("\n🚀 Starting TRUE nuclear cleanup...")
    print("=" * 60)
    
    try:
        # Step 1: Force delete ALL global users
        print("👥 Step 1: Force deleting ALL global users...")
        try:
            # Call the new endpoint to delete ALL global users
            response = requests.post(f"{base_url}/cleanup/delete-all-global-users", timeout=30)
            if response.status_code == 200:
                data = response.json()
                users_removed = data.get('users_removed', 0)
                print(f"   ✅ Deleted {users_removed} global users")
            else:
                print(f"   ❌ Failed to delete all global users: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error deleting all global users: {e}")
        
        # Step 2: Force delete ALL files from GCP bucket
        print("\n🗂️  Step 2: Force deleting ALL files from GCP bucket...")
        try:
            # Call the new endpoint to delete ALL files
            response = requests.post(f"{base_url}/cleanup/delete-all-files", timeout=60)
            if response.status_code == 200:
                data = response.json()
                files_removed = data.get('files_removed', 0)
                files_list = data.get('files_list', [])
                print(f"   ✅ Deleted {files_removed} files from GCP bucket")
                
                # Show the files that were deleted
                if files_list:
                    print(f"   📄 Files deleted:")
                    for file_info in files_list:
                        print(f"      - {file_info['name']} ({file_info['size']} bytes)")
                else:
                    print(f"   📄 No files found in bucket")
            else:
                print(f"   ❌ Failed to delete all files: {response.status_code}")
                print(f"   Error: {response.text}")
                print(f"   ⚠️  You may need to manually delete files from GCP Console")
        except Exception as e:
            print(f"   ❌ Error deleting all files: {e}")
            print(f"   ⚠️  You may need to manually delete files from GCP Console")
        
        # Step 3: Clean up all room data
        print("\n🧹 Step 3: Cleaning up ALL room data...")
        try:
            # Get all rooms
            response = requests.get(f"{base_url}/rooms", timeout=15)
            if response.status_code == 200:
                data = response.json()
                rooms = data.get('rooms', []) if isinstance(data, dict) else data
                print(f"   Found {len(rooms)} rooms to clean up")
                
                # Clean up each room's data
                for i, room in enumerate(rooms, 1):
                    room_id = room.get('id')
                    room_name = room.get('name', 'Unknown')
                    print(f"   [{i}/{len(rooms)}] Cleaning room: {room_name} (ID: {room_id})")
                    
                    try:
                        # Clean up room data
                        response = requests.post(f"{base_url}/cleanup/room-data/{room_id}", timeout=10)
                        if response.status_code == 200:
                            print(f"      ✅ Room data cleaned")
                        else:
                            print(f"      ❌ Failed to clean room data: {response.status_code}")
                    except Exception as e:
                        print(f"      ❌ Error cleaning room data: {e}")
            else:
                print(f"   ❌ Failed to get rooms: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error cleaning room data: {e}")
        
        # Step 4: Run all cleanup endpoints
        print("\n🔄 Step 4: Running all cleanup endpoints...")
        cleanup_endpoints = [
            ("orphaned-files", "Orphaned files"),
            ("orphaned-data", "Orphaned data"),
            ("force-stuck-users", "Stuck users"),
            ("server-restart", "Server restart cleanup"),
            ("comprehensive", "Comprehensive cleanup")
        ]
        
        for endpoint, description in cleanup_endpoints:
            try:
                print(f"   Running {description} cleanup...")
                response = requests.post(f"{base_url}/cleanup/{endpoint}", timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    print(f"      ✅ {description} cleanup completed")
                else:
                    print(f"      ❌ Failed to run {description} cleanup: {response.status_code}")
            except Exception as e:
                print(f"      ❌ Error running {description} cleanup: {e}")
        
        # Step 5: Final verification
        print("\n🔍 Step 5: Final verification...")
        try:
            # Check rooms
            response = requests.get(f"{base_url}/rooms", timeout=15)
            if response.status_code == 200:
                data = response.json()
                rooms = data.get('rooms', []) if isinstance(data, dict) else data
                print(f"   📊 Remaining rooms: {len(rooms)}")
                
                if len(rooms) == 0:
                    print("   ✅ All rooms cleaned up successfully!")
                else:
                    print("   ⚠️  Some rooms still exist:")
                    for room in rooms:
                        print(f"      - {room.get('name', 'Unknown')} (ID: {room.get('id', 'Unknown')})")
            
            # Check global users
            response = requests.get(f"{base_url}/users/global", timeout=15)
            if response.status_code == 200:
                data = response.json()
                global_users = data.get('global_users', [])
                print(f"   👥 Remaining global users: {len(global_users)}")
                
                if len(global_users) == 0:
                    print("   ✅ All global users cleaned up successfully!")
                else:
                    print("   ⚠️  Some global users still exist:")
                    for user in global_users:
                        print(f"      - {user.get('username', 'Unknown')}")
                        
        except Exception as e:
            print(f"   ❌ Error during verification: {e}")
        
        print("\n" + "=" * 60)
        print("🎉 TRUE NUCLEAR CLEANUP COMPLETED!")
        print("=" * 60)
        print("✅ All data has been cleared from Firestore and GCP Storage")
        print("✅ You can now start fresh with a clean slate")
        print("=" * 60)
        print("⚠️  If files still exist in GCP bucket, you may need to:")
        print("   1. Go to GCP Console > Storage > Browser")
        print("   2. Select your bucket")
        print("   3. Select all files and delete them manually")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Nuclear cleanup failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    nuclear_cleanup() 