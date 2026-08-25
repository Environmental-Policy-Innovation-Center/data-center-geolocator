#!/usr/bin/env python3
"""Download every DocuWare document exposed for one IEPA facility.

The script intentionally accepts exactly one agency ID per invocation. It uses
the public IEPA Document Explorer page to discover document categories, then a
temporary headless-Chrome profile to use each short-lived DocuWare integration
link. No DocuWare authorization token or browser profile is persisted.

Only Python's standard library and a local Google Chrome installation are
required.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import queue
import re
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


EXPLORER_BASE = "https://webapps.illinois.gov/EPA/DocumentExplorer/Documents/Index"
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_AGENT = "IEPA-one-facility-document-downloader/1.0"


@dataclass(frozen=True)
class Category:
    name: str
    document_count: int
    page_count: int | None
    bureau: str
    integration_url: str


@dataclass
class DownloadRecord:
    agency_id: str
    facility: str
    address: str
    category: str
    row_index: int
    row_text: list[str]
    expected_category_documents: int
    suggested_filename: str
    saved_path: str
    byte_count: int
    sha256: str


class ExplorerParser(HTMLParser):
    """Extract facility metadata and category rows from Document Explorer."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._in_blockquote = False
        self._blockquote_parts: list[str] = []
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []
        self._row_href: str | None = None
        self.facility_text = ""
        self.rows: list[tuple[list[str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "blockquote":
            self._in_blockquote = True
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
            self._row_href = None
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell_parts = []
        elif tag == "a" and self._in_row and self._in_cell and attrs_dict.get("href"):
            self._row_href = urllib.parse.urljoin(self.base_url, attrs_dict["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "blockquote":
            self._in_blockquote = False
            self.facility_text = " ".join(" ".join(self._blockquote_parts).split())
        elif tag in {"td", "th"} and self._in_cell:
            self._in_cell = False
            self._row_cells.append(" ".join(" ".join(self._cell_parts).split()))
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._row_href and self._row_cells:
                self.rows.append((self._row_cells, self._row_href))

    def handle_data(self, data: str) -> None:
        if self._in_blockquote and data.strip():
            self._blockquote_parts.append(data.strip())
        if self._in_cell and data.strip():
            self._cell_parts.append(data.strip())


def fetch_explorer(agency_id: str, timeout: float) -> tuple[str, str, list[Category], str]:
    url = f"{EXPLORER_BASE}/{agency_id}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")

    parser = ExplorerParser(url)
    parser.feed(html)
    facility_text = parser.facility_text
    facility = facility_text.split(" – ", 1)[0].strip() if facility_text else agency_id
    address = facility_text.split(agency_id, 1)[-1].strip(" -–") if agency_id in facility_text else ""

    categories: list[Category] = []
    for cells, href in parser.rows:
        if len(cells) < 3 or not cells[1].isdigit():
            continue
        categories.append(
            Category(
                name=cells[0],
                document_count=int(cells[1]),
                page_count=int(cells[2]) if cells[2].isdigit() else None,
                bureau=cells[3] if len(cells) > 3 else "",
                integration_url=href,
            )
        )

    if not categories:
        raise RuntimeError(f"No document categories found for IEPA agency ID {agency_id}")
    return facility, address, categories, url


def safe_name(value: str, fallback: str = "document") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or fallback


class WebSocket:
    """Small RFC 6455 client sufficient for the Chrome DevTools Protocol."""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise ValueError(f"Unsupported WebSocket URL: {url}")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
        self.socket = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname) if parsed.scheme == "wss" else raw
        self.socket.settimeout(timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.netloc}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = self._read_until(b"\r\n\r\n")
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(f"Chrome WebSocket handshake failed: {response[:200]!r}")
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        headers = {line.split(b":", 1)[0].lower(): line.split(b":", 1)[1].strip() for line in response.split(b"\r\n")[1:] if b":" in line}
        if headers.get(b"sec-websocket-accept") != expected:
            raise RuntimeError("Chrome WebSocket handshake returned an invalid accept key")
        self._send_lock = threading.Lock()

    def _read_until(self, marker: bytes) -> bytes:
        data = bytearray()
        while marker not in data:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise EOFError("WebSocket closed during handshake")
            data.extend(chunk)
        return bytes(data)

    def _read_exact(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = self.socket.recv(size - len(data))
            if not chunk:
                raise EOFError("WebSocket closed")
            data.extend(chunk)
        return bytes(data)

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        with self._send_lock:
            self.socket.sendall(bytes(header) + mask + masked)

    def receive_text(self) -> str | None:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_control(0xA, payload)
                continue
            if opcode == 0x1:
                return payload.decode("utf-8")

    def _send_control(self, opcode: int, payload: bytes) -> None:
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        with self._send_lock:
            self.socket.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked)

    def close(self) -> None:
        try:
            self._send_control(0x8, b"")
        except OSError:
            pass
        self.socket.close()


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.ws = WebSocket(websocket_url)
        self._next_id = 0
        self._condition = threading.Condition()
        self._responses: dict[int, dict[str, Any]] = {}
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._error: BaseException | None = None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while True:
                text = self.ws.receive_text()
                if text is None:
                    break
                message = json.loads(text)
                if "id" in message:
                    with self._condition:
                        self._responses[int(message["id"])] = message
                        self._condition.notify_all()
                else:
                    self.events.put(message)
        except BaseException as exc:
            with self._condition:
                self._error = exc
                self._condition.notify_all()

    def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
        with self._condition:
            self._next_id += 1
            message_id = self._next_id
        message: dict[str, Any] = {"id": message_id, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self.ws.send_text(json.dumps(message, separators=(",", ":")))
        deadline = time.monotonic() + timeout
        with self._condition:
            while message_id not in self._responses:
                if self._error:
                    raise RuntimeError("Chrome DevTools connection failed") from self._error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out waiting for Chrome command {method}")
                self._condition.wait(remaining)
            response = self._responses.pop(message_id)
        if "error" in response:
            raise RuntimeError(f"Chrome command {method} failed: {response['error']}")
        return response.get("result", {})

    def close(self) -> None:
        self.ws.close()


class ChromeSession:
    def __init__(self, chrome_path: str, download_dir: Path, timeout: float) -> None:
        self.chrome_path = chrome_path
        self.download_dir = download_dir
        self.timeout = timeout
        self.profile = tempfile.TemporaryDirectory(prefix="iepa-docuware-chrome-")
        self.process: subprocess.Popen[bytes] | None = None
        self.cdp: CDP | None = None
        self.session_id = ""

    def __enter__(self) -> "ChromeSession":
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [
                self.chrome_path,
                "--headless=new",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-port=0",
                f"--user-data-dir={self.profile.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        active_port = Path(self.profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + self.timeout
        while not active_port.exists():
            if self.process.poll() is not None:
                raise RuntimeError("Google Chrome exited before exposing DevTools")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out starting Google Chrome")
            time.sleep(0.1)
        port, websocket_path = active_port.read_text().splitlines()[:2]
        self.cdp = CDP(f"ws://127.0.0.1:{port}{websocket_path}")
        target_id = self.cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.session_id = self.cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
        self.cdp.send("Page.enable", session_id=self.session_id)
        self.cdp.send("Runtime.enable", session_id=self.session_id)
        self.cdp.send("Network.enable", session_id=self.session_id)
        self.cdp.send(
            "Browser.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(self.download_dir.resolve()), "eventsEnabled": True},
        )
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.cdp:
            try:
                self.cdp.send("Browser.close", timeout=5)
            except Exception:
                pass
            self.cdp.close()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.profile.cleanup()

    def navigate(self, url: str) -> None:
        assert self.cdp
        self.cdp.send("Page.navigate", {"url": url}, session_id=self.session_id, timeout=self.timeout)

    def evaluate(self, expression: str, timeout: float | None = None) -> Any:
        assert self.cdp
        result = self.cdp.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            session_id=self.session_id,
            timeout=timeout or self.timeout,
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "JavaScript evaluation failed"))
        return remote.get("value")

    def wait_for_rows(self, expected: int) -> list[list[str]]:
        deadline = time.monotonic() + self.timeout
        expression = """
(() => Array.from(document.querySelectorAll('.grid-canvas > .slick-row')).map(row =>
  Array.from(row.querySelectorAll('.slick-cell')).map(cell => cell.innerText.replace(/\u200b/g, '').trim())
))()
"""
        while time.monotonic() < deadline:
            rows = self.evaluate(expression) or []
            if len(rows) >= expected:
                return rows[:expected]
            time.sleep(0.5)
        title = self.evaluate("document.title")
        raise TimeoutError(f"DocuWare rendered {len(rows) if 'rows' in locals() else 0} of {expected} expected rows (page title: {title!r})")

    def select_row(self, index: int) -> None:
        assert self.cdp
        expression = f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('.grid-canvas > .slick-row'));
  const row = rows[{index}];
  if (!row) return null;
  row.scrollIntoView({{block: 'center'}});
  const target = row.querySelector('.slick-cell') || row;
  const rect = target.getBoundingClientRect();
  return {{x: rect.left + Math.min(rect.width / 2, 12), y: rect.top + rect.height / 2}};
}})()
"""
        point = self.evaluate(expression)
        if not point:
            raise RuntimeError(f"Could not select DocuWare result row {index}")
        params = {"x": point["x"], "y": point["y"], "button": "left", "clickCount": 1}
        self.cdp.send("Input.dispatchMouseEvent", {**params, "type": "mousePressed"}, session_id=self.session_id)
        self.cdp.send("Input.dispatchMouseEvent", {**params, "type": "mouseReleased"}, session_id=self.session_id)
        deadline = time.monotonic() + min(self.timeout, 10)
        while time.monotonic() < deadline:
            selected = self.evaluate("document.querySelectorAll('.grid-canvas > .slick-row .selected').length")
            if selected:
                return
            time.sleep(0.1)
        raise RuntimeError(f"DocuWare did not select result row {index}")

    def click_pdf_without_annotations(self) -> None:
        expression = """
(() => {
  const labels = Array.from(document.querySelectorAll('span')).filter(
    node => ['Download as PDF without annotations', 'as PDF without annotations'].includes(node.textContent.trim())
  );
  const candidate = labels.map(label => label.closest('li')).find(
    item => item && !item.classList.contains('ui-state-disabled') &&
      (item.getAttribute('data-bind') || '').includes('exportWithoutAnnotations')
  );
  if (!candidate) return false;
  const link = candidate.querySelector('a') || candidate;
  link.click();
  return true;
})()
"""
        deadline = time.monotonic() + min(self.timeout, 15)
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.25)
        diagnostic = self.evaluate("""
(() => ({
  selectedRows: document.querySelectorAll('.grid-canvas > .slick-row .selected').length,
  activeRows: document.querySelectorAll('.grid-canvas > .slick-row.active').length,
  commands: Array.from(document.querySelectorAll('span')).filter(
    node => /PDF without annotations/i.test(node.textContent)
  ).map(node => {
    const item = node.closest('li');
    return {
      text: node.textContent.trim(),
      className: item ? item.className : null,
      ariaDisabled: item ? item.getAttribute('aria-disabled') : null,
      display: item ? getComputedStyle(item).display : null,
      binding: item ? item.getAttribute('data-bind') : null
    };
  })
}))()
""")
        raise RuntimeError(
            "DocuWare did not enable its PDF-without-annotations download command; "
            f"diagnostic={json.dumps(diagnostic, separators=(',', ':'))}"
        )

    def wait_for_download(self) -> tuple[str, Path]:
        assert self.cdp
        deadline = time.monotonic() + self.timeout
        guid = ""
        suggested = ""
        while time.monotonic() < deadline:
            try:
                event = self.cdp.events.get(timeout=min(1.0, deadline - time.monotonic()))
            except queue.Empty:
                continue
            method = event.get("method")
            params = event.get("params", {})
            if method == "Browser.downloadWillBegin":
                guid = params["guid"]
                suggested = params.get("suggestedFilename") or f"{guid}.pdf"
            elif method == "Browser.downloadProgress" and guid and params.get("guid") == guid:
                if params.get("state") == "canceled":
                    raise RuntimeError("Chrome reported that the DocuWare download was canceled")
                if params.get("state") == "completed":
                    path = self.download_dir / suggested
                    settle_deadline = time.monotonic() + 5
                    while not path.exists() and time.monotonic() < settle_deadline:
                        time.sleep(0.1)
                    if not path.exists():
                        raise RuntimeError(f"Chrome completed a download but {path} was not created")
                    return suggested, path
        raise TimeoutError("Timed out waiting for DocuWare to download the selected document")


def unique_destination(directory: Path, filename: str, prefix: str) -> Path:
    candidate = directory / f"{prefix}_{safe_name(filename, 'document.pdf')}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{prefix}_{counter}_{safe_name(filename, 'document.pdf')}"
        counter += 1
    return candidate


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_download(path: Path) -> None:
    if path.stat().st_size == 0:
        raise RuntimeError(f"Downloaded file is empty: {path}")
    with path.open("rb") as stream:
        signature = stream.read(8)
    if not signature.startswith(b"%PDF-"):
        raise RuntimeError(f"DocuWare download is not a PDF: {path} (signature {signature!r})")


def download_facility(agency_id: str, output_root: Path, chrome_path: str, timeout: float, delay: float) -> Path:
    facility, address, categories, source_url = fetch_explorer(agency_id, timeout)
    facility_dir = output_root / agency_id
    staging_dir = facility_dir / ".downloads"
    facility_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    records: list[DownloadRecord] = []

    print(f"Facility: {facility}")
    print(f"Agency ID: {agency_id}")
    print(f"Categories: {', '.join(f'{item.name} ({item.document_count})' for item in categories)}")

    with ChromeSession(chrome_path, staging_dir, timeout) as chrome:
        for category in categories:
            category_dir = facility_dir / safe_name(category.name)
            category_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n{category.name}: expecting {category.document_count} document(s)")
            for row_index in range(category.document_count):
                chrome.navigate(category.integration_url)
                rows = chrome.wait_for_rows(category.document_count)
                chrome.select_row(row_index)
                chrome.click_pdf_without_annotations()
                suggested, staged_path = chrome.wait_for_download()
                destination = unique_destination(category_dir, suggested, f"{row_index + 1:03d}")
                shutil.move(staged_path, destination)
                validate_download(destination)
                record = DownloadRecord(
                    agency_id=agency_id,
                    facility=facility,
                    address=address,
                    category=category.name,
                    row_index=row_index,
                    row_text=rows[row_index],
                    expected_category_documents=category.document_count,
                    suggested_filename=suggested,
                    saved_path=str(destination.relative_to(facility_dir)),
                    byte_count=destination.stat().st_size,
                    sha256=file_digest(destination),
                )
                records.append(record)
                print(f"  [{row_index + 1}/{category.document_count}] {record.saved_path} ({record.byte_count:,} bytes)")
                time.sleep(delay)

    try:
        staging_dir.rmdir()
    except OSError:
        pass
    manifest = {
        "agency_id": agency_id,
        "facility": facility,
        "address": address,
        "source_url": source_url,
        "downloaded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "categories": [{key: value for key, value in asdict(item).items() if key != "integration_url"} for item in categories],
        "document_count": len(records),
        "documents": [asdict(record) for record in records],
    }
    manifest_path = facility_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved {len(records)} documents and manifest: {manifest_path}")
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agency_id", help="One numeric IEPA agency ID, for example 170000063561")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "iepa_pdfs")
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", DEFAULT_CHROME))
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds allowed for navigation, rendering, or one download")
    parser.add_argument("--delay", type=float, default=1.0, help="Polite delay in seconds after each completed download")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+", args.agency_id):
        parser.error("agency_id must contain digits only")
    if not Path(args.chrome).is_file():
        parser.error(f"Google Chrome was not found at {args.chrome!r}; use --chrome or CHROME_PATH")
    if args.timeout <= 0 or args.delay < 0:
        parser.error("--timeout must be positive and --delay cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    try:
        download_facility(args.agency_id, args.output_dir, args.chrome, args.timeout, args.delay)
    except (RuntimeError, TimeoutError, urllib.error.URLError, OSError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
