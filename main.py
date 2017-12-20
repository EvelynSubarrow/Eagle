#!/usr/bin/env python3

import sqlite3, json, datetime, os, math
from collections import OrderedDict, defaultdict, Counter
from datetime import timedelta


import flask, werkzeug
from flask import Response
from flask import request

import tops

class UnauthenticatedException(Exception): pass
AUTH_FAIL = Response(json.dumps({"success": False, "message":"Authentication failure"}, indent=2), mimetype="application/json", status=403)

with open("codes/tiploc.json") as f:
    TIPLOCS = json.load(f)

with open("codes/tocs.json") as f:
    TOCS = json.load(f)

with open("codes/activity.json") as f:
    ACTIVITY = json.load(f)

CODES = {}
for name in os.listdir("codes"):
    with open("codes/%s" % name) as f:
        CODES[name.split(".")[0]] = json.load(f)

with open("config.json") as f:
    config = json.load(f)

app = flask.Flask(__name__)
_database = None

def get_database():
    global _database
    if not _database:
        _database = sqlite3.connect('schedule.db', check_same_thread=False)
        _database.row_factory = sqlite3.Row
    return _database

def format(schedule, date, associations):
    global TIPLOCS, TOCS

    metres = 0
    last_en = None
    for location in schedule["locations"]:
        full = TIPLOCS[location["tiploc"]]
        if full["loc_source"]:
            if last_en:
                metres += int(math.sqrt((last_en[0]-full["easting"])**2 + (last_en[1]-full["northing"])**2))
            last_en = full["easting"], full["northing"]
        location["distance"] = metres
        location["distance_km"] = int(metres/1000)
        
        del location["iid"], location["seq"]
        tiploc = location["tiploc"]
        location["activity_list"] = [a+b for a,b in list(zip(*[iter(location["activity"])]*2)) if (a+b).strip()]
        location["associations"] = associations.get((tiploc, location["tiploc_instance"]), [])
        location["dolphin_times"] = OrderedDict()
        location["dolphin_times"]["sta"] = location.get("arrival_public") or location.get("arrival")
        location["dolphin_times"]["std"] = location.get("departure_public") or location.get("departure") or location.get("pass")
        location["dolphin_times"]["pass"] = location.get("pass")
    return schedule

def rowfor(uid, date, recurse=False):
    c = get_database().cursor()
    c.execute("SELECT * FROM `schedules` WHERE `uid`==? AND ? BETWEEN `valid_from` AND `valid_to` ORDER BY `stp` DESC;", (uid, date))
    all = c.fetchall()
    ret,schedule = None, None
    for schedule in all:
        if schedule["running_days"][date.weekday()] == "1":
            ret = schedule
    if not ret:
        ret = schedule
    if ret:
        ret = OrderedDict(ret)
        ret["operator_name"] = TOCS.get(ret["atoc_code"])
        ret["weekday_match"] = ret["running_days"][date.weekday()] == "1"
        c.execute("SELECT codes.*,locations.* FROM locations LEFT JOIN codes ON locations.tiploc==codes.tiploc WHERE locations.iid==? ORDER BY locations.seq;", [ret["iid"],])
        ret["locations"] = [OrderedDict(a) for a in c.fetchall()]
        ret = format(OrderedDict(ret), date, associations(uid, date, recurse))
    return ret

def associations(uid, date, recurse=False):
    c = get_database().cursor()
    c.execute("SELECT * FROM `associations` WHERE (`uid`==? OR `uid_assoc`==?) AND ? BETWEEN `valid_from` AND `valid_to` ORDER BY `stp` DESC;", (uid, uid, date))
    all = c.fetchall()
    all = [OrderedDict(a) for a in all]
    # Reduce with cancellations topmost, allowing for multiple categories per tiploc
    ret = OrderedDict()
    for assoc in all:
        if assoc["assoc_days"][date.weekday()]=="1":
            ret[(assoc["tiploc"], assoc["suffix"], assoc["category"], assoc["uid"], assoc["uid_assoc"])] = assoc
    ret2 = defaultdict(list)
    # Now let's put all the associations together
    for assoc in ret.values():
        if assoc["stp"]=="C": continue
        assoc["from"] = False
        assoc["relative_indicator"] = assoc["date_indicator"]
        # For the sake of simplicity, uid_assoc will always refer to the service associated (from)/to
        if assoc["uid_assoc"] == uid:
            assoc["uid"], assoc["uid_assoc"] = assoc["uid_assoc"], assoc["uid"]
            # This is a 'from' association. This train was separated from, joined from, or was previous service
            assoc["from"] = True
            assoc["relative_indicator"] = {"S":"S", "N":"P", "P":"N"}[assoc["date_indicator"]]
        # Direction is to indicate whether it's more helpful to indicate the origin as an associated from (VV, NP)
        # Or destination (JJ). Generally, if the association doesn't happen at the terminus or origin of the association,
        # Destination is preferable (and more useful for passengers)
        assoc["direction"] = assoc["from"]
        assoc.update({a:None for a in ["origin_name", "origin_crs", "origin_tiploc", "dest_name", "dest_crs", "dest_tiploc"]})
        if recurse:
            date_rel = date
            if assoc["relative_indicator"]=="N":
                date_rel += timedelta(days=1)
            if assoc["relative_indicator"]=="P":
                date_rel += timedelta(days=-1)
            assoc_sched = rowfor(assoc["uid_assoc"], date_rel, False)
            if assoc_sched:
                locs = assoc_sched["locations"]
                first, last = locs[0], locs[-1]
                assoc["direction"] = last["tiploc"]==assoc["tiploc"]
                far = first if assoc["direction"] else last
                assoc.update({"origin_name": first["name"], "origin_crs": first["crs"], "origin_tiploc": first["tiploc"],
                             "dest_name": last["name"], "dest_crs": last["crs"], "dest_tiploc": last["tiploc"],
                             "far_name": far["name"], "far_crs": far["crs"], "far_tiploc": far["tiploc"]
                    })
        ret2[(assoc["tiploc"], assoc["suffix"])].append(assoc)
    return ret2

def is_authenticated():
    key = request.args.get('key') or request.headers.get('x-eagle-key')
    if config.get("keys"):
        if key in config["keys"]:
            return True
        else:
            return False
    else:
        return True

def schedule_for(uid, date, recurse=False):
        current = rowfor(uid, date, recurse)
        struct = OrderedDict([
            ("success",True),
            ("message", "OK"),
            ("cancelled", current["stp"]=="C"),
            ("tops_inferred", None),("tops_possible",[]),("tops_familiar",None),("tops_image",None),
            ("current",  current),
            ])
        struct.update(tops.infer(current))
        return struct

@app.route('/style')
def style():
    return app.send_static_file('style.css')

@app.route('/logo')
def logo():
    return app.send_static_file('eagle.svg')

def half(time):
    return time.replace("H", "½")

def disambiguate(type, code, multiple=False):
    global CODES
    code = code or ''
    ret = ''
    for segment in code*multiple or [code] or []:
        summary = CODES[type].get(segment)
        if summary:
            ret += '<abbr title="%s">%s</abbr>' % (summary, segment)
        else:
            ret += segment
    return ret

@app.route('/html/schedule/<path:path>/<path:date>')
def html_schedule(path, date):
    global ACTIVITY

    schedule_notes = []
    schedule = None
    message, status = None, 200
    try:
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        if not is_authenticated(): raise UnauthenticatedException()
        schedule = rowfor(path, date, True)
        if not schedule:
            status, message = 404, "UID unknown, or date outside validity"
        else:
            schedule.update(tops.infer(schedule))
            for location in schedule["locations"]:
                location["activity_outlines"] = [ACTIVITY.get(a, {"classes": '', "summary": "unknown"}) for a in location["activity_list"]]
            if not schedule["weekday_match"]:
                schedule_notes.append("This train isn't scheduled to run on the specified weekday")
            if "Q" in schedule["operating_characteristics"]:
                schedule_notes.append("This train only runs as required")
    except ValueError as e:
        status, message = 400, "Invalid date format. Dates must be valid and in ISO 8601 format (YYYY-MM-DD)"
    except UnauthenticatedException as e:
        status, message = 403, "Unauthenticated"
    except Exception as e:
        raise e
        status, message = 500, "Unhandled exception"
    return Response(
        flask.render_template("schedule.html", schedule=schedule, message=message, half=half, disambiguate=disambiguate, notes=schedule_notes),
        status=status,
        mimetype="text/html"
        )

@app.route('/r/<path:path>')
def resource(path):
    return flask.send_from_directory("resources", path, mimetype="image/png")

@app.route('/schedule/<path:path>/<path:date>')
def root(path, date):
    if not is_authenticated(): return AUTH_FAIL
    failure_message = None
    status = 200
    try:
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        struct = schedule_for(path, date, True)
        return Response(json.dumps(struct, indent=2), mimetype="application/json", status=status)
    except ValueError as e:
        status, failure_message = 400, "Invalid date format. Dates must be valid and in ISO 8601 format (YYYY-MM-DD)"
    except Exception as e:
        if not failure_message:
            status, failure_message = 500, "Unhandled exception"
    return Response(json.dumps({"success": False, "message":failure_message}, indent=2), mimetype="application/json", status=status)

@app.route('/summaries/<path:date>')
def summaries(date):
    global TIPLOC
    if not is_authenticated(): return AUTH_FAIL
    status, failure_message = 200, ""
    uids = request.args.get('uids', "")
    uids = uids.split(" ")
    try:
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        out = OrderedDict()
        for uid in uids:
            current = rowfor(uid, date)
            if not current:
                out[uid] = {}
            else:
                out[uid] = OrderedDict([
                    ("cancelled", current["stp"]=="C"),
                    ("atoc_code", current["atoc_code"]),
                    ("power_type", current["power_type"]),
                    ("platforms", OrderedDict(
                        [(a["crs"],a["platform"]) for a in current["locations"] if not a.get("pass") and a["crs"]]
                        )),
                    ])
                out[uid].update(tops.infer(current))
        return Response(json.dumps(out, indent=2), mimetype="application/json", status=200)
            
    except ValueError as e:
        status, failure_message = 400, "Invalid date format. Dates must be valid and in ISO 8601 format"
    except Exception as e:
        if not failure_message:
            status, failure_message = 500, "Unhandled exception"
    return Response(json.dumps({"success": False, "message": failure_message}, indent=2), mimetype="application/json", status=status)

@app.teardown_appcontext
def close_connection(exception):
    global _database
    if _database:
        pass
        #_database.close()

if __name__ == "__main__":
    app.run(config["host"], config["port"], config["debug"], ssl_context=None)
