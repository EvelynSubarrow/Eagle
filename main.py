#!/usr/bin/env python3

import sqlite3, json, datetime
from collections import OrderedDict, defaultdict, Counter
import flask
from flask import Response
from flask import request

#ATOC, power, speed, timing load, "train class" (reservation availability)
TOPS_INFERENCES = OrderedDict([
    (("VT", "EMU", "125", "390", None), ("390", ["390"])),
    (("LO", "EMU", "075", "375", None), ("378", ["378"])),
    (("LO", "EMU", "075", "313", None), ("378", ["378"])),
    (("LO", "EMU", None , "315", None), ("315", ["315"])),
    (("LO", "EMU", None , "317", None), ("317", ["317"])),
    (("XR", "EMU", None , "315", None), ("315", ["315"])),
    (("SR", "EMU", None , "0",   None), ("380", ["380"])),
    (("LM", "EMU", None , "350", None), ("350", ["350"])),
    (("LM", "EMU", None , "323", None), ("323", ["323"])),
    (("ME", "EMU", None , None , None), ("507..508", ["507", "508"])),
    (("SE", "EMU", None , "395", None), ("395", ["395"])),

    ((None, "EMU", None , "321", None), ("321", ["321"])), #LE
    ((None, "EMU", None , "357", None), ("357", ["357"])), #LE
    ((None, "EMU", None , "483", None), ("483", ["483"])), #IL
    ((None, "HST", None , None , None), ("43", ["43"])), #HST means IC125 in practice. 225s are 'E'

    #SW EMUs can only be distinguished by seating classes, which is fine
    (("SW", "EMU", None , None,  "S"), ("455/456/458/707", ["455", "456", "458", "707"])),
    (("SW", "EMU", None , None,  "B"), ("444/450/458", ["444", "450", "458"])),

    #HX only properly indicates class for HXX(2/3)-HAF(4) 360/2 services
    (("HX", "EMU", None , "360", None), ("360", ["360"])),
    (("HX", "EMU", None ,  None, None), ("332", ["332"])),

    #NT doesn't operate any 143s, so exclude
    (("NT", "DMU", None , "A", None),   ("142/144", ["142", "144"])),

    #GW only operates class 143 pacers
    (("GW", "DMU", None , "A", None),   ("143", ["143"])),

    #EM operates only two "high speed" classes. 222 *should* be DEM but whatever
    (("EM", "DMU", "125", None, None),   ("222", ["222"])),

    #GR (VTEC)'s only 'E' locos *must* be IC225s
    (("GR", "E",   "125" , None, None), ("91", ["91"])),

    #Non-TOC-specific DMU ranges
    ((None, "DMU", None , "A", None),   ("142..144", ["142", "143", "144"])),
    ((None, "DMU", None , "E", None),   ("158/168/170/175", ["158", "168", "170", "175"])),
    ((None, "DMU", None , "N", None),   ("165", ["165"])),
    ((None, "DMU", None , "S", None),   ("150/153/155/156", ["150", "153", "155", "156"])),
    ((None, "DMU", None , "T", None),   ("165/1..166", ["165", "166"])),
    ((None, "DMU", None , "V", None),   ("220..221", ["220", "221"])),
    ((None, "DMU", None , "X", None),   ("158..159", ["158", "159"])),
    ])

AUTH_FAIL = Response(json.dumps({"success": False, "message":"Authentication failure"}, indent=2), mimetype="application/json", status=403)

with open("tiploc.json") as f:
    TIPLOCS = json.load(f)

with open("config.json") as f:
    config = json.load(f)

app = flask.Flask(__name__)
_database = None

def get_database():
    global _database
    if not _database:
        _database = sqlite3.connect('schedule.db', check_same_thread=False)
    return _database

def infer_tops(current):
    segment = current["schedule_segment"]
    tuple = (current["atoc_code"], segment["CIF_power_type"], segment["CIF_speed"],
        segment["CIF_timing_load"], segment["CIF_train_class"])
    for k,v in TOPS_INFERENCES.items():
        if all([not y or x==y for x,y in zip(tuple, k)]):
            return v
    return (None, [])

def format(schedule, date, associations):
    global TIPLOC
    schedule = order(schedule)
    tiploc_count = Counter()
    for location in schedule["schedule_segment"]["schedule_location"]:
        tiploc = location["tiploc_code"]
        tiploc_count[tiploc] += 1
        location["associations"] = associations.get((tiploc, tiploc_count[tiploc]))
        #location["crs"], location["stanox"] = None, None
        tiploc = location["tiploc_code"]
        if tiploc in TIPLOCS:
            location.update(TIPLOCS[tiploc])
        location["dolphin_times"] = OrderedDict()
        location["dolphin_times"]["sta"] = location.get("public_arrival") or location.get("arrival")
        location["dolphin_times"]["std"] = location.get("public_departure") or location.get("departure") or location.get("pass")
        location["dolphin_times"]["pass"] = location.get("pass")
    return schedule

def order(schedule):
    sched_recursed = [(k,order(v) if isinstance(v, dict) else v) for k,v in schedule.items()]
    schedule = OrderedDict(
        sorted(sched_recursed, key=lambda x: {list: "zzzy" + x[0], dict: "zzzz" + x[0], OrderedDict: "zzzz" + x[0]}.get(type(x[1]), x[0]))
        )
    return schedule

def rowsfor(uid, date):
    c = get_database().cursor()
    c.execute("SELECT `entry` FROM `schedules` WHERE uid==? AND ? BETWEEN `valid_from` AND `valid_to` ORDER BY `stp` DESC;", (uid, date))
    all = c.fetchall()
    all = [format(json.loads(a[0], object_pairs_hook=OrderedDict), date, associations(uid, date)) for a in all]
    return all

def associations(uid, date):
    c = get_database().cursor()
    c.execute("SELECT * FROM `associations` WHERE (`uid`==? OR `uid_assoc`=='asd') AND ? BETWEEN `valid_from` AND `valid_to` ORDER BY `stp` DESC;", (uid, date))
    all = c.fetchall()
    all = [OrderedDict([(k,v) for k,v in zip(["uid", "uid_assoc", "stp", "valid_from", "valid_to", "assoc_days", "date_indicator", "category", "tiploc", "suffix", "suffix_assoc"], a)]) for a in all]
    ret = defaultdict(list)
    for assoc in all:
        ret[(assoc["tiploc"], int(assoc["suffix"] or "1"))].append(assoc)
    return ret

def is_authenticated():
    key = request.args.get('key') or request.headers.get('x-eagle-key')
    if config.get("keys"):
        if key in config["keys"]:
            return True
        else:
            return False
    else:
        return True

@app.route('/schedule/<path:path>/<path:date>')
def root(path, date):
    if not is_authenticated(): return AUTH_FAIL
    failure_message = None
    status = 200
    try:
        #validate date
        datetime.datetime.strptime(date, "%Y-%m-%d")

        all = rowsfor(path, date)
        current = [a for a in all if a["CIF_stp_indicator"]!="C"][-1]
        struct = OrderedDict([
            ("success",True),
            ("message", "OK"),
            ("rows", len(all)),
            ("cancelled", "C" in [a["CIF_stp_indicator"] for a in all]),
            ("tops_inferred", infer_tops(current)[0]),
            ("current",  current),
            ("entries",  all),
            ])
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
        datetime.datetime.strptime(date, "%Y-%m-%d")
        out = OrderedDict()
        for uid in uids:
            entries = rowsfor(uid, date)
            if not entries:
                out[uid] = {}
            else:
                current = [a for a in entries if a["CIF_stp_indicator"]!="C"][-1]
                out[uid] = OrderedDict([
                    ("cancelled", "C" in [a["CIF_stp_indicator"] for a in entries]),
                    ("tops_inferred", infer_tops(current)[0]),
                    ("tops_possible", infer_tops(current)[1]),
                    ("atoc_code", current["atoc_code"]),
                    ("power_type", current["schedule_segment"]["CIF_power_type"]),
                    ("platforms", OrderedDict(
                        [(TIPLOCS[a["tiploc_code"]]["crs"],a["platform"]) for a in current["schedule_segment"]["schedule_location"] if not a.get("pass") and a["tiploc_code"] in TIPLOCS and a["crs"]]
                        )),
                    ])
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
