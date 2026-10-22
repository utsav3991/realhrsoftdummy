#!/usr/bin/env python
"""Seed each client's companies (organizations) and deliver their snapshots.

Requires seed_clients.py. Idempotent.

Usage::

    poetry run python scripts/seed_companies.py
"""

import sys

import _bootstrap


def main():
    _bootstrap.setup()
    from directory import demo

    print("Companies:")
    try:
        events = demo.seed_companies()
    except demo.MissingDependency as error:
        sys.exit(f"  {error}")
    _bootstrap.deliver_and_report(events)


if __name__ == "__main__":
    main()
