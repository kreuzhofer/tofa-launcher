"""Checksum and executable identity checks shared by host staging and guest probe."""
import hashlib
import struct


def verify_candidate(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError('invalid_candidate')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise ValueError('candidate_checksum_mismatch')
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('candidate_not_arm64')
    offset = struct.unpack_from('<I', data, 60)[0]
    if (offset + 6 > len(data) or data[offset:offset + 4] != b'PE\0\0'
            or struct.unpack_from('<H', data, offset + 4)[0] != 0xAA64):
        raise ValueError('candidate_not_arm64')
    return data
