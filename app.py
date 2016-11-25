import functools
import os
import re
from collections import namedtuple
from datetime import datetime, time

from dateutil.parser import parse as parse_datetime

from flask import Flask, jsonify, redirect, render_template, request

from flask_sslify import SSLify

from pyquery import PyQuery

import pytz

import requests


app = Flask(__name__)


Division = namedtuple("Division", ["name", "teams"])
Team = namedtuple("Team", ["name", "mls_code", "shortcode", "subreddit", "espn_url"])

DIVISIONS = [
    Division("West", [
        Team(
            "Colorado Rapids", "colorado-rapids", "COL", "rapids",
            "http://www.espnfc.us/club/colorado-rapids/184/index",
        ),
        Team(
            "FC Dallas", "fc-dallas", "DAL", "FCDallas",
            "http://www.espnfc.com/club/fc-dallas/185/index",
        ),
        Team(
            "Houston Dynamo", "houston-dynamo", "HOU", "dynamo",
            "http://espn.go.com/nba/team/_/name/ny/new-york-knicks",
        ),
        Team(
            "LA Galaxy", "la-galaxy", "LA", "LAGalaxy",
            "http://www.espnfc.com/club/la-galaxy/187/index",
        ),
        Team(
            "Minnesota United FC", "minnesota-united-fc", "MNU", "minnesotaunited",
            "http://www.espnfc.com/club/minnesota-united-fc/17362/index"
        ),
        Team(
            "Portland Timbers", "portland-timbers", "POR", "timbers",
            "http://www.espnfc.com/club/portland-timbers/9723/index"
        ),
        Team(
            "Real Salt Lake", "real-salt-lake", "RSL", "realsaltlake",
            "http://www.espnfc.com/club/real-salt-lake/4771/index"
        ),
        Team(
            "San Jose Earthquakes", "san-jose-earthquakes", "SJ", "SJEarthquakes",
            "http://www.espnfc.com/club/san-jose-earthquakes/191/index"
        ),
        Team(
            "Seattle Sounders FC", "seattle-sounders-fc", "SEA", "SoundersFC",
            "http://www.espnfc.com/club/seattle-sounders-fc/9726/index"
        ),
        Team(
            "Sporting Kansas City", "sporting-kansas-city", "SKC", "sportingkc",
            "http://www.espnfc.com/club/sporting-kansas-city/186/index"
        ),
        Team(
            "Vancouver Whitecaps FC", "vancouver-whitecaps-fc", "VAN", "mkebucks",
            "http://www.espnfc.com/club/vancouver-whitecaps/9727/index"
        ),
    ]),
    Division("East", [
        Team(
            "Atlanta United FC", "atlanta-united-fc", "ATL", "AtlantaUnited",
            "http://www.espnfc.com/club/atlanta-united-fc/17362/index"
        ),
        Team(
            "Chicago Fire", "chicago-fire", "CHI", "chicagofire",
            "http://www.espnfc.com/club/chicago-fire/182/index"
        ),
        Team(
            "Columbus Crew SC", "columbus-crew-sc", "CLB", "TheMassive",
            "http://www.espnfc.com/club/columbus-crew-sc/183/index"
        ),
        Team(
            "D.C. United", "dc-united", "DC", "DCUnited",
            "http://www.espnfc.com/club/dc-united/193/index"
        ),
        Team(
            "Montreal Impact", "montreal-impact", "MTL", "montrealimpact",
            "http://www.espnfc.com/club/montreal-impact/9720/index"
        ),
        Team(
            "New England Revolution", "new-england-revolution", "NE", "NewEnglandRevolution",
            "http://www.espnfc.com/club/new-england-revolution/189/index"
        ),
        Team(
            "New York City FC", "new-york-city-fc", "NYC", "NYCFC",
            "http://www.espnfc.com/club/new-york-city-fc/17606/index"
        ),
        Team(
            "New York Red Bulls", "new-york-red-bulls", "NY", "rbny",
            "http://www.espnfc.com/club/new-york-red-bulls/190/index"
        ),
        Team(
            "Orlando City SC", "orlando-city-sc", "ORL", "OCLions",
            "http://www.espnfc.com/club/orlando-city-sc/12011/index"
        ),
        Team(
            "Philadelphia Union", "philadelphia-union", "PHI", "PhillyUnion",
            "http://www.espnfc.com/club/philadelphia-union/10739/index"
        ),
        Team(
            "Toronto FC", "toronto-fc", "TOR", "TFC",
            "http://www.espnfc.com/club/toronto-fc/7318/index"
        ),
    ]),
]


def get_team(shortcode):
    for div in DIVISIONS:
        for team in div.teams:
            if team.shortcode == shortcode:
                return team
    raise LookupError


@app.route("/")
def home():
    return render_template("home.html", divisions=DIVISIONS)


@app.route("/reddit-stream/")
def reddit_stream():
    if request.referrer is None:
        return (
            "This link works via magic. Click it from the normal comment page."
        )
    target = re.sub("pay.reddit.com", "reddit-stream.com", request.referrer)
    target = re.sub("reddit.com", "reddit-stream.com", target)
    target = re.sub("https://", "http://", target)
    return redirect(target)


MLS_URL = (
    "http://matchcenter.mlssoccer.com/matchcenter/{year}-{month}-{day}"
    "{home.mls-code}-vs-{away.mls-code}/feed"
)


def sub_hours(orig_time, hours):
    return time(orig_time.hour - hours, orig_time.minute).strftime("%I:%M")


def error(msg):
    return jsonify(error=msg)


def handle_errors(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            if sentry is None:
                raise
            sentry.captureException()
            return error(
                "Uh oh. Something went wrong on our end. We've dispatched "
                "trained monkeys to investigate."
            )
    return inner

MLS_RECORD_RE = re.compile(r"\((?P<wins>\d+)-(?P<losses>\d+)\)")


def find_espn_record(team):
    r = requests.get(team.espn_url)
    r.raise_for_status()
    page = PyQuery(r.text)
    text = page("#sub-branding").find(".sub-title").text()
    record = text.split(",", 1)[0]
    return record.split("-")


@app.route("/generate/", methods=["POST"])
@handle_errors
def generate():
    try:
        away = get_team(request.form["away"])
        home = get_team(request.form["home"])
    except LookupError:
        return error("Please select a team.")

    today = pytz.timezone("US/Central").fromutc(datetime.utcnow()).date()
    mls_url = MLS_URL.format(
        year=today.year,
        month=str(today.month).zfill(2),
        day=str(today.day).zfill(2),
        away=away,
        home=home,
    )

    r = requests.get(mls_url)
    if r.status_code == 404 or "Sorry, Page Not Found" in r.text:
        return error(
            "These teams don't seem to be playing each other tonight."
        )
    r.raise_for_status()

    mls_page = PyQuery(r.text)
    info = mls_page("#mlsGIStation").find(".mlsGITime").text()
    if info is None:
        return error("It looks like you reversed the home and the away team.")
    gametime, stadium = info.split("-", 1)
    gametime = parse_datetime(gametime.strip()).time()
    gametimes = {
        "est": sub_hours(gametime, 0),
        "cst": sub_hours(gametime, 1),
        "mst": sub_hours(gametime, 2),
        "pst": sub_hours(gametime, 3),
    }
    stadium = stadium.strip()
    records = mls_page("#mlsGITeamStats thead th")
    home_rec = None
    away_rec = None
    if records and len(records) == 2:
        [away_rec_el, home_rec_el] = records
        match = MLS_RECORD_RE.search(home_rec_el.text_content())
        if match is not None:
            home_rec = match.groups()
        match = MLS_RECORD_RE.search(away_rec_el.text_content())
        if match is not None:
            away_rec = match.groups()

    if home_rec is None:
        home_rec = find_espn_record(home)
    if away_rec is None:
        away_rec = find_espn_record(away)

    r = requests.get(mls_url, allow_redirects=False)
    r.raise_for_status()

    return jsonify(
        title=render_template(
            "title.txt",
            away=away, away_rec=away_rec,
            home=home, home_rec=home_rec,
            today=today),
        body=render_template(
            "gamethread.txt",
            away=away, home=home, tv=", ".join(tvs),
            gametimes=gametimes, stadium=stadium, mls_url=mls_url,
            host=request.host,
        ),
    )


def configure_raven(app):
    if 'SENTRY_DSN' in os.environ:
        import raven
        from raven.contrib.flask import Sentry

        raven.load(os.environ['SENTRY_DSN'], app.config)
        return Sentry(app)

sentry = configure_raven(app)
sslify = SSLify(app, permanent=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
