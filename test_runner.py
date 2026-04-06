import auto_zoom
import time
import pyautogui

def main():
    print("--------------------------------------------------")
    print(" PABS Auto-Zoom Utility - Interactive Test Runner ")
    print("--------------------------------------------------")
    print("\n[Configuration]")
    print("Do you know the exact (x, y, width, height) of the Green 'Screenshot Area'?")
    answer = input("Press 'y' to enter them, or 'n' to run the calibration tool: ").strip().lower()

    if answer == 'y':
        try:
            val_str = input("Enter x, y, width, height separated by commas (e.g. 100, 200, 800, 600): ")
            vals = [int(v.strip()) for v in val_str.split(',')]
            scan_region = tuple(vals[:4])
        except Exception as e:
            print(f"[!] Invalid input: {e}")
            return
    else:
        print("\n--- Starting Interactive Calibration ---")
        scan_region = auto_zoom.calibrate_scan_region()

    print("\n--------------------------------------------------")
    print(f"[*] Final Target Scan Region confirmed: {scan_region}")
    print("\n--- Auto-Zoom execution will start in 5 seconds ---")
    print(">>> ACTION: Switch your window to the legacy PABS application now! <<<")
    print(">>> ACTION: Ensure the farm / screen area is fully visible on screen. <<<")
    
    # 5-second delay to let user switch active windows
    for i in range(5, 0, -1):
        print(f"Starting in {i}...")
        time.sleep(1)
        
    print("\n[*] Initiating Auto-Zoom execution (auto_zoom.maximize_polygon)...")
    success = auto_zoom.maximize_polygon(scan_region)
    
    print("\n--------------------------------------------------")
    if success:
        print("[SUCCESS] Polygon was maximized beautifully!")
        print("[SUCCESS] The viewport is now ready for the Auto-Clicker final screenshot hook.")
    else:
        print("[FAILED] Process timed out or encountered an error. Check application visibility.")
    print("--------------------------------------------------")

if __name__ == "__main__":
    main()
