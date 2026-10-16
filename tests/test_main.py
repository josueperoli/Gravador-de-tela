import subprocess
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import imageio_ffmpeg
import numpy as np

from main import (
    RegionSelector,
    ScreenRecorderApp,
    VIDEO_SIZE,
    centered_region,
    fit_frame,
    validate_custom_video_size,
)


class RecordingSetupTests(unittest.TestCase):
    def test_confirming_position_closes_selector_and_saves_region(self):
        region = {"left": 30, "top": 40, "width": 450, "height": 800}
        selected = []
        selector = object.__new__(RegionSelector)
        selector.region = region
        selector.window = SimpleNamespace(destroy=lambda: selected.append("closed"))
        selector.on_select = lambda selected_region: selected.append(selected_region)

        selector._confirm()

        self.assertEqual(selected, ["closed", region])

    def test_recording_starts_with_positioned_fixed_aspect_region(self):
        app = ScreenRecorderApp.__new__(ScreenRecorderApp)
        app.output_path = Path("recording.mp4")
        app.region = {"left": 10, "top": 20, "width": 450, "height": 800}
        app.profile = SimpleNamespace(get=lambda: "Instagram Reels")
        app.start_button = SimpleNamespace(configure=lambda **_kwargs: None)
        app.stop_button = SimpleNamespace(configure=lambda **_kwargs: None)
        app.status_text = SimpleNamespace(set=lambda _value: None)
        app.timer_text = SimpleNamespace(set=lambda _value: None)
        app.root = SimpleNamespace(after=lambda *_args: None)

        with patch("main.threading.Thread") as thread:
            app.start_recording()

        thread.assert_called_once()
        self.assertEqual(thread.call_args.kwargs["args"][0], app.region)
        self.assertEqual(thread.call_args.kwargs["args"][1], app.output_path)
        thread.return_value.start.assert_called_once_with()

    def test_recording_passes_custom_dimensions_to_worker(self):
        app = ScreenRecorderApp.__new__(ScreenRecorderApp)
        app.output_path = Path("recording.mp4")
        app.region = {"left": 10, "top": 20, "width": 1280, "height": 720}
        app.profile = SimpleNamespace(get=lambda: "Personalizado")
        app.custom_width = SimpleNamespace(get=lambda: "1280")
        app.custom_height = SimpleNamespace(get=lambda: "720")
        app.start_button = SimpleNamespace(configure=lambda **_kwargs: None)
        app.stop_button = SimpleNamespace(configure=lambda **_kwargs: None)
        app.status_text = SimpleNamespace(set=lambda _value: None)
        app.timer_text = SimpleNamespace(set=lambda _value: None)
        app.root = SimpleNamespace(after=lambda *_args: None)

        with patch("main.threading.Thread") as thread:
            app.start_recording()

        self.assertEqual(thread.call_args.kwargs["args"][3], (1280, 720))
        thread.return_value.start.assert_called_once_with()

    def test_centered_region_preserves_vertical_format_and_fits_desktop(self):
        desktop = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        region = centered_region(desktop)

        self.assertAlmostEqual(region["width"] / region["height"], 9 / 16, places=2)
        self.assertEqual(region["height"], desktop["height"])
        self.assertEqual(region["width"], int(desktop["height"] * 9 / 16))
        self.assertLessEqual(region["left"] + region["width"], desktop["width"])
        self.assertLessEqual(region["top"] + region["height"], desktop["height"])

    def test_centered_region_uses_custom_aspect_ratio_and_fits_desktop(self):
        desktop = {"left": 100, "top": 50, "width": 1920, "height": 1080}
        region = centered_region(desktop, (1280, 720))

        self.assertAlmostEqual(region["width"] / region["height"], 16 / 9, places=2)
        self.assertLessEqual(region["left"] + region["width"], 2020)
        self.assertLessEqual(region["top"] + region["height"], 1130)

    def test_custom_video_size_requires_valid_even_dimensions(self):
        self.assertEqual(validate_custom_video_size("1280", "720"), (1280, 720))
        for dimensions in (
            ("0", "720"),
            ("1281", "720"),
            ("8192", "2160"),
            ("x", "720"),
        ):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                validate_custom_video_size(*dimensions)


class FitFrameTests(unittest.TestCase):
    def test_scheduled_frames_preserve_elapsed_time_when_capture_falls_behind(self):
        self.assertEqual(ScreenRecorderApp._scheduled_frame_count(0.5, 15), 16)
        self.assertEqual(ScreenRecorderApp._scheduled_frame_count(0.5, 1), 15)

    def test_wide_frame_is_center_cropped_to_vertical_output(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = fit_frame(frame, 1080, 1920)
        self.assertEqual(result.shape, (1920, 1080, 3))

    def test_vertical_frame_is_center_cropped_to_target_ratio(self):
        frame = np.zeros((2000, 1000, 3), dtype=np.uint8)
        result = fit_frame(frame, 1080, 1920)
        self.assertEqual(result.shape, (1920, 1080, 3))

    def test_small_frame_uses_high_quality_upscaling(self):
        frame = np.zeros((800, 450, 3), dtype=np.uint8)
        with patch("main.cv2.resize", wraps=cv2.resize) as resize:
            fit_frame(frame, 1080, 1920)

        self.assertEqual(resize.call_args.kwargs["interpolation"], cv2.INTER_CUBIC)

    def test_custom_frame_is_resized_to_selected_dimensions(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = fit_frame(frame, 640, 360)
        self.assertEqual(result.shape, (360, 640, 3))

    def test_recording_hotkey_toggles_recording(self):
        app = ScreenRecorderApp.__new__(ScreenRecorderApp)
        app.stop_event = None

        with (
            patch.object(app, "start_recording") as start_recording,
            patch.object(app, "stop_recording") as stop_recording,
        ):
            self.assertEqual(app.toggle_recording(), "break")
            start_recording.assert_called_once_with()
            stop_recording.assert_not_called()

            app.stop_event = threading.Event()
            self.assertEqual(app.toggle_recording(), "break")
            stop_recording.assert_called_once_with()

    def test_mp4_writer_can_save_and_read_a_vertical_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recording.mp4"
            writer = cv2.VideoWriter(
                str(path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                30,
                VIDEO_SIZE,
            )
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8))
            writer.release()

            reader = cv2.VideoCapture(str(path))
            self.assertTrue(reader.isOpened())
            success, frame = reader.read()
            reader.release()

            self.assertTrue(success)
            self.assertEqual(frame.shape, (VIDEO_SIZE[1], VIDEO_SIZE[0], 3))

    def test_high_quality_encoder_saves_a_vertical_h264_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recording.mp4"
            encoder = ScreenRecorderApp._start_video_encoder(str(path))
            try:
                encoder.stdin.write(
                    np.zeros(
                        (VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8
                    ).tobytes()
                )
                ScreenRecorderApp._finish_video_encoder(encoder)
            except Exception:
                encoder.kill()
                encoder.communicate()
                raise

            probe = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-hide_banner",
                    "-i",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertIn("Video: h264", probe.stderr)
            reader = cv2.VideoCapture(str(path))
            success, frame = reader.read()
            reader.release()

            self.assertTrue(success)
            self.assertEqual(frame.shape, (VIDEO_SIZE[1], VIDEO_SIZE[0], 3))

    def test_video_encoder_uses_high_quality_compression_settings(self):
        with patch("main.subprocess.Popen") as popen:
            ScreenRecorderApp._start_video_encoder("recording.mp4")

        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("-preset") + 1], "medium")
        self.assertEqual(command[command.index("-crf") + 1], "14")

    def test_video_encoder_uses_custom_dimensions(self):
        with patch("main.subprocess.Popen") as popen:
            ScreenRecorderApp._start_video_encoder("recording.mp4", (1280, 720))

        command = popen.call_args.args[0]
        self.assertIn("1280x720", command)

    def test_system_audio_is_written_as_stereo_pcm_wave(self):
        stop_event = threading.Event()

        class Recorder:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def record(self, numframes):
                stop_event.set()
                return np.full((numframes, 2), 0.5, dtype=np.float32)

        class Loopback:
            def recorder(self, **_kwargs):
                return Recorder()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio.wav"
            with (
                patch(
                    "main.soundcard.default_speaker",
                    return_value=SimpleNamespace(name="Speaker"),
                ),
                patch("main.soundcard.get_microphone", return_value=Loopback()),
            ):
                ScreenRecorderApp._record_system_audio(str(path), stop_event)

            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 2)
                self.assertEqual(audio.getframerate(), 48000)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getnframes(), 2048)
                samples = np.frombuffer(audio.readframes(1), dtype="<i2")
                self.assertTrue(np.all(samples == 16383))

    def test_muxed_mp4_contains_video_and_audio_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            video_path = Path(directory) / "video.mp4"
            audio_path = Path(directory) / "audio.wav"
            output_path = Path(directory) / "output.mp4"
            writer = cv2.VideoWriter(
                str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 30, VIDEO_SIZE
            )
            writer.write(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8))
            writer.release()
            with wave.open(str(audio_path), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(bytes(48000 * 2 * 2))

            ScreenRecorderApp._mux_audio_video(
                str(video_path), str(audio_path), str(output_path)
            )
            probe = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-hide_banner",
                    "-i",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertIn("Video:", probe.stderr)
            self.assertIn("Audio:", probe.stderr)


if __name__ == "__main__":
    unittest.main()
