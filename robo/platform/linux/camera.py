"""Taking a picture with your camera on Linux (GStreamer, video4linux).

A snapshot opens the camera for about a second (its light comes on), lets
the exposure settle for a few frames, keeps the last one as a PNG and closes
it again. Robo flashes while it does (Companion.camera_flash). Nothing is
recorded or kept: the picture goes to the plugin that asked.
"""
import logging
import threading

import gi
from gi.repository import GLib

from robo.platform.base import Camera

log = logging.getLogger(__name__)

WARMUP_FRAMES = 15               # the first frames are often dark
WIDTH = 960
TIMEOUT = 8.0


def _gst():
    try:
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        return Gst
    except (ValueError, ImportError):
        return None


class GstCamera(Camera):
    def __init__(self, source=None):
        self.source = source             # a gst-launch source; None = the first camera
        self._busy = False

    def _device(self, Gst):
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter('Video/Source', None)
        if not monitor.start():
            return None
        try:
            for dev in monitor.get_devices():
                props = dev.get_properties()
                path = props.get_string('device.path') if props else None
                if path or props is None:
                    return f'v4l2src device={path}' if path else None
        finally:
            monitor.stop()
        return None

    def problem(self):
        Gst = _gst()
        if Gst is None or not Gst.ElementFactory.find('v4l2src') and self.source is None:
            return 'GStreamer with video4linux is needed (gstreamer1.0-plugins-good)'
        if self.source is None and self._device(Gst) is None:
            import glob
            if not glob.glob('/dev/video*'):
                return 'no camera was found'
        return None

    def snapshot(self, on_done):
        if self._busy:
            on_done(None, 'the camera is busy')
            return
        self._busy = True

        def work():
            png, error = None, None
            try:
                png = self._take()
            except Exception as e:      # noqa: BLE001
                error = f'the camera failed: {e}'
            GLib.idle_add(finish, png, error)

        def finish(png, error):
            self._busy = False
            on_done(png, error if png is None else None)
            return False
        threading.Thread(target=work, daemon=True, name='camera').start()

    def _take(self):
        Gst = _gst()
        source = self.source or self._device(Gst) or 'v4l2src'
        pipeline = Gst.parse_launch(
            f'{source} num-buffers={WARMUP_FRAMES} ! videoconvert ! videoscale '
            f'! video/x-raw,width={WIDTH},pixel-aspect-ratio=1/1 ! pngenc '
            '! appsink name=sink sync=false max-buffers=2 drop=true')
        sink = pipeline.get_by_name('sink')
        pipeline.set_state(Gst.State.PLAYING)
        last = None
        try:
            while True:
                sample = sink.emit('try-pull-sample', int(TIMEOUT * Gst.SECOND))
                if sample is None:
                    break
                buf = sample.get_buffer()
                ok, info = buf.map(Gst.MapFlags.READ)
                if ok:
                    last = bytes(info.data)
                    buf.unmap(info)
            msg = pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
            if last is None and msg is not None:
                raise RuntimeError(msg.parse_error()[0].message)
        finally:
            pipeline.set_state(Gst.State.NULL)
        if last is None:
            raise RuntimeError('no picture came from the camera')
        log.info('took a camera picture (%d bytes)', len(last))
        return last
