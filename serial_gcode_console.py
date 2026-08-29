import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import serial
import serial.tools.list_ports
import time
import threading
import argparse
import queue

class GCodeSenderApp:
    def __init__(self, root, port, busy_delay_ms):
        self.root = root
        self.root.title("Partner di Programmazione - GCODE Controller V7")
        self.root.geometry("900x700")

        # Parametri e Stato
        self.port_name = port
        self.busy_delay = busy_delay_ms / 1000.0  # Converte ms in secondi
        self.baud_rate = 115200
        self.character_delay = 0.000250  # almeno 250 us tra i caratteri
        self.line_delay = 0.200          # almeno 200 ms tra le righe
        self.last_line_transmitted_at = None
        self.ser = None
        self.running = False
        self.paused = False
        self.connected = False
        self.start_line = 1
        self._step_mode = False
        # FIFO comune: console, pendant e campo comando manuale condividono
        # rigorosamente lo stesso ordine. I comandi di servizio usano invece
        # la corsia immediata, sempre gestita dallo stesso worker seriale.
        self.gcode_queue = queue.Queue()
        self.immediate_queue = queue.Queue()
        self.serial_abort_wait = threading.Event()
        self.serial_rx_buffer = bytearray()
        self.pendant_window = None
        self.pendant_queue_label = None
        self.pendant_queue_label_dirty = True
        self.log_queue = queue.Queue()
        self.log_window = None
        self.log_area = None
        self.full_log_enabled = False

        self.setup_ui()
        self.open_log_window()
        self.root.after(50, self.flush_log_queue)

        threading.Thread(target=self.serial_worker, daemon=True).start()

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

        tk.Button(btn_frame, text="STOP", command=self.stop_all_operations,
                  bg="#e74c3c", fg="white", width=8, **btn_opt).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame, text="PENDANT", command=self.open_pendant,
                  width=10, **btn_opt_bold).pack(side=tk.LEFT, padx=10)

        tk.Button(btn_frame, text="MODALITA' GCODE", command=self.enable_gcode_mode,
                  width=16, **btn_opt).pack(side=tk.LEFT, padx=2)

        tk.Button(btn_frame, text="LOG", command=self.open_log_window, width=8, **btn_opt).pack(side=tk.LEFT, padx=2)
        self.full_log_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            btn_frame, text="Full log", variable=self.full_log_var,
            command=self.set_full_log,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Pulisci Log", command=self.clear_log, width=10, **btn_opt).pack(side=tk.RIGHT, padx=2)

        # --- 3. Comando immediato ---
        immediate_frame = tk.Frame(self.root)
        immediate_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        tk.Label(immediate_frame, text="Comando immediato:").pack(side=tk.LEFT)
        self.immediate_command_entry = tk.Entry(immediate_frame)
        self.immediate_command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.immediate_command_entry.bind("<Return>", self.send_immediate_command)

        # --- 4. Barra di Stato ---
        self.status_bar = tk.Label(self.root, text="DISCONNESSO", bd=1, relief=tk.SUNKEN,
                                   anchor=tk.W, bg="red", fg="white", font=('Helvetica', 8))
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def open_pendant(self):
        """Apre (o porta in primo piano) il pannello di jog cartesiano."""
        if self.pendant_window is not None and self.pendant_window.winfo_exists():
            self.pendant_window.deiconify()
            self.pendant_window.lift()
            self.pendant_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.pendant_window = window
        window.title("Pendant CNC")
        window.resizable(False, False)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self.close_pendant)

        body = tk.Frame(window, padx=12, pady=12)
        body.grid(sticky="nsew")

        tk.Label(body, text="Movimento:").grid(row=0, column=0, sticky="w")
        self.pendant_mode = tk.StringVar(value="Traslazione")
        axes = ttk.Combobox(
            body, textvariable=self.pendant_mode, state="readonly", width=14,
            values=("Traslazione", "Rotazione"),
        )
        axes.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(6, 0))

        tk.Label(body, text="Profilo:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.pendant_profile = tk.StringVar(value="G14 - Normale")
        ttk.Combobox(
            body, textvariable=self.pendant_profile, state="readonly", width=14,
            values=("G13 - Rapido", "G14 - Normale", "G15 - Configurabile"),
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(8, 0))

        tk.Label(body, text="Incremento:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.pendant_step = tk.StringVar(value="1")
        for column, value in enumerate(("0.5", "1", "10", "20"), start=1):
            tk.Radiobutton(body, text=value, variable=self.pendant_step, value=value).grid(
                row=2, column=column, pady=(8, 0)
            )
        tk.Label(body, text="mm per traslazioni, gradi per rotazioni", font=("Helvetica", 8)).grid(
            row=3, column=0, columnspan=5, sticky="w"
        )

        movement = tk.LabelFrame(body, text=" Movimento relativo ", padx=8, pady=8)
        movement.grid(row=4, column=0, columnspan=5, pady=(10, 6))
        tk.Button(movement, text="↑", width=7, command=lambda: self.queue_pendant_move(0, 1)).grid(row=0, column=1, padx=2, pady=2)
        tk.Button(movement, text="←", width=7, command=lambda: self.queue_pendant_move(1, -1)).grid(row=1, column=0, padx=2, pady=2)
        tk.Button(movement, text="→", width=7, command=lambda: self.queue_pendant_move(1, 1)).grid(row=1, column=2, padx=2, pady=2)
        tk.Button(movement, text="↓", width=7, command=lambda: self.queue_pendant_move(0, -1)).grid(row=2, column=1, padx=2, pady=2)
        tk.Button(movement, text="Z+", width=7, command=lambda: self.queue_pendant_move(2, 1)).grid(row=0, column=3, padx=(12, 2), pady=2)
        tk.Button(movement, text="Z−", width=7, command=lambda: self.queue_pendant_move(2, -1)).grid(row=2, column=3, padx=(12, 2), pady=2)

        tk.Button(body, text="ARRESTA", command=self.pendant_stop, bg="#e67e22", fg="white", width=16).grid(
            row=5, column=0, columnspan=5, pady=(4, 0)
        )
        self.pendant_queue_label = tk.Label(body, text="Coda G-code: 0")
        self.pendant_queue_label.grid(row=6, column=0, columnspan=5, pady=(6, 0))

    def close_pendant(self):
        if self.pendant_window is not None:
            self.pendant_window.destroy()
        self.pendant_window = None
        self.pendant_queue_label = None

    def queue_pendant_move(self, axis_index, direction):
        if not self.connected:
            self.log("Pendant: comando non accodato, seriale disconnessa.")
            return

        # I cursori comandano sempre X (verticale) e Y (orizzontale);
        # i due pulsanti laterali comandano Z. In modalita' rotazione
        # vengono inviati i rispettivi assi rotazionali.
        axes = {
            "Traslazione": ("X", "Y", "Z"),
            "Rotazione": ("Rx", "Ry", "Rz"),
        }
        axis = axes[self.pendant_mode.get()][axis_index]
        step = float(self.pendant_step.get()) * direction
        profile = self.pendant_profile.get().split()[0]
        command = f"{profile} {axis}={step:g}"
        self.enqueue_gcode_command(command, source="pendant")
        self.log(f"Pendant accodato: {command}")

    def pendant_stop(self):
        """Arresto normale: M18, mai M112 (ESTOP)."""
        self.stop_all_operations()

    def send_immediate_command(self, _event=None):
        """Accoda il comando della finestra principale alla FIFO comune."""
        command = self.immediate_command_entry.get().strip()
        if not command:
            return "break"
        if not self.connected:
            self.log("Comando immediato non accodato: seriale disconnessa.")
            return "break"
        self.enqueue_gcode_command(command, source="manual")
        self.immediate_command_entry.delete(0, tk.END)
        self.log(f"Comando immediato accodato: {command}")
        return "break"

    def enable_gcode_mode(self):
        """Invia gcode nella corsia immediata, fuori dalla FIFO G-code."""
        self.enqueue_immediate_command("gcode", source="system")
        self.log("Comando gcode inviato in corsia immediata.")

    def update_pendant_queue_label(self):
        if self.pendant_queue_label is not None and self.pendant_queue_label.winfo_exists():
            self.pendant_queue_label.config(text=f"Coda G-code: {self.gcode_queue.qsize()}")

    def open_log_window(self):
        """Apre la finestra separata del log seriale."""
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.deiconify()
            self.log_window.lift()
            self.log_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.log_window = window
        window.title("Log seriale")
        window.geometry("900x260")
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

        frame = tk.Frame(window, padx=8, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(
            frame, state="disabled", wrap=tk.NONE, bg="#2c3e50",
            fg="#ecf0f1", font=("Monospace", 8),
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        self.log_queue.put(f"[{time.strftime('%H:%M:%S')}] {message}\n")

    def set_full_log(self):
        """Copia lo stato Tk in una variabile sicura per il worker seriale."""
        self.full_log_enabled = self.full_log_var.get()
        self.log(f"Full log {'attivato' if self.full_log_enabled else 'disattivato'}.")

    def flush_log_queue(self):
        """Aggiorna Tkinter solo dal thread grafico."""
        try:
            if self.log_area is None:
                return
            at_bottom = self.log_area.yview()[1] >= 0.999
            self.log_area.configure(state='normal')
            while True:
                self.log_area.insert(tk.END, self.log_queue.get_nowait())
        except queue.Empty:
            pass
        finally:
            if self.log_area is not None:
                if at_bottom:
                    self.log_area.see(tk.END)
                self.log_area.configure(state='disabled')
            if self.pendant_queue_label_dirty:
                self.update_pendant_queue_label()
                self.pendant_queue_label_dirty = False
            self.root.after(50, self.flush_log_queue)

    def clear_log(self):
        self.open_log_window()
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

    def stop_all_operations(self):
        """Arresta il file, svuota la FIFO e trasmette M18 immediatamente."""
        self.stop_sending()
        self.clear_gcode_queue()
        self.serial_abort_wait.set()
        self.enqueue_immediate_command("M18", source="stop")
        self.log("STOP: FIFO svuotata, M18 inviato in corsia immediata.")

    @staticmethod
    def is_immediate_command(command):
        command_name = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
        return command_name in {"m114", "m18", "gcode"}

    def enqueue_gcode_command(self, command, source="console"):
        """Accoda una riga nella FIFO condivisa da console e pendant."""
        if self.is_immediate_command(command):
            return self.enqueue_immediate_command(command, source=source)
        request = {"command": command, "source": source, "done": threading.Event(), "result": None}
        self.gcode_queue.put(request)
        self.pendant_queue_label_dirty = True
        return request

    def enqueue_immediate_command(self, command, source="system"):
        """Inserisce un comando di servizio fuori dalla FIFO G-code."""
        request = {"command": command, "source": source, "done": threading.Event(), "result": None}
        self.immediate_queue.put(request)
        return request

    def clear_gcode_queue(self):
        while True:
            try:
                request = self.gcode_queue.get_nowait()
            except queue.Empty:
                break
            request["result"] = "cancelled"
            request["done"].set()
            self.gcode_queue.task_done()
        self.pendant_queue_label_dirty = True

    def serial_worker(self):
        """Unico proprietario della seriale e del buffer RX persistente."""
        while True:
            try:
                request = self.immediate_queue.get_nowait()
                immediate = True
            except queue.Empty:
                try:
                    request = self.gcode_queue.get(timeout=0.05)
                    immediate = False
                except queue.Empty:
                    continue

            try:
                command = request["command"]
                if not self.connected or self.ser is None:
                    request["result"] = "error"
                    self.log(f"Comando scartato, seriale disconnessa: {command}")
                else:
                    if command.upper() == "M18":
                        self.discard_serial_input()
                        self.serial_abort_wait.clear()
                    while True:
                        request["result"] = self.exchange_serial_command(command)
                        if request["result"] != "busy":
                            break
                        self.log(f"RX busy: ritento tra {int(self.busy_delay * 1000)}ms: {command}")
                        time.sleep(self.busy_delay)
                    if request["source"] == "pendant":
                        self.log(f"Pendant {request['result']}: {command}")
            finally:
                request["done"].set()
                (self.immediate_queue if immediate else self.gcode_queue).task_done()
                self.pendant_queue_label_dirty = True

    def exchange_serial_command(self, command):
        serial_port = self.ser
        try:
            self.wait_between_serial_lines()
            self.write_serial_line(serial_port, command)
            self.log(f"TX: {command}")
            while self.connected and self.ser is serial_port:
                if self.serial_abort_wait.is_set():
                    return "cancelled"
                for response in self.read_complete_serial_lines(serial_port):
                    self.log(f"RX: {response}")
                    response_lower = response.lower().lstrip("@ \t")
                    if response_lower == "ok":
                        return "ok"
                    if "error:busy" in response_lower:
                        return "busy"
                    if "error" in response_lower:
                        return "error"
        except (serial.SerialException, OSError, AttributeError) as error:
            self.log(f"Errore seriale: {error}")
            return "error"
        return "cancelled"

    def read_complete_serial_lines(self, serial_port):
        waiting = serial_port.in_waiting
        data = serial_port.read(waiting if waiting else 1)
        if data:
            if self.full_log_enabled:
                for byte in data:
                    self.log(f"RX char: {chr(byte)!r} (0x{byte:02X})")
            self.serial_rx_buffer.extend(data)
        lines = []
        while b"\n" in self.serial_rx_buffer:
            raw_line, _, remaining = self.serial_rx_buffer.partition(b"\n")
            self.serial_rx_buffer = bytearray(remaining)
            response = raw_line.decode(errors="replace").strip()
            if response:
                lines.append(response)
        return lines

    def discard_serial_input(self):
        """Scarta le risposte del comando interrotto prima di M18."""
        try:
            self.ser.reset_input_buffer()
            self.serial_rx_buffer.clear()
        except (serial.SerialException, OSError, AttributeError) as error:
            self.log(f"Impossibile pulire RX: {error}")

    def wait_between_serial_lines(self):
        if self.last_line_transmitted_at is not None:
            remaining = self.line_delay - (time.monotonic() - self.last_line_transmitted_at)
            if remaining > 0:
                time.sleep(remaining)

    def write_serial_line(self, serial_port, command):
        data = (command + "\n").encode()
        for index, byte in enumerate(data):
            serial_port.write(bytes((byte,)))
            if index < len(data) - 1:
                time.sleep(self.character_delay)
        self.last_line_transmitted_at = time.monotonic()

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

                request = self.enqueue_gcode_command(clean_line, source="console")
                request["done"].wait()
                if request["result"] != "ok":
                    self.log(f"Riga {i} non completata: {request['result']}")
                    self.stop_sending()
                    return

                next_line = i + 1
                self.root.after(0, lambda nl=next_line: self.editor.mark_set(tk.INSERT, f"{nl}.0"))
                if self._step_mode:
                    self.paused = True
                    self._step_mode = False
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
