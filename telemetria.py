import asyncio
import threading

try:
    from mavsdk import System
    MAVSDK_INSTALLED = True
except ImportError:
    System = None
    MAVSDK_INSTALLED = False


class DroneTelemetry:
    def __init__(self, connection_url: str):
        self.connection_url = connection_url
        self.available = MAVSDK_INSTALLED
        self.connected = False
        self.status = "SDK no instalado" if not self.available else "Inicializando"
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self._thread = None
        self._loop = None
        self._stop = False

    def start(self):
        if not self.available:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
        except Exception as exc:
            self.status = f"Error SDK: {exc}"

    async def _connect(self):
        self.status = f"Conectando a {self.connection_url}"
        drone = System()
        await drone.connect(system_address=self.connection_url)
        self.status = "Conectado"

        async for position in drone.telemetry.position():
            if self._stop:
                break
            self.latitude = position.latitude_deg
            self.longitude = position.longitude_deg
            self.altitude = position.relative_altitude_m
            self.connected = True
            self.status = "Conectado"

            if self._stop:
                break
            await asyncio.sleep(0.2)
