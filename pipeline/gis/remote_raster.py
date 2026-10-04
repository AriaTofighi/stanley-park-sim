"""Read public COG byte ranges with Python TLS and a persistent, hashed cache.

This avoids the Windows GDAL/Schannel credential failure without disabling TLS.
No authentication or private endpoint is used.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import requests


class RangeSource:
    def __init__(self, url: str, cache: Path, ceiling=1_500_000_000):
        self.url = url
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        response = self.session.head(url, timeout=45)
        response.raise_for_status()
        self.size = int(response.headers["Content-Length"])
        self.etag = response.headers.get("ETag")
        self.block_size = 1024 * 1024
        self.ceiling = ceiling
        self.fetched_bytes = 0
        self.metadata = {"url": url, "content_length": self.size, "etag": self.etag,
                         "last_modified": response.headers.get("Last-Modified"), "block_size": self.block_size,
                         "tls_verification": True, "ranges": {}}
        old = self.cache / "ranges.json"
        if old.exists():
            previous = json.loads(old.read_text())
            if previous.get("etag") != self.etag or previous.get("content_length") != self.size:
                raise RuntimeError("Remote object changed: use a new immutable source cache")
            self.metadata["ranges"] = previous.get("ranges", {})

    def block(self, index):
        start = index * self.block_size
        stop = min(self.size, start + self.block_size) - 1
        path = self.cache / f"{start:012d}-{stop:012d}.bin"
        if path.exists():
            payload = path.read_bytes()
            expected = self.metadata["ranges"].get(path.name, {}).get("sha256")
            if expected and hashlib.sha256(payload).hexdigest() != expected:
                raise RuntimeError(f"Immutable cached source range changed: {path}")
            return payload
        if self.fetched_bytes + stop-start+1 > self.ceiling:
            raise RuntimeError("Range download ceiling exceeded")
        response = self.session.get(self.url, headers={"Range": f"bytes={start}-{stop}", "If-Match": self.etag}, timeout=120)
        response.raise_for_status()
        if response.status_code != 206 or len(response.content) != stop-start+1:
            raise RuntimeError("Server did not honour the bounded Range request")
        payload = response.content
        path.write_bytes(payload)
        self.fetched_bytes += len(payload)
        self.metadata["ranges"][path.name] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        self.flush()
        return payload

    def flush(self):
        (self.cache / "ranges.json").write_text(json.dumps(self.metadata, indent=2) + "\n", encoding="utf-8")

    def opener(self, path, mode="rb"):
        if str(path) != self.url:
            raise FileNotFoundError(path)
        return RangeFile(self)


class RangeFile(io.RawIOBase):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.pos = 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        base = 0 if whence == 0 else self.pos if whence == 1 else self.source.size
        self.pos = base + offset
        if self.pos < 0:
            raise ValueError("Negative file position")
        return self.pos

    def read(self, size=-1):
        if size < 0:
            size = self.source.size - self.pos
        size = min(size, self.source.size - self.pos)
        if size > 64 * 1024 * 1024:
            raise RuntimeError("Unbounded raster read refused")
        if size <= 0:
            return b""
        chunks = []
        while size:
            idx, inner = divmod(self.pos, self.source.block_size)
            chunk = self.source.block(idx)
            take = min(size, len(chunk)-inner)
            if take <= 0:
                break
            chunks.append(chunk[inner:inner+take])
            self.pos += take
            size -= take
        return b"".join(chunks)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)
