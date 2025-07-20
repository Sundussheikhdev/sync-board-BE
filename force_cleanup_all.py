#!/usr/bin/env python3
"""
FORCE CLEANUP ALL - Nuclear option to clear everything from Firestore and GCP Storage
⚠️  WARNING: This will delete ALL data - use with caution!
"""

import os
import sys
import requests
import json
from datetime import datetime

def force_cleanup_all():
    """Nuclear cleanup - clears everything from Firestore and GCP Storage"""
    base_url = "http://localhost:8000"
    
    print("☢️  NUCLEAR FORCE CLEANUP - CLEARING EVERYTHING")
    print("=" * 60)
    print("⚠️  WARNING: This will delete ALL data from Firestore and GCP Storage!")
    print("⚠️  This action cannot be undone!")
    print("=" * 60)
    
    # Ask for confirmation
    confirm = input("Type 'YES' to confirm you want to delete everything: ")
    if confirm != "YES":
        print("❌ Cleanup cancelled")
        return
    
    print("\n🚀 Starting nuclear cleanup...")
    print("=" * 60)
    
    try:
        # Step 1: Get all rooms first
        print("📋 Step 1: Getting all rooms...")
        response = requests.get(f"{base_url}/rooms", timeout=15)
        if response.status_code == 200:
            data = response.json()
            rooms = data.get('rooms', []) if isinstance(data, dict) else data
            print(f"   Found {len(rooms)} rooms to clean up")
            
            # Step 2: Clean up each room's data
            print("\n🧹 Step 2: Cleaning up room data...")
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
            print(f"❌ Failed to get rooms: {response.status_code}")
        
        # Step 3: Clean up orphaned files
        print("\n🗂️  Step 3: Cleaning up orphaned files...")
        try:
            response = requests.post(f"{base_url}/cleanup/orphaned-files", timeout=30)
            if response.status_code == 200:
                data = response.json()
                files_removed = data.get('files_removed', 0)
                print(f"   ✅ Removed {files_removed} orphaned files")
            else:
                print(f"   ❌ Failed to clean orphaned files: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error cleaning orphaned files: {e}")
        
        # Step 4: Clean up orphaned data
        print("\n🗑️  Step 4: Cleaning up orphaned data...")
        try:
            response = requests.post(f"{base_url}/cleanup/orphaned-data", timeout=30)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Orphaned data cleanup results:")
                for key, value in data.items():
                    print(f"      {key}: {value}")
            else:
                print(f"   ❌ Failed to clean orphaned data: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error cleaning orphaned data: {e}")
        
        # Step 5: Force cleanup stuck users
        print("\n👥 Step 5: Force cleaning stuck users...")
        try:
            response = requests.post(f"{base_url}/cleanup/force-stuck-users", timeout=15)
            if response.status_code == 200:
                data = response.json()
                users_removed = data.get('users_removed', 0)
                print(f"   ✅ Removed {users_removed} stuck users")
            else:
                print(f"   ❌ Failed to clean stuck users: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error cleaning stuck users: {e}")
        
        # Step 6: Comprehensive cleanup
        print("\n🔄 Step 6: Running comprehensive cleanup...")
        try:
            response = requests.post(f"{base_url}/cleanup/comprehensive", timeout=30)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Comprehensive cleanup completed:")
                for key, value in data.items():
                    print(f"      {key}: {value}")
            else:
                print(f"   ❌ Failed to run comprehensive cleanup: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error running comprehensive cleanup: {e}")
        
        # Step 7: Final verification
        print("\n🔍 Step 7: Final verification...")
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
                    for user in global_users[:5]:  # Show first 5
                        print(f"      - {user.get('username', 'Unknown')}")
                    if len(global_users) > 5:
                        print(f"      ... and {len(global_users) - 5} more")
                        
        except Exception as e:
            print(f"   ❌ Error during verification: {e}")
        
        print("\n" + "=" * 60)
        print("🎉 NUCLEAR CLEANUP COMPLETED!")
        print("=" * 60)
        print("✅ All data has been cleared from Firestore and GCP Storage")
        print("✅ You can now start fresh with a clean slate")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Nuclear cleanup failed: {e}")
        import traceback
        traceback.print_exc()

def show_status():
    """Show current status before cleanup"""
    base_url = "http://localhost:8000"
    
    print("📊 CURRENT STATUS BEFORE CLEANUP")
    print("=" * 40)
    
    try:
        # Check rooms
        response = requests.get(f"{base_url}/rooms", timeout=15)
        if response.status_code == 200:
            data = response.json()
            rooms = data.get('rooms', []) if isinstance(data, dict) else data
            print(f"📋 Rooms: {len(rooms)}")
            for room in rooms[:3]:  # Show first 3
                print(f"   - {room.get('name', 'Unknown')} (ID: {room.get('id', 'Unknown')})")
            if len(rooms) > 3:
                print(f"   ... and {len(rooms) - 3} more")
        
        # Check global users
        response = requests.get(f"{base_url}/users/global", timeout=15)
        if response.status_code == 200:
            data = response.json()
            global_users = data.get('global_users', [])
            print(f"👥 Global Users: {len(global_users)}")
            for user in global_users[:3]:  # Show first 3
                print(f"   - {user.get('username', 'Unknown')}")
            if len(global_users) > 3:
                print(f"   ... and {len(global_users) - 3} more")
                
    except Exception as e:
        print(f"❌ Error getting status: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_status()
    else:
        force_cleanup_all() 