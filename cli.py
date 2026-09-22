#!/usr/bin/env python3
"""
ReadyDesk CLI — run the confidence gate against the 3 sample applications
and print routing decisions.

Usage:
    python cli.py
"""

import sys

from confidence_gate import TEST_APPLICATIONS, confidence_gated_response, format_result


def main():
    for name, app in TEST_APPLICATIONS.items():
        result = confidence_gated_response(app)
        print(format_result(name, app, result))
        print()


if __name__ == "__main__":
    sys.exit(main())
