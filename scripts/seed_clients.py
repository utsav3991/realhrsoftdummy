#!/usr/bin/env python
"""Seed the client groups and their HR users, and deliver the client snapshots.

Acme Group (HR: gita) and Himalaya Holdings (HR: anil, rita). Each client's first HR
user is its contact person, whom the Marketplace invites as client admin. HR users
sign in to /admin/ and see only their own client. Idempotent.

Usage::

    poetry run python scripts/seed_clients.py
"""

import _bootstrap


def main():
    _bootstrap.setup()
    from directory import demo

    print("Clients and client HR users:")
    _bootstrap.deliver_and_report(demo.seed_clients())


if __name__ == "__main__":
    main()
