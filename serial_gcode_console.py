import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import time
import threading
import argparse

class GCodeSenderApp:
    def __init__(self, root, port, busy_delay_ms):
        self.root = root
        self.root.title("Partner di Programmazione - GCODE Controller V7")
        self.root.geometry("900x700")

        # Parametri e Stato
        self.port_name = port
        self.busy_delay = busy_delay_ms / 1000.0  # Converte ms in secondi
        self.baud_rate = 115200
        self.ser = None
        self.running = False
        self.paused = False
        self.connected = False
        self.start_line = 1
        self._step_mode = False

        self.setup_ui()

        # Monitor della connessione
        threading.Thread(target=self.connection_monitor, daemon=True).start()
        self.log(f"Configurato delay busy a {busy_delay_ms}ms ({self.busy_delay}s)")

    def setup_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=0)

        # --- 1. Area Editor ---
        editor_frame = tk.LabelFrame(self.root, text=f" Editor GCODE - Avvio da cursore ")
        editor_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=2)
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self.editor = scrolledtext.ScrolledText(editor_frame, undo=True, wrap=tk.NONE, font=('Monospace', 10))
        self.editor.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.editor.tag_configure("current_line", background="#3498db", foreground="white")

        # --- 2. Pannello Pulsanti ---
        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=2)

        btn_opt = {'pady': 0, 'font': ('Helvetica', 8)}
        btn_opt_bold = {'pady': 0, 'font': ('Helvetica', 8, 'bold')}

        tk.Button(btn_frame, text="Carica", command=self.load_file, width=8, **btn_opt).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Salva", command=self.save_file, width=8, **btn_opt).pack(side=tk.LEFT, padx=2)

        self.btn_send = tk.Button(btn_frame, text="AVVIA", command=self.start_sending,
                                  bg="#2ecc71", fg="white", width=10, state="disabled", **btn_opt_bold)
        self.btn_send.pack(side=tk.LEFT, padx=10)

        self.btn_pause = tk.Button(btn_frame, text="PAUSA", command=self.toggle_pause,
                                   bg="#f1c40f", state="disabled", width=8, **btn_opt)
        self.btn_pause.pack(side=tk.LEFT, padx=2)

        self.btn_step = tk.Button(btn_frame, text="PASSO", command=self.step_execution,
                                  bg="#9b59b6", fg="white", state="disabled", width=8, **btn_opt)
        self.btn_step.pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame, text="STOP", command=self.stop_sending,
                  bg="#e74c3c", fg="white", width=8, **btn_opt).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame, text="Pulisci Log", command=self.clear_log, width=10, **btn_opt).pack(side=tk.RIGHT, padx=2)

        # --- 3. Area Log ---
        log_frame = tk.LabelFrame(self.root, text=" Log ")
        log_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        log_frame.columnconfigure(0, weight=1)

        self.log_area = scrolledtext.ScrolledText(log_frame, height=8, state='disabled',
                                                 bg="#2c3e50", fg="#ecf0f1", font=('Monospace', 8))
        self.log_area.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # --- 4. Barra di Stato ---
        self.status_bar = tk.Label(self.root, text="DISCONNESSO", bd=1, relief=tk.SUNKEN,
                                   anchor=tk.W, bg="red", fg="white", font=('Helvetica', 8))
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def clear_log(self):
        self.log_area.configure(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state='disabled')

    def highlight_line(self, line_number):
        self.editor.tag_remove("current_line", "1.0", tk.END)
        start = f"{line_number}.0"
        end = f"{line_number}.end"
        self.editor.tag_add("current_line", start, end)
        self.editor.see(start)

    def update_status(self, connected):
        self.connected = connected
        if connected:
            self.status_bar.config(text=f"ONLINE: {self.port_name}", bg="#27ae60")
            if not self.running:
                self.btn_send.config(state="normal")
                self.btn_step.config(state="normal")
        else:
            self.status_bar.config(text=f"OFFLINE: {self.port_name}", bg="#c0392b")
            self.btn_send.config(state="disabled")
            self.btn_pause.config(state="disabled")
            self.btn_step.config(state="disabled")
            self.running = False

    def connection_monitor(self):
        while True:
            # Caso 1: La seriale non è inizializzata o è stata chiusa
            if self.ser is None:
                try:
                    # Tentativo di apertura
                    self.ser = serial.Serial(self.port_name, self.baud_rate, timeout=0.1)
                    # Se arriva qui, l'apertura è riuscita
                    self.root.after(0, lambda: self.update_status(True))
                    self.log(f"Connessione stabilita su {self.port_name}")
                except (serial.SerialException, OSError):
                    # Ancora disconnesso
                    self.ser = None
                    self.root.after(0, lambda: self.update_status(False))

            # Caso 2: La seriale è aperta, ma dobbiamo verificare se il cavo è ancora lì
            else:
                try:
                    # Su Linux, controllare se il file esiste ancora nel filesystem
                    import os
                    if not os.path.exists(self.port_name):
                        raise serial.SerialException("Device physically removed")

                    # Test proattivo: controlla lo stato dei pin di controllo (non distruttivo)
                    self.ser.in_waiting

                except (serial.SerialException, OSError, AttributeError):
                    # Il cavo è stato staccato!
                    try:
                        self.ser.close()
                    except:
                        pass
                    self.ser = None
                    self.root.after(0, lambda: self.update_status(False))
                    self.log("ATTENZIONE: Dispositivo rimosso o non raggiungibile.")

            time.sleep(1) # Controllo ogni secondo

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("GCODE", "*.gcode"), ("Tutti", "*.*")])
        if path:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # 1. Carica il testo
                self.editor.delete(1.0, tk.END)
                self.editor.insert(tk.END, f.read())

                # 2. Ripristina lo stato di esecuzione
                self.start_line = 1

                # 3. Posiziona il cursore all'inizio (riga 1, colonna 0)
                self.editor.mark_set(tk.INSERT, "1.0")

                # 4. Evidenzia visivamente la prima riga come pronta
                self.highlight_line(1)

                # 5. Notifica nel log
                self.log(f"File caricato. Pronto a partire dalla riga 1.")

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".gcode")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.editor.get(1.0, tk.END))

    def toggle_pause(self):
        if self.running:
            self.paused = not self.paused
            self.btn_pause.config(text="RIPRENDI" if self.paused else "PAUSA",
                                  bg="#3498db" if self.paused else "#f1c40f",
                                  fg="white" if self.paused else "black")

    def step_execution(self):
        if not self.running and self.connected:
            cursor_pos = self.editor.index(tk.INSERT)
            self.start_line = int(cursor_pos.split('.')[0])
            self.running = True
            self.paused = False
            self._step_mode = True
            self.btn_send.config(state="disabled")
            self.btn_pause.config(state="normal")
            self.btn_step.config(state="normal")
            threading.Thread(target=self.send_process, daemon=True).start()
        elif self.running and self.paused:
            self._step_mode = True
            self.paused = False

    def start_sending(self):
        if not self.running and self.connected:
            cursor_pos = self.editor.index(tk.INSERT)
            self.start_line = int(cursor_pos.split('.')[0])
            self.running = True
            self.paused = False
            self._step_mode = False
            self.btn_send.config(state="disabled")
            self.btn_pause.config(state="normal")
            self.btn_step.config(state="normal")
            threading.Thread(target=self.send_process, daemon=True).start()

    def stop_sending(self):
        self.running = False
        self.paused = False
        self._step_mode = False
        self.editor.tag_remove("current_line", "1.0", tk.END)
        if self.connected:
            self.btn_send.config(state="normal")
            self.btn_step.config(state="normal")
        self.btn_pause.config(text="PAUSA", bg="#f1c40f", fg="black", state="disabled")

    def send_process(self):
        try:
            all_content = self.editor.get(1.0, tk.END).splitlines()
            for i, line in enumerate(all_content, start=1):
                if i < self.start_line: continue
                while self.paused and self.running: time.sleep(0.1)
                if not self.running or not self.connected: break

                clean_line = line.strip()
                if not clean_line or clean_line.startswith(";"): continue

                self.root.after(0, self.highlight_line, i)

                success = False
                while not success and self.running and self.connected:
                    while self.paused and self.running: time.sleep(0.1)
                    if not self.running: break

                    self.ser.write((clean_line + "\n").encode())
                    self.log(f"TX: {clean_line}")

                    command_done = False
                    while not command_done and self.running:
                        response = self.ser.readline().decode().strip()
                        if not response: continue
                        if response.startswith("@"): continue

                        self.log(f"RX: {response}")
                        resp_lower = response.lower()

                        if resp_lower == "ok":
                            success = True
                            command_done = True
                            next_line = i + 1
                            self.root.after(0, lambda nl=next_line: self.editor.mark_set(tk.INSERT, f"{nl}.0"))
                            if self._step_mode:
                                self.paused = True
                                self._step_mode = False
                        elif "error:busy" in resp_lower:
                            self.log(f"!! Occupato - Attendo {int(self.busy_delay*1000)}ms...")
                            time.sleep(self.busy_delay)
                            command_done = True
                        elif "error" in resp_lower:
                            self.log(f"!!! ERRORE: {response}")
                            self.stop_sending()
                            return
            self.log("--- Fine Sequenza ---")
        except Exception as e:
            self.log(f"Errore: {e}")
        finally:
            self.root.after(0, self.stop_sending)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCODE Sender ArmController-V7")
    parser.add_argument("port", nargs='?', default="/dev/ttyACM0", help="Porta seriale (default: /dev/ttyACM0)")
    parser.add_argument("-d", "--busy-delay", type=int, default=1000, help="Ritardo in ms in caso di error:busy (default: 1000)")
    args = parser.parse_args()

    root = tk.Tk()
    app = GCodeSenderApp(root, args.port, args.busy_delay)
    root.mainloop()
