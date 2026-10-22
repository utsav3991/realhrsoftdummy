#!/usr/bin/env python
"""Create the ``admin`` superuser (password in directory/demo.py). Idempotent.

Usage::

    poetry run python scripts/seed_admin.py
"""

import _bootstrap


def main():
    _bootstrap.setup()
    from directory import demo

    created = demo.seed_admin()
    print("Superuser admin " + ("created." if created else "already exists."))


if __name__ == "__main__":
    main()
