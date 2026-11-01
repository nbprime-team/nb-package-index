"""main.py -- nbCode's launcher: the Python half of a C code editor on the HP Prime."""
import sys


try:
    import ustruct as struct                       
except ImportError:                                
    import struct


try:
    import uio as _uio
except ImportError:
    _uio = None

try:
    import ujson as json
except ImportError:                                
    try:
        import json
    except ImportError:
        json = None

try:
    import hpprime
except ImportError:                                
    hpprime = None


try:
    from moreprint import p_log, p_warning, p_error, p_pass
except Exception:
    def p_log(text):
        print(text)

    def p_warning(text):
        print(text)

    def p_error(text):
        print(text)

    def p_pass(text):
        print(text)


def open_file(name, mode='rb'):

    if _uio is not None:
        try:
            return _uio.FileIO(name, mode)
        except Exception:
            pass
    return open(name, mode)


class _IOModule:


    FileIO = staticmethod(open_file)


io = _IOModule


HOOK_BUSY_OFF = 36


_held = []


BASE = 0x307FBCAC


def get_addr(svc):
    return BASE + 0xC * (svc - 0x10000)


ADDR_MALLOC = get_addr(0x10037)
ADDR_CALLOC = get_addr(0x10038)
ADDR_FREE = get_addr(0x1003A)


FW_FIND_FIRST = get_addr(0x10270)
FW_FIND_NEXT = get_addr(0x10271)
FW_FIND_CLOSE = get_addr(0x10273)
FW_GET_ATTR = get_addr(0x10272)
FW_GET_DISK_ID = get_addr(0x100E7)
FW_GETCWD = get_addr(0x1027A)
FW_FOPEN = get_addr(0x1026F)
FW_FCLOSE = get_addr(0x100CA)
FW_FSEEK = get_addr(0x100CF)
FW_FREAD = get_addr(0x100D4)


FW_EVENT_SLOT = 0x307FBFA0
SLOT_TRAP = 0xE51FF004


def is_device():

    try:
        impl = getattr(sys, 'implementation', None)
        name = getattr(impl, 'name', '') if impl is not None else ''
        if name:
            return name == 'micropython'
    except Exception:
        pass


    return hpprime is not None


def str_to_utf16le_bytes(s):

    out = bytearray()
    for ch in s:
        v = ord(ch)
        out.append(v & 0xFF)
        out.append((v >> 8) & 0xFF)
    out.append(0)
    out.append(0)
    return bytes(out)


def decode_bytes(raw):

    try:
        return raw.decode('utf-8')
    except Exception:
        pass
    try:
        return raw.decode('latin-1')
    except Exception:
        pass
    return ''.join(chr(b) for b in raw)


def utf8_bytes(s):

    out = bytearray()
    for ch in s:
        v = ord(ch)
        if v < 0x80:
            out.append(v)
        elif v < 0x800:
            out.append(0xC0 | (v >> 6))
            out.append(0x80 | (v & 0x3F))
        elif 0xD800 <= v < 0xE000:
            out.append(0x3F)
        elif v < 0x10000:
            out.append(0xE0 | (v >> 12))
            out.append(0x80 | ((v >> 6) & 0x3F))
            out.append(0x80 | (v & 0x3F))
        elif v < 0x110000:
            out.append(0xF0 | (v >> 18))
            out.append(0x80 | ((v >> 12) & 0x3F))
            out.append(0x80 | ((v >> 6) & 0x3F))
            out.append(0x80 | (v & 0x3F))
        else:
            out.append(0x3F)		
    return bytes(out)


class MemUtils:


    def __init__(self, dbg):
        self.dbg = dbg

    def malloc(self, size):
        return self.dbg.call(ADDR_MALLOC, (size + 3) & ~3)

    def free(self, addr):
        if addr:
            self.dbg.call(ADDR_FREE, addr)

    def alloc_wstr(self, s):
        b = str_to_utf16le_bytes(s)
        addr = self.malloc(len(b))
        if addr:
            self.dbg.write_mem_bytes(addr, b)
        return addr

    def read_wstr(self, addr, max_chars=260):
        if not addr:
            return ''
        raw = self.dbg.read_mem(addr, max_chars * 2)
        out = []
        for i in range(0, len(raw) - 1, 2):
            c = raw[i] | (raw[i + 1] << 8)
            if c == 0:
                break
            out.append(chr(c) if 32 <= c < 0xFFFD else '?')
        return ''.join(out)

    def read_utf8(self, addr, max_len=260):
        if not addr:
            return ''
        raw = self.dbg.read_mem(addr, max_len)
        end = raw.find(b'\x00')
        if end >= 0:
            raw = raw[:end]
        return decode_bytes(bytes(raw))


def open_debug():

    if _uio is not None:
        try:
            return _uio.FileIO('debug')
        except Exception:
            pass
    return open('debug', 'rb')


class PrimeDebug:


    def __init__(self):
        self.f = None


        self.round_trips = 0

    def open(self):
        if self.f is None:
            self.f = open_debug()
        return self.f


    def read_mem(self, addr, n):
        f = self.open()
        self.round_trips += 1
        f.write(struct.pack('<III', 0, addr, 0))
        return f.read(n)

    def write_mem(self, addr, value):
        f = self.open()
        self.round_trips += 1
        f.write(struct.pack('<III', 1, addr, value & 0xFFFFFFFF))

    def write_mem_bytes(self, addr, data):
        data = bytes(data)
        pad = (4 - (len(data) % 4)) % 4
        data += b'\x00' * pad
        for i in range(0, len(data), 4):
            self.write_mem(addr + i, struct.unpack('<I', data[i:i + 4])[0])

    def call(self, addr, r0=0, r1=0, r2=0, r3=0):

        f = self.open()
        self.round_trips += 1
        args = [r0, r1, r2, r3]
        buf = bytearray(struct.pack('<IIIIII', 2, addr, len(args), *args))
        f.write(buf)
        return struct.unpack_from('<I', buf, 0)[0]

    def close(self):
        if self.f is not None:
            self.f.close()
            self.f = None


class ElfTools:
    @staticmethod
    def seg_end(data):

        if len(data) < 52 or data[0:4] != b'\x7fELF':
            return 0
        phoff = struct.unpack_from('<I', data, 28)[0]
        phent = struct.unpack_from('<H', data, 42)[0]
        phnum = struct.unpack_from('<H', data, 44)[0]
        need = 0
        for i in range(phnum):
            off = phoff + i * phent
            if off + 32 > len(data):
                break
            if struct.unpack_from('<I', data, off)[0] != 1:
                continue
            vaddr = struct.unpack_from('<I', data, off + 8)[0]
            memsz = struct.unpack_from('<I', data, off + 20)[0]
            if vaddr + memsz > need:
                need = vaddr + memsz
        return need

    @staticmethod
    def memory_size(data):
        
        return (ElfTools.seg_end(data) + 3) & ~3

    @staticmethod
    def entry_point(data):
        if len(data) < 52 or data[0:4] != b'\x7fELF':
            return 0
        return struct.unpack_from('<I', data, 24)[0]

    @staticmethod
    def find_magic(data, magic, base):

        if len(data) < 52 or data[0:4] != b'\x7fELF':
            return 0
        phoff = struct.unpack_from('<I', data, 28)[0]
        phent = struct.unpack_from('<H', data, 42)[0]
        phnum = struct.unpack_from('<H', data, 44)[0]
        segs = []
        for i in range(phnum):
            off = phoff + i * phent
            if off + 32 > len(data):
                break
            if struct.unpack_from('<I', data, off)[0] == 1:
                segs.append((struct.unpack_from('<I', data, off + 4)[0],
                             struct.unpack_from('<I', data, off + 8)[0],
                             struct.unpack_from('<I', data, off + 16)[0]))
        idx = data.find(magic)
        if idx < 0:
            return 0
        for (p_off, p_vaddr, p_filesz) in segs:
            if p_off <= idx < p_off + p_filesz:
                return base + p_vaddr + (idx - p_off)
        return 0

    @staticmethod
    def segments(data):

        out = []
        phoff = struct.unpack_from('<I', data, 28)[0]
        phent = struct.unpack_from('<H', data, 42)[0]
        phnum = struct.unpack_from('<H', data, 44)[0]
        for i in range(phnum):
            off = phoff + i * phent
            if off + 32 > len(data):
                break
            fields = struct.unpack_from('<IIIIIIII', data, off)
            if fields[0] != 1:
                continue
            out.append((fields[1], fields[2], fields[4], fields[5]))
        return out

    @staticmethod
    def relocations(data):

        if len(data) < 52:
            return [], 0
        phoff = struct.unpack_from('<I', data, 28)[0]
        phent = struct.unpack_from('<H', data, 42)[0]
        phnum = struct.unpack_from('<H', data, 44)[0]
        dyn = None
        for i in range(phnum):
            off = phoff + i * phent
            if off + 32 > len(data):
                break
            if struct.unpack_from('<I', data, off)[0] == 2:      
                dyn = struct.unpack_from('<I', data, off + 4)[0]
        if dyn is None:
            return [], 0
        tags = {}
        off = dyn
        while off + 8 <= len(data):
            tag, val = struct.unpack_from('<II', data, off)
            if tag == 0:
                break
            tags[tag] = val
            off += 8
        rel, relsz = tags.get(17), tags.get(18)
        if not rel or not relsz:
            return [], 0
        out, unknown = [], 0
        for i in range(relsz // 8):
            off = rel + i * 8
            r_off, r_info = struct.unpack_from('<II', data, off)
            rtype = r_info & 0xFF
            if rtype == 23 or (r_info >> 8) == 0:
                out.append((r_off, 23, 0))
            else:
                unknown += 1
        return out, unknown


LOADER_CODE = (
    b'\x0b\x00\x00\xea\x04\x00\x2d\xe5\x04\xe0\x2d\xe5\x6f\x02\x01\xef'
    b'\x04\x00\x2d\xe5\x04\xe0\x2d\xe5\xca\x00\x01\xef\x04\x00\x2d\xe5'
    b'\x04\xe0\x2d\xe5\xd4\x00\x01\xef\x04\x00\x2d\xe5\x04\xe0\x2d\xe5'
    b'\xcf\x00\x01\xef\x68\x32\x9f\xe5\xf0\x4f\x2d\xe9\x03\x30\x8f\xe0'
    b'\x00\x20\xa0\xe1\x01\x60\xa0\xe1\x03\x00\x93\xe8\x64\xd0\x4d\xe2'
    b'\x04\x00\x8d\xe5\xb8\x10\xcd\xe1\x02\x00\xa0\xe1\x04\x10\x8d\xe2'
    b'\xe7\xff\xff\xeb\x00\x40\x50\xe2\x73\x00\x00\x0a\x04\x30\xa0\xe1'
    b'\x01\x20\xa0\xe3\x34\x10\xa0\xe3\x2c\x00\x8d\xe2\xe6\xff\xff\xeb'
    b'\x01\x00\x50\xe3\x6a\x00\x00\x1a\xbc\x22\xdd\xe1\x14\x32\x9f\xe5'
    b'\x03\x00\x52\xe1\x66\x00\x00\x1a\x48\x10\x9d\xe5\x00\x20\xa0\xe3'
    b'\x04\x00\xa0\xe1\xdf\xff\xff\xeb\xb8\x35\xdd\xe1\x00\x00\x53\xe3'
    b'\x78\x00\x00\x0a\x00\x50\xa0\xe3\x05\x70\xa0\xe1\x0c\xa0\x8d\xe2'
    b'\x04\x00\x00\xea\xb8\x35\xdd\xe1\x02\x00\x5b\xe3\x14\x70\x9d\x05'
    b'\x05\x00\x53\xe1\x19\x00\x00\xda\x04\x30\xa0\xe1\x01\x20\xa0\xe3'
    b'\x20\x10\xa0\xe3\x0a\x00\xa0\xe1\xcb\xff\xff\xeb\x0c\xb0\x9d\xe5'
    b'\x01\x50\x85\xe2\x01\x00\x5b\xe3\xf1\xff\xff\x1a\x1c\x30\x9d\xe5'
    b'\x14\x80\x9d\xe5\x48\x90\x9d\xe5\x00\x00\x53\xe3\x08\x80\x86\xe0'
    b'\x85\x92\x89\xe0\x4b\x00\x00\x1a\x20\x20\x9d\xe5\x03\x00\x52\xe1'
    b'\x55\x00\x00\x8a\x09\x10\xa0\xe1\x00\x20\xa0\xe3\x04\x00\xa0\xe1'
    b'\xbc\xff\xff\xeb\xb8\x35\xdd\xe1\x05\x00\x53\xe1\xe5\xff\xff\xca'
    b'\x04\x00\xa0\xe1\xb1\xff\xff\xeb\x00\x00\x57\xe3\x2f\x00\x00\x0a'
    b'\x07\x30\x96\xe7\x07\x70\x86\xe0\x00\x00\x53\xe3\x2b\x00\x00\x0a'
    b'\x00\x20\xa0\xe3\x08\xc0\xa0\xe3\x02\x00\xa0\xe1\x02\xe0\xa0\xe1'
    b'\x11\x00\x53\xe3\x04\xe0\x97\x05\x04\x00\x00\x0a\x12\x00\x53\xe3'
    b'\x04\x00\x97\x05\x01\x00\x00\x0a\x13\x00\x53\xe3\x04\xc0\x97\x05'
    b'\x08\x30\xb7\xe5\x01\x20\x82\xe2\x00\x00\x53\xe3\x64\x00\x52\x13'
    b'\x01\x10\xa0\x13\x00\x10\xa0\x03\xf0\xff\xff\x1a\x00\x00\x5e\xe3'
    b'\x00\x00\x50\x13\x15\x00\x00\x0a\x00\x00\x5c\xe3\x08\xc0\xa0\x03'
    b'\x0c\x00\x50\xe1\x11\x00\x00\x3a\x0c\x00\x40\xe0\x00\x00\x5c\xe1'
    b'\x01\x10\x81\xe2\xfb\xff\xff\x9a\x00\x00\x51\xe3\x0b\x00\x00\x0a'
    b'\x81\x11\x86\xe0\x0e\x30\x86\xe0\x0e\x10\x81\xe0\x04\x20\xd3\xe5'
    b'\x08\x30\x83\xe2\x17\x00\x52\xe3\x08\x00\x13\x05\x00\x20\x96\x07'
    b'\x02\x20\x86\x00\x00\x20\x86\x07\x01\x00\x53\xe1\xf6\xff\xff\x1a'
    b'\x00\x30\xa0\xe3\x7e\xff\x17\xee\xfd\xff\xff\x1a\x9a\x3f\x07\xee'
    b'\x15\x3f\x07\xee\x44\x30\x9d\xe5\x03\x00\x86\xe0\x64\xd0\x8d\xe2'
    b'\xf0\x8f\xbd\xe8\x04\x00\xa0\xe1\x74\xff\xff\xeb\x00\x00\xa0\xe3'
    b'\x64\xd0\x8d\xe2\xf0\x8f\xbd\xe8\x10\x10\x9d\xe5\x00\x20\xa0\xe3'
    b'\x04\x00\xa0\xe1\x73\xff\xff\xeb\x1c\x20\x9d\xe5\x04\x30\xa0\xe1'
    b'\x0b\x10\xa0\xe1\x08\x00\xa0\xe1\x6b\xff\xff\xeb\x1c\x30\x9d\xe5'
    b'\x20\x20\x9d\xe5\x03\x00\x52\xe1\xa9\xff\xff\x9a\x03\x30\x88\xe0'
    b'\x02\x80\x88\xe0\x00\x20\xa0\xe3\x01\x20\xc3\xe4\x08\x00\x53\xe1'
    b'\xfc\xff\xff\x1a\xa2\xff\xff\xea\x04\x00\xa0\xe1\x5b\xff\xff\xeb'
    b'\xda\xff\xff\xea\x68\x02\x00\x00\x7f\x45\x00\x00\x72\x00\x62\x00'
    b'\x00\x00'
)

class ShellcodeElfLoader:
    def __init__(self, dbg):
        self.dbg = dbg


        self.max_insn = 40000000
        self.image_raw = 0
        self.image_base = 0
        self.image_size = 0
        self.entry = 0
        self.ring = 0
        self.owned = False
        self.image_zeroed = False
        self.state_addr = 0
        self.blob_addr = 0

    def forget(self):

        self.image_raw = 0
        self.image_base = 0
        self.image_size = 0
        self.entry = 0
        self.ring = 0
        self.owned = False
        self.held = False

    def alloc_image(self, size):

        self.image_zeroed = False
        try:
            p = self.dbg.call(ADDR_CALLOC, size, 1)
        except Exception as e:
            note('[load] calloc is not usable here (%r): malloc + clear' % (e,))
            p = 0
        if p:
            self.image_zeroed = True
            return p
        return self.dbg.call(ADDR_MALLOC, size)

    def name_candidates(self, appdir):

        out = []
        if appdir:
            out.append(appdir.rstrip('\\') + '\\' + IMAGE_NAME)
        out.append(IMAGE_NAME)
        return out

    def copy_segments_fw(self, appdir, data):

        if not self.image_base or not data:
            return False
        segs = [t for t in ElfTools.segments(data) if t[2]]
        if not segs:
            return False
        mem = MemUtils(self.dbg)
        for name in self.name_candidates(appdir):
            p = mem.alloc_wstr(name)
            m = mem.alloc_wstr('rb')
            fd = 0
            try:
                if p and m:
                    fd = self.dbg.call(FW_FOPEN, p, m)
            except Exception as e:
                alert('[load] fopen(%s) raised: %r' % (name, e))
                fd = 0
            mem.free(p)
            mem.free(m)
            if not fd:
                note('[load] fopen(%s, rb) refused: trying the next spelling'
                    % name)
                continue
            try:
                ok = self.copy_segments_fd(fd, data, segs)
            except Exception as e:
                alert('[load] the firmware copy raised: %r' % (e,))
                ok = False
            finally:
                try:
                    self.dbg.call(FW_FCLOSE, fd)
                except Exception:
                    pass
            if ok:
                log('[load] segments copied by the firmware from %s' % name)
                return True
        return False

    def copy_segments_fd(self, fd, data, segs):

        for (p_off, p_vaddr, p_filesz, _p_memsz) in segs:
            if not self.read_into(fd, p_off, self.image_base + p_vaddr,
                                  p_filesz, data):
                return False
        return True

    def read_into(self, fd, off, dest, size, data):

        for chunk in (size, 65536, 8192):
            if chunk > size:
                continue
            if self.read_chunked(fd, off, dest, size, chunk, data):
                return True
            if chunk == size:
                break
        return False

    def read_chunked(self, fd, off, dest, size, chunk, data):

        done = 0
        while done < size:
            n = min(chunk, size - done)
            if not self.seek_and_read(fd, off + done, dest + done, n, data,
                                      off + done, n):
                return False
            done += n
        if chunk != size:
            log('[load] read %d B in %d byte chunks' % (size, chunk))
        return True

    def seek_and_read(self, fd, file_off, dest, n, data, want_off, want_len):

        try:
            self.dbg.call(FW_FSEEK, fd, file_off, 0)
        except Exception as e:
            alert('[load] fseek(%d) raised: %r' % (file_off, e))
            return False
        for (sz, nm) in ((n, 1), (1, n)):
            try:
                got = self.dbg.call(FW_FREAD, dest, sz, nm, fd)
            except Exception as e:
                alert('[load] fread(%d, %d) raised: %r' % (sz, nm, e))
                continue
            if not got:
                alert('[load] fread(%d, %d) returned 0' % (sz, nm))
                continue
            if self.window_matches(data, want_off, dest, want_len):
                return True
            log('[load] fread(%d, %d) returned %d but the bytes are wrong'
                % (sz, nm, got))
        return False

    def window_matches(self, data, off, dest, size):

        for start in (0, max(0, size // 2 - 4), max(0, size - 8)):
            n = min(8, size - start)
            if n <= 0:
                continue
            want = data[off + start:off + start + n]
            try:
                got = bytes(self.dbg.read_mem(dest + start, n))
            except Exception as e:
                alert('[load] read-back at +%d raised: %r' % (start, e))
                return False
            if got[:len(want)] != want:
                alert('[load] read-back at +%d differs from the file: %r vs %r'
                    % (start, got[:8], want[:8]))
                return False
        return True

    def load_via_blob(self, data, appdir):

        if not self.image_base or not data:
            return False
        segs = [t for t in ElfTools.segments(data) if t[2]]
        if not segs:
            return False
        mem = MemUtils(self.dbg)
        blob = self.blob_addr
        if not blob:


            blob = mem.malloc(len(LOADER_CODE))
            if not blob:
                alert('[load] no memory for the in-firmware loader (%d B)'
                    % len(LOADER_CODE))
                return False
            self.dbg.write_mem_bytes(blob, LOADER_CODE)
            self.blob_addr = blob
        try:
            for name in self.name_candidates(appdir):
                p = mem.alloc_wstr(name)
                if not p:
                    continue
                try:
                    entry = self.dbg.call(blob, p, self.image_base)
                finally:
                    mem.free(p)
                if not entry or entry < 0x30000000 or entry >= 0x32000000:
                    alert('[load] the in-firmware loader returned 0x%08X for %s'
                        % (entry, name))
                    continue
                
                
                off, vaddr, _filesz, _memsz = segs[0]
                want = data[off:off + 16]
                got = bytes(self.dbg.read_mem(self.image_base + vaddr,
                                              len(want)))
                if got != want:
                    alert('[load] the in-firmware loader did not copy the file '
                        '(%r vs %r)' % (got[:8], want[:8]))
                    continue
                if not (self.image_base <= entry < self.image_base +
                        ElfTools.memory_size(data)):
                    log('[load] the in-firmware loader returned an entry '
                        'outside the image (0x%08X)' % entry)
                    continue
                log('[load] loaded by the in-firmware loader from %s' % name)
                self.entry = entry
                return True
        finally:
            pass
        return False

    def copy_segments_py(self, data):

        chunk = 512
        total = 0
        for (p_off, p_vaddr, p_filesz, _p_memsz) in ElfTools.segments(data):
            dest = self.image_base + p_vaddr
            i = 0
            while i < p_filesz:
                n = min(chunk, p_filesz - i)
                self.dbg.write_mem_bytes(dest + i, data[p_off + i:p_off + i + n])
                i += n
                total += n
        log('[load] segments copied from Python: %d B in %d debug call(s)'
            % (total, (total + 3) // 4))

    def clear_bss(self, data):

        total = 0
        for (_p_off, p_vaddr, p_filesz, p_memsz) in ElfTools.segments(data):
            dest = self.image_base + p_vaddr
            for j in range(p_filesz, p_memsz, 512):
                n = min(512, p_memsz - j)
                self.dbg.write_mem_bytes(dest + j, b'\x00' * n)
                total += n
        if total:
            log('[load] cleared %d B of .bss the slow way: %d debug call(s) '
                '(calloc would have made this free)'
                % (total, (total + 3) // 4))

    def slot_armed(self):

        try:
            w0 = struct.unpack('<I', bytes(self.dbg.read_mem(FW_EVENT_SLOT, 4)))[0]
        except Exception:
            return None
        return w0 == SLOT_TRAP

    def hook_busy(self):
        
        if not self.state_addr:
            return 0            
        try:
            return struct.unpack('<i', bytes(
                self.dbg.read_mem(self.state_addr + HOOK_BUSY_OFF, 4)))[0]
        except Exception:
            return None

    def unload(self, keep=True):

        if not (self.owned and self.image_raw):
            self.forget()
            return
        busy = self.hook_busy()
        armed = self.slot_armed()
        if not keep and busy == 0 and armed is False:
            global _held
            self.dbg.call(ADDR_FREE, self.image_raw)
            if self.blob_addr:
                self.dbg.call(ADDR_FREE, self.blob_addr)
                self.blob_addr = 0
            log('[hook] image block 0x%08X given back' % self.image_raw)

            if _held:
                _held = [h for h in _held if h[0] != self.image_raw]
            self.forget()
        else:


            _held.append((self.image_raw, self.image_size, self.state_addr))
            self.held = True
            log('[hook] keeping the image at 0x%08X mapped (hook calls in '
                'flight: %r, slot still armed: %r): the next run reuses it'
                % (self.image_raw, busy, armed))

    def release_held(self):

        global _held
        keep = []
        for (raw, size, state) in _held:
            busy = None
            if state:
                try:
                    busy = struct.unpack('<i', bytes(
                        self.dbg.read_mem(state + HOOK_BUSY_OFF, 4)))[0]
                except Exception:
                    busy = None


            if busy == 0 and self.slot_armed() is False:
                self.dbg.call(ADDR_FREE, raw)
                log('[hook] released the held image block 0x%08X' % raw)

                if _resident.loader is not None and \
                        _resident.loader.image_raw == raw:
                    _resident.entry = 0
                    _resident.loader = None
            else:
                keep.append((raw, size, state))
        _held = keep
        if _held:
            alert('[hook] %d image block(s) still held: a hook call is in flight'
                % len(_held))

    def load(self, data, appdir=None):

        need = ElfTools.memory_size(data)
        if not need:
            alert('[load] FAIL: not an ELF image')
            return 0
        
        
        self.release_held()
        entry_off = ElfTools.entry_point(data)
        relocs, unknown = ElfTools.relocations(data)
        if unknown:
            
            
            alert('[load] FAIL: %d symbol relocation(s): rebuild with make '
                '(tools/fix_relocs.py folds them)' % unknown)
            return 0
        log('[load] image needs %d B, %d reloc(s)' % (need, len(relocs)))
        if not (self.owned and self.image_size >= need):
            if self.owned and self.image_raw:
                self.dbg.call(ADDR_FREE, self.image_raw)


            self.image_raw = self.alloc_image(need + 16)
            if not self.image_raw:
                alert('[load] FAIL: the firmware gave no memory for %d B'
                    % (need + 16,))
                return 0
            self.image_base = (self.image_raw + 15) & ~7
            self.image_size = need
            self.owned = True
            log('[load] image block 0x%08X base 0x%08X%s' %
                (self.image_raw, self.image_base,
                 ' (calloc: zeroed)' if self.image_zeroed else ' (malloc)'))


        by_blob = self.load_via_blob(data, appdir)
        if not by_blob:
            if not self.copy_segments_fw(appdir, data):
                self.copy_segments_py(data)
        if self.image_zeroed:
            log('[load] .bss comes zeroed from the firmware: nothing to clear')
        elif not by_blob:
            self.clear_bss(data)

        if by_blob:


            log('[load] relocations were applied by the in-firmware loader '
                '(%d of them)' % len(relocs))
        else:
            for (r_off, _rtype, _sym) in relocs:
                addr = self.image_base + r_off
                word = self.dbg.read_mem(addr, 4)
                if len(word) < 4:
                    alert('[load] FAIL: cannot read the reloc word at 0x%08X'
                        % addr)
                    self.unload()
                    return 0
                value = struct.unpack('<I', bytes(word))[0]
                self.dbg.write_mem(addr,
                                   (value + self.image_base) & 0xFFFFFFFF)

        self.entry = self.image_base + entry_off


        self.state_addr = ElfTools.find_magic(data, b'NBINPUT', self.image_base)


        self.ring = ElfTools.find_magic(data, b'NBCORING', self.image_base)
        self.seg_top = ElfTools.seg_end(data)
        log('[load] entry 0x%08X ring 0x%08X image_end 0x%08X'
            % (self.entry, self.ring, self.image_base + self.seg_top))
        if not self.ring:
            alert('[load] FAIL: no NBCORING ring in the image')
            self.unload()
            return 0
        return self.entry


CFG_MAGIC = 0x6763626E
CFG_VERSION = 4
CFG_MAX_WS = 8
CFG_MAX_FILES = 512
CFG_MAX_DIRS = 64


CFG_NO_DIR = 0xFFFFFFFF
CFG_MAX_NAMES = 512          
CFG_NAME_MAX = 64            
CFG_DIR_DEPTH = 2            
                             
                             


CFG_FILE = 'nbcode.cfg'


IMAGE_NAME = 'nbCode.elf'
LOG_TAIL = 'nbcode.log'


CLIP_TAIL = 'nbclip.txt'


def log_device_path(appdir):
    
    if not appdir:
        return LOG_TAIL
    return appdir.rstrip('\\') + '\\' + LOG_TAIL


def build_config(settings, workspaces, dirs, cwd, open_file='', logpath='',
                 frames=0):
    
    flags = 0
    if settings.get('readonly'):
        flags |= 0x0001
    if not settings.get('highlight', True):
        flags |= 0x0002
    if not settings.get('show_line_numbers', True):
        flags |= 0x0004
    if not settings.get('complete', True):
        flags |= 0x0008		
    if not settings.get('indent_guides', True):
        flags |= 0x0010		
    lang = settings.get('language', 'auto')
    if isinstance(lang, str):
        lang = LANG_NAMES.get(lang.lower(), 0)
    tab = settings.get('tab_width', 4)
    if not isinstance(tab, int) or tab < 2 or tab > 8:
        tab = 4
    ws = [w[1] for w in workspaces][:CFG_MAX_WS]

    out = bytearray()
    out += struct.pack('<IIIIIIIII', CFG_MAGIC, CFG_VERSION, flags,
                      1 if settings.get('theme') else 0, tab, int(lang),
                      int(frames or 0), len(ws),
                      int(settings.get('default_workspace', 0) or 0))
    out += utf8_bytes(cwd) + b'\x00'
    out += utf8_bytes(open_file or '') + b'\x00'
    out += utf8_bytes(logpath or '') + b'\x00'
    for w in ws:
        out += utf8_bytes(w) + b'\x00'
    out += struct.pack('<I', len(dirs))
    for d in dirs:
        out += utf8_bytes(str(d.get('path', ''))) + b'\x00'
        parent = d.get('parent')
        out += struct.pack('<I', 0xFFFFFFFF if parent is None else int(parent))
        files = d.get('files') or []
        out += struct.pack('<I', len(files))
        for f in files:
            out += struct.pack('<II', int(f.get('bytes', 0)),
                               1 if f.get('isdir') else 0)
            out += utf8_bytes(str(f.get('name', ''))) + b'\x00'
    return bytes(out)


def write_config(path, data):

    with io.FileIO(path, 'wb') as f:
        f.write(data)
    return len(data)


DEFAULTS = {
    "theme": 0,
    "tab_width": 4,
    "show_line_numbers": True,
    "highlight": True,
    "readonly": False,
    "language": "auto",
    "workspaces": [],
    "default_workspace": 0,
    "shellcode": 0xE51FF004,
}

LANG_NAMES = {"auto": 0, "ppl": 1, "lua": 2, "py": 3, "python": 3, "c": 4,
              "txt": 5, "text": 5}


class JsonError(Exception):
    pass


_JSON_WS = ' \t\r\n'
_JSON_ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
                 '/': '/', '\\': '\\', '"': '"'}


def _json_skip(s, i):
    while i < len(s) and s[i] in _JSON_WS:
        i += 1
    return i


def _json_string(s, i):
    i += 1
    out = []
    while True:
        if i >= len(s):
            raise JsonError('unterminated string')
        c = s[i]
        if c == '"':
            return ''.join(out), i + 1
        if c == '\\':
            i += 1
            if i >= len(s):
                raise JsonError('unterminated escape')
            e = s[i]
            if e == 'u':
                hex4 = s[i + 1:i + 5]
                if len(hex4) < 4:
                    raise JsonError('truncated \\u escape')
                out.append(chr(int(hex4, 16)))
                i += 5
                continue
            out.append(_JSON_ESCAPES.get(e, e))
            i += 1
            continue
        out.append(c)
        i += 1


def _json_value(s, i):
    i = _json_skip(s, i)
    if i >= len(s):
        raise JsonError('no value')
    c = s[i]
    if c == '{':
        obj = {}
        i = _json_skip(s, i + 1)
        if i < len(s) and s[i] == '}':
            return obj, i + 1
        while True:
            i = _json_skip(s, i)
            if i >= len(s) or s[i] != '"':
                raise JsonError('object key expected at %d' % i)
            key, i = _json_string(s, i)
            i = _json_skip(s, i)
            if i >= len(s) or s[i] != ':':
                raise JsonError('":" expected at %d' % i)
            val, i = _json_value(s, i + 1)
            obj[key] = val
            i = _json_skip(s, i)
            if i < len(s) and s[i] == ',':
                i += 1
                continue
            if i < len(s) and s[i] == '}':
                return obj, i + 1
            raise JsonError('"," or "}" expected at %d' % i)
    if c == '[':
        arr = []
        i = _json_skip(s, i + 1)
        if i < len(s) and s[i] == ']':
            return arr, i + 1
        while True:
            val, i = _json_value(s, i)
            arr.append(val)
            i = _json_skip(s, i)
            if i < len(s) and s[i] == ',':
                i += 1
                continue
            if i < len(s) and s[i] == ']':
                return arr, i + 1
            raise JsonError('"," or "]" expected at %d' % i)
    if c == '"':
        return _json_string(s, i)
    for lit, val in (('true', True), ('false', False), ('null', None)):
        if s[i:i + len(lit)] == lit:
            return val, i + len(lit)
    j = i
    while j < len(s) and s[j] in '-+0123456789.eE':
        j += 1
    if j == i:
        raise JsonError('unexpected %r at %d' % (c, i))
    text = s[i:j]
    try:
        return int(text), j
    except ValueError:
        try:
            return float(text), j
        except ValueError:
            raise JsonError('bad number %r' % text)


def parse_json(text):

    value, i = _json_value(text, 0)
    i = _json_skip(text, i)
    if i != len(text):
        raise JsonError('trailing text at %d' % i)
    return value


def setting_path(appdir):
    return appdir + '\\setting.json'


APP_DIRS = ['C:\\DATA\\nbCode.hpappdir', 'C:\\DATA', '\\']


def find_app_dir(dbg=None):

    if dbg is not None:
        d = fw_cwd(dbg)
        if d:
            for cand in (d.rstrip('\\'),
                         d.rstrip('\\') + '\\' + APP_DIR_NAME):
                if fw_exists(dbg, cand + '\\' + IMAGE_NAME):
                    log('[probe] app folder (firmware): %s' % cand)
                    return cand
            log('[probe] the firmware cwd is %s, but %s is not in it'
                % (d, IMAGE_NAME))
    try:
        import os
        d = os.getcwd()
        if d and os.path.isfile(os.path.join(d, IMAGE_NAME)):
            return d
    except Exception:
        pass
    return APP_DIR


def fw_exists(dbg, path):
    
    try:
        mem = MemUtils(dbg)
        p = mem.alloc_wstr(path)
        if not p:
            return False
        try:
            return dbg.call(FW_GET_ATTR, p) != 0xFFFFFFFF
        finally:
            mem.free(p)
    except Exception:
        return False


def fw_cwd(dbg):

    try:
        mem = MemUtils(dbg)
        disk = dbg.call(FW_GET_DISK_ID)
        buf = mem.malloc(520)
        if not buf:
            return ''
        try:
            if dbg.call(FW_GETCWD, disk, buf) == 0xFFFFFFFF:
                return ''
            return mem.read_wstr(buf).rstrip('\\')
        finally:
            mem.free(buf)
    except Exception:
        return ''


def read_bytes(name, appdir=None):

    cands = [name]
    if appdir:
        cands.append(appdir.rstrip('\\') + '\\' + name)
    for d in APP_DIRS:
        cands.append(d.rstrip('\\') + '\\' + name)
    for c in cands:
        try:
            with open_file(c, 'rb') as f:
                return f.read()
        except Exception:
            continue
    return None


def read_settings(appdir):

    out = dict(DEFAULTS)
    raw = None
    where = ''
    for candidate in ('setting.json', 'setting.json.txt',
                      setting_path(appdir), setting_path(appdir) + '.txt'):
        try:
            with open_file(candidate, 'rb') as f:
                raw = f.read()
            where = candidate
            break
        except Exception:
            raw = None
    if raw is None:
        log('[settings] setting.json not found: using the defaults')
        return out, 'missing'
    if isinstance(raw, bytes):
        if raw[0:3] == b'\xef\xbb\xbf':
            raw = raw[3:]
        try:
            raw = raw.decode('utf-8')
        except Exception:
            raw = raw.decode('latin-1')


    try:
        if json is not None:
            parsed = json.loads(raw)
        else:
            parsed = parse_json(raw)
    except Exception as e:
        note('[settings] %s is not valid JSON (%r): using the defaults'
            % (where, e))
        return out, 'invalid'
    if not isinstance(parsed, dict):
        note('[settings] %s is not an object: using the defaults' % where)
        return out, 'invalid'
    for k in parsed:
        out[k] = parsed[k]
    log('[settings] %s: %d key(s)' % (where, len(parsed)))
    return out, 'ok'


def write_settings(appdir, settings):

    if json is None:
        alert('[settings] no json module: not writing setting.json')
        return False
    try:
        text = json.dumps(settings)
    except Exception:
        return False
    for name in ('setting.json', setting_path(appdir)):
        try:
            with open_file(name, 'wb') as f:
                f.write(utf8_bytes(text))
            return True
        except Exception:
            continue
    return False


def read_text(path):
    raw = read_bytes(path)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        for enc in ('utf-8', 'gb2312', 'latin-1'):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return decode_bytes(raw)
    return raw


APP_DIR_NAME = 'nbCode.hpappdir'


FIND_CTX_BYTES = 256
FIND_LFN_OFF = 8
FIND_SFN_OFF = 12
FIND_SIZE_OFF = 20
FIND_ATTR_OFF = 37
FIND_ATTR_DIR = 0x10


def parse_find_entry(raw):

    if len(raw) < FIND_ATTR_OFF + 1:
        return None
    lfn = struct.unpack_from('<I', raw, FIND_LFN_OFF)[0]
    sfn = struct.unpack_from('<I', raw, FIND_SFN_OFF)[0]
    size = struct.unpack_from('<I', raw, FIND_SIZE_OFF)[0]
    attr = struct.unpack_from('<B', raw, FIND_ATTR_OFF)[0]
    return {'lfn': lfn, 'sfn': sfn, 'size': size, 'attr': attr}


def merge_find_rows(rows):

    out = []
    where = {}
    for row in rows:
        name = row[0]
        key = name.lower()
        if key not in where:
            where[key] = len(out)
            out.append(row)
            continue
        i = where[key]
        if not out[i][1] and row[1]:
            out[i] = (out[i][0], row[1], out[i][2] or row[2])
    return out


def list_dir_fw(dbg, path):

    out = []
    mem = MemUtils(dbg)
    pattern = path.rstrip('\\') + '\\*'


    passes = 0
    for mask in (0x37, 0xFF, 0x00, None):
        passes += 1
        p = mem.alloc_wstr(pattern)
        ctx = mem.malloc(FIND_CTX_BYTES)
        if not p or not ctx:
            mem.free(p)
            mem.free(ctx)
            break
        try:
            if mask is None:
                ok = dbg.call(FW_FIND_FIRST, p, ctx)
            else:
                ok = dbg.call(FW_FIND_FIRST, p, ctx, mask)
            if ok != 0:
                continue
            while True:
                ent = parse_find_entry(bytes(dbg.read_mem(ctx, 40)))
                if ent is not None:
                    name = mem.read_wstr(ent['lfn']) or \
                        mem.read_utf8(ent['sfn'])
                    if name and name not in ('.', '..'):
                        out.append((name, ent['size'],
                                    bool(ent['attr'] & FIND_ATTR_DIR)))
                if dbg.call(FW_FIND_NEXT, ctx) != 0:
                    break
        except Exception as e:
            alert('[list] the firmware finder failed on %s: %r' % (path, e))
        finally:
            try:
                dbg.call(FW_FIND_CLOSE, ctx)
            except Exception:
                pass
            mem.free(p)
            mem.free(ctx)
    merged = merge_find_rows(out)
    log('[list] %s: %d entr(ies) from %d finder result(s) over %d mask(s)'
        % (path, len(merged), len(out), passes))
    return merged


def list_dir_os(path):

    out = []
    import os
    where = path
    tail = path.replace('/', '\\').rstrip('\\')
    if tail.lower().endswith(APP_DIR_NAME.lower()):

        where = '.'
    elif not os.path.isdir(where):


        
        i = tail.lower().find('\\' + APP_DIR_NAME.lower() + '\\')
        if i >= 0:
            
            
            cand = tail[i + len(APP_DIR_NAME) + 2:].replace('\\', os.sep)
            if cand and os.path.isdir(cand):
                where = cand
    if not os.path.isdir(where):
        alert('[list] cannot read %s: not a directory' % (path,))
        return out
    try:
        names = os.listdir(where)
    except Exception as e:
        alert('[list] cannot read %s: %r' % (path, e))
        return out
    for fname in names:
        if fname in ('.', '..'):
            continue
        size, isdir = 0, False
        try:
            st = os.stat(os.path.join(where, fname))
            size = st[6] if len(st) > 6 else 0
            isdir = bool(st[0] & 0x4000)
        except Exception:
            pass
        out.append((fname, size, isdir))
    return out


def list_dir(path, dbg=None):

    out = []
    if dbg is not None and is_device():
        out = list_dir_fw(dbg, path)
        if out:
            log('[list] %s: %d entr(ies) from the firmware finder'
                % (path, len(out)))
        else:
            log('[list] %s: the firmware finder returned nothing' % path)
    else:
        out = list_dir_os(path)
        log('[list] %s: %d entr(ies) from os.listdir' % (path, len(out)))
    out.sort(key=lambda e: (not e[2], e[0].lower()))
    return out


LOG_PREFIX = 'LOG:'
_log_file = None


VERBOSE_MARKER = 'verbose'
_verbose = None


def verbose():

    global _verbose

    if _verbose is None:
        try:
            with open_file(VERBOSE_MARKER, 'rb') as f:
                f.read(1)
            _verbose = True
        except Exception:
            _verbose = False
    return _verbose


def set_verbose(on):
    global _verbose

    _verbose = True if on else False


def append_log_line(line):
    global _log_file
    try:
        if _log_file is None:
            _log_file = io.FileIO(LOG_TAIL, 'ab')
        _log_file.write(utf8_bytes(line + '\n'))
        return
    except Exception:
        _log_file = None
    log(line)

_session = None


class Session:


    def __init__(self, appdir, ui):
        self.dbg = PrimeDebug()
        self.loader = ShellcodeElfLoader(self.dbg)
        self.appdir = appdir
        self.ui = ui
        self.heap = 0

    def close(self):
        if self.heap:
            self.dbg.call(ADDR_FREE, self.heap)
            self.heap = 0
        self.loader.unload(keep=False)


_PROGRESS = None


def progress(step, total, what):

    global _PROGRESS

    line = 'nbCode %d/%d: %s' % (step, total, what)
    if _PROGRESS != line:
        _PROGRESS = line
    try:
        p_log(line)
    except Exception:
        pass
    log('[progress] %s' % what, force=True)


def alert(text):

    log(text, force=True, level=p_error)


def note(text):

    log(text, force=True, level=p_warning)


def succeed(text, force=True):

    log(text, force=force, level=p_pass)


def log(text, force=False, level=None):

    line = utf8_bytes(text + '\n')
    try:
        with io.FileIO(LOG_TAIL, 'ab') as f:
            f.write(line)
    except Exception:
        try:
            old = read_bytes(LOG_TAIL) or b''
            if len(old) > 16384:                 
                old = old[-8192:]
            with io.FileIO(LOG_TAIL, 'wb') as f:
                f.write(old + line)
        except Exception:
            pass
    if not force and not verbose():
        return
    try:
        (level or p_log)(text)
    except Exception:
        pass


def free_heap():
    
    try:
        total = hpprime.eval('mem')
        return int(total) * 1024 if total else 0
    except Exception:
        return 0


RING_MAGIC = b'NBCORING'
RING_COUNT_OFF = 8
RING_DATA_OFF = 12
RING_SIZE = 8192


def decode_ring(raw):

    return [decode_bytes(line) for line in raw.split(b'\n')]


def parse_rt_ret(dbg, ring, state):

    if not ring or state is None:
        return None
    try:
        start = state - 64 if state >= 64 else 0
        n = state - start
        raw = bytes(dbg.read_mem(ring + RING_DATA_OFF + (start % RING_SIZE), n))
    except Exception:
        return None
    code = None
    for line in decode_ring(raw):
        if line.startswith('RT_RET:'):
            try:
                code = int(line[7:].strip())
            except Exception:
                code = None
    return code


def drain_ring(dbg, ring, state):

    if not ring:
        return state
    try:
        head = struct.unpack('<I', bytes(dbg.read_mem(ring + RING_COUNT_OFF, 4)))[0]
    except Exception:
        return state
    if head == state:
        return state
    if head < state or head - state > RING_SIZE:
        state = head - RING_SIZE if head >= RING_SIZE else 0
    n = head - state
    try:
        raw = bytes(dbg.read_mem(ring + RING_DATA_OFF + (state % RING_SIZE), n))
    except Exception:
        return head
    try:
        text = decode_ring(raw)
    except Exception:
        text = []
    for line in text:
        if line.startswith('RT_RET:'):
            continue
        line = line.rstrip()
        if not line:
            continue
        if line.startswith(LOG_PREFIX):


            append_log_line('[nbCode] ' + line[len(LOG_PREFIX):])
            continue
        log('[nbCode] ' + line)
    return head


class Resident:


    def __init__(self):
        self.loader = None
        self.entry = 0
        self.ring = 0
        self.size = 0
        self.name = ''
        self.hits = 0
        self.loads = 0


_resident = Resident()


class RoundTrips:


    def __init__(self, dbg):
        self.dbg = dbg
        self.marks = []

    def mark(self, what):
        n = getattr(self.dbg, 'round_trips', None)
        if n is None:
            return
        self.marks.append((what, n))

    def report(self):
        if len(self.marks) < 2:
            return
        base = self.marks[0][1]
        prev = base
        for (what, n) in self.marks[1:]:
            log('[cost] %-22s %6d round trip(s)' % (what, n - prev))
            prev = n
        log('[cost] %-22s %6d round trip(s) in total'
            % ('start-up', prev - base))


def run_file(path, ui=None, frames=0, max_insn=None, dbg=None):

    dbg = dbg or PrimeDebug()
    cost = RoundTrips(dbg)


    progress(1, 6, 'finding the application folder')
    appdir = (ui or {}).get('appdir') or find_app_dir(dbg)
    cost.mark('start')
    progress(2, 6, 'reading setting.json')
    settings = (ui or {}).get('settings') or read_settings(appdir)[0]
    workspaces = (ui or {}).get('workspaces') or default_workspaces(appdir)
    cwd = (ui or {}).get('cwd') or workspaces[
        min(settings.get('default_workspace', 0) or 0,
            len(workspaces) - 1)][1]

    progress(3, 6, 'listing the workspaces and their folders')
    image = read_bytes(IMAGE_NAME, appdir)
    if image is None:
        alert('[load] FAIL: cannot read %s (tried a bare name and the '
            'application folders)' % IMAGE_NAME)
        return None
    log('[load] %s %d B' % (IMAGE_NAME, len(image)))


    cost.mark('settings + workspace list')


    dirs = []
    total = 0

    def add_dir(path, parent, depth=1):

        nonlocal total
        if len(dirs) >= CFG_MAX_DIRS:
            return -1
        me = len(dirs)
        dirs.append({'path': path, 'parent': parent, 'depth': depth,
                     'files': [], 'subdirs': []})
        for (name, size, isdir) in list_dir(path, dbg):
            if name in (CFG_FILE, LOG_TAIL, IMAGE_NAME, CLIP_TAIL):
                continue
            if total >= CFG_MAX_FILES:
                log('[list] %s: the file budget is full (%d entries)'
                    % (path, total))
                break
            if isdir:


                dirs[me]['files'].append({'name': name,
                                          'bytes': CFG_NO_DIR,
                                          'isdir': True, 'child': -1,
                                          'path': path + '\\' + name})
                dirs[me]['subdirs'].append(name)
            else:
                dirs[me]['files'].append({'name': name, 'bytes': size,
                                          'isdir': False})
            total += 1
        return me


    try:
        for (label, wsdir) in workspaces[:CFG_MAX_WS]:
            i = add_dir(wsdir, None)
            if i < 0:
                break
            log('[run] %s: %d entr(ies)' % (wsdir, len(dirs[i]['files'])))


        i = 0
        while i < len(dirs):
            parent = dirs[i]
            me = i
            i += 1
            if parent['depth'] > CFG_DIR_DEPTH:


                continue
            for f in parent['files']:
                if not f.get('isdir'):
                    continue
                if len(dirs) >= CFG_MAX_DIRS:
                    log('[list] %s: the directory budget is full (%d): %s stays '
                        'a row that cannot be opened'
                        % (parent['path'], len(dirs), f['name']))
                    break
                j = add_dir(f['path'], me, parent['depth'] + 1)
                if j < 0:
                    break
                f['child'] = j
                f['bytes'] = j
                log('[run] %s: %d entr(ies)'
                    % (dirs[j]['path'], len(dirs[j]['files'])))
    except Exception as e:
        alert('[list] the workspace listing stopped early: %r' % (e,))
        log('[list] at that point: %d dir(s) %s, workspaces %s, cwd %r'
            % (len(dirs), type(dirs).__name__, type(workspaces).__name__, cwd))

    for d in dirs:
        d.pop('subdirs', None)

    cost.mark('listing every workspace')
    cfg_bytes = build_config(settings, workspaces, dirs, cwd,
                             open_file=path or '',
                             logpath=log_device_path(appdir),
                             frames=frames)
    n = write_config(CFG_FILE, cfg_bytes)
    log('[run] launch file %s, %d B; %s (%d entries in %d dir(s))'
        % (CFG_FILE, n, path or cwd, total, len(dirs)))

    
    
    
    
    
    loader = _resident.loader
    if (loader is not None and _resident.entry and loader.owned
            and loader.dbg is dbg and len(image) == _resident.size
            and loader.slot_armed() is False):
        entry = _resident.entry
        _resident.hits += 1
        log('[load] reusing the image already in memory (run %d of this session)'
            % (_resident.hits + 1))
    else:
        loader = ShellcodeElfLoader(dbg)
        entry = loader.load(image, appdir)
        if entry:
            _resident.loader = loader
            _resident.entry = entry
            _resident.ring = loader.ring
            _resident.size = len(image)
            _resident.loads += 1
    if not entry:
        alert('[load] FAILED')
        loader.unload()
        return None

    progress(4, 6, 'loading nbCode.elf into the firmware')
    cost.mark('image load / reuse')
    ring = loader.ring
    state = struct.unpack('<I', bytes(dbg.read_mem(ring + RING_COUNT_OFF,
                                                   4)))[0]
    cap = max_insn if max_insn else loader.max_insn
    log('[run] entering the image at 0x%08X (cap %d instructions)'
        % (entry, cap))
    try:
        dbg.max_insn = cap
    except Exception:
        pass

    


    arg = 0
    if appdir:
        b = utf8_bytes(appdir) + b'\x00'
        arg = dbg.call(ADDR_MALLOC, len(b))
        if arg:
            dbg.write_mem_bytes(arg, b)
            log('[run] app folder in r0: %s' % appdir)
        else:
            alert('[run] no memory for the app folder: the image will use its '
                'built-in path')
    try:
        ret = dbg.call(entry, arg, 0, 0, 0)
    except Exception as e:


        drain_ring(dbg, ring, state)
        alert('[run] the editor did not return: %r' % (e,))


        stand_down_input(dbg, loader, image)
        loader.unload()
        return None
    finally:

        if arg:
            try:
                dbg.call(ADDR_FREE, arg)
            except Exception:
                pass


    state = drain_ring(dbg, ring, state)
    code = parse_rt_ret(dbg, ring, state)
    if code is None:
        code = ret if isinstance(ret, int) else 0

    
    
    
    progress(5, 6, 'starting the editor')
    cost.mark('the editor session')
    stand_down_input(dbg, loader, image)


    
    
    loader.unload()
    if loader.owned and _resident.loader is loader:
        log('[load] the image stays mapped: the next run reuses it')
    progress(6, 6, 'closing down')
    cost.mark('teardown')
    cost.report()


    if code == 0:


        succeed('[exit] status 0: the editor returned to the launcher',
                force=verbose())
    else:
        note('[exit] status %d: the editor did not come back cleanly' % code)
    return code


def stand_down_input(dbg, loader, image):

    try:
        slot = bytes(dbg.read_mem(FW_EVENT_SLOT, 8))
    except Exception:
        return
    if len(slot) < 8:
        return
    w0, hook_fn = struct.unpack('<II', slot)
    if w0 != SLOT_TRAP:
        return                  
    state = ElfTools.find_magic(image, b'NBINPUT', loader.image_base)
    if not state:
        alert('[hook] the slot holds our trap but the input state was not found in '
            'the image: leaving it alone rather than guessing')
        return
    their_fn = 0
    saved_valid = 0
    saved = None
    try:
        their_fn = struct.unpack('<I', bytes(dbg.read_mem(state + 8, 4)))[0]
        saved_valid = struct.unpack('<i', bytes(dbg.read_mem(state + 28, 4)))[0]
        if saved_valid:
            saved = bytes(dbg.read_mem(state + 12, 16))
    except Exception:
        saved = None
    if their_fn and their_fn != hook_fn:
        log('[hook] the state belongs to another image (hook_fn 0x%08X, the slot '
            'holds 0x%08X): leaving the slot alone' % (their_fn, hook_fn))
        return
    if not saved or len(saved) < 16 or struct.unpack('<I', saved[0:4])[0] == \
            SLOT_TRAP:
        saved = struct.pack('<IIII', 0xE52D0004, 0xE52DE004, 0xEF01003F,
                            0xE49D0004)
        why = "the firmware's own stub (no usable original was saved)"
    else:
        why = 'the bytes saved before the patch'
    words = list(struct.unpack('<IIII', saved[:16]))
    armed_now = w0 == SLOT_TRAP
    for i in ((1, 0, 2, 3) if armed_now else (0, 1, 2, 3)):
        try:
            if i == 1 and armed_now:
                dbg.write_mem(FW_EVENT_SLOT + 4, 0)
            dbg.write_mem(FW_EVENT_SLOT + 4 * i, words[i])
        except Exception as e:
            alert('[hook] slot write %d failed: %r' % (i, e))
            return
    try:
        back = bytes(dbg.read_mem(FW_EVENT_SLOT, 4))
        ok = len(back) >= 4 and struct.unpack('<I', back)[0] != SLOT_TRAP
    except Exception:
        ok = False
    log('[hook] firmware input slot restored from %s: %s'
        % (why, 'ok' if ok else 'the write did not take'))


def label_of(path):
    
    return path.rsplit('\\', 1)[-1] or path


def default_workspaces(appdir):

    out = []
    seen = set()
    for entry in (appdir, 'C:\\DATA', 'C:\\'):
        if entry and entry not in seen:
            seen.add(entry)
            out.append((label_of(entry), entry))
    return out


def settings_workspaces(settings, appdir):

    listed = []
    for entry in (settings.get('workspaces') or []):
        path = None
        label = None
        if isinstance(entry, str) and entry:
            path = entry
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            first, second = entry
            if isinstance(second, str) and second:
                path = second
                label = first if isinstance(first, str) and first else None
        if path:
            listed.append((label or label_of(path), path))
    if not listed:
        log('[settings] no usable "workspaces": offering the default folders')
        return default_workspaces(appdir)
    return listed


def probe(appdir=None, dbg=None):

    global _verbose
    saved = _verbose
    set_verbose(True)
    try:
        dbg = dbg or PrimeDebug()
        appdir = appdir or find_app_dir(dbg)
        log('[probe] appdir %s' % appdir)
        log('[probe] a bare name reads: %s'
            % ('yes' if read_bytes('setting.json') is not None else 'no'))
        settings, why = read_settings(appdir)
        log('[probe] settings: %s' % why)
        log('[probe] workspaces: %r'
            % (settings_workspaces(settings, appdir),))
        log('[probe] listing %s: %d entr(ies)'
            % (appdir, len(list_dir(appdir, dbg))))
        image = read_image(appdir)
        if image is None:
            return 2
        log('[probe] debug channel open')
        loader = ShellcodeElfLoader(dbg)
        entry = loader.load(image, appdir)
        log('[probe] loader -> entry 0x%08X' % entry)
        if entry:
            log('[probe] ring 0x%08X, image base 0x%08X' % (loader.ring,
                                                            loader.image_base))
            loader.unload()
        else:
            log('[probe] the image did not load: see the [load] lines above')
        return 0 if entry else 3
    finally:
        _verbose = saved


def read_image(appdir=None):

    raw = read_bytes(IMAGE_NAME, appdir)
    if raw is None:
        alert('[probe] cannot read %s (bare name and the application folders '
            'were tried)' % IMAGE_NAME)
    return raw


def unload():
    global _session
    if _session:
        _session.close()
        _session = None


APP_DIR = 'C:\\DATA\\nbCode.hpappdir'
SELFTEST_NO_EDITOR = False


def run(path=None, appdir=None, dbg=None):
    dbg = dbg or PrimeDebug()
    appdir = appdir or find_app_dir(dbg)
    settings, why = read_settings(appdir)
    workspaces = settings_workspaces(settings, appdir)
    ui = {
        'appdir': appdir,
        'settings': settings,
        'workspaces': workspaces,
        'cwd': workspaces[settings.get('default_workspace', 0) % len(workspaces)][1]
        if workspaces else 'C:\\',
    }
    if SELFTEST_NO_EDITOR:
        log('[selftest] settings=%s workspaces=%d' % (why, len(workspaces)))
        return 0
    return run_file(path, ui, dbg=dbg)


def main_menu(dbg=None):

    dbg = dbg or PrimeDebug()
    appdir = find_app_dir(dbg)
    settings, why = read_settings(appdir)
    log('nbCode -- settings: %s' % why)
    workspaces = settings_workspaces(settings, appdir)
    for i, (label, path) in enumerate(workspaces):
        log('  %d) %-16s %s' % (i + 1, label, path))
    return run(dbg=dbg)


if is_device():
    main_menu()
