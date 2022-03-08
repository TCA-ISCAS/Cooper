import __builtin__ as builtins
import sys

bytes_type = type(bytes()) # Works the same in Python 2.X and 3.X
string_type = getattr(builtins, "unicode", str)
int_types = (int, long) if sys.version_info[0] < 3 else (int,)

WHITESPACES = [' ', '\n', '\r', '\t', '\x00']

class PdfPaserError(Exception):
    pass

class PdfCannotDecrypted(Exception):
    pass

class PdfReadError(PdfPaserError):
    pass

class PdfStreamError(PdfPaserError):
    pass

class PdfReadWarning(UserWarning):
    pass

class PdfStreamWarning(UserWarning):
    pass


def u_(s):
    return unicode(s, 'unicode_escape')


def RC4_encrypt(key, plaintext):
    S = [i for i in range(256)]
    j = 0
    for i in range(256):
        j = (j + S[i] + ord(key[i % len(key)])) % 256
        S[i], S[j] = S[j], S[i]
    i, j = 0, 0
    retval = []
    for x in range(len(plaintext)):
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        t = S[(S[i] + S[j]) % 256]
        retval.append(chr(ord(plaintext[x]) ^ t))
    return "".join(retval)



def hexencode(b):
    return b.encode('hex')


def hexStr(num):
    return hex(num).replace('L', '')


def skipOverWhitespace(stream):
    """
    Similar to readNonWhitespace, but returns a Boolean if more than
    one whitespace character was read.
    """
    tok = WHITESPACES[0]
    cnt = 0
    while tok in WHITESPACES:
        tok = stream.read(1)
        cnt += 1
    return cnt > 1

def readNonWhitespace(stream):
    """
    Finds and reads the next non-whitespace character (ignores whitespace).
    """
    tok = WHITESPACES[0]
    while tok in WHITESPACES:
        tok = stream.read(1)
    return tok



def readUntilWhitespace(stream, maxchars=None):
    """
    Reads non-whitespace characters and returns them.
    Stops upon encountering whitespace or when maxchars is reached.
    """
    txt = ""
    while True:
        tok = stream.read(1)
        if tok.isspace() or not tok:
            break
        txt += tok
        if len(txt) == maxchars:
            break
    return txt


def readUntilRegex(stream, regex, ignore_eof=False):
    """
    Reads until the regular expression pattern matched (ignore the match)
    Raise PdfStreamError on premature end-of-file.
    :param bool ignore_eof: If true, ignore end-of-line and return immediately
    """
    name = ''
    while True:
        tok = stream.read(16)
        if not tok:
            # stream has truncated prematurely
            if ignore_eof == True:
                return name
            else:
                raise PdfStreamError("Stream has ended unexpectedly")
        m = regex.search(tok)
        if m is not None:
            name += tok[:m.start()]
            stream.seek(m.start()-len(tok), 1)
            break
        name += tok
    return name


def skipOverComment(stream):
    tok = stream.read(1)
    stream.seek(-1, 1)
    if tok == '%':
        while tok not in ('\n', '\r'):
            tok = stream.read(1)


def paethPredictor(left, up, up_left):
    p = left + up - up_left
    dist_left = abs(p - left)
    dist_up = abs(p - up)
    dist_up_left = abs(p - up_left)

    if dist_left <= dist_up and dist_left <= dist_up_left:
        return left
    elif dist_up <= dist_up_left:
        return up
    else:
        return up_left
