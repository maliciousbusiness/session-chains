import pyotp
import urllib.parse
import json


def totp(value):
    t = pyotp.TOTP(value)
    return t.now()


def urlenc(value):
    new_val = urllib.parse.quote_plus(value)
    return new_val


def urldec(value):
    new_val = urllib.parse.unquote(value)
    return new_val


def tojson(value):
    new_val = json.dumps(value)
    return new_val
