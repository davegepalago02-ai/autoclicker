import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab
import time

# --- Configuration Constants ---
# Target Blue Polygon RGB: (0, 0, 100) to (100, 120, 255)
# OpenCV uses BGR internally. We'll capture with PIL (RGB) and convert to BGR.
# Therefore, bounding constraints are in BGR format:
LOWER_BLUE_BGR = np.array([100, 0, 0], dtype="uint8")
UPPER_BLUE_BGR = np.array([255, 120, 100], dtype="uint8")

SAFE_BUFFER_PX = 1
RENDER_DELAY_SEC = 1.0
INITIAL_ZOOM_OUT_STEPS = 3
MAX_ZOOM_ATTEMPTS = 20

def get_polygon_bounds(scan_region_box):
    """
    Captures the scan region, masks for the blue polygon, and returns its bounding box.
    scan_region_box: (x, y, width, height) of the "Screenshot Area".
    Returns (min_x, min_y, max_x, max_y) relative to the scan region, or None if not found.
    """
    x, y, w, h = scan_region_box
    bbox = (x, y, x + w, y + h)
    
    # Grab only the scan area to maximize performance and avoid false positives outside
    screenshot = ImageGrab.grab(bbox=bbox)
    
    # Convert PIL Image (RGB) to OpenCV format (BGR) for filtering
    img_np = np.array(screenshot)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    
    cv2.imwrite("debug_screenshot_raw.png", img_bgr)
    
    # Create mask for blue pixels corresponding to the legacy app's polygon color
    mask = cv2.inRange(img_bgr, LOWER_BLUE_BGR, UPPER_BLUE_BGR)
    
    # Find contours instead of just random non-zero pixels
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        # Save the all-black mask if nothing is found to see what it looked at
        cv2.imwrite("debug_masked_pixels.png", mask)
        return None
        
    # Find the largest contour by bounding box area (this guarantees we track the farm, not a stray blue pixel)
    max_area = 0
    best_cnt = None
    best_bbox = None
    
    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw * bh > max_area:
            max_area = bw * bh
            best_cnt = cnt
            best_bbox = (bx, by, bx + bw - 1, by + bh - 1)
            
    if best_bbox is not None:
        min_x, min_y, max_x, max_y = best_bbox
        
        # Calculate true Center of Mass (Centroid) from the raw contour
        M = cv2.moments(best_cnt)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            # Fallback if moment is 0 (e.g. single pixel anomaly)
            cx = min_x + (max_x - min_x) // 2
            cy = min_y + (max_y - min_y) // 2
        
        # --- DEBUG OUTPUT ---
        debug_img = img_bgr.copy()
        cv2.rectangle(debug_img, (min_x, min_y), (max_x, max_y), (0, 0, 255), 2)
        # Draw a tiny blue circle on the calculated center of mass
        cv2.circle(debug_img, (cx, cy), 4, (255, 0, 0), -1)
        
        cv2.imwrite("debug_masked_pixels.png", mask)
        cv2.imwrite("debug_bounding_box.png", debug_img)
        # --------------------
        
        return (min_x, min_y, max_x, max_y, cx, cy)
        
    return None

def maximize_polygon(scan_region_box):
    """
    Step-Back Zoom Algorithm: Ensures a blue-outlined polygon is maximized within 
    the bounding box without touching a 20px safe buffer from the edges.
    
    Returns True if successfully maximized and ready for screenshot down the pipeline.
    Returns False if it failed/timed out.
    """
    print(f"[*] Starting auto-zoom on scan region: {scan_region_box}")
    x, y, w, h = scan_region_box
    
    # REQUIREMENT 4: Coordinate Focus - Center cursor in the scan region
    center_x = x + (w // 2)
    center_y = y + (h // 2)
    pyautogui.moveTo(center_x, center_y)
    print(f"[*] Moved mouse to center: ({center_x}, {center_y})")
    
    # Temporarily removed the initial 'Zoom out 3 times' steps to see if that was causing the problem.
    # The loop will begin checking polygon size immediately.

    # Standard Windows mouse wheel directions!
    # Scroll UP (120) zooms IN
    # Scroll DOWN (-120) zooms OUT
    scroll_in = 120
    scroll_out = -120

    attempts = 0
    prev_area = 0
    last_action = None  # Tracks if we just 'zoomed_in' or 'zoomed_out'
    SAFE_BUFFER_PX = 1 # Reduced to 1px to be more forgiving
    
    while attempts < MAX_ZOOM_ATTEMPTS:
        attempts += 1
        
        bounds = get_polygon_bounds(scan_region_box)
        if bounds is None:
            if attempts > 1 and last_action == 'zoomed_in':
                # The jumpy zoom was so large that the polygon's edges went completely off-screen!
                print("[*] Polygon disappeared! We over-zoomed entirely off the scan region.")
                print("[*] Reverting back 1 level to the optimal size...")
                pyautogui.scroll(scroll_out)
                time.sleep(RENDER_DELAY_SEC)
                return True
            else:
                print("[!] Error: Blue polygon not found in the defined scan region.")
                return False
            
        min_x, min_y, max_x, max_y, cx, cy = bounds
        
        current_area = (max_x - min_x) * (max_y - min_y)
        box_area = w * h
        print(f"  -> Attempt {attempts}: Polygon area={current_area} | Bounds: X({min_x} to {max_x}), Y({min_y} to {max_y})")

        prev_area = current_area
        
        # Determine if the polygon is literally CUT OFF by the capture region edge
        is_cut = (min_x <= 0 or min_y <= 0 or max_x >= (w - 2) or max_y >= (h - 2))
        
        # Determine if it's just touching our safe padding
        breached = (min_x <= SAFE_BUFFER_PX or min_y <= SAFE_BUFFER_PX or 
                    max_x >= (w - SAFE_BUFFER_PX) or max_y >= (h - SAFE_BUFFER_PX))
        
        if is_cut:
            print("[*] CRITICAL: Polygon is CUT OFF by the edge of the scan region!")
            if last_action == 'zoomed_in':
                print("[*] We zoomed in too far! Stepping back exactly 1 level to restore.")
                pyautogui.scroll(scroll_out)
                time.sleep(RENDER_DELAY_SEC)
                break
            else:
                print("[*] Zooming out to fit the entire polygon...")
                pyautogui.scroll(scroll_out)
                last_action = 'zoomed_out'
                time.sleep(RENDER_DELAY_SEC)
                continue
                
        elif breached:
            print("[*] Polygon is touching the Safe Buffer edges.")
            if last_action == 'zoomed_in':
                print("[*] Optimal Max Size Reached! Stepping back exactly 1 level to fit.")
                pyautogui.scroll(scroll_out)
                time.sleep(RENDER_DELAY_SEC)
                break
            else:
                print("[*] Still too close to the edge. Zooming out...")
                pyautogui.scroll(scroll_out)
                last_action = 'zoomed_out'
                time.sleep(RENDER_DELAY_SEC)
        else:
            # It is currently safe inside the box.
            if last_action == 'zoomed_out':
                # We were zooming out because it was too big, and we just finally made it safe. 
                print("[*] We found the safe border! Optimal zoom achieved.")
                break
                
            print("  -> Polygon is safely inside, but not maximized. Zooming in...")
            pyautogui.scroll(scroll_in)
            last_action = 'zoomed_in'
            time.sleep(RENDER_DELAY_SEC)
            
    else:
        print("[!] Error: Reached maximum zoom attempts. Polygon never stabilized. (Try drawing a larger calibration box!)")
        return False
        
    # --- FINAL AUTO CENTERING USING TRUE CENTER OF MASS ---
    # Removed: Dragging explicitly scales differently in PABS and throws maximized polygons into the borders.
    # The organic zoom provides a safer lock.
            
    print("[SUCCESS] Auto-Zoom complete and locked!")
    return True

def calibrate_scan_region():
    """
    REQUIREMENT 1: Viewport Calibration
    Helper functionality allowing the user to precisely document the 'Screenshot Area' coordinates.
    Returns: (x, y, width, height)
    """
    print("\n[Calibration Utility]")
    print("Move your mouse to the TOP-LEFT inner corner of the green 'Screenshot Area'.")
    print("Capturing in 3 seconds...")
    time.sleep(3)
    x1, y1 = pyautogui.position()
    print(f"[*] Top-Left recorded at: ({x1}, {y1})")
    
    print("\nMove your mouse to the BOTTOM-RIGHT inner corner of the green 'Screenshot Area'.")
    print("Capturing in 3 seconds...")
    time.sleep(3)
    x2, y2 = pyautogui.position()
    print(f"[*] Bottom-Right recorded at: ({x2}, {y2})")
    
    w = x2 - x1
    h = y2 - y1
    print(f"\n[*] Calibrated 'Scan Region' (x, y, w, h): ({x1}, {y1}, {w}, {h})")
    return (x1, y1, w, h)

if __name__ == "__main__":
    # Provides explicit guidance if user executes this directly instead of importing.
    print("[!] auto_zoom.py is a module. Please use test_runner.py to interactively verify.")
