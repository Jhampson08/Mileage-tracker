"""
Generates bcrypt password hashes to paste into config.yaml.

Usage:
    python hash_passwords.py

You'll be prompted for one or more plaintext passwords and get back
the hashed value to paste into the `password:` field for that user
in config.yaml. Never store plaintext passwords in config.yaml.
"""

import bcrypt
import getpass

print("Outreach Mileage Tracker — password hash generator")
print("Press Enter with no input when you're done.\n")

while True:
    pw = getpass.getpass("Plaintext password (leave blank to quit): ")
    if not pw:
        break
    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print(f"Hashed value:\n{hashed}\n")
