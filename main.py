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

with open("tocs.json") as f:
    TOCS = json.load(f)

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

def infer_tops(current):
    tuple = (current["atoc_code"], current["power_type"], current["speed"],
        current["timing_load"], current["seating_class"])
    for k,v in TOPS_INFERENCES.items():
        if all([not y or x==y for x,y in zip(tuple, k)]):
            return v
    return (None, [])

def format(schedule, date, associations):
    global TIPLOCS, TOCS

    for location in schedule["locations"]:
        del location["iid"], location["seq"], location["description"]
        tiploc = location["tiploc"]
        location["associations"] = associations.get((tiploc, location["tiploc_instance"]))
        
        location["name"], location["crs"] = None, None
        if tiploc in TIPLOCS:
            loc_data = TIPLOCS[tiploc]
            location["name"] = loc_data["name"]

        location["dolphin_times"] = OrderedDict()
        location["dolphin_times"]["sta"] = location.get("arrival_public") or location.get("arrival")
        location["dolphin_times"]["std"] = location.get("departure_public") or location.get("departure") or location.get("pass")
        location["dolphin_times"]["pass"] = location.get("pass")
    return schedule

def rowfor(uid, date, recurse=False):
    c = get_database().cursor()
    c.execute("SELECT * FROM `schedules` WHERE `uid`==? AND ? BETWEEN `valid_from` AND `valid_to` ORDER BY `stp` ASC LIMIT 1;", (uid, date))
    ret = c.fetchone()
    if ret:
        ret = OrderedDict(ret)
        ret["operator_name"] = TOCS.get(ret["atoc_code"])
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
        ret[(assoc["tiploc"], assoc["suffix"], assoc["category"])] = assoc
    ret2 = defaultdict(list)
    # Now let's put all the associations together
    for assoc in ret.values():
        assoc["from"] = False
        # For the sake of simplicity, uid_assoc will always refer to the service associated (from)/to
        if assoc["uid_assoc"] == uid:
            assoc["uid"], assoc["uid_assoc"] = assoc["uid_assoc"], assoc["uid"]
            # This is a 'from' association. This train was separated from, joined from, or was previous service
            assoc["from"] = True
        # Direction is to indicate whether it's more helpful to indicate the origin as an associated from (VV, NP)
        # Or destination (JJ). Generally, if the association doesn't happen at the terminus or origin of the association,
        # Destination is preferable (and more useful for passengers)
        assoc["direction"] = assoc["from"]
        assoc.update({a:None for a in ["origin_name", "origin_crs", "origin_tiploc", "dest_name", "dest_crs", "dest_tiploc"]})
        if recurse:
            assoc_sched = rowfor(assoc["uid_assoc"], date, False)
            if assoc_sched:
                locs = assoc_sched["locations"]
                first, last = locs[0], locs[-1]
                assoc["direction"] = last["tiploc"]==assoc["tiploc"]
                far = first if assoc["direction"] else last
                assoc.update({"origin_name": first["name"], "origin_crs": first["crs"], "origin_tiploc": first["tiploc"],
                             "dest_name": last["name"], "dest_crs": last["crs"], "dest_tiploc": last["tiploc"],
                             "far_name": far["name"], "far_crs": far["crs"], "far_tiploc": far["tiploc"]
                    })
        if assoc["stp"]!="C":
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
        datetime.datetime.strptime(date, "%Y-%m-%d")

        current = rowfor(uid, date, recurse)
        struct = OrderedDict([
            ("success",True),
            ("message", "OK"),
            ("cancelled", current["stp"]=="C"),
            ("tops_inferred", infer_tops(current)[0]),
            ("current",  current),
            ])
        return struct

@app.route('/schedule/<path:path>/<path:date>')
def root(path, date):
    if not is_authenticated(): return AUTH_FAIL
    failure_message = None
    status = 200
    try:
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
        datetime.datetime.strptime(date, "%Y-%m-%d")
        out = OrderedDict()
        for uid in uids:
            current = rowfor(uid, date)
            if not current:
                out[uid] = {}
            else:
                out[uid] = OrderedDict([
                    ("cancelled", current["stp"]=="C"),
                    ("tops_inferred", infer_tops(current)[0]),
                    ("tops_possible", infer_tops(current)[1]),
                    ("atoc_code", current["atoc_code"]),
                    ("power_type", current["power_type"]),
                    ("platforms", OrderedDict(
                        [(a["crs"],a["platform"]) for a in current["locations"] if not a.get("pass") and a["crs"]]
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
