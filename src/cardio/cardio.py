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

    def get_shell(self, prefix: str = "") -> None:
        """
        Retrieve eic-shell based on
        container + version specified
        in card.

        Arguments:
            prefix: file path to install shell and script to

        Raises:
            KeyError: if card has no 'eic_shell', 'container',
                      or 'version' keys in it.
        """
        if "eic_shell" not in self.data:
            raise KeyError("Key 'eic_shell' not found in card data! Please add before retrieving shell")

        contain = self.data["eic_shell"]["container"]
        version = self.data["eic_shell"]["version"]

        # create args to run install script with
        args = f"-c {contain} -v {version}"
        if prefix != "":
            args += f" -p {prefix}"

        # retrieve and run installation
        os.system("wget --output-document install.sh https://get.epic-eic.org --no-check-certificate")
        os.system(f"bash install.sh {args}")
        os.remove("install.sh")

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
