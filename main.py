import ctypes
import math
import os
import queue
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import wave
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import imageio_ffmpeg
import mss
import numpy as np
import soundcard


VIDEO_SIZE = (1080, 1920)
CUSTOM_PROFILE = "Personalizado"
MAX_VIDEO_DIMENSION = 7680
FPS = 30
VIDEO_PRESET = "medium"
VIDEO_CRF = 14
AUDIO_SAMPLE_RATE = 48000
AUDIO_BLOCK_SIZE = 2048


def enable_dpi_awareness():
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def fit_frame(frame, width, height):
    """Crop a frame to the target aspect ratio, then resize it."""
    source_height, source_width = frame.shape[:2]
    target_ratio = width / height
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        crop_width = int(source_height * target_ratio)
        left = (source_width - crop_width) // 2
        frame = frame[:, left : left + crop_width]
    elif source_ratio < target_ratio:
        crop_height = int(source_width / target_ratio)
        top = (source_height - crop_height) // 2
        frame = frame[top : top + crop_height, :]

    interpolation = (
        cv2.INTER_CUBIC
        if width > frame.shape[1] or height > frame.shape[0]
        else cv2.INTER_AREA
    )
    return cv2.resize(frame, (width, height), interpolation=interpolation)


def validate_custom_video_size(width, height):
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError) as error:
        raise ValueError("Informe a largura e a altura em pixels.") from error

    if not (2 <= width <= MAX_VIDEO_DIMENSION and 2 <= height <= MAX_VIDEO_DIMENSION):
        raise ValueError(
            f"As dimensões devem estar entre 2 e {MAX_VIDEO_DIMENSION} pixels."
        )
    if width % 2 or height % 2:
        raise ValueError("A largura e a altura precisam ser números pares.")
    return width, height


def centered_region(desktop, video_size=VIDEO_SIZE):
    scale = min(
        desktop["width"] / video_size[0],
        desktop["height"] / video_size[1],
    )
    width = max(1, int(video_size[0] * scale))
    height = max(1, int(video_size[1] * scale))
    return {
        "left": desktop["left"] + (desktop["width"] - width) // 2,
        "top": desktop["top"] + (desktop["height"] - height) // 2,
        "width": width,
        "height": height,
    }


class RegionSelector:
    def __init__(self, parent, desktop, on_select, on_cancel, video_size=VIDEO_SIZE):
        self.desktop = desktop
        self.on_select = on_select
        self.on_cancel = on_cancel
        self.region = centered_region(desktop, video_size)
        self.drag_offset = None

        self.window = tk.Toplevel(parent)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.45)
        self.window.configure(background="black")
        self.window.geometry(
            f"{desktop['width']}x{desktop['height']}"
            f"{desktop['left']:+d}{desktop['top']:+d}"
        )
        self.canvas = tk.Canvas(
            self.window, background="black", highlightthickness=0, cursor="fleur"
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_text(
            16,
            14,
            anchor="nw",
            text="Arraste a moldura para posicionar o enquadramento",
            fill="white",
            font=("Segoe UI", 14, "bold"),
        )
        self.canvas.create_text(
            16,
            42,
            anchor="nw",
            text="Enter confirma  |  Esc cancela",
            fill="white",
            font=("Segoe UI", 11),
        )
        self.confirm_button = tk.Button(
            self.window,
            text="Finalizar posicionamento",
            command=self._confirm,
            font=("Segoe UI", 10, "bold"),
            background="#00e5ff",
            foreground="black",
            activebackground="#00b8cc",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        )
        self.canvas.create_window(
            desktop["width"] - 16,
            16,
            anchor="ne",
            window=self.confirm_button,
        )
        self.frame = self.canvas.create_rectangle(
            0, 0, 0, 0, outline="#00e5ff", width=3, fill="#00e5ff", stipple="gray50"
        )
        self.grid_lines = []
        self._draw_region()

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.window.bind("<Return>", self._confirm)
        self.window.bind("<Escape>", self._cancel)
        self.window.focus_force()

    def _draw_region(self):
        left = self.region["left"] - self.desktop["left"]
        top = self.region["top"] - self.desktop["top"]
        right = left + self.region["width"]
        bottom = top + self.region["height"]
        self.canvas.coords(self.frame, left, top, right, bottom)

        for line in self.grid_lines:
            self.canvas.delete(line)
        self.grid_lines = []
        for fraction in (1 / 3, 2 / 3):
            x = left + self.region["width"] * fraction
            y = top + self.region["height"] * fraction
            self.grid_lines.append(
                self.canvas.create_line(
                    x, top, x, bottom, fill="white", width=1, dash=(4, 4)
                )
            )
            self.grid_lines.append(
                self.canvas.create_line(
                    left, y, right, y, fill="white", width=1, dash=(4, 4)
                )
            )

    def _start_drag(self, event):
        left = self.region["left"] - self.desktop["left"]
        top = self.region["top"] - self.desktop["top"]
        inside_frame = (
            left <= event.x <= left + self.region["width"]
            and top <= event.y <= top + self.region["height"]
        )
        self.drag_offset = (
            (event.x - left, event.y - top)
            if inside_frame
            else (self.region["width"] // 2, self.region["height"] // 2)
        )
        self._drag(event)

    def _drag(self, event):
        if self.drag_offset is None:
            return
        left = min(
            max(0, event.x - self.drag_offset[0]),
            self.desktop["width"] - self.region["width"],
        )
        top = min(
            max(0, event.y - self.drag_offset[1]),
            self.desktop["height"] - self.region["height"],
        )
        self.region["left"] = self.desktop["left"] + left
        self.region["top"] = self.desktop["top"] + top
        self._draw_region()

    def _confirm(self, _event=None):
        self.window.destroy()
        self.on_select(self.region)

    def _cancel(self, _event=None):
        self.window.destroy()
        self.on_cancel()


class ScreenRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gravador de Tela")
        self.root.resizable(False, False)

        self.output_path = None
        self.region = None
        self.stop_event = None
        self.messages = queue.Queue()
        self.recording_started = None

        self.profile = tk.StringVar(value="")
        self.custom_width = tk.StringVar(value=str(VIDEO_SIZE[0]))
        self.custom_height = tk.StringVar(value=str(VIDEO_SIZE[1]))
        self.region_text = tk.StringVar(value="Escolha um formato para posicionar")
        self.file_text = tk.StringVar(value="Nenhum arquivo escolhido")
        self.status_text = tk.StringVar(value="Pronto para gravar")
        self.timer_text = tk.StringVar(value="00:00")
        self.custom_width.trace_add("write", self._on_custom_size_changed)
        self.custom_height.trace_add("write", self._on_custom_size_changed)

        self._build_ui()
        self.root.bind_all("<Control-Alt-r>", self.toggle_recording)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=20)
        frame.grid()

        ttk.Label(
            frame, text="Gravador de Tela", font=("Segoe UI", 18, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="Formato do vídeo").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.profile_selector = ttk.Combobox(
            frame,
            textvariable=self.profile,
            values=("Instagram Reels", "YouTube Shorts", CUSTOM_PROFILE),
            state="readonly",
            width=25,
        )
        self.profile_selector.grid(row=1, column=1, sticky="ew", pady=4)
        self.profile_selector.bind("<<ComboboxSelected>>", self._on_profile_selected)

        self.custom_size_frame = ttk.Frame(frame)
        self.custom_size_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(self.custom_size_frame, text="Largura:").pack(side="left")
        self.custom_width_input = ttk.Spinbox(
            self.custom_size_frame,
            from_=2,
            to=MAX_VIDEO_DIMENSION,
            increment=2,
            textvariable=self.custom_width,
            width=7,
        )
        self.custom_width_input.pack(side="left", padx=(6, 14))
        ttk.Label(self.custom_size_frame, text="Altura:").pack(side="left")
        self.custom_height_input = ttk.Spinbox(
            self.custom_size_frame,
            from_=2,
            to=MAX_VIDEO_DIMENSION,
            increment=2,
            textvariable=self.custom_height,
            width=7,
        )
        self.custom_height_input.pack(side="left", padx=(6, 0))
        ttk.Label(
            self.custom_size_frame,
            text=f"pixels pares (até {MAX_VIDEO_DIMENSION})",
            foreground="#555555",
        ).pack(side="left", padx=(8, 0))
        self.custom_size_frame.grid_remove()

        ttk.Button(
            frame, text="Posicionar enquadramento", command=self.position_region
        ).grid(row=3, column=0, sticky="ew", pady=(10, 4))
        ttk.Label(frame, textvariable=self.region_text, wraplength=260).grid(
            row=3, column=1, sticky="w", padx=(10, 0), pady=(10, 4)
        )

        ttk.Button(frame, text="Escolher arquivo de saída", command=self.choose_file).grid(
            row=4, column=0, sticky="ew", pady=4
        )
        ttk.Label(frame, textvariable=self.file_text, wraplength=260).grid(
            row=4, column=1, sticky="w", padx=(10, 0), pady=4
        )

        controls = ttk.Frame(frame)
        controls.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(16, 8))
        self.start_button = ttk.Button(
            controls, text="Iniciar gravação", command=self.start_recording
        )
        self.start_button.pack(side="left", fill="x", expand=True)
        self.stop_button = ttk.Button(
            controls, text="Parar", command=self.stop_recording, state="disabled"
        )
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(8, 0))

        ttk.Label(frame, textvariable=self.status_text).grid(
            row=6, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Label(frame, textvariable=self.timer_text, font=("Segoe UI", 12, "bold")).grid(
            row=6, column=1, sticky="e", pady=(6, 0)
        )
        ttk.Label(
            frame,
            text="Ctrl+Alt+R inicia/para · H.264 CRF 14 · 30 FPS",
            foreground="#555555",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _on_profile_selected(self, _event=None):
        if self.profile.get() == CUSTOM_PROFILE:
            self.custom_size_frame.grid()
        else:
            self.custom_size_frame.grid_remove()
        self.region = None
        self.region_text.set("Posicione o enquadramento")
        self.position_region()

    def _on_custom_size_changed(self, *_args):
        if self.profile.get() == CUSTOM_PROFILE:
            self.region = None
            self.region_text.set("Posicione o enquadramento")

    def _selected_video_size(self):
        if self.profile.get() == CUSTOM_PROFILE:
            return validate_custom_video_size(
                self.custom_width.get(), self.custom_height.get()
            )
        return VIDEO_SIZE

    def position_region(self):
        if not self.profile.get():
            messagebox.showwarning(
                "Formato não escolhido",
                "Escolha um formato de vídeo antes de posicionar o enquadramento.",
            )
            return
        try:
            video_size = self._selected_video_size()
        except ValueError as error:
            messagebox.showwarning("Dimensões inválidas", str(error))
            return
        with mss.MSS() as screen:
            desktop = screen.monitors[0]
        RegionSelector(
            self.root,
            desktop,
            self._set_region,
            self._cancel_region,
            video_size,
        )

    def _set_region(self, region):
        self.region = region
        self.region_text.set(
            f"Área da tela: {region['width']} × {region['height']} pixels"
        )

    def _cancel_region(self):
        if self.region is None:
            self.region_text.set("Enquadramento não posicionado")

    def choose_file(self):
        videos = Path.home() / "Videos"
        initial_dir = videos if videos.is_dir() else Path.home()
        path = filedialog.asksaveasfilename(
            title="Salvar gravação",
            initialdir=str(initial_dir),
            initialfile="gravacao.mp4",
            defaultextension=".mp4",
            filetypes=(("Vídeo MP4", "*.mp4"),),
        )
        if path:
            self.output_path = Path(path).with_suffix(".mp4")
            self.file_text.set(self.output_path.name)

    def start_recording(self):
        if not self.profile.get():
            messagebox.showwarning(
                "Formato não escolhido", "Escolha um formato de vídeo."
            )
            return
        try:
            video_size = self._selected_video_size()
        except ValueError as error:
            messagebox.showwarning("Dimensões inválidas", str(error))
            return
        if self.region is None:
            messagebox.showwarning(
                "Enquadramento não posicionado",
                "Posicione o enquadramento antes de iniciar a gravação.",
            )
            return
        if self.output_path is None:
            messagebox.showwarning("Arquivo não escolhido", "Escolha onde salvar o vídeo.")
            return

        self.stop_event = threading.Event()
        self.recording_started = time.monotonic()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_text.set(
            f"Gravando vídeo e áudio do computador para {self.profile.get()}..."
        )
        self.timer_text.set("00:00")

        worker = threading.Thread(
            target=self._record,
            args=(self.region.copy(), self.output_path, self.stop_event, video_size),
            daemon=True,
        )
        worker.start()
        self.root.after(100, self._poll_recorder)

    def stop_recording(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.stop_button.configure(state="disabled")
            self.status_text.set("Finalizando arquivo...")

    def toggle_recording(self, _event=None):
        if self.stop_event is None:
            self.start_recording()
        else:
            self.stop_recording()
        return "break"

    def _record(self, region, output_path, stop_event, video_size=VIDEO_SIZE):
        encoder = None
        audio_thread = None
        audio_start_event = threading.Event()
        audio_ready_event = threading.Event()
        temporary_paths = []
        succeeded = False
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            video_temp = tempfile.NamedTemporaryFile(
                suffix=".mp4", dir=output_path.parent, delete=False
            )
            video_temp.close()
            temporary_paths.append(Path(video_temp.name))
            audio_temp = tempfile.NamedTemporaryFile(
                suffix=".wav", dir=output_path.parent, delete=False
            )
            audio_temp.close()
            temporary_paths.append(Path(audio_temp.name))
            mux_temp = tempfile.NamedTemporaryFile(
                suffix=".mp4", dir=output_path.parent, delete=False
            )
            mux_temp.close()
            temporary_paths.append(Path(mux_temp.name))

            encoder = self._start_video_encoder(video_temp.name, video_size)

            audio_errors = queue.Queue()

            def record_audio():
                try:
                    self._record_system_audio(
                        audio_temp.name,
                        stop_event,
                        audio_start_event,
                        audio_ready_event,
                    )
                except Exception as error:
                    audio_errors.put(error)
                    stop_event.set()
                finally:
                    audio_ready_event.set()

            audio_thread = threading.Thread(target=record_audio, daemon=True)
            audio_thread.start()

            interval = 1 / FPS
            with mss.MSS() as screen:
                shot = np.asarray(screen.grab(region))
                frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
                frame = fit_frame(frame, *video_size)

                audio_ready_event.wait()
                try:
                    audio_error = audio_errors.get_nowait()
                except queue.Empty:
                    audio_error = None
                if audio_error is not None:
                    raise RuntimeError(
                        "Falha ao capturar o áudio do computador: "
                        f"{audio_error}"
                    )

                recording_started = time.perf_counter()
                audio_start_event.set()
                encoder.stdin.write(frame.tobytes())
                frames_written = 1
                previous_frame = frame

                while not stop_event.is_set():
                    try:
                        audio_error = audio_errors.get_nowait()
                    except queue.Empty:
                        audio_error = None
                    if audio_error is not None:
                        raise RuntimeError(
                            "Falha ao capturar o áudio do computador: "
                            f"{audio_error}"
                        )

                    next_frame = recording_started + frames_written * interval
                    delay = next_frame - time.perf_counter()
                    if delay > 0 and stop_event.wait(delay):
                        break
                    if stop_event.is_set():
                        break

                    shot = np.asarray(screen.grab(region))
                    frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
                    frame = fit_frame(frame, *video_size)

                    elapsed = time.perf_counter() - recording_started
                    due_frame_count = self._scheduled_frame_count(
                        elapsed, frames_written
                    )
                    for _ in range(frames_written, due_frame_count - 1):
                        encoder.stdin.write(previous_frame.tobytes())
                    encoder.stdin.write(frame.tobytes())
                    frames_written = due_frame_count
                    previous_frame = frame

            audio_thread.join()
            try:
                audio_error = audio_errors.get_nowait()
            except queue.Empty:
                audio_error = None
            if audio_error is not None:
                raise RuntimeError(
                    "Falha ao capturar o áudio do computador: "
                    f"{audio_error}"
                )

            completed_encoder = encoder
            encoder = None
            self._finish_video_encoder(completed_encoder)
            self._mux_audio_video(video_temp.name, audio_temp.name, mux_temp.name)
            os.replace(mux_temp.name, output_path)
            succeeded = True
        except Exception as error:
            self.messages.put(("error", str(error)))
        finally:
            stop_event.set()
            audio_start_event.set()
            if encoder is not None:
                encoder.kill()
                encoder.communicate()
            if audio_thread is not None:
                audio_thread.join()
            for temporary_path in temporary_paths:
                temporary_path.unlink(missing_ok=True)

        if succeeded:
            self.messages.put(("done", str(output_path)))

    @staticmethod
    def _scheduled_frame_count(elapsed, frames_written):
        return max(frames_written + 1, math.ceil(elapsed * FPS))

    @staticmethod
    def _start_video_encoder(output_path, video_size=VIDEO_SIZE):
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{video_size[0]}x{video_size[1]}",
            "-framerate",
            str(FPS),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            VIDEO_PRESET,
            "-crf",
            str(VIDEO_CRF),
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def _finish_video_encoder(encoder):
        try:
            encoder.stdin.close()
        except BrokenPipeError:
            pass
        error = encoder.stderr.read().decode(errors="replace").strip()
        encoder.stderr.close()
        return_code = encoder.wait()
        if return_code != 0:
            detail = error or "Erro desconhecido do FFmpeg."
            raise RuntimeError(f"Não foi possível codificar o vídeo: {detail}")

    @staticmethod
    def _record_system_audio(
        output_path, stop_event, start_event=None, ready_event=None
    ):
        speaker = soundcard.default_speaker()
        if speaker is None:
            raise RuntimeError("Nenhuma saída de áudio padrão foi encontrada.")
        loopback = soundcard.get_microphone(
            id=str(speaker.name), include_loopback=True
        )
        if loopback is None:
            raise RuntimeError(
                "Não foi possível acessar a captura do áudio da saída padrão."
            )

        audio_file = None
        try:
            with loopback.recorder(
                samplerate=AUDIO_SAMPLE_RATE, blocksize=AUDIO_BLOCK_SIZE
            ) as recorder:
                if ready_event is not None:
                    ready_event.set()
                if start_event is not None:
                    start_event.wait()
                while not stop_event.is_set():
                    samples = recorder.record(numframes=AUDIO_BLOCK_SIZE)
                    if samples.size == 0:
                        continue
                    if samples.ndim == 1:
                        samples = samples.reshape(-1, 1)
                    if audio_file is None:
                        audio_file = wave.open(output_path, "wb")
                        audio_file.setnchannels(samples.shape[1])
                        audio_file.setsampwidth(2)
                        audio_file.setframerate(AUDIO_SAMPLE_RATE)
                    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
                    audio_file.writeframesraw(pcm.tobytes())
        finally:
            if audio_file is not None:
                audio_file.close()

        if audio_file is None:
            raise RuntimeError("A gravação terminou antes de capturar áudio.")

    @staticmethod
    def _mux_audio_video(video_path, audio_path, output_path):
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_path,
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "Erro desconhecido do FFmpeg."
            raise RuntimeError(f"Não foi possível juntar áudio e vídeo: {detail}")

    def _poll_recorder(self):
        try:
            kind, detail = self.messages.get_nowait()
        except queue.Empty:
            if self.recording_started is not None:
                elapsed = int(time.monotonic() - self.recording_started)
                self.timer_text.set(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
            self.root.after(100, self._poll_recorder)
            return

        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.stop_event = None
        self.recording_started = None
        if kind == "done":
            self.status_text.set("Gravação salva com sucesso")
            messagebox.showinfo("Gravação concluída", f"Vídeo salvo em:\n{detail}")
        else:
            self.status_text.set("A gravação foi interrompida por um erro")
            messagebox.showerror("Erro na gravação", detail)


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    ScreenRecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
