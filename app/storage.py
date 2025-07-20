from google.cloud import storage
from fastapi import UploadFile
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

class StorageManager:
    def __init__(self):
        # Initialize GCP Storage client with service account credentials
        self.client = None
        self.bucket_name = os.getenv("GCP_BUCKET_NAME", "collaborative-app-files-board-sync-466501")
        self.bucket = None
        
        # Try to initialize GCP Storage client
        try:
            # Try service account JSON first (for local development)
            key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "board-sync-466501-c38a2cead941.json")
            if os.path.exists(key_file):
                self.client = storage.Client.from_service_account_json(key_file)
                print(f"✅ GCP Storage initialized with service account: {key_file}")
            else:
                # Use default credentials (for Cloud Run)
                self.client = storage.Client()
                print("✅ GCP Storage initialized with default credentials (Cloud Run)")
            
        # Try to get or create bucket
            self.bucket = self.client.bucket(self.bucket_name)
            if not self.bucket.exists():
                self.bucket = self.client.create_bucket(self.bucket_name)
            print("✅ GCP Storage initialized successfully")
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize GCP Storage: {e}")
            print("📁 File uploads will be disabled for local development.")
            print("🔧 To enable file uploads, set up GCP credentials or use GCP_BUCKET_NAME environment variable.")
            self.client = None
            self.bucket = None

    async def upload_file(self, file: UploadFile) -> str:
        """Upload file to GCP Storage and return public URL"""
        print(f"🔧 Storage upload started for: {file.filename}")
        
        if not self.bucket:
            print("❌ No bucket available")
            raise Exception("GCP Storage not configured. File uploads are disabled for local development. Set up GCP credentials to enable file uploads.")
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        print(f"📝 Generated filename: {unique_filename}")
        
        # Create blob
        blob = self.bucket.blob(unique_filename)
        print(f"📦 Created blob: {blob.name}")
        
        # Set content type
        blob.content_type = file.content_type
        print(f"📋 Set content type: {file.content_type}")
        
        # Upload file
        print("📤 Reading file content...")
        content = await file.read()
        print(f"📊 File size: {len(content)} bytes")
        
        print("📤 Uploading to GCP Storage...")
        # Use upload_from_file with BytesIO to properly handle content type
        from io import BytesIO
        file_obj = BytesIO(content)
        blob.upload_from_file(file_obj, content_type=file.content_type)
        print("✅ Upload completed")
        
        # Make blob publicly readable
        print("🔓 Making blob public...")
        blob.make_public()
        print(f"✅ Blob is public: {blob.public_url}")
        
        return blob.public_url

    def generate_signed_url(self, filename: str, expiration_minutes: int = 60) -> Optional[str]:
        """Generate a signed URL for private file access"""
        if not self.bucket:
            return None
        
        try:
            blob = self.bucket.blob(filename)
            expiration = datetime.now() + timedelta(minutes=expiration_minutes)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
            return url
        except Exception as e:
            print(f"Error generating signed URL: {e}")
            return None

    def delete_file(self, filename: str) -> bool:
        """Delete file from GCP Storage"""
        if not self.bucket:
            return False
        
        try:
            blob = self.bucket.blob(filename)
            blob.delete()
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def list_files(self, prefix: str = "") -> list:
        """List files in bucket with optional prefix"""
        if not self.bucket:
            return []
        
        try:
            blobs = self.bucket.list_blobs(prefix=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            print(f"Error listing files: {e}")
            return [] 