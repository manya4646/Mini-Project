import os
import cv2
import numpy as np
import sqlite3
import hashlib
from imagehash import phash, hex_to_hash
from PIL import Image
from tqdm import tqdm
# import tkinter as tk
# from tkinter import filedialog
# from tkinter import Tk, filedialog

DB_FILE = "video_frames.db"  # SQLite Database File

def create_database():
    """Creates the database table only if it does not exist."""
    if not os.path.exists(DB_FILE):
        print("[INFO] Database not found, creating a new one...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_name TEXT,
                frame_hash TEXT,
                frame_number INTEGER
            )
        """)
        conn.commit()
        conn.close()
        print("[INFO] Database created successfully.")
    else:
        print("[INFO] Database already exists. Skipping database creation.")

# def select_database_folder():
#     """Opens a dialog to select the database folder dynamically."""
#     root = Tk()
#     root.withdraw()
#     folder_selected = filedialog.askdirectory(title="Select Database Videos Folder")
#     return folder_selected if folder_selected else os.path.join(os.getcwd(), "database_videos")

# def select_video_for_comparison():
#     """Opens a file dialog and starts in the default folder for comparison videos."""
#     root = tk.Tk()
#     root.withdraw()  # Hide Tkinter root window
#     root.call('wm', 'attributes', '.', '-topmost', True)  # Ensure the dialog appears on top

#     # Set the default folder where the comparison videos are stored
#     default_folder = r"C:\Users\g_n-n\Desktop\comparison_videos"

#     file_path = filedialog.askopenfilename(
#         initialdir=default_folder,  # Open in the correct folder
#         title="Select a video file for comparison",
#         filetypes=[("Video Files", "*.mp4;*.avi;*.mov;*.mkv")],  # ✅ Only show video files
#     )

#     root.destroy()  # Close Tkinter properly

#     if not file_path:
#         print("⚠️ No video selected! Please select a valid comparison video.")
#     else:
#         print(f"✅ Selected video: {file_path}")

#     return file_path  # Return the selected video file path




def extract_key_frames(video_path, step=3, resize_factor=0.5):
    """Efficiently extracts key frames at a fixed rate, reducing memory usage."""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    frame_number = 0

    with tqdm(total=total_frames, desc=f"Extracting Frames ({os.path.basename(video_path)})", unit="frame") as pbar:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_number % step == 0:
                frame = cv2.resize(frame, (0, 0), fx=resize_factor, fy=resize_factor)
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frames.append((frame_number, gray_frame))

            frame_number += 1
            pbar.update(1)

            if len(frames) >= 1000:
                yield frames
                frames = []

    cap.release()
    if frames:
        yield frames

def hash_frame(frame):
    """Computes a perceptual hash for each frame."""
    pil_image = Image.fromarray(frame).resize((16, 16))
    return str(phash(pil_image))

def save_video_to_database(video_name, key_frames_generator):
    """Saves extracted key frame hashes into the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM video_frames WHERE video_name=?", (video_name,))
    count = cursor.fetchone()[0]

    if count > 0:
        print(f"[INFO] Video '{video_name}' is already in the database. Skipping processing.")
        conn.close()
        return

    print(f"[INFO] Processing and saving frames for '{video_name}'...")

    for key_frames in key_frames_generator:
        for frame_number, frame in key_frames:
            frame_hash = hash_frame(frame)
            cursor.execute("INSERT INTO video_frames (video_name, frame_hash, frame_number) VALUES (?, ?, ?)", 
                           (video_name, frame_hash, frame_number))
        conn.commit()

    conn.close()
    print(f"[INFO] Frames for '{video_name}' saved successfully.")

def load_saved_frames():
    """Loads saved video frame hashes from the database and ensures full video paths."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT video_name, frame_hash, frame_number FROM video_frames ORDER BY video_name, frame_number ASC")
    saved_frames = cursor.fetchall()
    conn.close()

    saved_videos = {}
    for video_name, frame_hash, frame_number in saved_frames:
        full_video_path = os.path.join(DATABASE_FOLDER, video_name)  # Ensure correct path
        if full_video_path not in saved_videos:
            saved_videos[full_video_path] = []
        saved_videos[full_video_path].append((frame_number, frame_hash))

    return saved_videos




def hamming_distance(hash1, hash2):
    """Computes Hamming Distance between perceptual hashes."""
    try:
        hash1 = hex_to_hash(hash1.strip())
        hash2 = hex_to_hash(hash2.strip())
        return hash1 - hash2
    except Exception as e:
        print(f"[ERROR] Failed to convert hash: {hash1}, {hash2} - {e}")
        return 100

def find_all_matches(database_hashes, new_video_hashes, threshold=3):
    """Finds all occurrences of the new video's frames inside the database video."""
    db_hash_list = [frame_hash for _, frame_hash in database_hashes]
    new_hash_list = [frame_hash for _, frame_hash in new_video_hashes]

    db_len = len(db_hash_list)
    new_len = len(new_hash_list)
    min_match_ratio = 0.5  # Reduce threshold slightly to allow better matching

    match_positions = []

    with tqdm(total=db_len - new_len + 1, desc="Comparing Frames", unit="comparison") as pbar:
        for i in range(db_len - new_len + 1):
            matches = sum(hamming_distance(db_hash_list[i + j], new_hash_list[j]) < threshold for j in range(new_len))
            match_ratio = matches / new_len

            if match_ratio >= min_match_ratio:
                match_positions.append(i)  # Store all match positions (do not stop at the first one)

            pbar.update(1)

    if not match_positions:
        print("⚠️ No matches found for this video! Try reducing the threshold.")
    return match_positions


def convert_frame_to_time(video_path, frame_number):
    """Converts frame number to MM:SS format based on FPS."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    if fps == 0 or fps > 240:  # Avoid invalid FPS (e.g., 500+ FPS issues)
        print(f"⚠️ Warning: FPS {fps} is not valid for {video_path}. Setting to default 30.")
        fps = 30  # Default FPS value to avoid incorrect calculations

    seconds = frame_number / fps
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)

    return f"{minutes:02}:{seconds:02}"

def compare_with_database(new_video_path):
    """Checks if a new video matches any saved videos in the database using sequence matching."""
    
    key_frames = extract_key_frames(new_video_path)
    
    # Flatten frames from generator
    all_key_frames = [frame for batch in key_frames for frame in batch]

    # Extract hashes for the new video
    new_frame_hashes = [(frame_number, hash_frame(frame)) for frame_number, frame in all_key_frames]

    # print("[DEBUG] New video hashes:")
    # for frame_number, frame_hash in new_frame_hashes[:10]:  # Print only first 10
    #     print(f"Frame {frame_number} - Hash: {frame_hash}")

    # Load saved video frame hashes
    saved_frames = load_saved_frames()
    if not saved_frames:
        print("⚠️ No videos found in the database. Please add videos first.")
        return
    
    found_any = False  # Track if any matches were found

    # 🔍 Iterate over all database videos
    result_log = []

    for video_name, frames in saved_frames.items():
        db_video_path = os.path.join(DATABASE_FOLDER, video_name)
        print(f"[DEBUG] Checking against database video: {video_name}")

        if not os.path.exists(db_video_path):
            print(f"⚠️ Warning: Video file {db_video_path} does not exist. Skipping...")
            continue

        db_frames = [(frame_number, frame_hash) for frame_number, frame_hash in frames]
        cap = cv2.VideoCapture(db_video_path)
        if not cap.isOpened():
            print(f"⚠️ Warning: Could not open video file {db_video_path}. Skipping...")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if fps == 0 or fps > 240:
            fps = 30

        match_positions = find_all_matches(db_frames, new_frame_hashes)
        if match_positions:
            found_any = True
            for match_index in match_positions:
                start_time = match_index / fps
                end_time = (match_index + len(new_frame_hashes)) / fps
                timestamp = f"{int(start_time//60)}:{int(start_time%60)} - {int(end_time//60)}:{int(end_time%60)}"
                result_log.append(f"{os.path.basename(video_name)} at {timestamp}")

    if found_any:
        return result_log
    else:
        return []



def is_video_in_database(video_name):
    """Checks if a video is already stored in the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM video_frames WHERE video_name=?", (video_name,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0  # Returns True if video exists, False otherwise

# Initialize Database
create_database()

# 📂 Let the user select the database folder
DATABASE_FOLDER = r"C:\Users\g_n-n\Desktop\database_videos"
print(f"[INFO] Using database folder: {DATABASE_FOLDER}")

# Get all video files from the selected folder
database_videos = [f for f in os.listdir(DATABASE_FOLDER) if f.endswith((".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".rm", ".vob", ".3gp", ".ogg", ".asf", ".swf", ".ts", ".m2ts", ".divx", ".rmvb", ".f4v", ".mxf", ".mts", ".qt", ".dvr-ms", ".ogv"))]

# Store videos in database
for video in database_videos:
    if not os.path.exists(os.path.join(DATABASE_FOLDER, video)):
        continue
    if not is_video_in_database(video):
        print(f"[INFO] Storing '{video}' in the database...")
        key_frames = extract_key_frames(os.path.join(DATABASE_FOLDER, video))
        save_video_to_database(video, key_frames)

# # 🎥 Select and compare a video
# new_video = select_video_for_comparison()
# if not new_video:
#     print("⚠️ No video selected. Exiting...")
# else:
#     compare_with_database(new_video)
