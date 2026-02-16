"""Main CLI entry point for chaoswopr."""

import click

from chaoswopr import __version__


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """chaoswopr - AI-driven chaos engineering for Ethereum operational resilience testing."""


@main.command()
def version() -> None:
    """Print the version."""
    click.echo(f"chaoswopr {__version__}")


if __name__ == "__main__":
    main()
