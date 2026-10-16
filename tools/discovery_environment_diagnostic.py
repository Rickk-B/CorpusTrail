"""Offline, read-only Python/TLS environment report. No project or network access.

Run with the SAME interpreter used to launch CorpusTrail. Output deliberately
omits paths, proxy URLs, usernames, credentials and certificate contents.
"""
import json
import sys
from corpustrail.application.discovery import offline_environment_report as report


if __name__=='__main__':
    if len(sys.argv)!=1:raise SystemExit('No arguments accepted; this diagnostic is strictly offline.')
    print(json.dumps(report(),indent=2))
