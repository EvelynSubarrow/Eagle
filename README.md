# Eagle
Flask REST API for Network Rail's SCHEDULE. Originally intended for use by [BitBot](https://github.com/jesopo/bitbot)

## Dependencies
* Python 3.5+
* [Flask](https://pypi.python.org/pypi/Flask)

## Licences
* GPLv3
* `tiploc.json` can be used either under the same GPLv3, or the more restrictive Creative Commons BY-NC-SA, 4.0

## `tiploc.json`
* tiploc.json is based on reference data accessible from Network Rail's open feeds. This project is,
of course, not endorsed by Network Rail.

## Using Eagle
You'll need an email address and password for a Network Rail open data account. You can sign up
[here](https://datafeeds.networkrail.co.uk/ntrod/login).

It can take several days for your account to become active, and you'll have to
specifically add SCHEDULE to your account.

When you have an account, and have added SCHEDULE, you'll need to download it. A snapshot is published
daily at approximately 0600, and `pull.sh.example` is provided to demonstrate how to retrieve this information for
all TOCs. Once you have the JSON schedule, you should run `parse_daily.py`, which will create and populate `schedule.db`.

Once this is done, you'll want to rename `config.json.example` to `config.json`, review the settings, then run `main.py`.

## Additional credits
I wouldn't have been able to put this together without the NROD wiki, maintained by Peter Hicks.

http://nrodwiki.rockshore.net/