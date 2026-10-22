#!/usr/bin/env python
"""Seed employee logins with their current company employments, and deliver them.

Requires seed_companies.py. Includes an employee of two companies, one with no
current company and one inactive (former) employee. Idempotent: an existing
employee's employments are left as they are.

Usage::

    poetry run python scripts/seed_employees.py
"""

import sys

import _bootstrap


def main():
    _bootstrap.setup()
    from directory import demo

    print("Employees:")
    try:
        events = demo.seed_employees()
    except demo.MissingDependency as error:
        sys.exit(f"  {error}")
    _bootstrap.deliver_and_report(events)


if __name__ == "__main__":
    main()
