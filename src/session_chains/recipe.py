from session_chains.utils import metadata_path, project_dir, rerror, rwarning, session_data_path, data_dir, config_path, creds_path
from session_chains.config_parser import parse_config
from session_chains.utils import identifier
import json


def static_string_instruction(value):
    instruction = {
        "operation": "de.usd.cstchef.operations.string.StaticString",
        "parameters": {
            "Value": value
        },
        "is_enabled": True,
        "comment": None
    }
    return instruction


def nop_instruction(comment):
    instruction = {
        "operation": "de.usd.cstchef.operations.utils.NoOperation",
        "parameters": {},
        "is_enabled": True,
        "comment": comment
    }
    return instruction


def set_header_instruction(name, value, enabled=True):
    instruction = {
        "operation": "de.usd.cstchef.operations.setter.HttpHeaderSetter",
        "parameters": {
            "checkbox1": True,
            "Value": value,
            "Key": name
        },
        "is_enabled": enabled,
        "comment": None
    }
    return instruction


def set_cookie_instruction(name, value, enabled=True):
    instruction = {
        "operation": "de.usd.cstchef.operations.setter.HttpSetCookie",
        "parameters": {
            "checkbox1": True,
            "Value": value,
            "Key": name
        },
        "is_enabled": enabled,
        "comment": None
    }
    return instruction


def read_file_instruction(basepath, filepath):
    instruction = {
        "operation": "de.usd.cstchef.operations.misc.ReadFile",
        "parameters": {
            "Base path": str(basepath),
            "Filename": str(filepath),
            "button1": None
        },
        "is_enabled": True,
        "comment": None
    }
    return instruction


def strip_instruction():
    instruction = {
        "operation": "de.usd.cstchef.operations.string.Strip",
        "parameters": {
            "Strip at: ": "Both"
        },
        "is_enabled": True,
        "comment": None
    }
    return instruction


def store_variable_instruction(name):
    instruction = {
        "operation": "de.usd.cstchef.operations.utils.StoreVariable",
        "parameters": {
            "Variable name": name
        },
        "is_enabled": True,
        "comment": None
    }
    return instruction


def export_recipe():
    p_dir = project_dir()
    recipe_path = data_dir() / "recipe.json"
    creds = parse_config(creds_path(p_dir))
    config = parse_config(config_path(p_dir))
    metadata_dir = metadata_path(p_dir)
    with open(recipe_path, 'r') as f:
        recipe = json.load(f)
    for entry in creds:
        recipe[1][0].append(static_string_instruction(entry["name"]))
    p_session = session_data_path(p_dir)

    recipe[1][1].append(read_file_instruction(
        metadata_dir, metadata_dir / "colors" / "$color"))
    recipe[1][1].append(strip_instruction())
    recipe[1][1].append(store_variable_instruction("role"))

    cookie_names = set()
    for p_cookie in p_session.glob("*/cookies"):
        p_cookie_names = [p.name for p in p_cookie.iterdir() if p.is_file()]
        cookie_names = cookie_names.union(p_cookie_names)
    for p_user in p_session.iterdir():
        cookie_dir = p_user / "cookies"
        cookie_dir.mkdir(exist_ok=True, parents=True)
        for cookie_name in cookie_names:
            if not (cookie_dir / cookie_name).exists():
                with open(cookie_dir / cookie_name, "w") as f:
                    f.write("DOESNOTEXIST")
    for cookie_name in cookie_names:
        read = read_file_instruction(
            p_session, p_session / "$role" / "cookies" / cookie_name)
        strip = strip_instruction()
        variable_name = identifier(f"cookiejar_{cookie_name}")
        store = store_variable_instruction(variable_name)
        set_cookie = set_cookie_instruction(cookie_name, f"${variable_name}")
        recipe[1][3].append(read)
        recipe[1][3].append(strip)
        recipe[1][3].append(store)
        recipe[1][4].append(set_cookie)
    for request in config["requests"]:
        if "extract" not in request:
            continue
        for entry in request["extract"]:
            if "expose" not in entry:
                if len(cookie_names) == 0:
                    rwarning(
                        f"The request {request['request_file']} does not expose a variable. This might be intended as Cookies are automatically exposed. For all other variables, double check your config.")
                continue
            variable = entry["variable"]
            read = read_file_instruction(p_session, p_session / "$role" / variable)
            strip = strip_instruction()
            store = store_variable_instruction(identifier(variable))
            recipe[1][3].append(read)
            recipe[1][3].append(strip)
            recipe[1][3].append(store)
            expose_location = entry["expose"]["location"].lower()
            variable_name = identifier(variable)
            if expose_location == "cookie":
                expose_name = entry["expose"]["name"]
                instruction = set_cookie_instruction(
                    expose_name, f"${variable_name}")
            elif expose_location == "header":
                expose_name = entry["expose"]["name"]
                instruction = set_header_instruction(
                    expose_name, f"${variable_name}")
            elif expose_location == "bearer":
                instruction = set_header_instruction(
                    "Authorization", f"Bearer ${variable_name}")
            else:
                rerror("Empty or invalid expose section. Remove or specify location!")
            recipe[1][4].append(instruction)

    with open(p_dir / "recipe.cstc", 'w') as f:
        json.dump(recipe, f)
