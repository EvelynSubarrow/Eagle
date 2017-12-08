#!/usr/bin/env python3

import json, os, sqlite3
from collections import Counter, OrderedDict

# sqlite has no real equivalent to "TRUNCATE TABLE x". "DELETE FROM x" is recommended but it's slow.
# It turns out that dropping the table is also slow. It follows that the quickest way to remove all
# rows is to delete the DB file itself

try:
    os.remove('schedule.db')
except FileNotFoundError:
    pass

conn = sqlite3.connect('schedule.db')
c = conn.cursor()

c.execute("""CREATE TABLE schedules(
    iid INTEGER,
    uid CHAR(6),
    valid_from DATE,
    valid_to DATE,
    running_days CHAR(7),
    bank_holiday_running CHAR(1),
    status CHAR(1),
    category CHAR(2),
    signalling_id CHAR(4),
    headcode CHAR(4),
    business_sector CHAR(1),
    power_type CHAR(3),
    timing_load CHAR(7),
    speed CHAR(3),
    operating_characteristics CHAR(6),
    seating_class CHAR(1),
    sleepers CHAR(1),
    reservations CHAR(1),
    catering CHAR(4),
    branding CHAR(4),
    stp CHAR(1),
    traction_class CHAR(4),
    uic_code CHAR(5),
    atoc_code CHAR(2),
    applicable_timetable CHAR(1)
);""")
c.execute("CREATE INDEX idx_uid ON schedules(uid);")
c.execute("CREATE INDEX idx_sched_iid ON schedules(iid);")

c.execute("""CREATE TABLE associations(
    uid CHAR(6),
    uid_assoc CHAR(6),
    valid_from DATE,
    valid_to DATE,
    assoc_days CHAR(7),
    category CHAR(2),
    date_indicator CHAR(1),
    tiploc CHAR(7),
    suffix CHAR(1),
    suffix_assoc CHAR(1),
    type CHAR(1),
    stp CHAR(1)
);""")
c.execute("CREATE INDEX idx_main_uid ON associations(uid);")
c.execute("CREATE INDEX idx_assoc_uid ON associations(uid_assoc);")

c.execute("""CREATE TABLE locations(
    iid INTEGER,
    seq INTEGER,
    tiploc CHAR(7),
    tiploc_instance CHAR(1),
    arrival CHAR(5),
    arrival_public CHAR(5),
    departure CHAR(5),
    departure_public CHAR(5),
    pass CHAR(5),
    platform CHAR(3),
    line CHAR(3),
    path CHAR(3),
    activity CHAR(12),
    engineering_allowance CHAR(2),
    pathing_allowance CHAR(2),
    performance_allowance CHAR(2)
);""")
c.execute("CREATE INDEX idx_loc_iid ON locations(iid);")

c.execute("""CREATE TABLE codes(
    tiploc CHAR(7),
    description CHAR(26),
    stanox CHAR(5),
    crs CHAR(3)
);""")
c.execute("CREATE INDEX idx_codes_tiploc ON codes(tiploc);")
c.execute("CREATE INDEX idx_codes_stanox ON codes(stanox);")
c.execute("CREATE INDEX idx_codes_crs    ON codes(crs);")

def convert_chars(string):
    return string

def convert_string(string):
    return string.rstrip()

def convert_stringornull(string):
    return string.rstrip() or None

def convert_date(string):
    return "20" + string[0:2] + "-" + string[2:4] + "-" + string[4:6]

def convert_number(string):
    if string.strip():
        return int(string.strip())
    else:
        return None

def convert_discard(string):
    return None

class ParseEntity():
    def __init__(self, funct, length, tag):
        self.parse = funct
        self.length = length
        self.tag = tag

RECORDS = {
    "HD": "C20:mainframe_identity, D6:extract_date, R4:extract_time, C7:current_reference, C7:previous_reference, C:update_indicator, C:version, D6:user_date_start, D6:user_date_end, S20",
    "TI": "R7:tiploc, N2:caps_ident, N6:nlc, C:nlc_check, R26:description_tps, C5:stanox, N4:pomcp, U3:crs, R16:description_nlc, S8",
    "AA": "S, C6:uid_main, C6:uid_assoc, D6:valid_from, D6:valid_to, C7:assoc_days, U2:category, C:date_indicator, R7:tiploc, N:suffix, N:suffix_assoc, S, C:assoc_type, S31, C:stp",
    "BS": "S, C6:uid, D6:valid_from, D6:valid_to, C7:days_running, C:bankholiday_running, C:status, C2:category, U4:signalling_id, U4:headcode, S, S8, C1:business_sector, U3:power, U4:timing_load, U3:speed, C6:operating_characteristics, U:seating_class, U:sleepers, U:reservations, S, C4:catering, C4:branding, S, C:stp",
    "BX": "C4:traction_class, R5:uic_code, C2:atoc_code, C:applicable_timetable, S64",
    "LO": "R7:tiploc, U:tiploc_instance, I0:arrival, U5:departure, I0:pass, I0:public_arrival, U4:public_departure, U3:platform, U3:line, I0:path, U2:engineering_allowance, U2:pathing_allowance, C12:activity, U2:performance_allowance, S37",
    "LI": "R7:tiploc, U:tiploc_instance, U5:arrival, U5:departure, U5:pass, U4:public_arrival, U4:public_departure, U3:platform, U3:line, U3:path, C12:activity, U2:engineering_allowance, U2:pathing_allowance, U2:performance_allowance, S20",
    "LT": "R7:tiploc, U:tiploc_instance, U5:arrival, I0:departure, I0:pass, U4:public_arrival, I0:public_departure, U3:platform, I0:line, U3:path, C12:activity, I0:engineering_allowance, I0:pathing_allowance, I0:performance_allowance, S43",
    "CR": "S78",
    "ZZ": "S78",
}

def compile_records():
    global RECORDS
    functs = {"C": convert_chars, "D": convert_date, "N": convert_number, "S": convert_discard, "R": convert_string, "U": convert_stringornull, "I": convert_discard}
    ro = {}
    for rs in RECORDS:
        struct = RECORDS[rs]
        struct = struct.split(",")
        lr = []
        for entity in struct:
            entity = entity.strip()
            funct, length, tag = None, 1, None
            if ":" in entity:
                entity, tag = entity.split(":", 1)
            func_char = entity[:1]
            entity = entity[1:]
            if entity:
                length = int(entity.strip())
            if tag:
                tag = tag.strip()
            lr.append(ParseEntity(functs[func_char], length, tag))
        ro[rs] = lr
    RECORDS = ro

def r2d(record):
    global RECORDS
    record_type = record[:2]
    record_ptr = 2
    store_dict = record_type[0] in ["L","T"]
    rdict = {}
    rl = []
    for element in RECORDS[record_type]:
        string = record[record_ptr:record_ptr+element.length]
        converted = element.parse(string)
        if element.tag:
            if store_dict:
                rdict[element.tag] = converted
            else:
                rl.append(converted)
        record_ptr += element.length
    return (record_type, rdict if store_dict else rl)

compile_records()

lol = False
with open("sched.cif", "rb") as f:
    bs_id = -1
    loc_id = 0
    count = 0
    while True:
        # All records are padded to 80cols
        record = f.read(80).decode("ascii")
        # And have a following \n which isn't
        f.read(1)

        record_type, res = r2d(record)
        count +=1
        if count%10000==0:
            print("%8s %s" % (count, record_type))

        if record_type == "AA":
            c.execute("INSERT INTO `associations` VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                res)
        elif record_type == "TI":
            c.execute("INSERT INTO `codes` VALUES (?, ?, ?, ?);", (res["tiploc"], res["description_tps"], res["stanox"], res["crs"]))
        elif record_type == "BS":
            bs_id += 1
            loc_id = 0
            c.execute("INSERT INTO `schedules` VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                [bs_id] + res + [None, None, "ZZ", None])
        elif record_type == "BX":
            c.execute("UPDATE `schedules` SET traction_class=?, uic_code=?, atoc_code=?, applicable_timetable=? WHERE `iid`==?;",
                res + [bs_id])
        elif record_type == "LO" or record_type=="LI" or record_type=="LT":
            if res["public_arrival"] == "0000": res["public_arrival"] = None
            if res["public_departure"] == "0000": res["public_departure"] = None
            c.execute("INSERT INTO `locations` VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", (
                bs_id, loc_id, res["tiploc"], res["tiploc_instance"], res["arrival"], res["public_arrival"],
                res["departure"], res["public_departure"], res["pass"], res["platform"], res["line"],
                res["path"], res["activity"], res["engineering_allowance"], res["pathing_allowance"], res["performance_allowance"]
                ))
            loc_id += 1
        elif record_type == "ZZ":
            print(record)
            conn.commit()
            conn.close()
            exit()
