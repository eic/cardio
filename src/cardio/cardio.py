"""cardio -- example data card processing

A simple module to facilitate processing data cards
during a snakemake workflow.

Attributes:
    code_representer (function): custom yaml
        representer to enforce codeblock
        formatting
    CodeDumper (class): custom yaml dumper
        for codeblocks
    Card (class): wrapper class to hold and access
        data from loaded data card
    load_card (function): instantiate a Card
        object from data card at provided path
    make_card (function): create a data card
        based on a provided template and
        instantiate Card object from it
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
import datetime
import os
import re
import yaml


def code_representer(dumper, data):
    """
    Custom YAML representer to preserve
    literal block formatting of code
    snippets.
    """
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

class CodeDumper(yaml.Dumper):
    pass

CodeDumper.add_representer(str, code_representer)


@dataclass
class Card:
    """
    A simple wrapper class to hold data loaded
    from an input data card

    Attributes:
        data: data from the data card
        code_keywords: keywords identifying
            codeblocks in card data

    Interface:
        dump_files:    dump filepaths to a list
        dump_commands: dump commands to bash scripts
    """
    data: Dict[str, Any] = field(default_factory=dict)

    # keywords identifying code blocks
    # in card data
    CODE_KEYWORDS = {'configuration', 'workflow'}

    def __init__(self, path: str = None):
        """
        Initialize with a card at `path`.

        Arguments:
            path: path to card
        """
        if path is not None:
            with open(Path(path), 'r') as card:
                self.data = yaml.safe_load(card)
        else:
            self.data = {}

    def __getitem__(self, key: str) -> Any:
        """
        Get card data at 'key'.
        """
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """
        Set card data at 'key'.
        """
        self.data[key] = value

    def create(self, name: str, area: str = None) -> None:
        """
        Create a data card at 'name' and dump
        data to it. Can override 'location'
        entry with 'area' argument.

        Arguments:
            name: path to data card
            area: (optional) path to override
                  'location' entry with
        """
        card_data = self.data

        # if 'area' provided, set 'location' to it
        if area != None:
            card_data['location'] = area

        # add timestamp and tabulate all files in 'location'
        card_data['timestamp'] = str(datetime.datetime.now())
        card_data['files']     = list()
        for content in Path(card_data['location']).rglob("*"):
            if content.is_file():
                card_data['files'].append(str(content))

        # make sure full path of input card is resolved
        # if provided
        if 'input' in self.data:
            self._resolve_input()

        # sort data into code and non-code
        # (code needs forced literal blocks)
        code_data    = {}
        noncode_data = {}
        for key, value in card_data.items():
            if key in self.CODE_KEYWORDS:
                code_data[key] = value
            else:
                noncode_data[key] = value

        # dump data to output card
        with open(Path(name), 'w') as card:
            yaml.dump(noncode_data, card)
            yaml.dump(code_data, card, Dumper=CodeDumper)

    def dump_files(self, name: str, protocol: str = None) -> None:
        """
        Dump files to a list at 'name'. If
        protocol is 'rucio', will query file
        catalog based on `identifier`.

        Arguments:
            name:     name of file to dump to
            protocol: how to build list of files
        """
        dirname = os.path.dirname(name)
        if dirname != '':
            os.makedirs(dirname, exist_ok=True)
        if protocol == "rucio":
            rucio_did = self.data["identifier"]
            os.system(f"rucio replica list file --protocols root --pfns --rses isopenaccess {rucio_did} > {name}")
        else:
            with open (Path(name), 'w') as files:
                for file in self.data["files"]:
                    files.write(file + "\n")

    def dump_rules(self, rules_name: str, config_name: str = None) -> None:
        """
        Dump workflow rules to snakemake
        file.

        Arguments:
            rules_name:  name of file to dump rules to
            config_name: (optional) name of file to dump config to

        Raises:
            RuntimeError: if card has 'config' block in it, but
                          no name provided for file to dump into.
        """
        rules_dir = os.path.dirname(rules_name)
        if rules_dir != '':
            os.makedirs(rules_dir, exist_ok=True)

        # if config present, make sure config file
        # has been passed
        has_config = "configuration" in self.data
        if has_config and (config_name == None):
            raise RuntimeError("config present in data but no config_name provided! Please provide name to dump config to")
        elif has_config:
            config_dir = os.path.dirname(config_name)
            if config_dir != '':
                os.makedirs(config_dir, exist_ok=True)

        with open(rules_name, 'w') as file:
            if has_config:
                file.write(f"configfile: \"{config_name}\"\n\n")
            file.write(f"{self.data['workflow']}")

        if has_config:
            with open(config_name, 'w') as file:
                file.write(f"{self.data['configuration']}")

    def input(self) -> None:
        """
        Load and return input card data.
        """
        return Card(self.data["input"])

    def scrape_snakefile(self, snake_file: str, config_file: str = None) -> None:
        """
        Scrape code from a Snakefile and (optionally)
        a config file, and store in card data.

        Arguments:
            snake_file:  name of Snakefile to scrape
            config_file: (optional) name of config file to scrape

        Raises:
            RuntimeError: if card data already holds
                          'workflow' or 'configuration'
                          block
        """
        if 'workflow' in self.data:
            RuntimeError("Workflow already present in card data! Will not overwrite existing data")
        else:
            with open(Path(snake_file), 'r', encoding='utf-8') as snake:
                self.data['workflow'] = snake.read()

        if config_file != None:
            if 'configuration' in self.data:
                RuntimeError("Configuration already present in card data! Will not overwrite existing data")
            else:
                with open(Path(config_file), 'r') as config:
                    self.data['configuration'] = config.read()

    def _resolve_input(self) -> None:
        """
        Resolve filepath to input card.
        Likely will be handled by DB
        queries in full version.
        """
        self.data["input"] = str(Path(self.data["input"]).resolve())


def load_card(path: str) -> Card:
    """
    Load a data card at 'path'.

    Arguments:
        path: path to the card to load
    """
    return Card(path)


def make_card(path: str, temp: str, area: str = None) -> Card:
    """
    Make a data card at 'path' based
    on template at 'temp'. Can override
    'location' in card with 'area'.

    Arguments:
       path: path to card to make
       temp: path to template card
       area: (optional) output path to query
    """
    output = Card(temp)
    output.create(path, area)
    return Card(path)


def _campaign_run_number(card: Card, visited: set = None) -> int:
    """Find a campaign in the card or its linked input card and encode YYMMR."""
    if visited is None:
        visited = set()

    campaign = card.data.get("campaign")
    if campaign is not None:
        match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d)", str(campaign))
        if match is None:
            raise ValueError(
                f"Campaign must use YY.MM.R format; got {campaign!r}"
            )
        return int("".join(match.groups()))

    identifier = card.data.get("identifier")
    if isinstance(identifier, str):
        match = re.search(r"(?<!\d)(\d{2}\.\d{2}\.\d)(?!\d)", identifier)
        if match is not None:
            return int(match.group(1).replace(".", ""))

    input_path = card.data.get("input")
    if isinstance(input_path, str):
        resolved_input = Path(input_path).expanduser().resolve()
        if resolved_input in visited:
            raise ValueError(f"Cycle detected in input cards at {resolved_input}")
        if resolved_input.is_file():
            visited.add(resolved_input)
            return _campaign_run_number(Card(str(resolved_input)), visited)

    raise ValueError(
        "Could not determine campaign from card: expected a 'campaign' field "
        "or a YY.MM.R value in 'identifier' or its linked input card"
    )


def store_plot_metadata(
    card: Card,
    plot_type_name: str,
    run_period: str = "/work/eic3/validation/images/campaigns/",
) -> int:
    """
    Store a card's YAML data in Hydra's Plots table for a plot type.

    The plot type must match exactly one row in Plot_Types.Name. The
    frontend can use the matching Plot_Types.Name as the image name and
    Plots.RunPeriod as its directory. The campaign is read from the card's
    ``campaign`` field, its ``identifier``, or a linked input card, and stored
    in Plots.RunNumber as YYMMR. Connection settings are loaded from the
    cardio/.env file and can be overridden with HYDRA_DB_HOST, HYDRA_DB_USER,
    and HYDRA_DB_DATABASE.

    Returns the ID of the inserted Plots row.
    """
    run_number = _campaign_run_number(card)

    import mysql.connector
    from dotenv import load_dotenv

    env_file = os.environ.get(
        "HYDRA_DB_ENV_FILE",
        Path(__file__).resolve().parents[2] / ".env",
    )
    load_dotenv(dotenv_path=env_file)

    connection = mysql.connector.connect(
        host=os.environ.get("HYDRA_DB_HOST", "localhost"),
        user=os.environ.get("HYDRA_DB_USER", "YOUR_USERNAME"),
        database=os.environ.get("HYDRA_DB_DATABASE", "ePIC_Hydra"),
    )
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT ID FROM Plot_Types WHERE Name = %s",
            (plot_type_name,),
        )
        plot_type_ids = cursor.fetchall()
        if len(plot_type_ids) != 1:
            raise ValueError(
                f"Expected exactly one Plot_Types row named "
                f"{plot_type_name!r}; found {len(plot_type_ids)}"
            )

        metadata = yaml.safe_dump(card.data, sort_keys=False).encode("utf-8")
        cursor.execute(
            "INSERT INTO Plots (Plot_Types_ID, RunPeriod, RunNumber, MetaData) "
            "VALUES (%s, %s, %s, %s)",
            (plot_type_ids[0][0], run_period, run_number, metadata),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()
