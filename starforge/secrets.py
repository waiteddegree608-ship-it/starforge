"""Load credentials from environment or Windows user-bound DPAPI files."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


def credential(name, directory):
    env = {'github':'GH_TOKEN', 'deepseek':'DEEPSEEK_API_KEY', 'opencode':'OPENCODE_API_KEY'}[name]
    if os.environ.get(env):
        return os.environ[env]
    if os.name != 'nt':
        raise RuntimeError(f'Set {env} in the service environment')
    encrypted = bytes.fromhex((Path(directory) / (name + '.dpapi')).read_text(encoding='utf-8-sig').strip())
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    source = ctypes.create_string_buffer(encrypted)
    src = Blob(len(encrypted), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    dest = Blob()
    decrypt = ctypes.windll.crypt32.CryptUnprotectData
    decrypt.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    decrypt.restype = wintypes.BOOL
    if not decrypt(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dest)):
        raise RuntimeError('Cannot decrypt credential for this Windows user')
    try:
        return ctypes.string_at(dest.data, dest.size).decode('utf-16-le')
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dest.data, ctypes.c_void_p))
