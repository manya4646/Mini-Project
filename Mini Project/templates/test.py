def extract_key_frames(video_path, step=3, resize_factor=0.5):
    cap = cv2.VideoCapture(video_path)
    frame_number = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        if frame_number % step == 0:
            frame = cv2.resize(frame, (0, 0), fx=resize_factor, fy=resize_factor)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            yield frame_number, gray_frame
        frame_number += 1
    cap.release()
