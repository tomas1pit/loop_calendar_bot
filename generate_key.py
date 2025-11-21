#!/usr/bin/env python3
"""
Script to generate a new encryption key
"""

from encryption import EncryptionManager

if __name__ == "__main__":
    key = EncryptionManager.generate_key()
    print("Generated encryption key:")
    print(key)
    print("\nAdd this to your .env file as ENCRYPTION_KEY:")
    print(f"ENCRYPTION_KEY={key}")
