"""
Microphone capture and interruptible playback.

Two responsibilities, deliberately kept apart from every other module:
capturing fixed-size 16 kHz frames for the VAD, and playing synthesised audio
in a way that can be cut off mid-word when the user starts talking.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator

import numpy as np

try:
    import sounddevice as sd
except OSError as exc:  # PortAudio missing
    raise RuntimeError(
        "PortAudio could not be loaded. Install it with: pip install sounddevice"
    ) from exc

from voice.settings import SAMPLE_RATE, VAD_FRAME_SAMPLES


class MicStream:
    """
    Continuous microphone capture as an iterator of int16 numpy frames.

    Frames are exactly ``VAD_FRAME_SAMPLES`` long because Silero VAD rejects
    any other size at 16 kHz. Capture keeps running while Halcyon is speaking —
    that is what makes barge-in possible — so the consumer, not this class,
    decides which frames matter.
    """

    def __init__(self, device: int | str | None = None, max_queued_frames: int = 64) -> None:
        self.device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queued_frames)
        self._stream: sd.InputStream | None = None
        self.overflow_count = 0

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            # Input overflow means the consumer fell behind. Dropping the frame
            # is correct: stale audio is worse than missing audio for VAD.
            self.overflow_count += 1
        try:
            self._queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            self.overflow_count += 1

    def __enter__(self) -> MicStream:
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=VAD_FRAME_SAMPLES,
            device=self.device,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(self, stop: threading.Event | None = None) -> Iterator[np.ndarray]:
        """Yield captured frames until ``stop`` is set."""
        while stop is None or not stop.is_set():
            try:
                yield self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

    def drain(self) -> None:
        """
        Discard everything currently buffered.

        Called after Halcyon finishes speaking, so the echo of its own voice
        that the microphone picked up is not then transcribed as user input.
        """
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return


class Player:
    """
    Queued playback that can be interrupted at any point.

    Audio is pushed in as int16 numpy arrays. ``stop()`` abandons whatever is
    queued and cuts the current chunk off immediately — the alternative,
    letting the sentence finish, is what makes an assistant feel unresponsive
    when you try to interrupt it.
    """

    def __init__(self, sample_rate: int, device: int | str | None = None) -> None:
        self.sample_rate = sample_rate
        self.device = device
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._stream: sd.OutputStream | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._lock = threading.Lock()

    @property
    def is_playing(self) -> bool:
        return not self._idle.is_set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            device=self.device,
            channels=1,
            dtype="int16",
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._run, name="halcyon-player", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            if self._stop.is_set():
                continue
            self._idle.clear()
            # Write in small blocks so a stop() lands within ~20 ms rather than
            # after the whole sentence has been handed to the device.
            block = self.sample_rate // 50
            for start in range(0, len(chunk), block):
                if self._stop.is_set():
                    break
                assert self._stream is not None
                self._stream.write(chunk[start:start + block])
            if self._queue.empty():
                self._idle.set()

    def play(self, samples: np.ndarray) -> None:
        if self._stop.is_set():
            return
        self._idle.clear()
        self._queue.put(np.asarray(samples, dtype=np.int16))

    def stop(self) -> None:
        """Cut playback off now and discard anything pending."""
        with self._lock:
            self._stop.set()
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            if self._stream is not None:
                # abort() drops the device buffer; stop() would drain it first,
                # which is audible as a trailing fragment after an interruption.
                self._stream.abort()
                self._stream.start()
            self._idle.set()
            self._stop.clear()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def close(self) -> None:
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


def list_devices() -> str:
    return str(sd.query_devices())
