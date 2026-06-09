#!/usr/bin/env python3
import os
import sys
import time
import argparse

# Go up one level from 'scripts' directory to the project root, then join with 'backend'
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
try:
    from ssh_connect import SSHConnector
except ImportError:
    print("Error: Could not import 'SSHConnector' from 'backend/ssh_connect.py'")
    sys.exit(1)

def progress_callback(transferred, total):
    percent = (transferred / total) * 100
    mb_transferred = transferred / (1024 * 1024)
    mb_total = total / (1024 * 1024)
    sys.stdout.write(f"\rUploading: {mb_transferred:.2f}MB / {mb_total:.2f}MB ({percent:.1f}%)")
    sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(
        description="Upload a local file to a remote server using SSH/SFTP.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("local_path", help="Path to the local file to upload")
    parser.add_argument("remote_path", nargs="?", help="Target path on the remote server. Defaults to /root/<filename>")

    # Connection details default to the most recent server credentials
    parser.add_argument("--host", default="217.18.60.123", help="Remote SSH server host")
    parser.add_argument("--user", "-u", default="root", help="SSH username")
    parser.add_argument("--password", "-p", default="w1LENdygKqX9.7", help="SSH password")
    parser.add_argument("--port", "-P", type=int, default=22, help="SSH port")

    args = parser.parse_args()

    # Verify local file exists
    if not os.path.isfile(args.local_path):
        print(f"Error: Local file '{args.local_path}' does not exist.")
        sys.exit(1)

    local_path = os.path.abspath(args.local_path)
    filename = os.path.basename(local_path)

    # Determine remote path
    if args.remote_path:
        remote_path = args.remote_path
        # If remote_path ends with a slash, treat it as a directory and append the filename
        if remote_path.endswith("/"):
            remote_path = os.path.join(remote_path, filename)
    else:
        remote_path = f"/root/{filename}"

    remote_dir = os.path.dirname(remote_path)

    print(f"Connecting to {args.host}:{args.port} as '{args.user}'...")
    ssh = SSHConnector(host=args.host, username=args.user, password=args.password, port=args.port)

    if not ssh.connect():
        print("Failed to establish SSH connection.")
        sys.exit(1)

    try:
        # 1. Ensure remote parent directory exists
        if remote_dir and remote_dir != "/":
            print(f"Ensuring remote directory '{remote_dir}' exists...")
            stdout, stderr, code = ssh.execute(f"mkdir -p {remote_dir}")
            if code != 0:
                print(f"Warning: failed to run 'mkdir -p {remote_dir}': {stderr}")

        # 2. Start SFTP and upload to a temp path first
        print(f"Starting SFTP session...")
        sftp = ssh.client.open_sftp()

        temp_path = f"/tmp/{filename}.upload_tmp"
        print(f"Uploading '{local_path}' to temp path '{temp_path}'...")
        start_time = time.time()
        sftp.put(local_path, temp_path, callback=progress_callback)
        duration = time.time() - start_time
        print(f"\nUpload to temp completed in {duration:.1f} seconds.")

        # 3. Atomically move from temp to final destination
        print(f"Moving '{temp_path}' -> '{remote_path}'...")
        stdout, stderr, code = ssh.execute(f"mv {temp_path} {remote_path}")
        if code != 0:
            print(f"Error: failed to move file to '{remote_path}': {stderr}")
            ssh.execute(f"rm -f {temp_path}")
            sys.exit(1)

        print(f"File moved successfully. Upload completed in {duration:.1f} seconds total.")

    except Exception as e:
        print(f"\nAn error occurred during upload: {e}")
        # Attempt to clean up temp file if it was created
        try:
            ssh.execute(f"rm -f /tmp/{filename}.upload_tmp")
        except Exception:
            pass
        sys.exit(1)
    finally:
        if 'sftp' in locals():
            sftp.close()
        ssh.close()

if __name__ == "__main__":
    main()