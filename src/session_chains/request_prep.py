import re

from .utils import ChainException, UserContext, rerror, load_filter
from difflib import get_close_matches
from http import cookies


def transform_http(raw_request, ctx: UserContext) -> str:
    request = raw_request
    if "HTTP/1.0" in raw_request:
        request = request.replace("HTTP/1.0", "HTTP/1.1")
    if "HTTP/2" in raw_request:
        request = request.replace("HTTP/2", "HTTP/1.1")
    return request


def transform_content_length(raw_request, ctx: UserContext):
    request = raw_request
    request = re.sub(r'(Content-Length:\s*)\d+', r'\g<1>1000000', request)
    return request


def transform_variables(raw_request, ctx: UserContext):
    request = raw_request
    matches = re.findall(r"\{\{(.*?)\}\}", request)
    for entry in matches:
        t_names = []
        match = entry
        if '|' in entry:
            parts = entry.split('|')
            match = parts[0].strip()
            t_names = [t_name.strip() for t_name in parts[1:]]
        if match in ctx.vars:
            replacement = ctx.vars[match]
            for name in t_names:
                f = load_filter(name, ctx)
                replacement = f(replacement)
            request = request.replace(f"{{{{{entry}}}}}", replacement)
        else:
            close_matches = get_close_matches(match, ctx.vars.keys())
            rerror(
                f"Trying to replace '{match}' without valid value.", throw=False)
            if close_matches:
                rerror(
                    f"Typo? Check for requests and variables with similar names: {','.join(close_matches)}")
            raise ChainException
    return request


def transform_new_line(raw_request: str, ctx: UserContext):
    request = raw_request.replace("\n", "\r\n")
    return request


def prepare_raw_request(raw_request: str, ctx: UserContext) -> str:
    request = raw_request
    request = transform_http(request, ctx)
    request = transform_content_length(request, ctx)
    request = transform_variables(request, ctx)
    request = transform_new_line(request, ctx)
    return request


def prepare_headers(raw_headers, server_set_cookies):
    headers = raw_headers
    raw_cookies = {}
    if "Cookie" in headers:
        raw_cookies = headers["Cookie"]
    c = cookies.SimpleCookie()
    c.load(raw_cookies)
    for key, value in server_set_cookies.items():
        clean_value = value.strip('"')
        c[key] = clean_value
    headers["Cookie"] = c.output(header="", sep=';').strip()
    headers["X-Ignore-Chain"] = "True"
    return headers
