"""Ed25519 signature verification (RFC 8032, section 5.1.7), for checking downloaded updates.

Only verification, in plain Python: the Windows app bundles no crypto library. Speed doesn't matter here (one check
per update); the message itself is only hashed."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)


def _add(a, b):
    """Points in extended coordinates (X, Y, Z, T)."""
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    e = (y1 - x1) * (y2 - x2) % P
    f = (y1 + x1) * (y2 + x2) % P
    g = 2 * t1 * t2 * D % P
    h = 2 * z1 * z2 % P
    e, f, g, h = f - e, h - g, h + g, f + e
    return e * f % P, g * h % P, f * g % P, e * h % P


def _multiply(scalar, point):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % P == 0 and (a[1] * b[2] - b[1] * a[2]) % P == 0


def _x_from(y, sign):
    if y >= P:
        return None
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if xx == 0:
        return None if sign else 0
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P:
        x = x * SQRT_M1 % P
    if (x * x - xx) % P:
        return None
    return P - x if (x & 1) != sign else x


def _decompress(encoded):
    if len(encoded) != 32:
        return None
    y = int.from_bytes(encoded, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _x_from(y, sign)
    return None if x is None else (x, y, 1, x * y % P)


_BY = 4 * pow(5, P - 2, P) % P
BASE = (_x_from(_BY, 0), _BY, 1, _x_from(_BY, 0) * _BY % P)


def verify(public_key, message, signature):
    """True when signature (64 bytes) is public_key's (32 bytes) signature of message."""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    a = _decompress(public_key)
    r = _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % L
    return _equal(_multiply(s, BASE), _add(r, _multiply(h, a)))
