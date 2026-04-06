import tkinter as tk
from tkinter import messagebox
import threading
import time
import pyautogui
import auto_zoom

class CalibrationOverlay:
    def __init__(self, parent_gui):
        self.parent = parent_gui
        self.root = tk.Toplevel(self.parent.root)
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.4)
        self.root.config(bg='black', cursor="cross")
        self.root.attributes('-topmost', True)

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        # User can press esc to abort calibration
        self.root.bind('<Escape>', lambda e: self.abort_calibration())

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # Draw a semi-transparent green box with a red outline to mimic screenshot region
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=3, fill='green')

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        end_x, end_y = (event.x, event.y)
        
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        w = x2 - x1
        h = y2 - y1
        
        self.root.destroy()
        
        if w > 20 and h > 20:
            self.parent.x_var.set(str(x1))
            self.parent.y_var.set(str(y1))
            self.parent.w_var.set(str(w))
            self.parent.h_var.set(str(h))
            self.parent.set_status("Calibration Complete", "green")
            
            # Show success and bring main GUI back
            self.parent.root.lift()
            self.parent.root.attributes('-topmost', True)
            self.parent.root.after_idle(self.parent.root.attributes, '-topmost', False)
        else:
            self.abort_calibration()

    def abort_calibration(self):
        self.root.destroy()
        self.parent.set_status("Calibration Canceled", "red")


class AutoZoomGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PABS Auto-Zoom Utility")
        self.root.geometry("450x380")
        self.root.resizable(False, False)
        
        # --- Variables ---
        self.x_var = tk.StringVar(value="0")
        self.y_var = tk.StringVar(value="0")
        self.w_var = tk.StringVar(value="0")
        self.h_var = tk.StringVar(value="0")
        
        # --- UI Layout ---
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        tk.Label(main_frame, text="PABS Auto-Zoom Module", font=("Helvetica", 16, "bold")).pack(pady=(0, 15))
        
        # Coordinates Frame
        coord_frame = tk.LabelFrame(main_frame, text="Target Display Area (Scan Region)", padx=10, pady=10)
        coord_frame.pack(fill=tk.X, pady=(0, 10))
        
        # X, Y row
        row1 = tk.Frame(coord_frame)
        row1.pack(fill=tk.X, pady=5)
        tk.Label(row1, text="X:", width=5).pack(side=tk.LEFT)
        tk.Entry(row1, textvariable=self.x_var, width=10).pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(row1, text="Y:", width=5).pack(side=tk.LEFT)
        tk.Entry(row1, textvariable=self.y_var, width=10).pack(side=tk.LEFT)
        
        # W, H row
        row2 = tk.Frame(coord_frame)
        row2.pack(fill=tk.X, pady=5)
        tk.Label(row2, text="Width:", width=5).pack(side=tk.LEFT)
        tk.Entry(row2, textvariable=self.w_var, width=10).pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(row2, text="Height:", width=5).pack(side=tk.LEFT)
        tk.Entry(row2, textvariable=self.h_var, width=10).pack(side=tk.LEFT)
        
        # Instructions
        tk.Label(main_frame, text="1. Click 'Visual Calibration' to draw a box over the map.\n2. Click Run and switch to PABS immediately.", justify=tk.LEFT, fg="gray").pack(pady=10)

        # Buttons
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.btn_calibrate = tk.Button(btn_frame, text="Visual Calibration", bg="#e0e0e0", font=("Helvetica", 10), height=2, command=self.start_calibration)
        self.btn_calibrate.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        
        self.btn_run = tk.Button(btn_frame, text="RUN AUTO-ZOOM", bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold"), height=2, command=self.start_auto_zoom)
        self.btn_run.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(5, 0))
        
        self.status_label = tk.Label(main_frame, text="Ready", fg="blue", font=("Helvetica", 11, "bold"))
        self.status_label.pack(side=tk.BOTTOM, pady=15)

    def set_status(self, text, color="blue"):
        self.status_label.config(text=text, fg=color)
        self.root.update()

    def start_calibration(self):
        messagebox.showinfo("Visual Calibration", "When you click OK, your screen will dim.\n\nClick and Drag your mouse to draw a box defining your target area (where the polygon should be contained)!")
        CalibrationOverlay(self)

    def start_auto_zoom(self):
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            region = (x, y, w, h)
            
            if w <= 0 or h <= 0:
                messagebox.showwarning("Warning", "Please Calibrate or enter valid Width and Height first.")
                return
                
        except ValueError:
            messagebox.showwarning("Warning", "Coordinates must be numeric.")
            return

        self.btn_calibrate.config(state=tk.DISABLED)
        self.btn_run.config(state=tk.DISABLED)
        threading.Thread(target=self._auto_zoom_thread, args=(region,), daemon=True).start()

    def _auto_zoom_thread(self, region):
        try:
            # 2 second countdown
            for i in range(2, 0, -1):
                self.set_status(f"Switch to PABS! Starting in {i}s...", "orange")
                time.sleep(1)
                
            self.set_status("Running Auto-Zoom algorithm...", "blue")
            
            # Execute core module logic
            success = auto_zoom.maximize_polygon(region)
            
            if success:
                self.set_status("Success! Polygon Maximized.", "green")
                messagebox.showinfo("Complete", "Auto-Zoom completed successfully!")
            else:
                self.set_status("Failed to maximize polygon.", "red")
                messagebox.showerror("Failed", "Auto-Zoom failed. Could not find polygon or reached max attempts.")
                
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.set_status("Error", "red")
        finally:
            self.btn_calibrate.config(state=tk.NORMAL)
            self.btn_run.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoZoomGUI(root)
    # Bring window to front
    root.lift()
    root.attributes('-topmost',True)
    root.after_idle(root.attributes,'-topmost',False)
    root.mainloop()
