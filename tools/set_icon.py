"""Replace the main icon (first RT_GROUP_ICON, every language) of an exe with a multi-size .ico.
Run on the bare projector BEFORE the swf is appended (UpdateResource rewrites the file).
usage: python -I set_icon.py <exe> <ico>"""
import ctypes
import struct
import sys
from ctypes import wintypes

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.LoadLibraryExW.restype = wintypes.HMODULE
k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
k32.FreeLibrary.argtypes = [wintypes.HMODULE]
k32.BeginUpdateResourceW.restype = wintypes.HANDLE
k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
k32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_void_p,
                                wintypes.DWORD]
k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
NAMEPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
LANGPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD,
                              ctypes.c_void_p)
k32.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, NAMEPROC, ctypes.c_void_p]
k32.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, LANGPROC, ctypes.c_void_p]
RT_ICON, RT_GROUP_ICON = 3, 14


def first_group(exe):
    """-> (name: int or str, [languages]) of the first icon group"""
    m = k32.LoadLibraryExW(exe, None, 2)  # LOAD_LIBRARY_AS_DATAFILE
    names, langs = [], []

    def on_name(h, t, name, p):
        names.append(name if name < 0x10000 else ctypes.wstring_at(name))
        return False

    k32.EnumResourceNamesW(m, RT_GROUP_ICON, NAMEPROC(on_name), None)
    n = names[0]
    key = n if isinstance(n, int) else ctypes.c_wchar_p(n)
    k32.EnumResourceLanguagesW(m, RT_GROUP_ICON, key, LANGPROC(lambda h, t, nm, lang, p: langs.append(lang) or True),
                               None)
    k32.FreeLibrary(m)
    return n, langs


def main(exe, ico):
    name, langs = first_group(exe)
    d = open(ico, 'rb').read()
    n = struct.unpack('<HHH', d[:6])[2]
    entries = [struct.unpack('<BBBBHHII', d[6 + 16 * i:22 + 16 * i]) for i in range(n)]
    h = k32.BeginUpdateResourceW(exe, False)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    key = name if isinstance(name, int) else ctypes.c_wchar_p(name)
    for lang in langs:
        group = struct.pack('<HHH', 0, 1, n)
        for i, (w, hh, cc, r, planes, bpp, size, off) in enumerate(entries):
            rid = 9000 + i
            img = ctypes.create_string_buffer(d[off:off + size], size)
            assert k32.UpdateResourceW(h, RT_ICON, rid, lang, img, size)
            group += struct.pack('<BBBBHHIH', w, hh, cc, r, planes, bpp, size, rid)
        gb = ctypes.create_string_buffer(group, len(group))
        assert k32.UpdateResourceW(h, RT_GROUP_ICON, key, lang, gb, len(group))
    if not k32.EndUpdateResourceW(h, False):
        raise ctypes.WinError(ctypes.get_last_error())
    print('icon set:', exe, 'group', name, 'langs', langs, n, 'sizes')


if __name__ == '__main__':
    main(*sys.argv[1:])
