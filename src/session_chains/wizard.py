import curses
from curses.textpad import Textbox, rectangle
from dataclasses import asdict, dataclass
from pathlib import Path
import os
import shutil
from typing import Optional
import re
from prompt_toolkit.shortcuts import choice
from prompt_toolkit import prompt
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
import yaml


from session_chains.utils import rerror, rprint, rwarning

bindings = KeyBindings()


def print_header(header: str, separator="-"):
    print(header)
    print(separator * len(header))


@dataclass
class Extractor:
    key: str
    strat: str
    variable: str

    def __str__(self) -> str:
        return f"({self.strat}) {self.variable}: {self.key}"


@dataclass
class Step:
    idx: int
    request: str
    extractors: list[Extractor]

    def print_overview(self):
        print_header(f"\033[1mRequest {self.idx + 1}\033[0m", "#")
        print(self.request)

        print("\n")

        print_header("Extractors")
        if len(self.extractors) == 0:
            print("No extractors defined")
        else:
            for extractor in self.extractors:
                print(f"  - {extractor}")

        print("\n")


@dataclass
class Credential:
    name: str
    variables: dict[str, str]


@dataclass
class Configuration:
    proto: str = "https"
    repeat_after: int = 300
    proxy: Optional[str] = None


def start_wizard(dir_name: str):
    os.system("clear")
    print("""Welcome to the Session-Chains Wizard.

This wizard aims to help you in creating your Session-Chains configuration without manually creating the config files.
It guides you through the several configuration steps and lets you build the entire configuration step-by-step.
At then end, you get an overview of all settings and can change anything before generating the configuration files.

First, configure some general settings for Session-Chains or simply accept the default settings.
""")

    general_configuration = configure_general_configuration()

    credentials = configure_credentials()

    steps = configure_steps()

    while True:
        final_overview(general_configuration, steps, credentials)

        print("\n")

        decision = choice(
            message="Are you happy with the chain or would you like to change something?",
            options=[
                ("generate", "Generate the chain configuration"),
                ("general", "Edit general configuration"),
                ("steps", "Edit steps"),
                ("credentials", "Edit accounts"),
            ]
        )

        match decision:
            case "general":
                os.system("clear")
                general_configuration = configure_general_configuration(
                    general_configuration, is_final_overview=True)
            case "credentials":
                credentials = configure_credentials(
                    credentials, is_final_overview=True)
            case "steps":
                steps = configure_steps(steps, is_final_overview=True)
            case "generate":
                break

    print("Generating session-chain files")
    generate_config(dir_name, general_configuration, steps, credentials)


def configure_general_configuration(
        default_config: Optional[Configuration] = None, is_final_overview: bool = False) -> Configuration:
    if default_config is None:
        configuration = Configuration()
    else:
        configuration = default_config

    while True:
        print("General Settings")
        option = choice(
            message="These are the general settings for a session chain. Change them or accept the default values.",
            options=[
                ("done", "Accept these values and define the accounts" if not is_final_overview else "Back to final overview"),
                ("proto", f"Protocol: {configuration.proto}"),
                ("repeat",
                 f"Chain repeats every {configuration.repeat_after} seconds"),
                ("proxy", f"Proxy: {configuration.proxy}"),
            ]
        )

        match option:
            case "done":
                return configuration
            case "proto":
                os.system("clear")
                print("Protocol")
                print("--------")
                print("This setting defines what protocol your chain is using.")
                print(f"Current value is: {configuration.proto}")
                print()
                protocol = choice("Change the protocol", options=[
                                  ("http", "HTTP"), ("https", "HTTPS")])
                configuration.proto = protocol
            case "repeat":
                os.system("clear")
                print("Repeat After")
                print("------------")
                print(
                    "Set how often your chain should be repeated. This settings is in seconsd.")
                print(f"Current value is {configuration.repeat_after}")
                print()

                while True:
                    try:

                        repeat_after = prompt(
                            "After how many seconds should the chain be executed again? ")
                        repeat_after_int = int(repeat_after)
                        configuration.repeat_after = repeat_after_int
                        break
                    except ValueError:
                        print("Please enter a number")
                        print()

            case "proxy":
                os.system("clear")
                print("Proxy")
                print("-----")
                print(
                    "Define a proxy. Session-Chains will use this proxy when sending requests.")
                print(
                    f"Current value is: {'No proxy set' if configuration.proxy is None else configuration.proxy}")
                print()
                proxy = prompt(
                    "Set the proxy or enter None to disable this: ").lower()
                if proxy == "none" or len(proxy) <= 0:
                    configuration.proxy = None
                else:
                    configuration.proxy = proxy

        os.system("clear")


def configure_steps(default_steps: Optional[list[Step]]
                    = None, is_final_overview=False) -> list[Step]:
    steps: list[Step] = []

    if default_steps is not None:
        steps = default_steps

    skip_overview = False

    while True:
        if not skip_overview:
            os.system("clear")

            options = []

            if is_final_overview is True:
                options.append(("save", "Back to final overview"))

            options.append(("add", "New step"))

            for idx, step in enumerate(steps):
                options.append((idx, f"Edit step {idx + 1}"))

            if len(steps) > 0 and is_final_overview is False:
                options.append(("overview", "Go to final overview"))

            print("""Steps
-----
Configure the individual steps that are executed each time Session-Chains runs the chain.
For each step define the HTTP request and the extractors.
An extractor extracts a value from the response and stores it in a variable that can be used in any following step.
Cookies are automatically extracted and added to each following step.
""")

            action = choice("Configure the Steps", options=options)
        else:
            skip_overview = False

        match action:
            case "add":
                action, step = configure_step(
                    len(steps), is_final_overview=is_final_overview)
                steps.append(step)

                match action:
                    case "overview":
                        pass
                    case "creds":
                        return steps
                    case "add":
                        skip_overview = True
            case "overview":
                return steps
            case "save":
                return steps
            case idx:
                action, step = configure_step(
                    idx, steps[int(idx)], is_final_overview)
                steps[int(idx)] = step

                match action:
                    case "overview":
                        pass
                    case "creds":
                        return steps
                    case "add":
                        skip_overview = True


def draw_request(stdscr, text_lines, step_idx):
    stdscr.clear()
    header = f"Enter Request {step_idx + 1}\n"
    stdscr.addstr(header)
    stdscr.addstr("-" * (len(header) - 1) + "\n")
    stdscr.addstr(
        "Paste the request and mark variables with {{...}}. Enter Ctrl+S to submit the request:\n\n")

    y = 4
    for line in text_lines:
        start = 0
        for match in re.finditer(r"(\{\{.*?\}\})", line):
            # Print normal text before the match
            stdscr.addstr(y, start, line[start:match.start()])
            # Print matched text in red
            stdscr.addstr(y, match.start(),
                          line[match.start():match.end()], curses.color_pair(1))
            start = match.end()
        # Print remainder of line
        stdscr.addstr(y, start, line[start:])
        y += 1
    stdscr.refresh()


def enter_request(stdscr: curses.window, step_idx: int, default_value: Optional[str] = None) -> str:
    curses.curs_set(1)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)

    text_lines = [""]

    if default_value is not None:
        text_lines = default_value.split("\n")

    starting_y, starting_x = 4, 0
    y, x = 0, 0

    draw_request(stdscr, text_lines, step_idx)

    while True:
        stdscr.move(y + starting_y, x + starting_x)
        ch = stdscr.get_wch()

        if ch == '\x13' or ch == "\x07":  # Ctrl+G
            break
        elif ch == '\n' or ch == curses.KEY_ENTER:
            # Split line at x position and break last part into the next part
            line = text_lines[y]

            first = line[:x]
            second = line[x:]

            text_lines[y] = second
            text_lines.insert(y, first)
            y += 1
            x = 0
        elif ch == curses.KEY_BACKSPACE:  # Backspace
            if x > 0:
                line = text_lines[y]
                text_lines[y] = line[:x - 1] + line[x:]
                x -= 1
            elif y > 0:
                prev_line = text_lines.pop(y)
                y -= 1
                x = len(text_lines[y])
                text_lines[y] += prev_line
        elif isinstance(ch, str) and ch.isprintable():
            line = text_lines[y]
            text_lines[y] = line[:x] + ch + line[x:]
            x += 1
        elif ch == curses.KEY_LEFT:
            if x > 0:
                x -= 1
        elif ch == curses.KEY_RIGHT:
            if x < len(text_lines[y]):
                x += 1
        elif ch == curses.KEY_UP:
            if y > 0:
                y -= 1
                x = min(x, len(text_lines[y]))
        elif ch == curses.KEY_DOWN:
            if y < len(text_lines) - 1:
                y += 1
                if y < len(text_lines):
                    x = min(x, len(text_lines[y]))
        elif ch == curses.BUTTON_CTRL:
            line = text_lines[y]
            text_lines[y] = line[:x] + "A" + line[x:]

        draw_request(stdscr, text_lines, step_idx)

    stdscr.clear()
    return "\n".join(text_lines)


def configure_extractors(step: Step) -> list[Extractor]:
    extractors = step.extractors

    while True:
        os.system("clear")
        step.print_overview()

        options = [("new", "Add a new extractor")]

        for idx, extractor in enumerate(extractors):
            options.append((idx, str(extractor)))

        options.append(("exit", "Go back"))

        print("Extractors / Configure the extactors")
        print

        result = choice("Extractors / Configure the extactors",
                        options=options)

        match result:
            case "new":
                os.system("clear")
                step.print_overview()
                print("Extractors / Add a new extractor")
                extractor = add_extractor()
                extractors.append(extractor)
            case "exit":
                break
            case idx:
                extractor = extractors[idx]

                result = edit_extractor(step, extractor)
                if result is None:
                    extractors.pop(idx)

    return extractors


def edit_extractor(step: Step, extractor: Extractor) -> Optional[Extractor]:
    style = Style.from_dict({
        "": "",
        "bold": "bold"
    })

    while True:
        os.system("clear")
        step.print_overview()

        result = choice(
            [("", "Extractors / Edit extractor '"),
             ("class:bold", str(extractor)), ("", "'")],
            style=style,
            options=[
                ("name", "Change the name"),
                ("strat", "Change the strategy"),
                ("key", "Change the extractor value"),
                ("done", "Save Changes"),
                ("delete", "Delete this extractor"),
            ]
        )
        print()

        match result:
            case "delete":
                return None
            case "name":
                new_name = prompt("Enter the new name: ")
                extractor.variable = new_name
            case "strat":
                new_strat = prompt_extractor_strat("Change the strat")
                extractor.strat = new_strat
            case "key":
                new_key = prompt("Enter the new extactor: ")
                extractor.key = new_key
            case "done":
                break

    return extractor


def prompt_extractor_strat(message: str) -> str:
    return choice(
        message,
        options=[("header", "Header"),
                 ("json", "JSON"),
                 ("cssselect", "CSS selector"),
                 ("regex", "Regex")
                 ]
    )


def add_extractor() -> Extractor:
    print()
    name = prompt(" How should the extractor be called? ")
    print()

    strat = prompt_extractor_strat("What strat should be used?")
    print()

    key = prompt(" Write the extractor: ")
    print()

    return Extractor(key, strat, name)


def configure_step(
        step_idx: int, default_step: Optional[Step] = None, is_final_overview: bool = False) -> tuple[str, Step]:
    if default_step is None:
        request = curses.wrapper(
            lambda stdscr: enter_request(stdscr, step_idx))

        step = Step(idx=step_idx, request=request, extractors=[])
    else:
        step = default_step

    while True:
        os.system("clear")
        step.print_overview()

        options = []

        options.append(("edit", "Edit the request"))
        options.append(("extractor", "Configure the extractors"))

        if not is_final_overview:
            options.append(("add", "Add the next step"))
            options.append(
                ("creds", "All steps added? Go to the final overview"))

        options.append(("overview", "Go back to overiew"))

        result = choice(
            message="Configure this step or continue",
            options=options,
        )

        print("\n")

        match result:
            case "edit":
                edited_request = curses.wrapper(
                    lambda stdscr: enter_request(stdscr, step.idx, step.request))
                step.request = edited_request
            case "extractor":
                configure_extractors(step)
            case "add":
                return ("add", step)
            case "creds":
                return ("creds", step)
            case "overview":
                return ("overview", step)


def print_credential_help():
    print("""Accounts
--------
Configure the different accounts you want Session-Chains to use.
Each account defines a set of variables that can be used during the chain execution.
Session-Chain will run the chain for each account and make their session available separately.
""")


def configure_credentials(
        default_credentials: Optional[list[Credential]] = None, is_final_overview=False) -> list[Credential]:
    credentials: list[Credential] = []

    if default_credentials is not None:
        credentials = default_credentials

    while True:
        os.system("clear")

        options = []

        if is_final_overview:
            options.append(("finish", "Back to final overview"))

        options.append(("new", "New account"))

        for idx, credential in enumerate(credentials):
            options.append((idx, f"Edit '{credential.name}'"))

        if len(credentials) > 0 and not is_final_overview:
            options.append(
                ("finish", "All accounts added? Configure the steps next"))

        print_credential_help()

        result = choice(
            message="Manage Accounts",
            options=options,
        )

        match result:
            case "new":
                existing_names = set(map(lambda c: c.name, credentials))
                credential = add_credential(existing_names)
                if credential is not None:
                    credentials.append(credential)
            case "finish":
                break
            case idx:
                existing_names = set(map(lambda c: c.name, credentials))
                edited_creds = edit_credential(
                    credentials[idx], existing_names)
                if edited_creds is None:
                    credentials.pop(idx)

    return credentials


def add_credential(existing_names: set[str]) -> Optional[Credential]:
    print()
    name = prompt("Enter the account name: ")

    while name in existing_names:
        name = prompt("Name already used. Please use another: ")

    credential = Credential(name=name, variables=dict())

    return edit_credential(credential, existing_names)


def edit_credential(credential: Credential, existing_names: set[str]) -> Optional[Credential]:
    while True:
        os.system("clear")
        print_credential_help()

        result = choice(
            f"Accounts / {credential.name}",
            options=[
                ("vars", "Configure the variables"),
                ("name", "Change the name"),
                ("done", "Done"),
                ("delete", "Delete this account"),
            ]
        )

        match result:
            case "delete":
                return None
            case "done":
                break
            case "name":
                print()
                name = prompt("Enter the new name: ")

                while name in existing_names:
                    name = prompt("Name already used. Please use another: ")

                credential.name = name
            case "vars":
                edit_credential_variables(credential)

    return credential


def edit_credential_variables(credential: Credential):
    while True:
        os.system("clear")
        print_credential_help()

        options = [("new", "Add a new variable")]

        for key, value in credential.variables.items():
            options.append((key, f"Edit '{key}: {value}'"))

        options.append(("done", "Go Back"))

        result = choice(
            message=f"Accounts / {credential.name} / Variables",
            options=options,
            key_bindings=bindings,
        )

        match result:
            case "new":
                print()
                key = prompt("Enter the key: ")
                while key in credential.variables:
                    key = prompt("Variable already exists. Use another key: ")

                value = prompt("Enter the value: ")

                credential.variables[key] = value
            case "done":
                break
            case key:
                edit_credential_variable(credential, key)


def edit_credential_variable(credential: Credential, key: str):
    variables = credential.variables

    while True:
        os.system("clear")
        print_credential_help()

        result = choice(
            f"Accounts / {credential.name} / Variables / {key}",
            options=[
                ("done", "Go Back"),
                ("key", f"Change key ({key})"),
                ("value", f"Change value ({variables[key]})"),
                ("delete", "Delete variable")
            ]
        )

        match result:
            case "done":
                break
            case "key":
                print()
                new_key = prompt("Enter the new key: ")
                while new_key in variables:
                    new_key = prompt(
                        "Variable already exists. Use a different key: ")

                variables[new_key] = variables[key]
                del variables[key]
                key = new_key
            case "value":
                print()
                new_value = prompt("Enter the new value: ")
                variables[key] = new_value
            case "delete":
                del variables[key]
                return


def final_overview(general_config: Configuration, steps: list[Step], credentials: list[Credential]):
    os.system("clear")
    print("Overview")
    print("--------")

    print(f"Protocol: {general_config.proto}")
    print(f"Repeat after: {general_config.repeat_after} seconds")
    print(
        f"Proxy: {'Not set' if general_config.proxy is None else general_config.proxy}")

    print()
    print()

    print(
        f"In total, your chain consists of {len(steps)} step{'s' if len(steps) > 1 else ''}")
    for idx, step in enumerate(steps):
        print(f" {idx + 1: >2}. Request")

        if len(step.extractors) <= 0:
            print(f"     No extractors")
        else:
            print(f"     Extractors:")

            for extractor in step.extractors:
                print(f"      - {extractor}")

    print("\n")
    print(f"The following accounts are configured:")

    for credential in credentials:
        print(f" - {credential.name}")

        for key, value in credential.variables.items():
            print(f"     {key}: {value}")


def generate_config(dir_name: str, general_config: Configuration,
                    steps: list[Step], credentials: list[Credential]):
    # Create directory structure
    project_dir = Path(dir_name)

    if os.path.exists(project_dir):
        rwarning("The project directory already exists")

        while True:
            decision = prompt("Do you want to overwrite it? [y/n]").lower()
            if decision == "y" or decision == "yes":
                shutil.rmtree(project_dir)
                break
            elif decision == "n" or decision == "no":
                exit(-1)
            else:
                rprint("Not a valid answer")

    os.mkdir(project_dir)

    metadata_path = project_dir / "metadata"
    os.makedirs(metadata_path)

    request_files_path = project_dir / "request_files"
    os.makedirs(request_files_path)

    session_data_path = project_dir / "session_data"
    os.makedirs(session_data_path)

    # Generate the configuration
    config_file_content = {
        "repeat_after": general_config.repeat_after,
        "proto": general_config.proto,
        "proxy": general_config.proxy,
        "requests": [],
    }

    for idx, step in enumerate(steps):
        step_configuration = dict()
        request_name = f"r{idx + 1}.req"
        request_path = request_files_path / request_name

        step_configuration["request_file"] = request_name

        with open(request_path, "x") as request_file:
            request_file.write(step.request)

        if len(step.extractors) > 0:
            step_configuration["extract"] = []

            for extractor in step.extractors:
                step_configuration["extract"].append({
                    "key": extractor.key,
                    "strat": extractor.strat,
                    "variable": extractor.variable,
                })

        config_file_content["requests"].append(step_configuration)

    config_path = project_dir / "config.yaml"
    with open(config_path, "x") as config_file:
        yaml.dump(config_file_content, config_file)

    # Generate the credential file
    creds = list(asdict(cred) for cred in credentials)
    creds_file_path = project_dir / "creds.yaml"
    with open(creds_file_path, "x") as creds_file:
        yaml.dump(creds, creds_file)
