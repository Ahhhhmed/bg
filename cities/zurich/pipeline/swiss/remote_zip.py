"""
Read single members of a big remote ZIP over HTTP Range requests, without
downloading the whole archive (swissTLM3D's national shapefile ZIP is 3.6 GB;
the rail network inside it is ~10 MB). Handles ZIP64 and deflate / stored.

  from remote_zip import RemoteZip
  z = RemoteZip(url)
  z.names()                      # member names
  z.extract(name, dest_path)     # one member to a local file
"""
import struct
import urllib.request
import zlib


class RemoteZip:
    def __init__(self, url):
        self.url = url
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        self.size = int(head.headers["Content-Length"])
        tail = self._range(max(0, self.size - 65536), self.size - 1)
        i = tail.rfind(b"PK\x05\x06")
        cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
        j = tail.rfind(b"PK\x06\x06")                     # ZIP64 end of central directory
        if j >= 0:
            cd_size, cd_off = struct.unpack("<QQ", tail[j + 40:j + 56])
        self.members = self._parse_cd(self._range(cd_off, cd_off + cd_size - 1))

    def _range(self, a, b):
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    @staticmethod
    def _parse_cd(cd):
        out, p = {}, 0
        while cd[p:p + 4] == b"PK\x01\x02":
            method = struct.unpack("<H", cd[p + 10:p + 12])[0]
            csize, usize = struct.unpack("<II", cd[p + 20:p + 28])
            nlen, elen, clen = struct.unpack("<HHH", cd[p + 28:p + 34])
            off = struct.unpack("<I", cd[p + 42:p + 46])[0]
            name = cd[p + 46:p + 46 + nlen].decode("utf8", "replace")
            extra = cd[p + 46 + nlen:p + 46 + nlen + elen]
            q = 0
            while q + 4 <= len(extra):                     # ZIP64 extra field: 64-bit sizes / offset
                tag, ln = struct.unpack("<HH", extra[q:q + 4])
                if tag == 1:
                    vals, k = extra[q + 4:q + 4 + ln], 0
                    if usize == 0xFFFFFFFF:
                        usize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                    if csize == 0xFFFFFFFF:
                        csize = struct.unpack("<Q", vals[k:k + 8])[0]; k += 8
                    if off == 0xFFFFFFFF:
                        off = struct.unpack("<Q", vals[k:k + 8])[0]
                q += 4 + ln
            out[name] = (method, csize, usize, off)
            p += 46 + nlen + elen + clen
        return out

    def names(self):
        return list(self.members)

    def extract(self, name, dest, chunk=8 << 20):
        method, csize, usize, off = self.members[name]
        hdr = self._range(off, off + 29)
        nlen, elen = struct.unpack("<HH", hdr[26:30])
        start = off + 30 + nlen + elen
        dec = zlib.decompressobj(-15) if method == 8 else None
        with open(dest, "wb") as f:
            for a in range(start, start + csize, chunk):
                data = self._range(a, min(a + chunk, start + csize) - 1)
                f.write(dec.decompress(data) if dec else data)
            if dec:
                f.write(dec.flush())
        return dest
