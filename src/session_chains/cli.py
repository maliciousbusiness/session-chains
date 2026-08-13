import typer
import enum
import asyncio

from typing import Annotated

from .recipe import export_recipe

from .utils import init_project_dir, config_map, rsuccess, validate_in_project_dir, rerror
from .chain import main
from .wizard import start_wizard


app = typer.Typer(no_args_is_help=True)

Configs = enum.Enum("Configs", list(config_map().items()))


def validate_dir_name(dir_name: str):
    if not dir_name:
        raise typer.BadParameter("Please provide a name for your chain")
    return dir_name


@app.command()
@validate_in_project_dir(False)
def init(dir_name: Annotated[str, typer.Argument(
        callback=validate_dir_name, help="The name of your chain")]):
    """
    Creates a new project by creating a new directory in you cwd containing all relevant files.
    """
    config_name = "ginandjuice"
    init_project_dir(config_name, dir_name)
    rsuccess("Project created...")


@app.command()
@validate_in_project_dir(True)
def run():
    """
    Once you configured and checked your chain, this command is used to actually execute the chain.
    """
    asyncio.run(main())


@app.command()
@validate_in_project_dir(True)
def check():
    """
    Checks your chains configuration. Once no errors are found the chain can be executed via the 'run' command.
    """
    asyncio.run(main(dry_run=True))
    export_recipe()


@validate_in_project_dir(True)
def recipe():
    """
    Once the chains is configured and checked for errors, this command will generate the CSTC recipe for you.
    """
    export_recipe()


@app.command()
@validate_in_project_dir(False)
def wizard(dir_name: Annotated[str, typer.Argument(
        callback=validate_dir_name, help="The name of your chain")]):
    """
    This command creates a new project from scratch while guiding you throuhgh to process of configuring you chain.
    """
    if not dir_name:
        rerror("Please provide a name for your project", False)
        typer.Exit(code=1)
    start_wizard(dir_name)
