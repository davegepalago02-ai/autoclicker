import sys
import time
import json
import threading
import re
import os
import tkinter as tk
from tkinter import messagebox, filedialog

from pynput import mouse, keyboard
import pyautogui
import auto_zoom

# Helper functions for serialization
def key_to_str(key):
    if isinstance(key, keyboard.KeyCode):
        if hasattr(key, 'vk') and key.vk is not None:
            return f"vk.{key.vk}"
        return key.char
    return str(key)

def str_to_key(s):
    if s is None: return None
    if s.startswith('Key.'): return getattr(keyboard.Key, s.split('.')[1])
    if s.startswith('vk.'): return keyboard.KeyCode(vk=int(s.split('.')[1]))
    return keyboard.KeyCode.from_char(s)

def btn_to_str(btn): return str(btn)
def str_to_btn(s): return getattr(mouse.Button, s.split('.')[1])

class CalibrationOverlay:
    def __init__(self, parent_gui):
        self.parent = parent_gui
        self.root = tk.Toplevel(self.parent.root)
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.4)
        self.root.config(bg='black', cursor="cross")
        self.root.attributes('-topmost', True)
        self.root.deiconify()
        self.root.lift()

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.root.bind('<Escape>', lambda e: self.abort_calibration())

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=3, fill='green')

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        end_x, end_y = (event.x, event.y)
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        w = abs(end_x - self.start_x)
        h = abs(end_y - self.start_y)
        
        self.root.destroy()
        if w > 20 and h > 20:
            self.parent.scan_region = (x1, y1, w, h)
            self.parent.root.after(0, lambda: messagebox.showinfo("Success", f"Capture Region Saved:\n(x:{x1}, y:{y1}, w:{w}, h:{h})"))
            self.parent.root.deiconify()
        else:
            self.parent.root.deiconify()

    def abort_calibration(self):
        self.root.destroy()
        self.parent.root.deiconify()

class SettingsDialog:
    def __init__(self, parent):
        self.parent = parent
        self.top = tk.Toplevel(parent.root)
        self.top.title("Settings")
        self.top.geometry("260x320")
        self.top.attributes('-topmost', True)
        self.top.config(bg=parent.bg_color)
        
        tk.Label(self.top, text="Macros", bg=parent.bg_color, fg=parent.text_color, font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        f1 = tk.Frame(self.top, bg=parent.bg_color)
        f1.pack(fill=tk.X, padx=10)
        tk.Button(f1, text="💾 Save Macro", bg=parent.panel_bg, fg=parent.text_color, command=parent.save_macro).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        tk.Button(f1, text="📂 Load Macro", bg=parent.panel_bg, fg=parent.text_color, command=parent.load_macro).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        tk.Label(self.top, text="Delays (Seconds)", bg=parent.bg_color, fg=parent.text_color, font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        f2 = tk.Frame(self.top, bg=parent.bg_color)
        f2.pack(fill=tk.X, padx=10)
        tk.Label(f2, text="Record Delay:", bg=parent.bg_color, fg=parent.text_color).grid(row=0, column=0, sticky="w")
        self.rec_v = tk.IntVar(value=parent.rec_delay_val)
        tk.Entry(f2, textvariable=self.rec_v, width=5).grid(row=0, column=1)
        
        tk.Label(f2, text="Play Delay:", bg=parent.bg_color, fg=parent.text_color).grid(row=1, column=0, sticky="w")
        self.play_v = tk.IntVar(value=parent.play_delay_val)
        tk.Entry(f2, textvariable=self.play_v, width=5).grid(row=1, column=1)
        
        tk.Label(self.top, text="Playback", bg=parent.bg_color, fg=parent.text_color, font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        f3 = tk.Frame(self.top, bg=parent.bg_color)
        f3.pack(fill=tk.X, padx=10)
        tk.Label(f3, text="Speed Multiplier:", bg=parent.bg_color, fg=parent.text_color).grid(row=0, column=0, sticky="w")
        self.speed_v = tk.DoubleVar(value=parent.speed_val)
        tk.Scale(f3, variable=self.speed_v, from_=0.5, to=5.0, resolution=0.1, orient=tk.HORIZONTAL, bg=parent.bg_color, fg=parent.text_color, highlightthickness=0).grid(row=0, column=1)
        
        tk.Label(f3, text="Loop Count (0=Inf):", bg=parent.bg_color, fg=parent.text_color).grid(row=1, column=0, sticky="w")
        self.loop_c = tk.IntVar(value=parent.loop_count_val)
        tk.Entry(f3, textvariable=self.loop_c, width=5).grid(row=1, column=1)
        
        tk.Button(self.top, text="Close and Save", bg=parent.panel_bg, fg=parent.text_color, command=self.save_and_close).pack(pady=20)
        
    def save_and_close(self):
        self.parent.rec_delay_val = self.rec_v.get()
        self.parent.play_delay_val = self.play_v.get()
        self.parent.speed_val = self.speed_v.get()
        self.parent.loop_count_val = self.loop_c.get()
        self.top.destroy()

class AutoClickerWin7:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Diamante-Clicker")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        
        self.bg_color = "#1E1E1E"
        self.panel_bg = "#252526"
        self.text_color = "#E0E0E0"
        self.accent_color = "#007ACC"
        self.success_color = "#4CAF50"
        self.error_color = "#D32F2F"
        
        self.root.config(bg=self.bg_color)
        
        self.events = []
        self.recording = False
        self.playing = False
        self.paused = False
        self.date_pasting = False
        self.recording_starting = False
        self.start_time = 0.0
        self.current_filename = "No macro loaded"
        self.scan_region = None
        self.overlay = None
        
        self.rec_delay_val = 3
        self.play_delay_val = 3
        self.speed_val = 1.0
        self.loop_val = tk.BooleanVar(value=False)
        self.loop_count_val = 0

        self.mouse_ctrl = mouse.Controller()
        self.keyboard_ctrl = keyboard.Controller()

        self.is_linear_mode = False
        self._drag_data = {"x": 0, "y": 0}

        self.init_ui()
        self.start_global_listener()
        
    def init_ui(self):
        self.main_frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.main_frame.bind('<ButtonPress-1>', self.on_drag_start)
        self.main_frame.bind('<B1-Motion>', self.on_drag_motion)
        
        self.status_lbl = tk.Label(self.main_frame, text="Idle", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 14, "bold"))
        self.info_lbl = tk.Label(self.main_frame, text="0 events", bg=self.bg_color, fg="#858585", font=("Segoe UI", 9))
        
        self.rec_btn = tk.Button(self.main_frame, text="⏺ Rec (F3)", bg=self.error_color, fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.toggle_recording)
        self.play_btn = tk.Button(self.main_frame, text="▶ Play (F4)", bg=self.success_color, fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.toggle_playing)
        self.pause_btn = tk.Button(self.main_frame, text="⏸ Pause (F6)", bg="#FF9800", fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.toggle_pause)
        self.date_btn = tk.Button(self.main_frame, text="📅 Date (4s)", bg=self.panel_bg, fg=self.text_color, font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.trigger_date_paste)
        
        self.zoom_cal_btn = tk.Button(self.main_frame, text="📐 Calibration Area", bg=self.panel_bg, fg=self.text_color, font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.start_calibration)
        self.zoom_btn = tk.Button(self.main_frame, text="🔍 Auto-Zoom (F5)", bg=self.accent_color, fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, command=self.trigger_auto_zoom)
        
        self.loop_chk = tk.Checkbutton(self.main_frame, text="Loop Playlist", variable=self.loop_val, bg=self.bg_color, fg=self.text_color, selectcolor=self.panel_bg, font=("Segoe UI", 10))
        
        self.bottom_frame = tk.Frame(self.main_frame, bg=self.panel_bg)
        self.settings_btn = tk.Button(self.main_frame, text="⚙", bg=self.panel_bg, fg=self.text_color, relief=tk.FLAT, command=self.open_settings)
        self.toggle_mode_btn = tk.Button(self.main_frame, text="🔳", bg=self.panel_bg, fg=self.text_color, relief=tk.FLAT, command=self.toggle_ui_mode)
        self.close_btn = tk.Button(self.main_frame, text="✖", bg=self.error_color, fg="white", relief=tk.FLAT, command=self.root.destroy)
        
        self.file_lbl = tk.Label(self.main_frame, text=self.current_filename, bg=self.bg_color, fg="#858585", font=("Segoe UI", 8))
        
        self.apply_layout()
        
    def on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def on_drag_motion(self, event):
        deltax = event.x - self._drag_data["x"]
        deltay = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def toggle_ui_mode(self):
        self.is_linear_mode = not self.is_linear_mode
        self.apply_layout()

    def apply_layout(self):
        for widget in self.main_frame.winfo_children():
            widget.pack_forget()

        if self.is_linear_mode:
            self.root.geometry("860x70")
            h_layout = tk.Frame(self.main_frame, bg=self.bg_color)
            h_layout.pack(fill=tk.BOTH, expand=True)
            
            self.status_lbl.pack(in_=h_layout, side=tk.LEFT, padx=5)
            self.info_lbl.pack(in_=h_layout, side=tk.LEFT, padx=5)
            self.rec_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.play_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.pause_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.date_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.zoom_cal_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.zoom_btn.pack(in_=h_layout, side=tk.LEFT, padx=2, fill=tk.Y)
            self.loop_chk.pack(in_=h_layout, side=tk.LEFT, padx=2)
            
            self.settings_btn.pack(in_=h_layout, side=tk.LEFT, padx=2)
            self.toggle_mode_btn.pack(in_=h_layout, side=tk.LEFT, padx=2)
            self.close_btn.pack(in_=h_layout, side=tk.LEFT, padx=2)
            self.bottom_frame.pack(in_=h_layout, side=tk.RIGHT, padx=5)
            self.file_lbl.pack_forget()
            
            self.toggle_mode_btn.config(text="🔲")
        else:
            self.root.geometry("200x420")
            self.status_lbl.pack(pady=(0,5))
            self.info_lbl.pack()
            self.rec_btn.pack(fill=tk.X, pady=2)
            self.play_btn.pack(fill=tk.X, pady=2)
            self.pause_btn.pack(fill=tk.X, pady=2)
            self.date_btn.pack(fill=tk.X, pady=2)
            self.zoom_cal_btn.pack(fill=tk.X, pady=2)
            self.zoom_btn.pack(fill=tk.X, pady=2)
            self.loop_chk.pack(pady=5)
            
            self.bottom_frame.pack(fill=tk.X, pady=5)
            self.settings_btn.pack(in_=self.bottom_frame, side=tk.LEFT, expand=True, fill=tk.X)
            self.toggle_mode_btn.pack(in_=self.bottom_frame, side=tk.LEFT, expand=True, fill=tk.X)
            self.close_btn.pack(in_=self.bottom_frame, side=tk.LEFT, expand=True, fill=tk.X)
            
            self.file_lbl.pack()
            self.toggle_mode_btn.config(text="🔳")

    def open_settings(self):
        SettingsDialog(self)

    def start_global_listener(self):
        self.h_listener = keyboard.GlobalHotKeys({
            '<f3>': lambda: self.root.after(0, self.toggle_recording),
            '<f4>': lambda: self.root.after(0, self.toggle_playing),
            '<f5>': lambda: self.root.after(0, self.trigger_auto_zoom),
            '<f6>': lambda: self.root.after(0, self.toggle_pause)
        })
        self.h_listener.start()

    def record_event(self, event_type, *args):
        if self.recording:
            current_time = time.time() - self.start_time
            self.events.append((current_time, event_type, args))

    # Listeners
    def on_move(self, x, y): self.record_event('move', x, y)
    def on_click(self, x, y, button, pressed): self.record_event('click', x, y, btn_to_str(button), pressed)
    def on_scroll(self, x, y, dx, dy): self.record_event('scroll', x, y, dx, dy)
    def on_press(self, key):
        if key in (keyboard.Key.f3, keyboard.Key.f4, keyboard.Key.f5, keyboard.Key.f6): return
        self.record_event('press', key_to_str(key))
    def on_release(self, key):
        if key in (keyboard.Key.f3, keyboard.Key.f4, keyboard.Key.f5, keyboard.Key.f6): return
        self.record_event('release', key_to_str(key))

    def start_calibration(self):
        CalibrationOverlay(self)

    def trigger_auto_zoom(self):
        if self.scan_region is None:
            messagebox.showwarning("Warning", "Please Calibrate the Zoom Area first before running or recording Auto-Zoom!")
            return
            
        if self.recording:
            # 1. Record the event chronologically into the timeline
            self.record_event('autozoom', self.scan_region)
            
            # 2. Stop listeners so we don't 'record ourselves' scrolling during the bot's auto-zoom
            self.m_listener.stop()
            self.k_listener.stop()
            
            self.root.after(0, lambda: self.status_lbl.config(text="Live Zooming..."))
            threading.Thread(target=self._execute_zoom_during_record, daemon=True).start()
            
        elif not self.playing:
            self.root.after(0, lambda: self.status_lbl.config(text="Zooming pending..."))
            threading.Thread(target=self._execute_zoom, daemon=True).start()

    def _execute_zoom_during_record(self):
        try:
            # Give the user exactly 2 seconds to tab back into PABS!
            for i in range(2, 0, -1):
                self.root.after(0, lambda v=i: self.status_lbl.config(text=f"Switch instantly! {v}s..."))
                time.sleep(1)
                
            self.root.after(0, lambda: self.status_lbl.config(text="CV Zooming..."))
            
            # Execute the actual CV module
            cv_start = time.time()
            success = auto_zoom.maximize_polygon(self.scan_region)
            cv_duration = time.time() - cv_start
            
            # Crucial: Push internal recording start_time forward so the next physical click 
            # the user makes doesn't have a massive 10-second gap from when the zoom started!
            self.start_time += cv_duration
            
            if success:
                self.root.after(0, lambda: self.status_lbl.config(text="Zoom Success!"))
            else:
                self.root.after(0, lambda: self.status_lbl.config(text="Zoom Failed!"))
        finally:
            # Restart the listeners safely on the main thread so user can continue recording
            self.root.after(2000, self._resume_recording_listeners)
            
    def _resume_recording_listeners(self):
        if self.recording:
            self.m_listener = mouse.Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
            self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
            self.m_listener.start()
            self.k_listener.start()
            self.status_lbl.config(text="Rec...")

    def _execute_zoom(self):
        try:
            # 2 second countdown to allow the user to immediately tab into PABS
            for i in range(2, 0, -1):
                self.root.after(0, lambda v=i: self.status_lbl.config(text=f"Switch instantly! {v}s..."))
                time.sleep(1)
                
            self.root.after(0, lambda: self.status_lbl.config(text="CV Zooming..."))
            success = auto_zoom.maximize_polygon(self.scan_region)
            
            if success:
                self.root.after(0, lambda: self.status_lbl.config(text="Success!"))
                self.root.after(0, lambda: messagebox.showinfo("Complete", "Auto-Zoom completed successfully!", parent=self.root))
            else:
                self.root.after(0, lambda: self.status_lbl.config(text="Failed"))
                self.root.after(0, lambda: messagebox.showerror("Failed", "Auto-Zoom failed. Could not find polygon or reached max attempts.", parent=self.root))
        except Exception as e:
            self.root.after(0, lambda: self.status_lbl.config(text="Error"))
            self.root.after(0, lambda err=e: messagebox.showerror("Error", str(err), parent=self.root))
        finally:
            self.root.after(2000, self.reset_status)

    def trigger_date_paste(self):
        if self.date_pasting: return
        self.date_pasting = True
        self.date_btn.config(state=tk.DISABLED)
        threading.Thread(target=self.date_countdown, daemon=True).start()

    def date_countdown(self):
        for i in range(4, 0, -1):
            if not self.date_pasting: break
            self.root.after(0, lambda v=i: self.status_lbl.config(text=f"Date in {v}"))
            time.sleep(1)
        if self.date_pasting:
            self.root.after(0, self.execute_date_paste)

    def execute_date_paste(self):
        try:
            clipboard_text = self.root.clipboard_get().strip()
            if re.match(r'^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}$', clipboard_text):
                if self.recording: self.k_listener.stop()
                pyautogui.write(clipboard_text, interval=0.01)
                if self.recording:
                    for char in clipboard_text:
                        k = keyboard.KeyCode.from_char(char)
                        self.record_event('press', key_to_str(k))
                        time.sleep(0.005)
                        self.record_event('release', key_to_str(k))
                        time.sleep(0.005)
                    self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
                    self.k_listener.start()
                self.status_lbl.config(text="Typed Date")
            else:
                self.status_lbl.config(text="Invalid Date")
        except:
            self.status_lbl.config(text="Error")
        finally:
            self.date_pasting = False
            self.date_btn.config(state=tk.NORMAL)
            self.root.after(1000, self.reset_status)

    def reset_status(self):
        if self.recording: self.status_lbl.config(text="Rec...")
        elif self.playing:
            if self.paused: self.status_lbl.config(text="Paused")
            else: self.status_lbl.config(text="Play...")
        else: self.status_lbl.config(text="Idle")

    def toggle_pause(self):
        if not self.playing: return
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.config(text="▶ Resume (F6)", bg=self.success_color)
            self.status_lbl.config(text="Paused")
        else:
            self.pause_btn.config(text="⏸ Pause (F6)", bg="#FF9800")
            self.status_lbl.config(text="Play...")

    def toggle_recording(self):
        if self.recording: self.stop_recording()
        elif self.recording_starting:
            self.recording_starting = False
            self.status_lbl.config(text="Idle")
            self.rec_btn.config(text="⏺ Rec (F3)")
        else: self.start_recording_sequence()

    def start_recording_sequence(self):
        self.recording_starting = True
        self.rec_btn.config(text="⏹ Cxl (F3)")
        threading.Thread(target=self.recording_countdown, daemon=True).start()

    def recording_countdown(self):
        for i in range(self.rec_delay_val, 0, -1):
            if not self.recording_starting: return
            self.root.after(0, lambda v=i: self.status_lbl.config(text=f"Rec in {v}..."))
            time.sleep(1)
        if self.recording_starting:
            self.recording_starting = False
            self.root.after(0, self.actual_start_recording)

    def actual_start_recording(self):
        self.events = []
        self.recording = True
        self.start_time = time.time()
        self.status_lbl.config(text="Rec...")
        self.rec_btn.config(text="⏹ Stop (F3)")
        self.m_listener = mouse.Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
        self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.m_listener.start()
        self.k_listener.start()

    def stop_recording(self):
        self.recording = False
        self.m_listener.stop()
        self.k_listener.stop()
        self.status_lbl.config(text="Idle")
        self.rec_btn.config(text="⏺ Rec (F3)")
        self.info_lbl.config(text=f"{len(self.events)} events")

    def toggle_playing(self):
        if self.playing: self.playing = False
        else: self.start_playing()

    def start_playing(self):
        if not self.events:
            messagebox.showwarning("Warning", "No events recorded!")
            return
        self.playing = True
        self.play_btn.config(text="⏹ Stop (F4)")
        threading.Thread(target=self.play_events, daemon=True).start()

    def play_events(self):
        # Allow time to tab into PABS
        for i in range(self.play_delay_val, 0, -1):
            if not self.playing: break
            self.root.after(0, lambda v=i: self.status_lbl.config(text=f"Play in {v}..."))
            time.sleep(1)
        
        if not self.playing:
            self.root.after(0, self.reset_play_ui)
            return

        self.root.after(0, lambda: self.status_lbl.config(text="Play..."))
        speed = self.speed_val
        looping = self.loop_val.get()
        max_loops = self.loop_count_val
        current_loop = 0

        while self.playing:
            start_time = time.time()
            for event in self.events:
                if not self.playing: break
                target_time = event[0] / speed
                
                while True:
                    if not self.playing: break
                    if self.paused:
                        pause_start = time.time()
                        self.root.after(0, lambda: self.status_lbl.config(text="Paused"))
                        while self.paused and self.playing:
                            time.sleep(0.1)
                        if self.playing:
                            self.root.after(0, lambda: self.status_lbl.config(text="Play..."))
                        start_time += (time.time() - pause_start)
                        continue
                        
                    time_to_wait = target_time - (time.time() - start_time)
                    if time_to_wait > 0:
                        time.sleep(min(0.01, time_to_wait))
                    else:
                        break
                        
                if not self.playing: break
                
                type, args = event[1], event[2]
                try:
                    if type == 'move': self.mouse_ctrl.position = (args[0], args[1])
                    elif type == 'click':
                        btn = str_to_btn(args[2])
                        if args[3]: self.mouse_ctrl.press(btn)
                        else: self.mouse_ctrl.release(btn)
                    elif type == 'scroll': self.mouse_ctrl.scroll(args[2], args[3])
                    elif type == 'autozoom': 
                        self.root.after(0, lambda: self.status_lbl.config(text="CV Zooming..."))
                        
                        cv_start_time = time.time()
                        auto_zoom.maximize_polygon(args[0])
                        cv_duration = time.time() - cv_start_time
                        
                        # Crucial Sync Fix: Because the CV loop takes real-world seconds to wait for PABS map tile 
                        # rendering, we MUST freeze the macro timeline while it executes, or the subsequent clicks
                        # will instantly fire with massive negative wait-times to 'catch up' to the clock!
                        start_time += cv_duration
                        
                        self.root.after(0, lambda: self.status_lbl.config(text="Play..."))
                    elif type == 'press': self.keyboard_ctrl.press(str_to_key(args[0]))
                    elif type == 'release': self.keyboard_ctrl.release(str_to_key(args[0]))
                except: pass

            if not looping: break
            if max_loops > 0:
                current_loop += 1
                if current_loop >= max_loops: break
        
        self.root.after(0, self.reset_play_ui)

    def reset_play_ui(self):
        self.playing = False
        self.paused = False
        self.status_lbl.config(text="Idle")
        self.play_btn.config(text="▶ Play (F4)")
        self.pause_btn.config(text="⏸ Pause (F6)", bg="#FF9800")

    def save_macro(self):
        if not self.events:
            messagebox.showwarning("Warning", "No events to save!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if path:
            with open(path, 'w') as f: json.dump(self.events, f)
            self.current_filename = os.path.basename(path)
            self.file_lbl.config(text=f"📄 {self.current_filename}")

    def load_macro(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if path:
            with open(path, 'r') as f: self.events = json.load(f)
            self.current_filename = os.path.basename(path)
            self.file_lbl.config(text=f"📄 {self.current_filename}")
            self.info_lbl.config(text=f"Loaded {len(self.events)} events")

if __name__ == "__main__":
    app = AutoClickerWin7()
    app.root.mainloop()
