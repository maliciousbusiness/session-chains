from rich import print
import sys
import importlib
import inspect
from difflib import get_close_matches
from pathlib import Path
from shutil import copy, copytree
from functools import wraps
from hashlib import sha1
import ast
import subprocess


IO_PREFIX = ""
CONFIG = "config.yaml"
CREDS = "creds.yaml"
SESSIONS_DATA = "session_data"
REQUEST_FILES = "request_files"
METADATA = "metadata"
CUSTOM_FILTERS = "custom_filters.py"
CUSTOM_REQUIREMENTS = "requirements.txt"
REQUIREMENT_MAPPINGS = "requirement_mappings"

# ===============================================================================
# Exceptions
# ===============================================================================


class ChainException(Exception):
    pass


# ===============================================================================
# IO
# ===============================================================================
def rerror(message: str, throw: bool = True):
    print(f"[bold red]{IO_PREFIX}{message}[/bold red]")
    if throw:
        raise ChainException


def rwarning(message: str):
    print(f"[bold yellow]{IO_PREFIX}{message}[/bold yellow]")


def rsuccess(message: str):
    print(f"[bold green]{IO_PREFIX}{message}[/bold green]")


def rprint(message: str):
    print(f"[bold]{IO_PREFIX}{message}[/bold]")


def rprint_list(entries: list):
    for entry in entries:
        print(f"[bold]- {entry}[/bold]")

# ===============================================================================
# Context
# ===============================================================================


class UserContext:
    def __init__(self, role: str, vars: dict[str, str], project_dir: Path):
        self.role = role
        self.vars = vars
        self.dir = project_dir
        self.state = {}  # maybe useful later for custom filters to optionally store ephemeral values

    def get(self, key, default=None):
        return self.vars.get(key, default)

    def set(self, key, value):
        self.vars[key] = value

# ===============================================================================
# Functions
# ===============================================================================


def project_dir() -> Path:
    # Get vault base path
    cwd = Path.cwd()
    if is_project_root(cwd):
        return cwd
    current_dir = cwd
    for i in range(len(cwd.parts) - 1, -1, -1):
        current_dir = Path(*cwd.parts[:i])
        if is_project_root(current_dir):
            return current_dir
    raise ValueError("session-chains project not found")


def is_project_root(path: Path) -> bool:
    return (path / REQUEST_FILES).exists() and (path / "config.yaml").exists()


def data_dir() -> Path:
    return (Path(__file__).resolve().parent) / "data"


def config_map() -> dict[str, Path]:
    config_dir = data_dir() / "configs"
    config_dict = {file.stem: file.resolve() for file in config_dir.iterdir()}
    return config_dict


def init_project_dir(config_name, dir_name):
    project_dir = Path.cwd() / dir_name
    project_dir.mkdir()
    session_dir = session_data_path(project_dir)
    session_dir.mkdir()
    request_files = request_files_path(project_dir)
    request_files.mkdir()
    config = config_map()[config_name]
    copy(config, config_path(project_dir))
    copy(data_dir() / "creds.yaml", creds_path(project_dir))
    copytree(data_dir() / "requests",
             request_files_path(project_dir), dirs_exist_ok=True)
    copy(data_dir() / "filters/custom_filters.py", cf_py_path(project_dir))
    copy(data_dir() / "filters/requirements.txt", cf_reqs_path(project_dir))
    copy(data_dir() / "filters/requirement_mappings", cf_req_mappings(project_dir))


def config_path(project_dir):
    return project_dir / CONFIG


def creds_path(project_dir):
    return project_dir / CREDS


def metadata_path(project_dir):
    return project_dir / METADATA


def session_data_path(project_dir):
    return project_dir / SESSIONS_DATA


def request_files_path(project_dir):
    return project_dir / REQUEST_FILES


def cf_py_path(project_dir):
    return project_dir / CUSTOM_FILTERS


def cf_reqs_path(project_dir):
    return project_dir / CUSTOM_REQUIREMENTS


def cf_req_mappings(project_dir):
    return project_dir / REQUIREMENT_MAPPINGS


def identifier(value):
    # return value.replace('-', '_')
    return str(sha1(value.encode("utf-8")).digest()[:8].hex())

# ===============================================================================
# Manage Dependencies
# ===============================================================================


def _sha1(path: Path) -> str:
    return sha1(path.read_bytes()).hexdigest()


def _std_mods():
    try:
        return sys.stdlib_module_names
    except AttributeError:
        import sysconfig
        import pathlib
        import pkgutil
        stdlib_path = pathlib.Path(sysconfig.get_paths()['stdlib'])
        return {p.name for p in stdlib_path.iterdir() if p.is_dir()}


def _map_requirements(project_dir: Path, req) -> set[str]:
    req_mapping_file = Path(cf_req_mappings(project_dir))
    with open(req_mapping_file, "r") as f:
        mappings = dict(line.strip().split(":") for line in f)
    if req in mappings:
        return mappings[req]
    else:
        return req


def _missing_requirements(project_dir: Path) -> set[str]:
    cf = Path(cf_py_path(project_dir))
    tree = ast.parse(cf.read_text())
    wanted = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                wanted.add(_map_requirements(
                    project_dir, n.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.module:
            wanted.add(_map_requirements(
                project_dir, node.module.split(".")[0]))
    wanted -= _std_mods()
    wanted.remove("session_chains")
    missing = set()
    for name in wanted:
        if importlib.util.find_spec(name) is None:
            missing.add(name)
    return missing


def ensure_dependencies(ctx: UserContext):
    req_file = Path(cf_reqs_path(ctx.dir))
    missing = _missing_requirements(ctx.dir)
    if not missing:
        return  # nothing to do

    existing = {line.strip().split("==")[0]
                for line in req_file.read_text().splitlines()}
    new_pkgs = sorted(missing - existing)
    if new_pkgs:
        with req_file.open("a") as f:
            for pkg in new_pkgs:
                confirmation = input(
                    f"Do you want to add {pkg} to your requirements.txt? (y/n) ")
                if confirmation.lower() == "y":
                    print(f"Adding {pkg} to requirements.txt")
                    f.write(pkg + "\n")
                else:
                    confirmation2 = input(
                        f"Do you want to edit the package name {pkg} before adding it? (y/n) ")
                    if confirmation2.lower() == "y":
                        pkg_corrected = input(
                            "Please enter the edited package name: ")
                        print(f"Adding {pkg_corrected} to requirements.txt")
                        f.write(pkg_corrected + "\n")

    # hash compare
    deps_hash_path = Path(ctx.dir / ".deps_hash")
    new_hash = _sha1(req_file)
    if deps_hash_path.exists() and deps_hash_path.read_text() == new_hash:
        return  # deps already satisfied

    # install / inject
    try:
        subprocess.check_call(
            ["pipx", "inject", "session-chains", "-r", str(req_file)]
        )
    except subprocess.CalledProcessError as e:
        rerror(
            f"Dependency installation failed (exit {e.returncode})", throw=False)
        return

    deps_hash_path.write_text(new_hash)


# ===============================================================================
# Filters
# ===============================================================================
_custom_module_cache = {}


def _get_filter_module(project_dir: Path):
    if project_dir not in _custom_module_cache:
        sys.path.insert(0, str(project_dir))
        try:
            _custom_module_cache[project_dir] = importlib.import_module(
                "custom_filters")
        except ModuleNotFoundError as e:
            _custom_module_cache[project_dir] = None
    custom_mod = _custom_module_cache[project_dir]
    builtins_mod = importlib.import_module("session_chains.filters")
    return custom_mod, builtins_mod


def available_filter_names(ctx) -> list[str]:
    custom_mod, builtins_mod = _get_filter_module(ctx.dir)

    def _names(mod):
        if not mod:
            return set()
        return {
            n for n, obj in inspect.getmembers(mod, inspect.isfunction)
            if not n.startswith("_")
        }

    names = _names(custom_mod) | _names(builtins_mod)
    return sorted(names)


def load_filter(name: str, ctx: UserContext):
    ensure_dependencies(ctx)
    custom_mod, builtins_mod = _get_filter_module(ctx.dir)
    func = None
    if custom_mod and hasattr(custom_mod, name):
        func = getattr(custom_mod, name)
    elif hasattr(builtins_mod, name):
        func = getattr(builtins_mod, name)

    if func is None:
        close_matches = get_close_matches(name, available_filter_names(ctx))
        rerror(
            f"Transformation '{name}' not found in built-in or custom filters", throw=False)
        if close_matches:
            rerror(
                f"Typo? Check filters with similar names: {','.join(close_matches)}")
        raise ChainException

    param_count = len(inspect.signature(func).parameters)
    if param_count == 1:
        return lambda val: func(val)
    elif param_count == 2:
        return lambda val: func(val, ctx)
    else:
        rerror(f"Transformation '{name}' has unsupported signature")

# ===============================================================================
# Decorators
# ===============================================================================


def validate_in_project_dir(required: bool = True):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                project_dir()
            except BaseException:
                if required:
                    rerror(
                        "CWD not inside existing session-chains project. Aborting...", throw=False)
                    return
                else:
                    return func(*args, **kwargs)
            if not required:
                rerror(
                    "This command cannot be executed from within session-chains project. Aborting...", throw=False)
                return
            return func(*args, **kwargs)
        return wrapper
    return decorator
