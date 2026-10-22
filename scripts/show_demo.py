#!/usr/bin/env python
"""Print the demo logins, companies and RealHRSoft UUIDs.

Usage::

    poetry run python scripts/show_demo.py
"""

import _bootstrap


def main():
    _bootstrap.setup()
    from directory import demo

    print("\n".join(demo.describe()))


if __name__ == "__main__":
    main()
